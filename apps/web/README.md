# Web application

The frontend is a Next.js App Router application written in TypeScript and
styled with Tailwind CSS v4. Theme tokens live in `src/app/globals.css`; layout
and component styling use Tailwind utility classes. Auth.js manages the web
session and authenticates email/password credentials with Supabase Auth. The
resulting Supabase access token is used for authenticated FastAPI requests.

Reusable shadcn/ui components are source-owned under `src/components/ui` and
configured by `components.json`. Their semantic color tokens map to the
existing product palette in `globals.css`; keep component variants accessible
and avoid introducing a second styling system.

## Requirements

- Node.js 24.x LTS (see `.nvmrc`)
- npm 11+
- Copy `.env.example` to `.env.local` and set the Auth.js and Supabase values.

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

The app is marked `noindex` until its deployment/access model is in place. Do
not add real or fabricated recruiting data to this scaffold. See
[`../../docs/integrations/supabase-auth.md`](../../docs/integrations/supabase-auth.md)
for identity-provider and API claim setup.
