"use client";

import React from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from "recharts";
import { TRENDS_DATA } from "@/constants/analytics";

export const ApplicationsChart = () => {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 flex flex-col w-full h-100">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-sr-text-blue">Hiring Trends</h2>
          <p className="text-sm text-gray-500 mt-1">Applications vs. Interviews over time</p>
        </div>
      </div>

      <div className="flex-1 w-full h-full min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={TRENDS_DATA}
            margin={{ top: 5, right: 0, left: -20, bottom: 0 }}
          >
            <defs>
              <linearGradient id="colorApps" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#0284c7" stopOpacity={0.2} />
                <stop offset="95%" stopColor="#0284c7" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorInts" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.2} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
            <XAxis
              dataKey="date"
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#64748b', fontSize: 12 }}
              dy={10}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#64748b', fontSize: 12 }}
            />
            <Tooltip
              contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
              itemStyle={{ fontWeight: 600 }}
            />
            <Legend
              iconType="circle"
              wrapperStyle={{ paddingTop: '20px', fontSize: '13px', fontWeight: 500 }}
            />
            <Area
              type="monotone"
              dataKey="applications"
              name="Applications"
              stroke="#0284c7"
              strokeWidth={3}
              fillOpacity={1}
              fill="url(#colorApps)"
            />
            <Area
              type="monotone"
              dataKey="interviews"
              name="Interviews Scheduled"
              stroke="#10b981"
              strokeWidth={3}
              fillOpacity={1}
              fill="url(#colorInts)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
