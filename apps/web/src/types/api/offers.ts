export type OfferStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "sent"
  | "accepted"
  | "declined"
  | "expired"
  | "cancelled";

export type OfferPayPeriod = "monthly" | "annually";

export interface CreateOfferRequest {
  currency: string;
  base_salary: string | number;
  pay_period: OfferPayPeriod;
  bonus_amount?: string | number | null;
  equity_summary?: string | null;
  proposed_start_date: string;
  expires_at: string;
}

export interface ExpectedOfferVersionRequest {
  expected_offer_version: number;
}

export interface OfferResponse {
  id: string;
  application_id: string;
  status: OfferStatus;
  currency: string;
  base_salary: string | number;
  pay_period: OfferPayPeriod;
  bonus_amount: string | number | null;
  equity_summary: string | null;
  proposed_start_date: string;
  expires_at: string;
  approval_requested_at: string | null;
  approved_at: string | null;
  sent_at: string | null;
  accepted_at: string | null;
  declined_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
}
