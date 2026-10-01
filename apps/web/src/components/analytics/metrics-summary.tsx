import React from "react";
import { ANALYTICS_METRICS } from "@/constants/analytics";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

export const MetricsSummary = () => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
      {ANALYTICS_METRICS.map((metric) => (
        <div key={metric.label} className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm flex flex-col justify-between">
          <p className="text-sm font-medium text-gray-500">{metric.label}</p>
          <div className="mt-2 flex items-end justify-between">
            <h3 className="text-3xl font-bold text-sr-text-blue">{metric.value}</h3>
            <div className={`flex items-center gap-1 text-sm font-semibold mb-1 ${
              metric.trend === "up" ? "text-emerald-600" : 
              metric.trend === "down" ? "text-red-600" : 
              "text-gray-500"
            }`}>
              {metric.trend === "up" && <TrendingUp className="w-4 h-4" />}
              {metric.trend === "down" && <TrendingDown className="w-4 h-4" />}
              {metric.trend === "neutral" && <Minus className="w-4 h-4" />}
              {metric.change}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};
