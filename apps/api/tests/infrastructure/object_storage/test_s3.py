"""Offline unit tests for the S3-compatible object-storage adapter."""

import base64
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.infrastructure.object_storage.s3 import (
    S3ObjectStorage,
    S3ObjectStorageConfig,
)
from app.services.object_storage import StoredObjectMetadata


class FakeS3Client:
    """In-memory S3 client substitute; no network or credentials required."""

    def __init__(self) -> None:
        self.presigned_url = "http://localhost:9000/tap-documents/signed-upload"
        self.head_object_response: dict[str, object] = {
            "ContentType": "application/pdf",
            "ContentLength": 512_000,
        }
        self.head_bucket_error: ClientError | None = None
        self.delete_error: Exception | None = None
        self.generate_presigned_url_calls: list[tuple[str, dict[str, object]]] = []
        self.head_object_calls: list[dict[str, object]] = []
        self.head_bucket_calls: list[dict[str, object]] = []
        self.create_bucket_calls: list[dict[str, object]] = []

    def generate_presigned_url(
        self,
        client_method: str,
        **kwargs: object,
    ) -> str:
        """Record a signing request and return a deterministic URL."""
        self.generate_presigned_url_calls.append((client_method, kwargs))
        return self.presigned_url

    def head_object(self, **kwargs: object) -> dict[str, object]:
        """Return configured object metadata."""
        self.head_object_calls.append(kwargs)
        return self.head_object_response

    def delete_object(self, **_kwargs: object) -> dict[str, object]:
        """Return success or raise a simulated provider failure."""
        if self.delete_error is not None:
            raise self.delete_error
        return {}

    def head_bucket(self, **kwargs: object) -> dict[str, object]:
        """Return success or the configured bucket-missing error."""
        self.head_bucket_calls.append(kwargs)

        if self.head_bucket_error is not None:
            raise self.head_bucket_error

        return {}

    def create_bucket(self, **kwargs: object) -> dict[str, object]:
        """Record bucket creation."""
        self.create_bucket_calls.append(kwargs)
        return {}


def _config(region: str = "us-east-1") -> S3ObjectStorageConfig:
    """Build non-secret deterministic adapter configuration."""
    return S3ObjectStorageConfig(
        endpoint_url="http://minio:9000",
        public_endpoint_url="http://localhost:9000",
        access_key="local-admin",
        secret_key="x" * 32,
        bucket="tap-documents",
        region=region,
        presigned_upload_expiry_seconds=900,
    )


def _storage(client: FakeS3Client) -> S3ObjectStorage:
    """Create an adapter with fully offline clients."""
    return S3ObjectStorage(
        _config(),
        client=client,
        presigning_client=client,
    )


def _client_error(code: str, operation: str) -> ClientError:
    """Build an S3-compatible provider error for one operation."""
    return ClientError(
        {"Error": {"Code": code, "Message": "test error"}},
        operation,
    )


@pytest.mark.asyncio
async def test_wraps_transport_failures_during_object_deletion() -> None:
    """Expose network outages as retryable storage errors, not raw SDK errors."""
    client = FakeS3Client()
    client.delete_error = EndpointConnectionError(endpoint_url="http://minio:9000")

    with pytest.raises(RuntimeError, match="could not complete document deletion"):
        await _storage(client).delete_object(object_key="opaque/object-key")


@pytest.mark.asyncio
async def test_creates_signed_put_with_content_type_and_base64_checksum() -> None:
    """Sign only the expected bucket, key, type, checksum, and expiry."""
    client = FakeS3Client()
    storage = _storage(client)
    checksum_hex = "a" * 64
    expected_checksum_base64 = base64.b64encode(
        bytes.fromhex(checksum_hex)
    ).decode("ascii")
    started_at = datetime.now(UTC)

    upload = await storage.create_presigned_upload(
        object_key="v1/tenants/tenant/candidates/candidate/documents/document/content",
        content_type="application/pdf",
        checksum_sha256=checksum_hex,
        expires_in=timedelta(minutes=15),
    )

    assert upload.url == client.presigned_url
    assert upload.required_headers == {
        "Content-Type": "application/pdf",
        "x-amz-checksum-sha256": expected_checksum_base64,
    }
    assert upload.expires_at >= started_at + timedelta(minutes=15)

    assert len(client.generate_presigned_url_calls) == 1
    client_method, options = client.generate_presigned_url_calls[0]
    parameters = cast(dict[str, object], options["Params"])

    assert client_method == "put_object"
    assert parameters == {
        "Bucket": "tap-documents",
        "Key": "v1/tenants/tenant/candidates/candidate/documents/document/content",
        "ContentType": "application/pdf",
        "ChecksumAlgorithm": "SHA256",
        "ChecksumSHA256": expected_checksum_base64,
    }
    assert options["ExpiresIn"] == 900
    assert options["HttpMethod"] == "PUT"


@pytest.mark.asyncio
async def test_reads_provider_metadata_and_converts_checksum_to_hex() -> None:
    """Convert S3's base64 checksum representation to the persisted hex form."""
    client = FakeS3Client()
    expected_checksum_hex = "b" * 64
    client.head_object_response = {
        "ContentType": "application/pdf",
        "ContentLength": 512_000,
        "ChecksumSHA256": base64.b64encode(
            bytes.fromhex(expected_checksum_hex)
        ).decode("ascii"),
    }

    metadata = await _storage(client).get_object_metadata(
        object_key="v1/tenants/tenant/candidates/candidate/documents/document/content",
    )

    assert metadata == StoredObjectMetadata(
        content_type="application/pdf",
        byte_size=512_000,
        checksum_sha256=expected_checksum_hex,
    )
    assert client.head_object_calls == [
        {
            "Bucket": "tap-documents",
            "Key": "v1/tenants/tenant/candidates/candidate/documents/document/content",
            "ChecksumMode": "ENABLED",
        }
    ]


@pytest.mark.asyncio
async def test_rejects_incomplete_provider_metadata() -> None:
    """Fail closed when object storage cannot verify required metadata."""
    client = FakeS3Client()
    client.head_object_response = {
        "ContentType": "application/pdf",
    }

    with pytest.raises(
        RuntimeError,
        match="Object storage returned incomplete document metadata",
    ):
        await _storage(client).get_object_metadata(
            object_key="v1/tenants/tenant/candidates/candidate/documents/document/content",
        )


@pytest.mark.asyncio
async def test_bucket_bootstrap_creates_missing_bucket_once() -> None:
    """Create a missing local-development bucket without public ACL settings."""
    client = FakeS3Client()
    client.head_bucket_error = _client_error("404", "HeadBucket")

    await _storage(client).ensure_bucket()

    assert client.head_bucket_calls == [{"Bucket": "tap-documents"}]
    assert client.create_bucket_calls == [{"Bucket": "tap-documents"}]


@pytest.mark.asyncio
async def test_bucket_bootstrap_does_not_recreate_existing_bucket() -> None:
    """Leave an existing bucket unchanged."""
    client = FakeS3Client()

    await _storage(client).ensure_bucket()

    assert client.head_bucket_calls == [{"Bucket": "tap-documents"}]
    assert not client.create_bucket_calls
