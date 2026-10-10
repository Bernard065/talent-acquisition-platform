import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, BriefcaseBusiness } from "lucide-react";
import { PublicJobApplicationForm } from "@/components/careers/public-job-application-form";
import { ApiError } from "@/lib/api/errors";
import { getPublicJob } from "@/lib/api/services/jobs";

type ApplyPageProps = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: ApplyPageProps): Promise<Metadata> {
  const { id } = await params;

  try {
    const job = await getPublicJob(id, { next: { revalidate: 60 } });
    return {
      title: `Apply for ${job.title}`,
      robots: { index: false, follow: false },
    };
  } catch {
    return { title: "Apply for a job", robots: { index: false, follow: false } };
  }
}

export default async function ApplyPage({
  params,
}: ApplyPageProps) {
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
    <div className="min-h-screen bg-gray-50 px-6 py-14 pb-24">
      <main className="mx-auto max-w-2xl">
        <Link
          href={`/careers/${job.public_id}`}
          className="inline-flex items-center gap-2 text-sm font-semibold text-gray-600 hover:text-sr-text-blue"
        >
          <ArrowLeft aria-hidden="true" className="h-4 w-4" />
          Back to job details
        </Link>

        <div className="mb-8 mt-8">
          <p className="flex items-center gap-2 text-sm font-medium text-gray-600">
            <BriefcaseBusiness aria-hidden="true" className="h-4 w-4" />
            {job.title}
          </p>
          <h1 className="mt-3 text-3xl font-bold tracking-tight text-gray-900">Apply for this role</h1>
          <p className="mt-2 text-gray-600">
            Share your contact information with the hiring team.
          </p>
        </div>
        <PublicJobApplicationForm publicJobId={job.public_id} jobTitle={job.title} />
      </main>
    </div>
  );
}
