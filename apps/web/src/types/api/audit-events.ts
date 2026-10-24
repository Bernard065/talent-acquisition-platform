export interface AuditEvent {
  id: string;
  actor_display_name: string | null;
  actor_subject: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  request_id: string;
  occurred_at: string;
}

export interface AuditEventListResponse {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditEventSearchParams {
  action?: string;
  entity_type?: string;
  actor?: string;
  occurred_from?: string;
  occurred_to?: string;
  limit?: number;
  offset?: number;
}
