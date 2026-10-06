import { AcceptInvitationForm } from "./accept-invitation-form";

export default async function AcceptInvitationPage({
  searchParams,
}: {
  searchParams: Promise<{ token_hash?: string | string[]; type?: string | string[] }>;
}) {
  const params = await searchParams;
  const tokenHash = typeof params.token_hash === "string" ? params.token_hash : null;
  const type = typeof params.type === "string" ? params.type : null;
  return <AcceptInvitationForm tokenHash={type === "invite" ? tokenHash : null} />;
}
