import type { Metadata } from "next";
import Link from "next/link";
import { BriefcaseBusiness, ChevronRight, MapPin, Search } from "lucide-react";
import { listPublicJobs } from "@/lib/api/services/jobs";
import type { PublicJobSummaryResponse } from "@/types/api/jobs";

export const metadata: Metadata = {
  title: "Open jobs",
  description: "Explore current job opportunities and learn more about each role.",
  robots: { index: true, follow: true },
};

function formatEmploymentType(value: string): string {
  return value
    .split("_")
    .map((word) => word[0]?.toUpperCase() + word.slice(1))
    .join(" ");
}

export default async function CareersPage({
  searchParams,
}: {
  searchParams: Promise<{ cursor?: string }>;
}) {
  const { cursor } = await searchParams;
  let jobs: PublicJobSummaryResponse[] = [];
  let nextCursor: string | null = null;
  let failedToLoad = false;

  try {
    const page = await listPublicJobs(
      { limit: 50, cursor },
      { next: { revalidate: 60 } },
    );
    jobs = page.items;
    nextCursor = page.next_cursor ?? null;
  } catch {
    failedToLoad = true;
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-24">
      <section className="relative overflow-hidden bg-sr-text-blue px-6 py-20 text-white sm:py-24">
        <div className="relative z-10 mx-auto max-w-4xl text-center">
          <p className="mb-4 text-sm font-semibold uppercase tracking-[0.18em] text-sr-mint">
            Careers
          </p>
          <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl md:text-6xl">
            Find your next opportunity
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-blue-100 sm:text-xl">
            Explore open roles and find a place to do meaningful work.
          </p>
        </div>
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-24 -top-32 h-96 w-96 rounded-full bg-blue-400/10 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-48 -left-24 h-96 w-96 rounded-full bg-emerald-400/10 blur-3xl"
        />
      </section>

      <section aria-labelledby="open-roles-heading" className="mx-auto mt-14 max-w-5xl px-6 sm:mt-16">
        <div className="mb-8">
          <h2 id="open-roles-heading" className="text-3xl font-bold text-gray-900">
            Open roles
          </h2>
          <p className="mt-2 text-gray-600">
            Explore currently published opportunities.
          </p>
        </div>

        {failedToLoad ? (
          <div role="alert" className="rounded-xl border border-rose-200 bg-white p-8 text-center">
            <h3 className="text-lg font-semibold text-gray-900">Jobs are temporarily unavailable</h3>
            <p className="mt-2 text-sm text-gray-600">Please try again in a little while.</p>
          </div>
        ) : jobs.length === 0 ? (
          <div className="rounded-xl border border-gray-200 bg-white p-10 text-center">
            <Search aria-hidden="true" className="mx-auto h-9 w-9 text-gray-400" />
            <h3 className="mt-4 text-lg font-semibold text-gray-900">
              {cursor ? "No more roles to show" : "No open roles right now"}
            </h3>
            <p className="mt-2 text-sm text-gray-600">Please check back later for new opportunities.</p>
            {cursor && (
              <Link href="/careers" className="mt-5 inline-flex font-semibold text-sr-text-blue hover:underline">
                Back to the first page
              </Link>
            )}
          </div>
        ) : (
          <ul className="grid grid-cols-1 gap-4">
            {jobs.map((job) => (
              <li key={job.public_id}>
                <Link
                  href={`/careers/${job.public_id}`}
                  className="group flex flex-col justify-between gap-5 rounded-xl border border-gray-200 bg-white p-6 transition hover:border-sr-mint hover:shadow-md sm:flex-row sm:items-center sm:p-8"
                >
                  <div>
                    <h3 className="text-xl font-bold text-sr-text-blue transition-colors group-hover:text-sr-green">
                      {job.title}
                    </h3>
                    <div className="mt-3 flex flex-wrap items-center gap-3 text-sm font-medium text-gray-600">
                      {job.department && (
                        <span className="inline-flex items-center gap-1.5 rounded-md bg-gray-100 px-2.5 py-1 text-gray-700">
                          <BriefcaseBusiness aria-hidden="true" className="h-4 w-4" />
                          {job.department}
                        </span>
                      )}
                      {job.location && (
                        <span className="inline-flex items-center gap-1.5">
                          <MapPin aria-hidden="true" className="h-4 w-4" />
                          {job.location}
                        </span>
                      )}
                      <span>{formatEmploymentType(job.employment_type)}</span>
                    </div>
                  </div>
                  <span className="inline-flex shrink-0 items-center gap-2 font-semibold text-sr-text-blue">
                    View role
                    <ChevronRight aria-hidden="true" className="h-5 w-5 transition-transform group-hover:translate-x-1" />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}

        {!failedToLoad && nextCursor && (
          <div className="mt-8 flex justify-center">
            <Link
              href={`/careers?cursor=${encodeURIComponent(nextCursor)}`}
              className="inline-flex items-center justify-center rounded-lg border border-gray-300 bg-white px-5 py-3 font-semibold text-sr-text-blue transition-colors hover:bg-gray-50"
            >
              Load more roles
            </Link>
          </div>
        )}
        {!failedToLoad && cursor && jobs.length > 0 && (
          <div className="mt-5 text-center">
            <Link href="/careers" className="text-sm font-semibold text-gray-600 hover:text-sr-text-blue hover:underline">
              Back to the first page
            </Link>
          </div>
        )}
      </section>
    </div>
  );
}
