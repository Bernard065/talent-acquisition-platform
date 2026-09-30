export type CandidateStage = "new" | "screening" | "interview" | "offer" | "hired" | "rejected";

export interface Candidate {
  id: string;
  name: string;
  email: string;
  role: string;
  department: string;
  stage: CandidateStage;
  matchScore: number; // 0-100
  appliedDate: string;
  avatarUrl?: string;
  initials: string;
}

export const mockCandidates: Candidate[] = [
  {
    id: "cand-001",
    name: "Alex Johnson",
    email: "alex.j@example.com",
    role: "Senior Frontend Engineer",
    department: "Engineering",
    stage: "interview",
    matchScore: 92,
    appliedDate: "2026-09-28T10:00:00Z",
    initials: "AJ",
  },
  {
    id: "cand-002",
    name: "Samantha Lee",
    email: "sam.lee@example.com",
    role: "Product Designer",
    department: "Design",
    stage: "screening",
    matchScore: 85,
    appliedDate: "2026-09-29T14:30:00Z",
    initials: "SL",
  },
  {
    id: "cand-003",
    name: "Michael Chen",
    email: "m.chen@example.com",
    role: "Data Scientist",
    department: "Engineering",
    stage: "offer",
    matchScore: 98,
    appliedDate: "2026-09-15T09:15:00Z",
    initials: "MC",
  },
  {
    id: "cand-004",
    name: "Emily Davis",
    email: "emily.d@example.com",
    role: "Marketing Manager",
    department: "Marketing",
    stage: "new",
    matchScore: 76,
    appliedDate: "2026-09-30T08:45:00Z",
    initials: "ED",
  },
  {
    id: "cand-005",
    name: "David Wilson",
    email: "dwilson@example.com",
    role: "DevOps Engineer",
    department: "Engineering",
    stage: "rejected",
    matchScore: 65,
    appliedDate: "2026-09-10T11:20:00Z",
    initials: "DW",
  },
  {
    id: "cand-006",
    name: "Jessica Taylor",
    email: "j.taylor@example.com",
    role: "HR Business Partner",
    department: "People",
    stage: "hired",
    matchScore: 95,
    appliedDate: "2026-08-20T16:00:00Z",
    initials: "JT",
  },
  {
    id: "cand-007",
    name: "Robert Martinez",
    email: "robert.m@example.com",
    role: "Sales Development Rep",
    department: "Sales",
    stage: "screening",
    matchScore: 82,
    appliedDate: "2026-09-27T13:10:00Z",
    initials: "RM",
  },
  {
    id: "cand-008",
    name: "Amanda White",
    email: "awhite@example.com",
    role: "Senior Frontend Engineer",
    department: "Engineering",
    stage: "new",
    matchScore: 88,
    appliedDate: "2026-09-30T09:30:00Z",
    initials: "AW",
  },
  {
    id: "cand-009",
    name: "Christopher Moore",
    email: "c.moore@example.com",
    role: "Product Designer",
    department: "Design",
    stage: "interview",
    matchScore: 91,
    appliedDate: "2026-09-22T10:45:00Z",
    initials: "CM",
  },
  {
    id: "cand-010",
    name: "Sarah Anderson",
    email: "sarah.a@example.com",
    role: "Data Scientist",
    department: "Engineering",
    stage: "screening",
    matchScore: 79,
    appliedDate: "2026-09-28T15:20:00Z",
    initials: "SA",
  },
];
