import React from "react";
import Link from "next/link";
import { mockJobs } from "@/lib/mock-jobs";
import { notFound } from "next/navigation";
import { MapPin, Briefcase, Clock, ArrowLeft, CheckCircle2 } from "lucide-react";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = await params;
  const job = mockJobs.find((j) => j.id === resolvedParams.id);
  
  if (!job) return { title: "Job Not Found" };
  
  return {
    title: `${job.title} - Careers | MindHire`,
    description: `Apply for the ${job.title} role at MindHire.`,
  };
}

export default async function JobDetailsPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = await params;
  const job = mockJobs.find((j) => j.id === resolvedParams.id);

  if (!job) {
    notFound();
  }

  // Generate generic job description data for the UI since mock data doesn't have it
  const responsibilities = [
    "Design, build, and maintain high performance, reusable, and reliable code.",
    "Ensure the best possible performance, quality, and responsiveness of the application.",
    "Identify and correct bottlenecks and fix bugs.",
    "Help maintain code quality, organization, and automatization.",
    "Collaborate with a cross-functional team of designers, product managers, and engineers."
  ];

  const requirements = [
    "5+ years of experience in software engineering.",
    "Strong proficiency in JavaScript, TypeScript, and modern React.",
    "Experience with state management libraries and Next.js App Router.",
    "Familiarity with RESTful APIs and modern backend architectures.",
    "A knack for benchmarking and optimization.",
    "Excellent communication skills and a team player mentality."
  ];

  const benefits = [
    "Competitive salary and equity package.",
    "Comprehensive health, dental, and vision insurance.",
    "Flexible PTO and remote work options.",
    "Learning & development stipend.",
    "Latest Apple hardware and home office budget."
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
            <span className="flex items-center gap-2 bg-white border border-gray-200 px-3 py-1.5 rounded-lg text-gray-700 shadow-sm">
              <Briefcase className="w-4 h-4 text-sr-mint" /> {job.department}
            </span>
            <span className="flex items-center gap-2 bg-white border border-gray-200 px-3 py-1.5 rounded-lg text-gray-700 shadow-sm">
              <MapPin className="w-4 h-4 text-gray-400" /> {job.location}
            </span>
            <span className="flex items-center gap-2 bg-white border border-gray-200 px-3 py-1.5 rounded-lg text-gray-700 shadow-sm capitalize">
              <Clock className="w-4 h-4 text-gray-400" /> {job.type.replace("-", " ")}
            </span>
          </div>

          <div className="mt-8">
            <Link 
              href={`/careers/${job.id}/apply`}
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
            <div className="prose prose-gray max-w-none text-gray-600">
              <p>
                We are looking for a highly skilled <strong>{job.title}</strong> to join our growing {job.department} team. 
                In this role, you will be responsible for building world-class experiences that delight our users and drive the business forward.
                You will tackle complex technical challenges, collaborate closely with cross-functional partners, and have a massive impact on our product trajectory.
              </p>
              <p className="mt-4">
                If you are passionate about building scalable software, solving hard problems, and working with a talented, low-ego team, we want to hear from you!
              </p>
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

          <section>
            <h2 className="text-xl font-bold text-gray-900 mb-4">What You Need</h2>
            <ul className="space-y-3">
              {requirements.map((item, i) => (
                <li key={i} className="flex items-start gap-3 text-gray-600">
                  <CheckCircle2 className="w-5 h-5 text-sr-mint shrink-0 mt-0.5" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </section>

        </div>

        <div className="md:col-span-1">
          <div className="bg-gray-50 border border-gray-200 rounded-xl p-6 sticky top-24">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Why MindHire?</h3>
            <ul className="space-y-4">
              {benefits.map((item, i) => (
                <li key={i} className="flex items-start gap-3 text-sm text-gray-600">
                  <div className="w-1.5 h-1.5 rounded-full bg-sr-mint shrink-0 mt-2" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <div className="mt-8 pt-6 border-t border-gray-200">
              <Link 
                href={`/careers/${job.id}/apply`}
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
