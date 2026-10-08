export function getUserDisplayName(
  name?: string | null,
  email?: string | null,
): string | undefined {
  const trimmedName = name?.trim();
  if (trimmedName && !trimmedName.includes("@")) return trimmedName;

  const emailUsername = email?.split("@", 1)[0]?.trim();
  if (!emailUsername) return undefined;

  return emailUsername
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toLocaleUpperCase() + part.slice(1))
    .join(" ");
}

export function getUserFirstName(name?: string | null, email?: string | null): string | undefined {
  return getUserDisplayName(name, email)?.split(/\s+/)[0];
}
