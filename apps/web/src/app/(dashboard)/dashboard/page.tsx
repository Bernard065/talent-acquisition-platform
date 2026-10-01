import React from "react";
import { StatsCards } from "@/components/dashboard/stats-cards";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { UpcomingInterviews } from "@/components/dashboard/upcoming-interviews";

export const metadata = {
  title: "Dashboard | MindHire",
  description: "Recruiter overview and hiring pipeline metrics",
};

export default function DashboardPage() {
  const todayFormatted = new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date());

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto w-full">
      {/* 1. Welcome Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-sr-text-blue tracking-tight">
            Welcome back, Bernard
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Here&apos;s what&apos;s happening with your hiring pipeline
          </p>
        </div>
        <div className="inline-flex items-center gap-2 self-start sm:self-auto bg-white px-3.5 py-2 rounded-xl border border-gray-200 shadow-sm text-xs sm:text-sm font-medium text-gray-600">
          <svg className="w-4 h-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          <span>{todayFormatted}</span>
        </div>
      </div>

      {/* 2. Stats Cards Row */}
      <StatsCards />

      {/* 3. Two-Column Layout Below Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <RecentActivity />
        <UpcomingInterviews />
      </div>
    </div>
  );
}
