import type { StatCardData, ActivityItem, InterviewItem, IntegrationItem, NotificationItem } from "@/types/dashboard";
import { Users, BriefcaseBusiness, Clock3, CalendarDays } from "@/components/icons";

export const STATS_DATA: StatCardData[] = [
  {
    label: "Total Candidates",
    value: "1,284",
    change: "+12%",
    changeNote: "+12% from last month",
    changeType: "positive",
    isDown: false,
    icon: <Users className="w-5 h-5" aria-hidden="true" />,
  },
  {
    label: "Open Positions",
    value: "24",
    change: "-2",
    changeNote: "-2 from last week",
    changeType: "negative",
    isDown: true,
    icon: <BriefcaseBusiness className="w-5 h-5" aria-hidden="true" />,
  },
  {
    label: "Avg. Time to Hire",
    value: "18 days",
    change: "-3 days",
    changeNote: "-3 days improvement",
    changeType: "positive",
    isDown: true,
    icon: <Clock3 className="w-5 h-5" aria-hidden="true" />,
  },
  {
    label: "Interviews This Week",
    value: "12",
    change: "+4",
    changeNote: "+4 from last week",
    changeType: "positive",
    isDown: false,
    icon: <CalendarDays className="w-5 h-5" aria-hidden="true" />,
  },
];

export const RECENT_ACTIVITIES: ActivityItem[] = [
  { id: "act-1", text: "Emily Rodriguez was hired for Senior UX Designer", time: "1 hour ago", dotColor: "bg-emerald-500", dotRing: "ring-emerald-50" },
  { id: "act-2", text: "James Wilson applied for Backend Engineer", time: "2 hours ago", dotColor: "bg-blue-500", dotRing: "ring-blue-50" },
  { id: "act-3", text: "Sarah Chen moved to Interview stage", time: "3 hours ago", dotColor: "bg-amber-500", dotRing: "ring-amber-50" },
  { id: "act-4", text: "Michael Park applied for Product Manager", time: "5 hours ago", dotColor: "bg-blue-500", dotRing: "ring-blue-50" },
  { id: "act-5", text: "Lisa Wang completed onboarding", time: "6 hours ago", dotColor: "bg-emerald-500", dotRing: "ring-emerald-50" },
  { id: "act-6", text: "David Kim scheduled for final interview", time: "8 hours ago", dotColor: "bg-amber-500", dotRing: "ring-amber-50" },
];

export const UPCOMING_INTERVIEWS: InterviewItem[] = [
  { id: "int-1", initials: "SC", name: "Sarah Chen", role: "Frontend Engineer", datetime: "Today, 2:00 PM", type: "Technical", avatarBg: "bg-sr-mint text-sr-text-blue", badgeStyle: "bg-blue-50 text-blue-700 border-blue-200/60" },
  { id: "int-2", initials: "MK", name: "Mike Kumar", role: "Data Scientist", datetime: "Today, 4:30 PM", type: "Culture Fit", avatarBg: "bg-purple-50 text-purple-700", badgeStyle: "bg-purple-50 text-purple-700 border-purple-200/60" },
  { id: "int-3", initials: "AJ", name: "Alex Johnson", role: "DevOps Engineer", datetime: "Tomorrow, 10:00 AM", type: "Technical", avatarBg: "bg-blue-50 text-blue-700", badgeStyle: "bg-blue-50 text-blue-700 border-blue-200/60" },
  { id: "int-4", initials: "RB", name: "Rachel Brown", role: "Product Manager", datetime: "Tomorrow, 1:00 PM", type: "Final Round", avatarBg: "bg-amber-50 text-amber-800", badgeStyle: "bg-emerald-50 text-emerald-700 border-emerald-200/60" },
];

export const INITIAL_INTEGRATIONS: IntegrationItem[] = [
  { id: "bamboohr", name: "BambooHR", description: "Sync employee data and onboarding workflows", connected: true, category: "HRIS & Onboarding" },
  { id: "workday", name: "Workday", description: "Enterprise HR management and analytics", connected: false, category: "Enterprise HCM" },
  { id: "slack", name: "Slack", description: "Get hiring notifications in your Slack channels", connected: true, category: "Communication" },
  { id: "google-calendar", name: "Google Calendar", description: "Sync interview schedules automatically", connected: true, category: "Scheduling" },
  { id: "linkedin", name: "LinkedIn Recruiter", description: "Import candidate profiles directly", connected: false, category: "Sourcing" },
  { id: "greenhouse", name: "Greenhouse", description: "ATS integration for pipeline management", connected: false, category: "Applicant Tracking" },
];

export const INITIAL_NOTIFICATIONS: NotificationItem[] = [
  { id: "new-applications", title: "New Applications", description: "Get notified when candidates apply", enabled: true },
  { id: "interview-reminders", title: "Interview Reminders", description: "Receive reminders 30 min before interviews", enabled: true },
  { id: "stage-changes", title: "Stage Changes", description: "Alerts when candidates move between stages", enabled: true },
  { id: "weekly-reports", title: "Weekly Reports", description: "Receive weekly hiring pipeline summary", enabled: false },
  { id: "team-mentions", title: "Team Mentions", description: "Notifications when you're mentioned in notes", enabled: true },
  { id: "candidate-messages", title: "Candidate Messages", description: "Alerts for new candidate messages", enabled: false },
];
