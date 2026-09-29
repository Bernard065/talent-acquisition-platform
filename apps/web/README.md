# Web application

The frontend is a Next.js App Router application written in TypeScript. This
foundation PR establishes the runtime, quality checks, and a minimal route. It
does not yet authenticate users or make API requests.

## Requirements

- Node.js 24.x LTS (see `.nvmrc`)
- npm 11+

## Local development

From this directory:

```bash
npm ci
npm run dev
```

The app is available at <http://localhost:3000>.

Run all checks before committing:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

The application route is intentionally minimal. The app is marked `noindex`
until authentication, API integration, and the deployment/access model are in
place. Do not add real or fabricated recruiting data to this scaffold.
