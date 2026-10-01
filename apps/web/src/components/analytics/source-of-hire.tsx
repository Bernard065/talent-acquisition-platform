import React from "react";
import { SOURCE_OF_HIRE } from "@/constants/analytics";

export const SourceOfHire = () => {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 flex flex-col h-full">
      <div>
        <h2 className="text-lg font-bold text-sr-text-blue">Source of Hire</h2>
        <p className="text-sm text-gray-500 mt-1">Where your best candidates are coming from</p>
      </div>

      <div className="mt-8 flex-1 flex flex-col justify-center gap-5">
        {SOURCE_OF_HIRE.map((source, index) => {
          // Cycle through some nice UI colors for the bars
          const colors = [
            "bg-blue-500",
            "bg-emerald-500",
            "bg-purple-500",
            "bg-amber-500",
            "bg-gray-400"
          ];
          const colorClass = colors[index % colors.length];

          return (
            <div key={source.source}>
              <div className="flex justify-between text-sm mb-1.5">
                <span className="font-medium text-gray-700">{source.source}</span>
                <span className="font-bold text-gray-900">{source.percentage}% <span className="text-gray-400 font-normal ml-1">({source.count})</span></span>
              </div>
              <div className="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden">
                <div 
                  className={`h-2.5 rounded-full ${colorClass} transition-all duration-1000 ease-out`}
                  style={{ width: `${source.percentage}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
