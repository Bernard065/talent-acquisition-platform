
# Security Policy

```md
# Security Policy

## Reporting a vulnerability

Do not create a public issue for a suspected security vulnerability.

Report it privately to the repository owner with:

- A clear description of the issue
- Steps to reproduce
- Potential impact
- Any suggested mitigation

## Security requirements

- Secrets must never be committed.
- Tenant context must come from verified identity claims.
- Every data query must be tenant-scoped.
- Candidate PII must not be logged.
- Dependencies must be reviewed and updated regularly.
- Security-sensitive changes require peer review before merge.
