export type JobStatus = "active" | "paused" | "closed" | "draft";
export type JobType = "full-time" | "part-time" | "contract" | "internship";

export interface Job {
  id: string;
  title: string;
  department: string;
  location: string;
  type: JobType;
  status: JobStatus;
  applicants: number;
  newApplicants: number;
  postedDate: string;
  closingDate: string;
}

export const mockJobs: Job[] = [
  {
    id: "job-001",
    title: "Senior Frontend Engineer",
    department: "Engineering",
    location: "San Francisco, CA",
    type: "full-time",
    status: "active",
    applicants: 142,
    newApplicants: 12,
    postedDate: "2026-09-15",
    closingDate: "2026-10-30",
  },
  {
    id: "job-002",
    title: "Product Designer",
    department: "Design",
    location: "Remote",
    type: "full-time",
    status: "active",
    applicants: 89,
    newApplicants: 5,
    postedDate: "2026-09-10",
    closingDate: "2026-10-25",
  },
  {
    id: "job-003",
    title: "Data Scientist",
    department: "Engineering",
    location: "New York, NY",
    type: "full-time",
    status: "active",
    applicants: 203,
    newApplicants: 18,
    postedDate: "2026-09-01",
    closingDate: "2026-10-15",
  },
  {
    id: "job-004",
    title: "Marketing Manager",
    department: "Marketing",
    location: "Austin, TX",
    type: "full-time",
    status: "paused",
    applicants: 67,
    newApplicants: 0,
    postedDate: "2026-08-20",
    closingDate: "2026-10-10",
  },
  {
    id: "job-005",
    title: "DevOps Engineer",
    department: "Engineering",
    location: "Remote",
    type: "contract",
    status: "active",
    applicants: 54,
    newApplicants: 8,
    postedDate: "2026-09-18",
    closingDate: "2026-11-01",
  },
  {
    id: "job-006",
    title: "HR Business Partner",
    department: "People",
    location: "Chicago, IL",
    type: "full-time",
    status: "closed",
    applicants: 112,
    newApplicants: 0,
    postedDate: "2026-07-15",
    closingDate: "2026-09-01",
  },
  {
    id: "job-007",
    title: "Sales Development Representative",
    department: "Sales",
    location: "Denver, CO",
    type: "full-time",
    status: "active",
    applicants: 76,
    newApplicants: 3,
    postedDate: "2026-09-22",
    closingDate: "2026-11-05",
  },
  {
    id: "job-008",
    title: "UX Research Intern",
    department: "Design",
    location: "San Francisco, CA",
    type: "internship",
    status: "draft",
    applicants: 0,
    newApplicants: 0,
    postedDate: "2026-09-28",
    closingDate: "2026-12-01",
  },
  {
    id: "job-009",
    title: "Backend Engineer",
    department: "Engineering",
    location: "Seattle, WA",
    type: "full-time",
    status: "active",
    applicants: 165,
    newApplicants: 22,
    postedDate: "2026-09-05",
    closingDate: "2026-10-20",
  },
  {
    id: "job-010",
    title: "Content Strategist",
    department: "Marketing",
    location: "Remote",
    type: "part-time",
    status: "active",
    applicants: 38,
    newApplicants: 6,
    postedDate: "2026-09-25",
    closingDate: "2026-11-10",
  },
];
