import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, BriefcaseBusiness } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { getPublicJob } from "@/lib/api/services/jobs";

export const metadata: Metadata = {
  title: "Applications coming soon",
  robots: { index: false, follow: false },
};

export default async function ApplyPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let job;

  try {
    job = await getPublicJob(id, { next: { revalidate: 60 } });
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidationError)) {
      notFound();
    }

    return (
      <div className="min-h-screen bg-gray-50 px-6 py-20">
        <div role="alert" className="mx-auto max-w-xl rounded-xl border border-rose-200 bg-white p-8 text-center">
          <h1 className="text-xl font-semibold text-gray-900">We couldn’t load this job</h1>
          <p className="mt-2 text-gray-600">Please try again in a little while.</p>
          <Link href="/careers" className="mt-6 inline-flex font-semibold text-sr-text-blue hover:underline">
            Browse open roles
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 px-6 py-14">
      <main className="mx-auto max-w-2xl">
        <Link
          href={`/careers/${job.public_id}`}
          className="inline-flex items-center gap-2 text-sm font-semibold text-gray-600 hover:text-sr-text-blue"
        >
          <ArrowLeft aria-hidden="true" className="h-4 w-4" />
          Back to job details
        </Link>

        <section className="mt-8 rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-sm sm:p-10">
          <BriefcaseBusiness aria-hidden="true" className="mx-auto h-10 w-10 text-sr-green" />
          <p className="mt-5 text-sm font-semibold uppercase tracking-wide text-gray-500">
            {job.title}
          </p>
          <h1 className="mt-2 text-2xl font-bold text-gray-900">Applications are coming soon</h1>
          <p className="mt-3 text-gray-600">
            We’re preparing the online application form for this role. Please check back soon.
          </p>
          <Link
            href="/careers"
            className="mt-7 inline-flex items-center justify-center rounded-lg bg-sr-text-blue px-5 py-3 font-semibold text-white transition-colors hover:bg-sr-text-blue/90"
          >
            Browse other roles
          </Link>
        </section>
      </main>
    </div>
  );
}
