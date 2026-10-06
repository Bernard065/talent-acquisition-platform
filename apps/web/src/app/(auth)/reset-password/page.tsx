import { ResetPasswordForm } from "./reset-password-form";

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token_hash?: string | string[]; type?: string | string[] }>;
}) {
  const params = await searchParams;
  const tokenHash = typeof params.token_hash === "string" ? params.token_hash : null;
  return <ResetPasswordForm tokenHash={tokenHash} />;
}
