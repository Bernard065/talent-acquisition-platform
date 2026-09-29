"""Google Calendar adapter for deleting interview events after erasure."""

from app.services.calendar_credentials import (
    CalendarCredentialResolutionError,
    CalendarCredentialResolver,
)
from app.services.calendar_provider import (
    CalendarEventDeletion,
    CalendarEventProvider,
    CalendarProviderError,
)
from app.services.candidate_processor_provider import (
    CandidateProcessorDeletionCommand,
    CandidateProcessorProviderError,
)


class GoogleCalendarProcessorDeletionProvider:
    """Delete one disclosed Google Calendar event idempotently."""

    processor_code = "calendar.google"

    def __init__(
        self,
        *,
        credential_resolver: CalendarCredentialResolver,
        calendar_provider: CalendarEventProvider,
    ) -> None:
        self._credential_resolver = credential_resolver
        self._calendar_provider = calendar_provider

    async def delete_candidate_data(
        self,
        *,
        command: CandidateProcessorDeletionCommand,
    ) -> None:
        if (
            command.credential_reference is None
            or command.calendar_connection_id is None
            or command.interview_session_id is None
        ):
            raise CandidateProcessorProviderError(
                "calendar_deletion_metadata_invalid",
                retryable=False,
            )
        try:
            credentials = await self._credential_resolver.resolve(
                credential_reference=command.credential_reference,
            )
            await self._calendar_provider.delete_event(
                credentials=credentials,
                event=CalendarEventDeletion(
                    calendar_connection_id=command.calendar_connection_id,
                    interview_session_id=command.interview_session_id,
                    external_calendar_id=command.external_calendar_id,
                    external_event_id=command.external_record_reference,
                    idempotency_key=command.idempotency_key,
                ),
            )
        except CalendarCredentialResolutionError as error:
            raise CandidateProcessorProviderError(
                error.code,
                retryable=error.retryable,
            ) from error
        except CalendarProviderError as error:
            raise CandidateProcessorProviderError(
                error.code,
                retryable=error.retryable,
            ) from error
