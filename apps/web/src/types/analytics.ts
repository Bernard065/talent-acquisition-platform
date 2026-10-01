export interface AnalyticsMetric {
  label: string;
  value: string;
  change: string;
  trend: "up" | "down" | "neutral";
}

export interface FunnelStage {
  stage: string;
  count: number;
  dropoffPercentage: number; // percentage dropped off from previous stage
  color: string;
}

export interface SourceMetric {
  source: string;
  count: number;
  percentage: number;
}
