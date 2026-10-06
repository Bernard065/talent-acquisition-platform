import { NextResponse } from "next/server";

const supabaseUrl = process.env.SUPABASE_URL;
const supabasePublishableKey = process.env.SUPABASE_PUBLISHABLE_KEY;

export async function POST(request: Request) {
  const body: unknown = await request.json().catch(() => null);
  const values =
    typeof body === "object" && body !== null
      ? (body as { tokenHash?: unknown; password?: unknown })
      : {};

  if (
    typeof values.tokenHash !== "string" ||
    values.tokenHash.length < 10 ||
    typeof values.password !== "string" ||
    values.password.length < 8
  ) {
    return NextResponse.json(
      { error: "The reset link is invalid or expired, or the password is too short." },
      { status: 400 },
    );
  }
  if (!supabaseUrl || !supabasePublishableKey) {
    return NextResponse.json({ error: "Password reset is not configured." }, { status: 503 });
  }

  const baseUrl = supabaseUrl.replace(/\/$/, "");
  const headers = {
    apikey: supabasePublishableKey,
    "Content-Type": "application/json",
  };

  try {
    const verifyResponse = await fetch(`${baseUrl}/auth/v1/verify`, {
      method: "POST",
      headers,
      body: JSON.stringify({ token_hash: values.tokenHash, type: "recovery" }),
      cache: "no-store",
    });

    if (!verifyResponse.ok) {
      return NextResponse.json(
        { error: "This reset link is invalid or expired. Request a new one." },
        { status: 400 },
      );
    }

    const verified = (await verifyResponse.json()) as { access_token?: string };
    if (!verified.access_token) {
      return NextResponse.json(
        { error: "This reset link is invalid or expired. Request a new one." },
        { status: 400 },
      );
    }

    const updateResponse = await fetch(`${baseUrl}/auth/v1/user`, {
      method: "PUT",
      headers: { ...headers, Authorization: `Bearer ${verified.access_token}` },
      body: JSON.stringify({ password: values.password }),
      cache: "no-store",
    });

    if (!updateResponse.ok) {
      const details = (await updateResponse.json().catch(() => ({}))) as { msg?: string; message?: string };
      return NextResponse.json(
        { error: details.msg ?? details.message ?? "Couldn’t update the password. Request a new reset link." },
        { status: 400 },
      );
    }

    return NextResponse.json({ message: "Your password has been updated. You can sign in now." });
  } catch {
    return NextResponse.json(
      { error: "Couldn’t update the password right now. Please try again." },
      { status: 502 },
    );
  }
}
