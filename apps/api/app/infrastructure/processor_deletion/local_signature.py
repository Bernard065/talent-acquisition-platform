"""Development adapter for the in-process local signature provider."""

from app.services.candidate_processor_provider import (
    CandidateProcessorDeletionCommand,
    CandidateProcessorProviderError,
)


class LocalSignatureProcessorDeletionProvider:
    """Treat local mock envelopes as deleted; no external store is contacted."""

    processor_code = "signature.local"

    async def delete_candidate_data(
        self,
        *,
        command: CandidateProcessorDeletionCommand,
    ) -> None:
        if command.processor_code != self.processor_code:
            raise CandidateProcessorProviderError(
                "signature_provider_mismatch",
                retryable=False,
            )
