import React from "react";
import { Button } from "@/components/ui/button";

export const metadata = {
  title: "Dashboard",
};

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto w-full h-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-sr-text-blue tracking-tight">Good morning, Bernard</h1>
          <p className="text-sm text-gray-500 mt-1">Here is what&apos;s happening with your pipeline today.</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" className="h-9 border-gray-200 text-gray-700 hover:bg-gray-50 hover:text-gray-900">
            Customize
          </Button>
          <Button variant="secondary" className="h-9 bg-sr-mint hover:bg-sr-green text-sr-text-blue hover:text-white transition-colors">
            Share Report
          </Button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Stat Card 1 */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="flex justify-between items-start mb-4">
            <span className="text-sm font-medium text-gray-500">Total Candidates</span>
            <span className="flex items-center text-xs font-medium text-green-600 bg-green-50 px-2 py-1 rounded-md">
              <svg className="w-3 h-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
              </svg>
              12%
            </span>
          </div>
          <div className="text-3xl font-bold text-sr-text-blue">2,845</div>
        </div>

        {/* Stat Card 2 */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="flex justify-between items-start mb-4">
            <span className="text-sm font-medium text-gray-500">Active Jobs</span>
            <span className="flex items-center text-xs font-medium text-green-600 bg-green-50 px-2 py-1 rounded-md">
              <svg className="w-3 h-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
              </svg>
              4%
            </span>
          </div>
          <div className="text-3xl font-bold text-sr-text-blue">34</div>
        </div>

        {/* Stat Card 3 */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="flex justify-between items-start mb-4">
            <span className="text-sm font-medium text-gray-500">Interviews Scheduled</span>
            <span className="flex items-center text-xs font-medium text-red-600 bg-red-50 px-2 py-1 rounded-md">
              <svg className="w-3 h-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
              </svg>
              2%
            </span>
          </div>
          <div className="text-3xl font-bold text-sr-text-blue">142</div>
        </div>

        {/* Stat Card 4 */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="flex justify-between items-start mb-4">
            <span className="text-sm font-medium text-gray-500">Time to Hire</span>
            <span className="flex items-center text-xs font-medium text-green-600 bg-green-50 px-2 py-1 rounded-md">
              <svg className="w-3 h-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
              </svg>
              18%
            </span>
          </div>
          <div className="text-3xl font-bold text-sr-text-blue">14 days</div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 min-h-[400px] bg-white rounded-xl border border-gray-200 shadow-sm flex items-center justify-center border-dashed">
        <div className="text-center">
          <div className="mx-auto w-16 h-16 bg-gray-50 rounded-full flex items-center justify-center mb-4">
            <svg className="w-8 h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-sr-text-blue">Pipeline View Coming Soon</h3>
          <p className="text-sm text-gray-500 mt-2 max-w-sm mx-auto">
            This area will contain the fully interactive Kanban board for tracking candidates across hiring stages.
          </p>
        </div>
      </div>
    </div>
  );
}
