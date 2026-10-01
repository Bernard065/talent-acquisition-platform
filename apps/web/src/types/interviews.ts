export type InterviewTabType = "upcoming" | "past" | "needs-feedback";

export type InterviewType = "Screening" | "Technical" | "Culture Fit" | "Final Round" | "Executive";
export type InterviewStatus = "Scheduled" | "Completed" | "Cancelled" | "Pending Feedback";

export interface InterviewParticipant {
  name: string;
  initials: string;
  avatarBg: string;
  role: string;
}

export interface Interview {
  id: string;
  candidateName: string;
  candidateInitials: string;
  candidateRole: string; // Current role of candidate or simple title
  jobTitle: string; // The job they are applying for
  date: string;
  startTime: string;
  endTime: string;
  type: InterviewType;
  status: InterviewStatus;
  interviewers: InterviewParticipant[];
  meetingLink?: string;
  isVideoCall: boolean;
}
