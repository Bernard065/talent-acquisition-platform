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

### Retention schedule

The platform stores versioned, tenant-scoped policy schedules and can produce an aggregate dry-run report. The following durations are proposals for tenant review, not periods prescribed by law and not enabled as automatic deletion rules:

| Data purpose | Proposed review point | Guardrails |
| --- | --- | --- |
| Unsuccessful applicants | 12 months after the final rejected outcome | Do not consider while any application remains active. |
| Withdrawn applicants | 12 months after withdrawal | Do not consider while any other application remains active. |
| Talent pool | 12 months after a distinct, recorded talent-pool opt-in or renewal | Only the latest explicit, purpose-specific grant/renewal event extends future-role retention; generic application consent is not proof. Withdrawal and erasure end that purpose consent. |
| Hired candidate recruiting copies | 90 days after onboarding completion | This applies only to redundant recruiting copies; it is not the employee-record schedule. |
| Legal hold / evidence | Review every 90 days while the hold remains active | Authorized tenant administrators and people-operations users can place and release audited, reason-coded holds. Active holds are excluded from retention previews and block erasure. Holds do not automate release; the responsible privacy/legal reviewer must assess and release them. |
| Backups | 35 days maximum proposed, subject to the chosen host | Backup expiry is infrastructure policy and is not managed by this application. |

The policy defaults are deliberately marked as proposals. A tenant administrator may version and activate a schedule, but activation only selects the schedule for reporting: it does not erase, anonymize, or enqueue deletion. The platform stores talent-pool consent as immutable, versioned grant/renewal/withdrawal events with a notice-version reference and controlled capture method; the generic application consent field is separate. Erasure records a withdrawal of any active talent-pool consent in the same transaction. Preview results contain aggregate counts only and are not a finding that a record is legally eligible for deletion. A human review must assess purpose, active matters, evidence/legal holds, other lawful retention grounds, applicable employee-record duties, and downstream processors before using the existing erasure workflow.

Kenya's Data Protection Act, section 39, and the Data Protection (General) Regulations, regulation 19, establish purpose-based storage limitation and require a retention schedule with review, audit, and disposal actions; they do not prescribe these proposed applicant durations. Section 10(6) of the Employment Act requires retention for five years of the written particulars described in section 10(1) after employment ends; do not generalize that rule to all candidate records. See the [Data Protection Act](https://new.kenyalaw.org/akn/ke/act/2019/24/eng%402019-11-15/source), [General Regulations, regulation 19](https://www.odpc.go.ke/wp-content/uploads/2024/03/THE-DATA-PROTECTION-GENERAL-REGULATIONS-2021-1.pdf), and [Employment Act, section 10(6)](https://new.kenyalaw.org/akn/ke/act/2007/11/eng%402021-04-15/source.pdf). This implementation is not legal advice; the controller's privacy lead or counsel should approve each tenant's policy and exceptions.

Before any deletion worker is considered, implement candidate-level review evidence, processor deletion tracking, backup expiry and restore tombstones, and a separately reviewed employee-record schedule. Then run a production dry run and obtain approval before enabling destructive execution. Automatic candidate deletion remains disabled.

Erasure here covers data controlled by this application, including candidate document objects in configured object storage. Any data already delivered to external signature, calendar, HRIS, or email providers needs a separate provider-specific deletion/retention process and should not be assumed erased by this workflow.
