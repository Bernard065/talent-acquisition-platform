# Web application

The frontend is a Next.js App Router application written in TypeScript and
styled with Tailwind CSS v4. Theme tokens live in `src/app/globals.css`; layout
and component styling use Tailwind utility classes. The app does not yet
authenticate users or make API requests.

Reusable shadcn/ui components are source-owned under `src/components/ui` and
configured by `components.json`. Their semantic color tokens map to the
existing product palette in `globals.css`; keep component variants accessible
and avoid introducing a second styling system.

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
