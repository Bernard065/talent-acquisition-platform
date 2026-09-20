"""Unit tests for the BambooHR HRIS provider adapter."""

from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.infrastructure.hris.bamboohr_provider import BambooHrProviderAdapter
from app.services.hris_credentials import HrisCredentials
from app.services.hris_provider import (
    HrisEmployeeHandoffCommand,
    HrisProviderError,
)


def _credentials() -> HrisCredentials:
    """Build private BambooHR credentials for an in-memory test."""
    return HrisCredentials(
        values={
            "api_key": SecretStr("test-api-key"),
            "company_domain": SecretStr("example-company"),
        }
    )


def _command() -> HrisEmployeeHandoffCommand:
    """Build a representative private employee handoff."""
    return HrisEmployeeHandoffCommand(
        hris_handoff_id=uuid4(),
        application_id=uuid4(),
        onboarding_instance_id=uuid4(),
        full_name="Ada Lovelace",
        email="ada@example.test",
        proposed_start_date=date(2026, 10, 1),
        idempotency_key="stable-handoff-key",
    )


@pytest.mark.asyncio
async def test_creates_employee_after_empty_idempotency_lookup() -> None:
    """Create one employee using only supported BambooHR fields."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        if request.method == "GET":
            return httpx.Response(200, json={"data": []})

        if request.method == "POST":
            return httpx.Response(201, json={"id": "employee-123"})

        raise AssertionError(f"Unexpected request: {request.method}")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        adapter = BambooHrProviderAdapter(http_client=client)
        result = await adapter.create_or_update_employee(
            command=_command(),
            credentials=_credentials(),
        )

    post_request = next(
        request for request in requests if request.method == "POST"
    )
    payload = json.loads(post_request.content)

    assert result.external_employee_reference == "employee-123"
    assert post_request.url.scheme == "https"
    assert post_request.url.host == "example-company.bamboohr.com"
    assert post_request.url.path == "/api/v1/employees"
    assert payload == {
        "firstName": "Ada",
        "lastName": "Lovelace",
        "workEmail": "ada@example.test",
        "hireDate": "2026-10-01",
        "employeeNumber": payload["employeeNumber"],
    }
    assert payload["employeeNumber"].startswith("tap-")


@pytest.mark.asyncio
async def test_reuses_existing_employee_without_posting_again() -> None:
    """Recover an earlier provider success using the stable employee number."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"data": [{"employeeId": "employee-456"}]},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        adapter = BambooHrProviderAdapter(http_client=client)
        result = await adapter.create_or_update_employee(
            command=_command(),
            credentials=_credentials(),
        )

    assert result.external_employee_reference == "employee-456"
    assert [request.method for request in requests] == ["GET"]


@pytest.mark.asyncio
async def test_recovers_conflict_by_looking_up_employee_number() -> None:
    """Treat a duplicate create response as a recoverable idempotency outcome."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1

        if calls == 1:
            return httpx.Response(200, json={"data": []})

        if request.method == "POST":
            return httpx.Response(409)

        return httpx.Response(
            200,
            json={"data": [{"employeeId": "employee-789"}]},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        adapter = BambooHrProviderAdapter(http_client=client)
        result = await adapter.create_or_update_employee(
            command=_command(),
            credentials=_credentials(),
        )

    assert result.external_employee_reference == "employee-789"


@pytest.mark.asyncio
async def test_classifies_provider_outage_as_retryable() -> None:
    """Retry a temporary BambooHR failure without exposing response content."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="provider details must not persist")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        adapter = BambooHrProviderAdapter(http_client=client)

        with pytest.raises(HrisProviderError) as error:
            await adapter.create_or_update_employee(
                command=_command(),
                credentials=_credentials(),
            )

    assert error.value.code == "bamboohr_lookup_failed"
    assert error.value.retryable is True
    assert "provider details" not in str(error.value)


@pytest.mark.asyncio
async def test_rejects_invalid_company_domain_before_network_request() -> None:
    """Prevent credential-controlled URLs from becoming SSRF targets."""
    credentials = HrisCredentials(
        values={
            "api_key": SecretStr("test-api-key"),
            "company_domain": SecretStr("evil.example/path"),
        }
    )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: pytest.fail("Network request must not occur")
        ),
        follow_redirects=False,
    ) as client:
        adapter = BambooHrProviderAdapter(http_client=client)

        with pytest.raises(HrisProviderError) as error:
            await adapter.create_or_update_employee(
                command=_command(),
                credentials=credentials,
            )

    assert error.value.code == "bamboohr_company_domain_invalid"
    assert error.value.retryable is False


@pytest.mark.asyncio
async def test_requires_first_last_name_and_start_date() -> None:
    """Reject insufficient HRIS data before sending a provider request."""
    invalid_command = HrisEmployeeHandoffCommand(
        hris_handoff_id=uuid4(),
        application_id=uuid4(),
        onboarding_instance_id=uuid4(),
        full_name="Ada",
        email="ada@example.test",
        proposed_start_date=None,
        idempotency_key="stable-handoff-key",
    )

    async with httpx.AsyncClient() as client:
        adapter = BambooHrProviderAdapter(http_client=client)

        with pytest.raises(HrisProviderError) as error:
            await adapter.create_or_update_employee(
                command=invalid_command,
                credentials=_credentials(),
            )

    assert error.value.code == "bamboohr_start_date_missing"
    assert error.value.retryable is False
