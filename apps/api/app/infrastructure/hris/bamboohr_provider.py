"""Retry-safe BambooHR employee handoff adapter."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from re import compile as re_compile

import httpx
from pydantic import SecretStr

from app.domains.hris.enums import HrisProvider
from app.services.hris_credentials import HrisCredentials
from app.services.hris_provider import (
    HrisEmployeeHandoffCommand,
    HrisEmployeeHandoffResult,
    HrisProviderError,
)

_COMPANY_DOMAIN_PATTERN = re_compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_MAX_EMPLOYEE_NUMBER_LENGTH = 50


@dataclass(frozen=True, slots=True)
class _BambooHrCredentials:
    """Validated BambooHR connection data, resolved only in worker memory."""

    api_key: SecretStr
    company_domain: str

    @classmethod
    def from_hris_credentials(
        cls,
        credentials: HrisCredentials,
    ) -> _BambooHrCredentials:
        """Extract the minimum supported BambooHR credential set."""
        api_key = credentials.values.get("api_key")
        company_domain_value = credentials.values.get("company_domain")

        if api_key is None or not api_key.get_secret_value():
            raise HrisProviderError(
                "bamboohr_api_key_missing",
                retryable=False,
            )

        if company_domain_value is None:
            raise HrisProviderError(
                "bamboohr_company_domain_missing",
                retryable=False,
            )

        company_domain = company_domain_value.get_secret_value().strip().lower()
        if not _COMPANY_DOMAIN_PATTERN.fullmatch(company_domain):
            raise HrisProviderError(
                "bamboohr_company_domain_invalid",
                retryable=False,
            )

        return cls(
            api_key=api_key,
            company_domain=company_domain,
        )


class BambooHrProviderAdapter:
    """
    BambooHR employee creation adapter.

    The stable employee number is derived from the platform handoff key. The
    adapter first looks for it, creates the employee only when absent, then
    looks again after creation. This recovers safely if BambooHR succeeds but
    the worker crashes before PostgreSQL records the employee reference.
    """

    provider = HrisProvider.BAMBOOHR.value

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._http_client = http_client

    @staticmethod
    def _employee_number(idempotency_key: str) -> str:
        """Create a deterministic, non-PII BambooHR employee number."""
        digest = sha256(idempotency_key.encode("utf-8")).hexdigest()
        return f"tap-{digest[:40]}"

    @staticmethod
    def _split_name(full_name: str) -> tuple[str, str]:
        """Require first and last names for BambooHR's employee API."""
        parts = full_name.split()

        if len(parts) < 2:
            raise HrisProviderError(
                "bamboohr_employee_name_invalid",
                retryable=False,
            )

        return parts[0], " ".join(parts[1:])

    @staticmethod
    def _base_url(company_domain: str) -> str:
        """Build a fixed BambooHR HTTPS host without caller-controlled URLs."""
        return f"https://{company_domain}.bamboohr.com/api/v1"

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        """Classify provider responses without reading response text."""
        return status_code in {408, 429} or status_code >= 500

    @staticmethod
    def _response_employee_id(response: httpx.Response) -> str | None:
        """Read a non-sensitive employee identifier from a response body."""
        try:
            payload = response.json()
        except ValueError:
            return None

        if not isinstance(payload, dict):
            return None

        for key in ("id", "employeeId"):
            value = payload.get(key)
            if isinstance(value, (str, int)) and str(value):
                return str(value)

        return None

    async def _find_employee_id(
        self,
        *,
        base_url: str,
        auth: httpx.BasicAuth,
        employee_number: str,
    ) -> str | None:
        """Find an employee only by this platform's deterministic identifier."""
        try:
            response = await self._http_client.get(
                f"{base_url}/employees",
                auth=auth,
                headers={"Accept": "application/json"},
                params={
                    "filter[employeeNumber]": employee_number,
                    "fields": "employeeNumber",
                    "page[limit]": "2",
                },
            )
        except httpx.HTTPError as error:
            raise HrisProviderError(
                "bamboohr_lookup_failed",
                retryable=True,
            ) from error

        if response.is_error:
            raise HrisProviderError(
                "bamboohr_lookup_failed",
                retryable=self._is_retryable_status(response.status_code),
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise HrisProviderError(
                "bamboohr_lookup_response_invalid",
                retryable=False,
            ) from error

        if not isinstance(payload, dict):
            raise HrisProviderError(
                "bamboohr_lookup_response_invalid",
                retryable=False,
            )

        records = payload.get("data")
        if not isinstance(records, list):
            raise HrisProviderError(
                "bamboohr_lookup_response_invalid",
                retryable=False,
            )

        if not records:
            return None

        if len(records) > 1:
            raise HrisProviderError(
                "bamboohr_employee_number_not_unique",
                retryable=False,
            )

        record = records[0]
        if not isinstance(record, dict):
            raise HrisProviderError(
                "bamboohr_lookup_response_invalid",
                retryable=False,
            )

        employee_id = record.get("employeeId", record.get("id"))
        if not isinstance(employee_id, (str, int)) or not str(employee_id):
            raise HrisProviderError(
                "bamboohr_lookup_response_invalid",
                retryable=False,
            )

        return str(employee_id)

    async def create_or_update_employee(
        self,
        *,
        command: HrisEmployeeHandoffCommand,
        credentials: HrisCredentials,
    ) -> HrisEmployeeHandoffResult:
        """Create or recover an employee through BambooHR safely."""
        bamboo_credentials = _BambooHrCredentials.from_hris_credentials(credentials)

        if command.proposed_start_date is None:
            raise HrisProviderError(
                "bamboohr_start_date_missing",
                retryable=False,
            )

        first_name, last_name = self._split_name(command.full_name)
        employee_number = self._employee_number(command.idempotency_key)

        if len(employee_number) > _MAX_EMPLOYEE_NUMBER_LENGTH:
            raise HrisProviderError(
                "bamboohr_employee_number_invalid",
                retryable=False,
            )

        base_url = self._base_url(bamboo_credentials.company_domain)
        auth = httpx.BasicAuth(
            bamboo_credentials.api_key.get_secret_value(),
            "x",
        )

        existing_employee_id = await self._find_employee_id(
            base_url=base_url,
            auth=auth,
            employee_number=employee_number,
        )
        if existing_employee_id is not None:
            return HrisEmployeeHandoffResult(external_employee_reference=existing_employee_id)

        payload = {
            "firstName": first_name,
            "lastName": last_name,
            "workEmail": command.email,
            "hireDate": command.proposed_start_date.isoformat(),
            "employeeNumber": employee_number,
        }

        try:
            response = await self._http_client.post(
                f"{base_url}/employees",
                auth=auth,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as error:
            raise HrisProviderError(
                "bamboohr_create_failed",
                retryable=True,
            ) from error

        if response.status_code not in {200, 201, 409}:
            raise HrisProviderError(
                "bamboohr_create_failed",
                retryable=self._is_retryable_status(response.status_code),
            )

        # A provider response may contain an ID. Lookup remains authoritative:
        # it also recovers a 409 duplicate or a previous successful request.
        employee_id = self._response_employee_id(response)
        if employee_id is None:
            employee_id = await self._find_employee_id(
                base_url=base_url,
                auth=auth,
                employee_number=employee_number,
            )

        if employee_id is None:
            raise HrisProviderError(
                "bamboohr_employee_reference_unavailable",
                retryable=True,
            )

        return HrisEmployeeHandoffResult(external_employee_reference=employee_id)

    async def delete_employee(
        self,
        *,
        employee_id: str,
        credentials: HrisCredentials,
    ) -> None:
        """Permanently delete one BambooHR employee by its internal ID.

        BambooHR's endpoint requires the immutable internal employee ID, not
        the editable employee number. A repeated delete treats ``404`` as
        success so a timeout after provider-side deletion is safely retryable.
        """
        bamboo_credentials = _BambooHrCredentials.from_hris_credentials(credentials)
        normalized_employee_id = employee_id.strip()
        if not normalized_employee_id.isdecimal():
            raise HrisProviderError(
                "bamboohr_employee_id_invalid",
                retryable=False,
            )

        base_url = self._base_url(bamboo_credentials.company_domain)
        auth = httpx.BasicAuth(
            bamboo_credentials.api_key.get_secret_value(),
            "x",
        )
        try:
            response = await self._http_client.delete(
                f"{base_url}/employees/{normalized_employee_id}",
                auth=auth,
                headers={"Accept": "application/json"},
            )
        except httpx.TimeoutException as error:
            raise HrisProviderError(
                "bamboohr_delete_timeout",
                retryable=True,
            ) from error
        except httpx.HTTPError as error:
            raise HrisProviderError(
                "bamboohr_delete_failed",
                retryable=True,
            ) from error

        if response.status_code in {200, 204, 404}:
            return
        raise HrisProviderError(
            "bamboohr_delete_failed",
            retryable=self._is_retryable_status(response.status_code),
        )
