"""MinIO and Amazon S3 implementation of the object-storage port."""

import asyncio
import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import NoReturn, Protocol, cast

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import AnyHttpUrl, SecretStr

from app.core.config import Settings
from app.services.object_storage import (
    ObjectNotFoundError,
    ObjectStorage,
    ObjectStorageError,
    PresignedUpload,
    StoredObjectMetadata,
)


class ObjectStorageConfigurationError(ValueError):
    """Raised when required object-storage configuration is absent."""


class ObjectStorageProviderError(ObjectStorageError):
    """Raised when the S3-compatible storage provider rejects an operation."""


class ObjectStorageObjectNotFoundError(ObjectNotFoundError):
    """Raised when an object does not exist in object storage."""


class _S3Client(Protocol):
    """Small protocol that keeps the adapter independently unit-testable."""

    def generate_presigned_url(
        self,
        client_method: str,
        **kwargs: object,
    ) -> str:
        """Generate a signed URL."""

    def head_object(self, **kwargs: object) -> dict[str, object]:
        """Read object metadata."""

    def delete_object(self, **kwargs: object) -> dict[str, object]:
        """Delete an object."""

    def head_bucket(self, **kwargs: object) -> dict[str, object]:
        """Verify a bucket exists."""

    def create_bucket(self, **kwargs: object) -> dict[str, object]:
        """Create a bucket."""


@dataclass(frozen=True, slots=True)
class S3ObjectStorageConfig:
    """Validated configuration for a private S3-compatible object store."""

    endpoint_url: str
    public_endpoint_url: str
    access_key: str
    secret_key: str
    bucket: str
    region: str
    presigned_upload_expiry_seconds: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3ObjectStorageConfig":
        """Build configuration while rejecting partial storage setup."""
        required = {
            "S3_ENDPOINT_URL": settings.s3_endpoint_url,
            "S3_PUBLIC_ENDPOINT_URL": settings.s3_public_endpoint_url,
            "S3_ACCESS_KEY": settings.s3_access_key,
            "S3_SECRET_KEY": settings.s3_secret_key,
            "S3_BUCKET": settings.s3_bucket,
            "S3_REGION": settings.s3_region,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ObjectStorageConfigurationError(
                f"Missing required object-storage configuration: {', '.join(missing)}."
            )

        endpoint_url = cast(AnyHttpUrl, settings.s3_endpoint_url)
        public_endpoint_url = cast(AnyHttpUrl, settings.s3_public_endpoint_url)
        access_key = cast(SecretStr, settings.s3_access_key)
        secret_key = cast(SecretStr, settings.s3_secret_key)
        bucket = cast(str, settings.s3_bucket)
        region = cast(str, settings.s3_region)

        return cls(
            endpoint_url=str(endpoint_url),
            public_endpoint_url=str(public_endpoint_url),
            access_key=access_key.get_secret_value(),
            secret_key=secret_key.get_secret_value(),
            bucket=bucket,
            region=region,
            presigned_upload_expiry_seconds=settings.s3_presigned_upload_expiry_seconds,
        )


class S3ObjectStorage(ObjectStorage):
    """S3-compatible adapter used by both MinIO and Amazon S3."""

    def __init__(
        self,
        config: S3ObjectStorageConfig,
        *,
        client: _S3Client | None = None,
        presigning_client: _S3Client | None = None,
    ) -> None:
        self.config = config
        self._client = client or self._create_client(config.endpoint_url)
        self._presigning_client = presigning_client or self._create_client(
            config.public_endpoint_url
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3ObjectStorage":
        """Create the adapter from validated application settings."""
        return cls(S3ObjectStorageConfig.from_settings(settings))

    def _create_client(self, endpoint_url: str) -> _S3Client:
        """Create a path-style S3 client compatible with MinIO and AWS S3."""
        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=self.config.access_key,
            aws_secret_access_key=self.config.secret_key,
            region_name=self.config.region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )
        return cast(_S3Client, client)

    async def create_presigned_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        checksum_sha256: str,
        expires_in: timedelta,
    ) -> PresignedUpload:
        """Create a short-lived signed PUT authorization for one object."""
        try:
            checksum_bytes = bytes.fromhex(checksum_sha256)
        except ValueError as error:
            raise ValueError("checksum_sha256 must be hexadecimal.") from error

        expiry_seconds = int(expires_in.total_seconds())
        if expiry_seconds <= 0:
            raise ValueError("Upload URL expiry must be positive.")

        checksum_base64 = base64.b64encode(checksum_bytes).decode("ascii")
        params: dict[str, object] = {
            "Bucket": self.config.bucket,
            "Key": object_key,
            "ContentType": content_type,
            "ChecksumAlgorithm": "SHA256",
            "ChecksumSHA256": checksum_base64,
        }

        try:
            url = await asyncio.to_thread(
                self._presigning_client.generate_presigned_url,
                "put_object",
                Params=params,
                ExpiresIn=expiry_seconds,
                HttpMethod="PUT",
            )
        except ClientError as error:
            raise ObjectStorageProviderError(
                "Unable to create a document upload authorization."
            ) from error

        return PresignedUpload(
            url=url,
            required_headers={
                "Content-Type": content_type,
                "x-amz-checksum-sha256": checksum_base64,
            },
            expires_at=datetime.now(UTC) + expires_in,
        )

    async def get_object_metadata(
        self,
        *,
        object_key: str,
    ) -> StoredObjectMetadata:
        """Read provider-verified object metadata after upload completion."""
        try:
            response = await asyncio.to_thread(
                self._client.head_object,
                Bucket=self.config.bucket,
                Key=object_key,
                ChecksumMode="ENABLED",
            )
        except ClientError as error:
            self._raise_provider_error(error, "read document metadata")

        content_type = response.get("ContentType")
        byte_size = response.get("ContentLength")
        checksum_base64 = response.get("ChecksumSHA256")

        if not isinstance(content_type, str) or not isinstance(byte_size, int):
            raise ObjectStorageProviderError(
                "Object storage returned incomplete document metadata."
            )

        checksum_sha256: str | None = None
        if isinstance(checksum_base64, str):
            try:
                checksum_sha256 = base64.b64decode(
                    checksum_base64,
                    validate=True,
                ).hex()
            except ValueError as error:
                raise ObjectStorageProviderError(
                    "Object storage returned an invalid document checksum."
                ) from error

        return StoredObjectMetadata(
            content_type=content_type,
            byte_size=byte_size,
            checksum_sha256=checksum_sha256,
        )

    async def delete_object(self, *, object_key: str) -> None:
        """Delete one document object during a privacy or retention workflow."""
        try:
            await asyncio.to_thread(
                self._client.delete_object,
                Bucket=self.config.bucket,
                Key=object_key,
            )
        except ClientError as error:
            self._raise_provider_error(error, "delete document")

    async def ensure_bucket(self) -> None:
        """Create the configured bucket when it does not already exist."""
        try:
            await asyncio.to_thread(
                self._client.head_bucket,
                Bucket=self.config.bucket,
            )
            return
        except ClientError as error:
            if not self._is_missing(error):
                self._raise_provider_error(error, "verify document bucket")

        create_parameters: dict[str, object] = {"Bucket": self.config.bucket}
        if self.config.region != "us-east-1":
            create_parameters["CreateBucketConfiguration"] = {
                "LocationConstraint": self.config.region,
            }

        try:
            await asyncio.to_thread(
                self._client.create_bucket,
                **create_parameters,
            )
        except ClientError as error:
            self._raise_provider_error(error, "create document bucket")

    @staticmethod
    def _is_missing(error: ClientError) -> bool:
        """Identify provider responses that mean an object or bucket is absent."""
        code = str(error.response.get("Error", {}).get("Code", ""))
        return code in {"404", "NoSuchBucket", "NoSuchKey", "NotFound"}

    def _raise_provider_error(self, error: ClientError, operation: str) -> NoReturn:
        """Map provider failures without exposing provider details to callers."""
        if self._is_missing(error):
            raise ObjectStorageObjectNotFoundError(
                "Requested document object was not found."
            ) from error

        raise ObjectStorageProviderError(
            f"Object storage could not {operation}."
        ) from error
