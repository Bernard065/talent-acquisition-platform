# Talent Acquisition Platform

A secure, multi-tenant talent acquisition platform for corporate recruiting.

## Product scope

The platform will support the complete hiring lifecycle:

- Requisition and approval management
- Branded careers sites and job applications
- Applicant tracking and candidate relationship management
- Interview scheduling and hiring-team collaboration
- Offers, e-signatures, and HRIS handoff
- Analytics, integrations, and governed AI assistance

## Technology direction

- Backend: Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL
- Frontend: Next.js and TypeScript
- Async processing: Redis and worker processes
- File storage: S3-compatible object storage
- Infrastructure: Docker, GitHub Actions, Terraform

## Engineering principles

- Multi-tenant isolation by design
- Privacy and security by default
- API-first, versioned contracts
- Auditability for all significant business actions
- Asynchronous, idempotent integrations
- Accessible candidate and hiring-team experiences

## Public job discovery

Public job detail pages, Google `JobPosting` structured data, sitemap, and
deployment configuration are described in
[`docs/integrations/google-jobs-discovery.md`](docs/integrations/google-jobs-discovery.md).

## Repository status

The frontend foundation lives in [`apps/web`](apps/web/README.md). This repository
is still in foundation setup; see `docs/architecture.md` and `CONTRIBUTING.md`.
