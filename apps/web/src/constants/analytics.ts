import type { AnalyticsMetric, FunnelStage, SourceMetric } from "@/types/analytics";

export const ANALYTICS_METRICS: AnalyticsMetric[] = [
  { label: "Total Candidates", value: "3,284", change: "+15.2%", trend: "up" },
  { label: "Time to Hire", value: "18 Days", change: "-2 Days", trend: "up" }, // Faster is better
  { label: "Offer Acceptance", value: "86%", change: "+4.1%", trend: "up" },
  { label: "Cost per Hire", value: "$1,250", change: "+$50", trend: "down" }, // Higher is worse
];

export const HIRING_FUNNEL: FunnelStage[] = [
  { stage: "Applications", count: 3284, dropoffPercentage: 0, color: "bg-blue-100 border-blue-200 text-blue-700" },
  { stage: "Screened", count: 852, dropoffPercentage: 74, color: "bg-indigo-100 border-indigo-200 text-indigo-700" },
  { stage: "Interviewed", count: 215, dropoffPercentage: 75, color: "bg-purple-100 border-purple-200 text-purple-700" },
  { stage: "Offers Extended", count: 65, dropoffPercentage: 70, color: "bg-amber-100 border-amber-200 text-amber-700" },
  { stage: "Hired", count: 56, dropoffPercentage: 14, color: "bg-emerald-100 border-emerald-200 text-emerald-700" },
];

export const SOURCE_OF_HIRE: SourceMetric[] = [
  { source: "LinkedIn", count: 24, percentage: 42 },
  { source: "Referrals", count: 18, percentage: 32 },
  { source: "Company Careers Page", count: 10, percentage: 18 },
  { source: "Indeed", count: 3, percentage: 5 },
  { source: "Other", count: 1, percentage: 3 },
];

export const PIPELINE_REPORTS: import("@/types/analytics").PipelineReport[] = [
  {
    jobId: "job-1",
    jobTitle: "Senior Frontend Engineer",
    candidates: [
      { id: "c-1", name: "Sarah Chen", initials: "SC", stage: "Technical Interview", timeInStage: "2 days", matchScore: 94, status: "On Track" },
      { id: "c-2", name: "Mike Kumar", initials: "MK", stage: "Final Round", timeInStage: "5 days", matchScore: 88, status: "Slipping" },
      { id: "c-3", name: "Elena Rodriguez", initials: "ER", stage: "Screening", timeInStage: "1 day", matchScore: 91, status: "On Track" },
      { id: "c-4", name: "David Kim", initials: "DK", stage: "Offer Extended", timeInStage: "8 days", matchScore: 96, status: "Stalled" },
    ]
  },
  {
    jobId: "job-2",
    jobTitle: "Product Manager",
    candidates: [
      { id: "c-5", name: "Jessica Alba", initials: "JA", stage: "Culture Fit", timeInStage: "3 days", matchScore: 89, status: "On Track" },
      { id: "c-6", name: "Tom Holland", initials: "TH", stage: "Screening", timeInStage: "4 days", matchScore: 82, status: "Slipping" },
    ]
  }
];

export const TRENDS_DATA: import("@/types/analytics").TimeSeriesData[] = [
  { date: "Oct 1", applications: 120, interviews: 15, offers: 2 },
  { date: "Oct 2", applications: 132, interviews: 18, offers: 3 },
  { date: "Oct 3", applications: 101, interviews: 12, offers: 1 },
  { date: "Oct 4", applications: 145, interviews: 22, offers: 4 },
  { date: "Oct 5", applications: 190, interviews: 25, offers: 6 },
  { date: "Oct 6", applications: 210, interviews: 30, offers: 5 },
  { date: "Oct 7", applications: 175, interviews: 28, offers: 8 },
  { date: "Oct 8", applications: 188, interviews: 35, offers: 7 },
  { date: "Oct 9", applications: 220, interviews: 40, offers: 9 },
  { date: "Oct 10", applications: 245, interviews: 42, offers: 12 },
  { date: "Oct 11", applications: 270, interviews: 48, offers: 15 },
  { date: "Oct 12", applications: 295, interviews: 55, offers: 18 },
  { date: "Oct 13", applications: 310, interviews: 60, offers: 20 },
  { date: "Oct 14", applications: 335, interviews: 68, offers: 22 },
];
