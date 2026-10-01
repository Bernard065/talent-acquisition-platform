import React from "react";
import { HIRING_FUNNEL } from "@/constants/analytics";

export const HiringFunnel = () => {
  const maxCount = Math.max(...HIRING_FUNNEL.map(s => s.count));

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 flex flex-col h-full">
      <div>
        <h2 className="text-lg font-bold text-sr-text-blue">Hiring Funnel</h2>
        <p className="text-sm text-gray-500 mt-1">Conversion rates across your hiring stages</p>
      </div>

      <div className="mt-8 flex-1 flex flex-col justify-center space-y-4">
        {HIRING_FUNNEL.map((stage, index) => {
          // Calculate a minimum width to keep it visible, but scale based on the previous stage to show a funnel effect
          // Or just scale relative to maxCount but with a logarithmic/custom feel so small numbers don't disappear.
          const widthPercent = Math.max(15, (stage.count / maxCount) * 100);
          
          return (
            <div key={stage.stage} className="relative group">
              {/* Dropoff Indicator (skip first item) */}
              {index > 0 && (
                <div className="absolute -top-3 right-0 sm:right-4 text-[10px] font-bold text-gray-400 bg-gray-50 px-2 rounded-full border border-gray-100 z-10">
                  -{stage.dropoffPercentage}%
                </div>
              )}

              <div className="flex items-center gap-4">
                <div className="w-32 sm:w-40 shrink-0 text-right">
                  <span className="text-sm font-semibold text-gray-700">{stage.stage}</span>
                </div>
                
                <div className="flex-1 bg-gray-50 rounded-r-lg h-10 flex items-center relative overflow-hidden">
                  <div 
                    className={`h-full border-r-2 flex items-center px-3 transition-all duration-1000 ease-out ${stage.color}`}
                    style={{ width: `${widthPercent}%` }}
                  >
                    <span className="text-xs font-bold">{stage.count.toLocaleString()}</span>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
