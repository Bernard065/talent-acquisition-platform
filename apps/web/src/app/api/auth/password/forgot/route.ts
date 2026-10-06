import { NextResponse } from "next/server";

const supabaseUrl = process.env.SUPABASE_URL;
const supabasePublishableKey = process.env.SUPABASE_PUBLISHABLE_KEY;

export async function POST(request: Request) {
  const body: unknown = await request.json().catch(() => null);
  const email =
    typeof body === "object" && body !== null && "email" in body
      ? (body as { email?: unknown }).email
      : null;

  if (typeof email !== "string" || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
    return NextResponse.json({ error: "Enter a valid email address." }, { status: 400 });
  }
  if (!supabaseUrl || !supabasePublishableKey) {
    return NextResponse.json({ error: "Password reset is not configured." }, { status: 503 });
  }

  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? new URL(request.url).origin;
  const redirectTo = new URL("/reset-password", siteUrl).toString();

  try {
    const recoverUrl = new URL(`${supabaseUrl.replace(/\/$/, "")}/auth/v1/recover`);
    recoverUrl.searchParams.set("redirect_to", redirectTo);
    const response = await fetch(recoverUrl, {
      method: "POST",
      headers: {
        apikey: supabasePublishableKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email: email.trim() }),
      cache: "no-store",
    });

    if (!response.ok) {
      console.error("Supabase password recovery request failed", response.status);
      return NextResponse.json(
        { error: "We couldn’t send a reset link right now. Please try again." },
        { status: 502 },
      );
    }

    // Keep the response identical whether or not this email has an account.
    return NextResponse.json({
      message: "If an account exists for that email, we’ve sent a password reset link.",
    });
  } catch {
    return NextResponse.json(
      { error: "We couldn’t send a reset link right now. Please try again." },
      { status: 502 },
    );
  }
}
