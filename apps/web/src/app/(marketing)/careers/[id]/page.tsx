import React from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { MapPin, Briefcase, Clock, ArrowLeft, CheckCircle2 } from "lucide-react";
import { fetchApi, ApiError } from "@/lib/api-client";
import type { PublicJobDetail } from "@/types/api";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = await params;
  try {
    const job = await fetchApi<PublicJobDetail>(`/public/jobs/${resolvedParams.id}`);
    return {
      title: `${job.title} - Careers | MindHire`,
      description: `Apply for the ${job.title} role at MindHire.`,
    };
  } catch {
    return { title: "Job Not Found" };
  }
}

export const revalidate = 60;

export default async function JobDetailsPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = await params;
  let job: PublicJobDetail | null = null;

  try {
    job = await fetchApi<PublicJobDetail>(`/public/jobs/${resolvedParams.id}`, {
      next: { revalidate: 60 }
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    // If it's a 500 or network error, it will throw up to the nearest error boundary.
    // For now, if we can't find it, we 404.
    notFound();
  }

  const formatType = (type: string) => {
    return type.replace("_", "-").toLowerCase();
  };

  // We are keeping static requirements/benefits for visual display since the backend only has 'description' currently.
  const responsibilities = [
    "Design, build, and maintain high performance, reusable, and reliable code.",
    "Collaborate with a cross-functional team of designers, product managers, and engineers."
  ];

  return (
    <div className="bg-white min-h-screen pb-24">
      {/* Header Banner */}
      <div className="bg-gray-50 border-b border-gray-200 py-12 px-6">
        <div className="max-w-4xl mx-auto">
          <Link href="/careers" className="inline-flex items-center gap-2 text-sm font-semibold text-gray-500 hover:text-sr-text-blue transition-colors mb-8">
            <ArrowLeft className="w-4 h-4" /> Back to Careers
          </Link>

          <h1 className="text-3xl sm:text-4xl md:text-5xl font-extrabold text-gray-900 tracking-tight">
            {job.title}
          </h1>

          <div className="flex flex-wrap items-center gap-6 mt-6 text-sm text-gray-600 font-medium">
            {job.department && (
              <span className="flex items-center gap-2 bg-white border border-gray-200 px-3 py-1.5 rounded-lg text-gray-700 shadow-sm">
                <Briefcase className="w-4 h-4 text-sr-mint" /> {job.department}
              </span>
            )}
            {job.location && (
              <span className="flex items-center gap-2 bg-white border border-gray-200 px-3 py-1.5 rounded-lg text-gray-700 shadow-sm">
                <MapPin className="w-4 h-4 text-gray-400" /> {job.location}
              </span>
            )}
            <span className="flex items-center gap-2 bg-white border border-gray-200 px-3 py-1.5 rounded-lg text-gray-700 shadow-sm capitalize">
              <Clock className="w-4 h-4 text-gray-400" /> {formatType(job.employment_type)}
            </span>
          </div>

          <div className="mt-8">
            <Link
              href={`/careers/${job.public_id}/apply`}
              className="inline-flex items-center justify-center h-12 px-8 rounded-lg bg-sr-mint hover:bg-sr-green text-sr-text-blue hover:text-white font-bold text-lg transition-colors shadow-sm"
            >
              Apply for this Job
            </Link>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-6 mt-12 grid grid-cols-1 md:grid-cols-3 gap-12">
        <div className="md:col-span-2 space-y-10">

          <section>
            <h2 className="text-2xl font-bold text-gray-900 mb-4">About the Role</h2>
            <div className="prose prose-gray max-w-none text-gray-600 whitespace-pre-wrap">
              {job.description || "No description provided for this role."}
            </div>
          </section>

          <section>
            <h2 className="text-xl font-bold text-gray-900 mb-4">What You Will Do</h2>
            <ul className="space-y-3">
              {responsibilities.map((item, i) => (
                <li key={i} className="flex items-start gap-3 text-gray-600">
                  <CheckCircle2 className="w-5 h-5 text-sr-green shrink-0 mt-0.5" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </section>

        </div>

        <div className="md:col-span-1">
          <div className="bg-gray-50 border border-gray-200 rounded-xl p-6 sticky top-24">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Ready to join?</h3>
            <p className="text-sm text-gray-600 mb-6">
              Take the next step in your career by applying to the {job.title} role today.
            </p>
            <div className="mt-8 pt-6 border-t border-gray-200">
              <Link
                href={`/careers/${job.public_id}/apply`}
                className="flex items-center justify-center w-full h-11 rounded-lg bg-sr-text-blue hover:bg-sr-text-blue/90 text-white font-bold transition-colors shadow-sm"
              >
                Apply Now
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
