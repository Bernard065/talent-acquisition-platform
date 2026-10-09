import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, BriefcaseBusiness, MapPin } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { getPublicJob } from "@/lib/api/services/jobs";

type JobPageProps = {
  params: Promise<{ id: string }>;
};

async function loadPublicJob(id: string) {
  return getPublicJob(id, { next: { revalidate: 60 } });
}

function formatEmploymentType(value: string): string {
  return value
    .split("_")
    .map((word) => word[0]?.toUpperCase() + word.slice(1))
    .join(" ");
}

export async function generateMetadata({ params }: JobPageProps): Promise<Metadata> {
  const { id } = await params;

  try {
    const job = await loadPublicJob(id);
    return {
      title: `${job.title} | Careers`,
      description:
        job.description?.replace(/\s+/g, " ").trim().slice(0, 160) ||
        `Learn more about the ${job.title} role.`,
      robots: { index: true, follow: true },
    };
  } catch {
    return {
      title: "Job details | Careers",
      robots: { index: false, follow: false },
    };
  }
}

export default async function JobDetailsPage({ params }: JobPageProps) {
  const { id } = await params;
  let job;

  try {
    job = await loadPublicJob(id);
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidationError)) {
      notFound();
    }

    return (
      <div className="min-h-screen bg-white px-6 py-20">
        <div className="mx-auto max-w-3xl rounded-xl border border-rose-200 bg-rose-50 p-8 text-center">
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
    <div className="min-h-screen bg-white pb-24">
      <header className="border-b border-gray-200 bg-gray-50 px-6 py-12">
        <div className="mx-auto max-w-4xl">
          <Link
            href="/careers"
            className="mb-8 inline-flex items-center gap-2 text-sm font-semibold text-gray-600 transition-colors hover:text-sr-text-blue"
          >
            <ArrowLeft aria-hidden="true" className="h-4 w-4" />
            Back to careers
          </Link>

          <h1 className="text-3xl font-extrabold tracking-tight text-gray-900 sm:text-4xl md:text-5xl">
            {job.title}
          </h1>

          <div className="mt-6 flex flex-wrap items-center gap-3 text-sm font-medium text-gray-700">
            {job.department && (
              <span className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 shadow-sm">
                <BriefcaseBusiness aria-hidden="true" className="h-4 w-4 text-sr-green" />
                {job.department}
              </span>
            )}
            {job.location && (
              <span className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 shadow-sm">
                <MapPin aria-hidden="true" className="h-4 w-4 text-gray-500" />
                {job.location}
              </span>
            )}
            <span className="rounded-lg border border-gray-200 bg-white px-3 py-2 shadow-sm">
              {formatEmploymentType(job.employment_type)}
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-4xl grid-cols-1 gap-10 px-6 pt-10 md:grid-cols-3">
        <article className="md:col-span-2">
          <h2 className="text-2xl font-bold text-gray-900">About this role</h2>
          {job.description?.trim() ? (
            <div className="mt-4 whitespace-pre-wrap text-base leading-7 text-gray-700">
              {job.description}
            </div>
          ) : (
            <p className="mt-4 text-gray-600">
              More information about this role will be available soon.
            </p>
          )}
        </article>

        <aside className="h-fit rounded-xl border border-gray-200 bg-gray-50 p-6">
          <h2 className="text-lg font-bold text-gray-900">Interested in this role?</h2>
          <p className="mt-2 text-sm leading-6 text-gray-600">
            Online applications are coming soon. Please check back to apply.
          </p>
          <Link
            href="/careers"
            className="mt-6 inline-flex w-full items-center justify-center rounded-lg bg-sr-text-blue px-4 py-3 font-semibold text-white transition-colors hover:bg-sr-text-blue/90"
          >
            Browse other roles
          </Link>
        </aside>
      </main>
    </div>
  );
}
