# Architecture Overview

## System style

The platform starts as a modular FastAPI monolith with explicit domain boundaries.
We will only extract services when there is a demonstrated scaling, security,
ownership, or deployment requirement.

## Core domains

- Identity and tenancy
- Organizations and user access
- Requisitions
- Candidates
- Applications and workflow
- Interviews and evaluations
- Offers
- Onboarding handoff
- Integrations
- Analytics
- Audit and compliance

## Core technical rules

- PostgreSQL is the transactional system of record.
- SQLAlchemy models are not API response models.
- Pydantic schemas validate all external input and response output.
- Tenant ID comes from verified JWT claims, never client input.
- Significant business changes write audit and outbox events in the same transaction.
- Long-running tasks run asynchronously outside HTTP request handlers.
- Files use signed object-storage URLs and are malware-scanned.
- API routes use `/api/v1`.
