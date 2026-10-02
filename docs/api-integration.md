# API integration

The Next.js frontend (`apps/web`) communicates with the FastAPI backend
(`apps/api`) over HTTP. This document describes the integration layers,
conventions, and implementation order.

## Current state

The backend exposes versioned REST endpoints under `/api/v1` with JWT
authentication, multi-tenant isolation, and Pydantic request/response schemas.
CORS is configured to allow the frontend dev origin (`http://localhost:3000`).

The frontend is a foundation scaffold: App Router layout, Tailwind theme, and
shadcn/ui primitives. It does not yet authenticate users, define API types, or
make backend requests.

## Environment configuration

The frontend needs one public environment variable to locate the backend:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

During development, Next.js rewrites proxy `/api/v1/*` requests to the backend
to avoid CORS preflight. In production the frontend calls the backend origin
directly.

| Variable              | Purpose                          | Example                    |
|-----------------------|----------------------------------|----------------------------|
| `NEXT_PUBLIC_API_URL` | Backend base URL                 | `http://localhost:8000`    |

## API client

A shared fetch wrapper at `src/lib/api/client.ts` handles:

- Base URL resolution from `NEXT_PUBLIC_API_URL`.
- `Authorization: Bearer <token>` injection for authenticated requests.
- JSON serialization and deserialization.
- RFC 7807 problem+json error parsing into a typed `ApiError` class.
- `Idempotency-Key` header attachment on mutating requests.
- `X-Request-ID` propagation.

No external HTTP library is required; native `fetch` is sufficient because
Next.js extends it with caching and revalidation support.

## TypeScript API types

TypeScript interfaces in `src/types/api/` mirror backend Pydantic schemas.
Types are maintained manually and organized by domain:

| Module               | Entities                                       |
|----------------------|------------------------------------------------|
| `auth.ts`            | User, Tenant, TokenClaims                      |
| `requisitions.ts`    | Requisition, RequisitionCreate, statuses        |
| `candidates.ts`      | Candidate, CandidateCreate, search params       |
| `jobs.ts`            | JobPosting, JobPostingCreate, statuses           |
| `applications.ts`    | Application, ApplicationCreate, stage history    |
| `interviews.ts`      | InterviewSession, InterviewFeedback              |
| `offers.ts`          | Offer, OfferStatus                              |
| `common.ts`          | PaginatedResponse, SortOrder, shared enums       |

Automated OpenAPI type generation may replace the manual types once the
backend schemas stabilize.

## API service modules

Domain-specific service modules at `src/lib/api/services/` wrap the API
client into typed function calls:

- `auth.ts` — `login`, `signup`, `getCurrentUser`, `refreshToken`
- `requisitions.ts` — CRUD and status transitions
- `candidates.ts` — CRUD and search
- `jobs.ts` — CRUD, publishing, and scheduling
- `applications.ts` — CRUD and pipeline stage transitions
- `interviews.ts` — scheduling, lifecycle, and feedback
- `offers.ts` — CRUD and approval workflows
- `dashboard.ts` — recruiting metrics and pipeline stats

## Authentication

Authentication uses JWT bearer tokens verified by the backend against a
JWKS endpoint. The frontend manages auth state through:

- An `AuthProvider` React context (`src/providers/auth-provider.tsx`) that
  stores the current user and token state.
- A `useAuth` hook (`src/hooks/use-auth.ts`) exposing `user`,
  `isAuthenticated`, `login`, `logout`, and `refreshToken`.
- Token storage in an `httpOnly` cookie managed by Next.js middleware, which
  is more secure than `localStorage` and works with server-side rendering.
- Automatic token refresh before expiry.

Protected dashboard routes check authentication in Next.js middleware and
redirect unauthenticated users to `/login`.

## Implementation phases

### Phase 1 — API foundation

Set up the environment variable, Next.js proxy rewrite, API client, error
handling, and core TypeScript types. No visible UI changes; this phase
provides the plumbing for all subsequent work.

### Phase 2 — Authentication

Build the `AuthProvider`, login and signup pages, and route protection
middleware. After this phase users can sign in and the frontend can make
authenticated requests.

### Phase 3 — Dashboard features

Implement the authenticated dashboard routes:

| Route                        | Data source                |
|------------------------------|----------------------------|
| `/dashboard`                 | Recruiting metrics         |
| `/dashboard/jobs`            | Job postings list          |
| `/dashboard/jobs/new`        | Create job posting form    |
| `/dashboard/jobs/[id]`       | Job posting detail         |
| `/dashboard/candidates`      | Candidates list            |
| `/dashboard/candidates/[id]` | Candidate detail           |
| `/dashboard/interviews`      | Interview schedule         |
| `/dashboard/analytics`       | Pipeline analytics         |
| `/dashboard/settings`        | Tenant settings            |

### Phase 4 — Public career pages

Implement the unauthenticated public routes:

| Route                   | Data source              |
|-------------------------|--------------------------|
| `/careers`              | Public job catalog       |
| `/careers/[id]`         | Public job detail        |
| `/careers/[id]/apply`   | Application submission   |

These routes call the backend's public endpoints, which do not require
authentication but enforce CAPTCHA and rate limiting.

## Conventions

- API routes use the `/api/v1` prefix. The frontend never constructs raw
  endpoint URLs outside the API client.
- All mutating requests include an `Idempotency-Key` header.
- Error responses follow RFC 7807 and are parsed into `ApiError` instances
  with `status`, `title`, `detail`, and optional `errors` field validation
  array.
- Pagination uses cursor-based tokens returned by the backend; the frontend
  passes `cursor` and `limit` query parameters.
- Tenant isolation is enforced by the backend through JWT claims. The
  frontend never sends a `tenant_id` in request bodies.
