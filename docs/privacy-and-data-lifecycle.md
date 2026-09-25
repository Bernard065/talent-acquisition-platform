# Candidate consent and erasure lifecycle

## Consent withdrawal

Tenant recruiters, tenant administrators, and people-operations users may record a candidate consent withdrawal. The operation is tenant-scoped, idempotent, audited without candidate contact details, and does not delete applications or workflow history. Future anonymous application submissions that match a withdrawn profile receive the same generic acknowledgement as other submissions but do not create another application.

Consent withdrawal and erasure are distinct actions. Withdrawal changes the recorded consent state; it does not imply that every other lawful processing basis has ended.

## Erasure request

Only tenant administrators and people-operations users may initiate erasure in this release. A request immediately:

1. Marks consent withdrawn.
2. Replaces the profile name and email with generic/opaque values and clears phone, location, and source metadata.
3. Marks associated candidate documents unavailable and clears filenames, checksums, and content metadata from their rows.
4. Enqueues one identifier-only outbox event per document, in the same database transaction.
5. Preserves applications, workflow history, and audit records against the anonymized candidate ID.

The candidate is hidden from profile reads and candidate search as soon as erasure begins. Documents remain in the database only until their object has been deleted successfully. A cleanup worker waits until the latest recorded presigned upload authorization has expired plus a grace interval, deletes the object through the storage adapter, then removes document metadata. Failures are retried using the shared outbox lease/backoff/dead-letter policy. A candidate with no documents is marked erased immediately; otherwise erasure completes after the final document cleanup.

The API endpoints are private, no-store, require `Idempotency-Key`, and return no profile data. Outbox payloads and audit details contain identifiers and state/count metadata only—never names, emails, filenames, checksums, or object keys.

## Explicitly not automated yet

No automatic age-based deletion is enabled. A tenant retention interval, active-application exception, legal-hold behavior, and post-hire record schedule have not been approved, so the platform does not guess at those rules. Define and review that policy before scheduling automatic erasure.

Erasure here covers data controlled by this application, including candidate document objects in configured object storage. Any data already delivered to external signature, calendar, HRIS, or email providers needs a separate provider-specific deletion/retention process and should not be assumed erased by this workflow.
