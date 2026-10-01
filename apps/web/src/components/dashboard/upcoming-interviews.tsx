import React from "react";
import { UPCOMING_INTERVIEWS } from "@/constants/dashboard";

export const UpcomingInterviews = () => {
  return (
    <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200 shadow-sm flex flex-col h-full">
      <div className="p-5 sm:p-6 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-sr-text-blue">Upcoming Interviews</h2>
          <p className="text-xs text-gray-500 mt-0.5">Scheduled for today and tomorrow</p>
        </div>
        <span className="text-xs font-semibold text-sr-text-blue bg-sr-mint px-2.5 py-1 rounded-full">
          4 Total
        </span>
      </div>
      <div className="p-5 sm:p-6 flex-1 flex flex-col">
        <div className="space-y-3">
          {UPCOMING_INTERVIEWS.map((interview) => (
            <div key={interview.id} className="p-3.5 sm:p-4 rounded-xl border border-gray-100 bg-gray-50/60 hover:bg-gray-50 hover:border-gray-200 transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-3 min-w-0">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-xs shrink-0 ${interview.avatarBg}`}>
                  {interview.initials}
                </div>
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-sr-text-blue truncate">{interview.name}</h3>
                  <p className="text-xs text-gray-500 truncate mt-0.5">{interview.role}</p>
                </div>
              </div>
              <div className="flex items-center justify-between sm:justify-end gap-2.5 pt-2 sm:pt-0 border-t border-gray-100 sm:border-t-0">
                <div className="flex items-center gap-1.5 text-xs text-gray-500 whitespace-nowrap">
                  <svg className="w-3.5 h-3.5 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>{interview.datetime}</span>
                </div>
                <span className={`inline-flex items-center text-xs font-medium px-2.5 py-0.5 rounded-full border ${interview.badgeStyle}`}>
                  {interview.type}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
