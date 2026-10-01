import type { Interview } from "@/types/interviews";

export const MOCK_INTERVIEWS: Interview[] = [
  {
    id: "int-001",
    candidateName: "Sarah Chen",
    candidateInitials: "SC",
    candidateRole: "Senior React Developer",
    jobTitle: "Frontend Engineer",
    date: "Today",
    startTime: "2:00 PM",
    endTime: "3:00 PM",
    type: "Technical",
    status: "Scheduled",
    isVideoCall: true,
    meetingLink: "https://meet.google.com/abc-defg-hij",
    interviewers: [
      { name: "Bernard Bebeni", initials: "BB", avatarBg: "bg-sr-mint text-sr-text-blue", role: "Hiring Manager" },
      { name: "Alex Kumar", initials: "AK", avatarBg: "bg-blue-100 text-blue-700", role: "Lead Engineer" }
    ]
  },
  {
    id: "int-002",
    candidateName: "Michael Park",
    candidateInitials: "MP",
    candidateRole: "Product Manager",
    jobTitle: "Senior Product Manager",
    date: "Today",
    startTime: "4:30 PM",
    endTime: "5:00 PM",
    type: "Culture Fit",
    status: "Scheduled",
    isVideoCall: true,
    meetingLink: "https://zoom.us/j/123456789",
    interviewers: [
      { name: "Bernard Bebeni", initials: "BB", avatarBg: "bg-sr-mint text-sr-text-blue", role: "Hiring Manager" },
      { name: "Jessica Alba", initials: "JA", avatarBg: "bg-purple-100 text-purple-700", role: "VP of Product" }
    ]
  },
  {
    id: "int-003",
    candidateName: "Elena Rodriguez",
    candidateInitials: "ER",
    candidateRole: "UX Designer",
    jobTitle: "Product Designer",
    date: "Tomorrow",
    startTime: "10:00 AM",
    endTime: "11:30 AM",
    type: "Final Round",
    status: "Scheduled",
    isVideoCall: false,
    interviewers: [
      { name: "Design Team", initials: "DT", avatarBg: "bg-amber-100 text-amber-700", role: "Panel" }
    ]
  },
  {
    id: "int-004",
    candidateName: "David Kim",
    candidateInitials: "DK",
    candidateRole: "Backend Engineer",
    jobTitle: "Backend Engineer",
    date: "Yesterday",
    startTime: "1:00 PM",
    endTime: "2:00 PM",
    type: "Technical",
    status: "Pending Feedback",
    isVideoCall: true,
    interviewers: [
      { name: "Bernard Bebeni", initials: "BB", avatarBg: "bg-sr-mint text-sr-text-blue", role: "Hiring Manager" },
      { name: "Sam Smith", initials: "SS", avatarBg: "bg-emerald-100 text-emerald-700", role: "Backend Lead" }
    ]
  },
  {
    id: "int-005",
    candidateName: "Lisa Wang",
    candidateInitials: "LW",
    candidateRole: "Data Scientist",
    jobTitle: "Lead Data Scientist",
    date: "Oct 12, 2026",
    startTime: "11:00 AM",
    endTime: "11:45 AM",
    type: "Screening",
    status: "Completed",
    isVideoCall: true,
    interviewers: [
      { name: "Bernard Bebeni", initials: "BB", avatarBg: "bg-sr-mint text-sr-text-blue", role: "Recruiter" }
    ]
  }
];
