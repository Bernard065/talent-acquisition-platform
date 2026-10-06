import Link from "next/link";

export default function SignupPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2 text-center lg:text-left mb-4">
        <h1 className="text-3xl font-semibold tracking-tight text-sr-text-blue">
          Join your hiring workspace
        </h1>
        <p className="text-sm text-sr-gray">
          MindHire accounts are connected to a company workspace. Ask your
          workspace administrator for an invitation.
        </p>
      </div>

      <Link
        href="/login"
        className="inline-flex h-12 items-center justify-center rounded-lg bg-sr-mint px-5 font-semibold text-sr-text-blue transition-colors hover:bg-sr-green hover:text-white"
      >
        Go to sign in
      </Link>
    </div>
  );
}
