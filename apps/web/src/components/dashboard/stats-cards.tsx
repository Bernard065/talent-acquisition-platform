import React from "react";
import { STATS_DATA } from "@/constants/dashboard";

export const StatsCards = () => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 sm:gap-6">
      {STATS_DATA.map((stat) => (
        <div key={stat.label} className="bg-white rounded-xl border border-gray-200 p-5 sm:p-6 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <div className="w-10 h-10 rounded-lg bg-sr-mint/50 text-sr-text-blue flex items-center justify-center shrink-0">
              {stat.icon}
            </div>
            <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${stat.changeType === "positive" ? "text-emerald-700 bg-emerald-50 border border-emerald-100" : "text-red-700 bg-red-50 border border-red-100"}`}>
              {stat.isDown ? (
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                </svg>
              ) : (
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
                </svg>
              )}
              {stat.change}
            </span>
          </div>
          <div className="mt-4">
            <div className="text-3xl font-bold text-sr-text-blue tracking-tight">{stat.value}</div>
            <p className="text-sm font-medium text-gray-500 mt-1">{stat.label}</p>
          </div>
          <div className="mt-3 pt-3 border-t border-gray-100 flex items-center text-xs text-gray-400">
            <span>{stat.changeNote}</span>
          </div>
        </div>
      ))}
    </div>
  );
};
