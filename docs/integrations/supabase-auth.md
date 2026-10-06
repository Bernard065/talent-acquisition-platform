# Supabase Auth and Auth.js

The web app uses Auth.js to manage an encrypted, HTTP-only application session.
Its Credentials provider authenticates email/password credentials against
Supabase Auth. The Supabase access token is refreshed server-side and exposed
to the web API client for bearer authentication. The Supabase refresh token is
kept inside the Auth.js session token and is never returned by the session
endpoint.

## Configuration

Set these web-app variables in the environment used to run `apps/web`:

- `AUTH_SECRET`: generate with `npx auth secret`.
- `SUPABASE_URL`: project URL, such as `https://project-ref.supabase.co`.
- `SUPABASE_PUBLISHABLE_KEY`: the project's publishable key. Never use the
  Supabase `service_role` key in the web app.
- `NEXT_PUBLIC_SITE_URL`: the app origin used for password recovery redirects,
  such as `http://localhost:3000` locally or the production app origin.
- `NEXT_PUBLIC_API_URL`: API origin, such as `http://localhost:8000`.

Configure the API to verify the Supabase Auth access-token issuer, audience,
JWKS URL, and signing algorithm:

- `JWT_ISSUER`: `${SUPABASE_URL}/auth/v1`.
- `JWT_AUDIENCE`: `authenticated`.
- `JWT_JWKS_URL`: `${SUPABASE_URL}/auth/v1/.well-known/jwks.json`.
- `JWT_ALGORITHM`: the asymmetric algorithm configured for the project, either
  `RS256` or `ES256`.

Use an asymmetric signing key so the API can verify tokens through the public
JWKS endpoint. Do not configure the API with a shared signing secret.

## Tenant and role claims

The API requires a signed `org_id` claim and a signed `roles` array. Configure
a Supabase Custom Access Token Hook to add these claims from trusted
`app_metadata`. The `app_metadata` values must be assigned by a trusted
provisioning process using the Supabase Admin API; never accept organization or
role values from `user_metadata`, sign-up forms, or browser input.

The hook should copy:

- `app_metadata.organization_id` to the top-level `org_id` claim. This value
  must match a tenant's `identity_provider_organization_id` in the API database.
- `app_metadata.roles` to the top-level `roles` claim, using only the API's
  supported role values.

Example Supabase SQL for the hook function:

```sql
create or replace function public.mindhire_access_token_hook(event jsonb)
returns jsonb
language plpgsql
stable
as $$
declare
  claims jsonb := event -> 'claims';
  trusted_metadata jsonb := coalesce(claims -> 'app_metadata', '{}'::jsonb);
begin
  claims := jsonb_set(
    claims,
    '{org_id}',
    coalesce(trusted_metadata -> 'organization_id', 'null'::jsonb),
    true
  );
  claims := jsonb_set(
    claims,
    '{roles}',
    case
      when jsonb_typeof(trusted_metadata -> 'roles') = 'array'
        then trusted_metadata -> 'roles'
      else '[]'::jsonb
    end,
    true
  );
  return jsonb_set(event, '{claims}', claims);
end;
$$;

grant usage on schema public to supabase_auth_admin;
grant execute on function public.mindhire_access_token_hook(jsonb)
  to supabase_auth_admin;
revoke execute on function public.mindhire_access_token_hook(jsonb)
  from authenticated, anon, public;
```

Enable this function as the **Custom Access Token Hook** in the Supabase
dashboard. Add `organization_id` and `roles` through a trusted admin or
invitation flow. The example intentionally emits no organization and an empty
role list when metadata has not been provisioned; the API will reject such a
token for tenant data.

Users without a provisioned organization and roles can authenticate but the
API will deny access. Tenant invitation, membership administration, and
organization switching remain application workflows; this integration does
not make Supabase user metadata an authorization source.

## Local setup

1. Create a Supabase project and enable email/password authentication.
2. Configure an asymmetric JWT signing key and the custom access-token hook.
3. Add the project's issuer and JWKS settings to the API environment.
4. Add the project URL and publishable key, plus an Auth.js secret, to the web
   environment.
5. Provision each tenant's external organization identifier and assign each
   authorized user `organization_id` and `roles` in trusted `app_metadata`.
6. Apply the API Alembic migrations before using tenant-authenticated routes.

## Password recovery

The web app sends recovery requests through Supabase Auth and validates the
single-use recovery token on the server before updating the password. Configure
the `NEXT_PUBLIC_SITE_URL` value in the web environment and add
`<site-url>/reset-password` to **Authentication → URL Configuration → Redirect
URLs** in Supabase.

In **Authentication → Email Templates → Reset Password**, use a link that sends
the token hash to the app's reset page:

```html
<a href="{{ .RedirectTo }}?token_hash={{ .TokenHash }}&type=recovery">Reset password</a>
```

The app accepts passwords of at least eight characters. Supabase Auth also
applies the project's configured password policy. The forgot-password response
does not disclose whether an email address has an account.

The app currently supports email/password sign-in and password recovery.
Social login, tenant invitations, and user provisioning are separate workflows
to implement before production rollout.
