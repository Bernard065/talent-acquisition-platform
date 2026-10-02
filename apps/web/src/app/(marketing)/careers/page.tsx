import React from "react";
import Link from "next/link";
import { mockJobs } from "@/lib/mock-jobs";
import { MapPin, Briefcase, Clock, ChevronRight } from "lucide-react";

export const metadata = {
  title: "Careers | Join Our Team",
  description: "View our open positions and apply today.",
};

export default function CareersPage() {
  const activeJobs = mockJobs.filter(job => job.status === "active");

  return (
    <div className="bg-gray-50 min-h-screen pb-24">
      {/* Hero Section */}
      <div className="bg-sr-text-blue text-white py-24 px-6 relative overflow-hidden">
        <div className="max-w-4xl mx-auto text-center relative z-10">
          <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold tracking-tight mb-6">
            Help us build the future of hiring
          </h1>
          <p className="text-lg sm:text-xl text-blue-100 max-w-2xl mx-auto mb-10 leading-relaxed">
            We are a team of builders, designers, and problem solvers. Join us in our mission to connect great talent with great opportunities.
          </p>
        </div>
        
        {/* Decorative elements */}
        <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none">
          <div className="absolute -top-[20%] -right-[10%] w-[50%] h-[150%] bg-blue-500/10 rotate-12 blur-3xl rounded-full" />
          <div className="absolute top-[60%] -left-[10%] w-[40%] h-[80%] bg-emerald-500/10 -rotate-12 blur-3xl rounded-full" />
        </div>
      </div>

      {/* Open Positions List */}
      <div className="max-w-5xl mx-auto px-6 mt-16">
        <div className="mb-10 text-center">
          <h2 className="text-3xl font-bold text-gray-900">Open Positions</h2>
          <p className="text-gray-500 mt-2 text-lg">Find a role that fits your skills and passions.</p>
        </div>

        <div className="grid grid-cols-1 gap-4">
          {activeJobs.map((job) => (
            <Link 
              key={job.id} 
              href={`/careers/${job.id}`}
              className="bg-white border border-gray-200 rounded-xl p-6 sm:p-8 hover:border-sr-mint hover:shadow-md transition-all group flex flex-col sm:flex-row sm:items-center justify-between gap-6"
            >
              <div>
                <h3 className="text-xl font-bold text-sr-text-blue group-hover:text-sr-mint transition-colors">
                  {job.title}
                </h3>
                <div className="flex flex-wrap items-center gap-4 mt-3 text-sm text-gray-600 font-medium">
                  <span className="flex items-center gap-1.5 bg-gray-100 px-2.5 py-1 rounded-md text-gray-700">
                    <Briefcase className="w-4 h-4" /> {job.department}
                  </span>
                  <span className="flex items-center gap-1.5 text-gray-500">
                    <MapPin className="w-4 h-4" /> {job.location}
                  </span>
                  <span className="flex items-center gap-1.5 text-gray-500 capitalize">
                    <Clock className="w-4 h-4" /> {job.type.replace("-", " ")}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2 text-sr-text-blue font-semibold shrink-0">
                View Role <ChevronRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
