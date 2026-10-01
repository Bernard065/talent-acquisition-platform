export interface AnalyticsMetric {
  label: string;
  value: string;
  change: string;
  trend: "up" | "down" | "neutral";
}

export interface FunnelStage {
  stage: string;
  count: number;
  dropoffPercentage: number;
  color: string;
}

export interface SourceMetric {
  source: string;
  count: number;
  percentage: number;
}

export interface PipelineCandidate {
  id: string;
  name: string;
  initials: string;
  stage: string;
  timeInStage: string;
  matchScore: number;
  status: "On Track" | "Slipping" | "Stalled";
}

export interface PipelineReport {
  jobId: string;
  jobTitle: string;
  candidates: PipelineCandidate[];
}
