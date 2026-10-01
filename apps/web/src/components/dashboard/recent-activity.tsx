import React from "react";
import { RECENT_ACTIVITIES } from "@/constants/dashboard";

export const RecentActivity = () => {
  return (
    <div className="lg:col-span-3 bg-white rounded-xl border border-gray-200 shadow-sm flex flex-col h-full">
      <div className="p-5 sm:p-6 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-sr-text-blue">Recent Activity</h2>
          <p className="text-xs text-gray-500 mt-0.5">Real-time updates across the candidate pipeline</p>
        </div>
        <span className="text-xs font-medium text-gray-400 bg-gray-50 px-2.5 py-1 rounded-full border border-gray-200/60">
          6 items
        </span>
      </div>
      <div className="p-5 sm:p-6 flex-1">
        <div className="overflow-y-auto pr-2 divide-y divide-gray-100 h-full max-h-87.5" style={{ scrollbarWidth: "none", WebkitOverflowScrolling: "touch" }}>
          {RECENT_ACTIVITIES.map((activity) => (
            <div key={activity.id} className="py-3.5 first:pt-0 last:pb-0 flex items-start justify-between gap-4 group">
              <div className="flex items-start gap-3.5 min-w-0">
                <div className="mt-1.5 shrink-0 flex items-center justify-center">
                  <span className={`w-2.5 h-2.5 rounded-full ${activity.dotColor} ring-4 ${activity.dotRing}`} />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-800 leading-snug group-hover:text-sr-text-blue transition-colors">
                    {activity.text}
                  </p>
                  <span className="text-xs text-gray-400 sm:hidden block mt-1">{activity.time}</span>
                </div>
              </div>
              <span className="text-xs text-gray-400 whitespace-nowrap shrink-0 hidden sm:inline-block pt-0.5">
                {activity.time}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
