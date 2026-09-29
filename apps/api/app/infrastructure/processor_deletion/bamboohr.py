"""BambooHR adapter for permanent employee-record deletion."""

from typing import Protocol

from app.services.candidate_processor_provider import (
    CandidateProcessorDeletionCommand,
    CandidateProcessorProviderError,
)
from app.services.hris_credentials import (
    HrisCredentials,
    HrisCredentialVault,
    HrisCredentialVaultError,
)
from app.services.hris_provider import HrisProviderError


class BambooHrDeletionPort(Protocol):
    """Minimum BambooHR adapter surface required for deletion."""

    async def delete_employee(
        self,
        *,
        employee_id: str,
        credentials: HrisCredentials,
    ) -> None:
        """Permanently delete the internally identified employee record."""


class BambooHrProcessorDeletionProvider:
    """Resolve tenant credentials, then delete by BambooHR internal ID."""

    processor_code = "hris.bamboohr"

    def __init__(
        self,
        *,
        credential_vault: HrisCredentialVault,
        bamboohr_provider: BambooHrDeletionPort,
    ) -> None:
        self._credential_vault = credential_vault
        self._bamboohr_provider = bamboohr_provider

    async def delete_candidate_data(
        self,
        *,
        command: CandidateProcessorDeletionCommand,
    ) -> None:
        if command.credential_reference is None:
            raise CandidateProcessorProviderError(
                "hris_credential_reference_unavailable",
                retryable=False,
            )
        try:
            credentials = await self._credential_vault.resolve_hris_credentials(
                credential_reference=command.credential_reference,
            )
            await self._bamboohr_provider.delete_employee(
                employee_id=command.external_record_reference,
                credentials=credentials,
            )
        except HrisCredentialVaultError as error:
            raise CandidateProcessorProviderError(
                error.code,
                retryable=error.retryable,
            ) from error
        except HrisProviderError as error:
            raise CandidateProcessorProviderError(
                error.code,
                retryable=error.retryable,
            ) from error
