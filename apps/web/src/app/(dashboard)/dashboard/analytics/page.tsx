import React from "react";
import { MetricsSummary } from "@/components/analytics/metrics-summary";
import { HiringFunnel } from "@/components/analytics/hiring-funnel";
import { SourceOfHire } from "@/components/analytics/source-of-hire";
import { DetailedPipeline } from "@/components/analytics/detailed-pipeline";

export const metadata = {
  title: "Analytics | MindHire",
  description: "Hiring analytics and reports",
};

export default function AnalyticsPage() {
  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-sr-text-blue tracking-tight">Analytics & Reports</h1>
          <p className="text-sm text-gray-500 mt-1">Deep dive into your hiring performance metrics</p>
        </div>
        <div className="flex items-center gap-3">
          <select className="h-10 px-4 rounded-lg border border-gray-200 bg-white text-sm outline-none focus:border-sr-green font-medium text-gray-700">
            <option>Last 30 Days</option>
            <option>Last 90 Days</option>
            <option>This Year</option>
            <option>All Time</option>
          </select>
          <button className="h-10 px-4 rounded-lg bg-sr-mint text-sr-text-blue font-bold text-sm hover:bg-sr-green hover:text-white transition-colors flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Export
          </button>
        </div>
      </div>

      {/* Top Metrics Row */}
      <MetricsSummary />

      {/* Main Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <HiringFunnel />
        <SourceOfHire />
      </div>

      <DetailedPipeline />
    </div>
  );
}
