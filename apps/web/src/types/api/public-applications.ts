export interface SubmitPublicApplicationRequest {
  full_name: string;
  email: string;
  phone?: string | null;
  location?: string | null;
  privacy_consent: true;
  challenge_token?: string;
}

export interface PublicApplicationAcceptedResponse {
  message: "Application received.";
}

export interface PublicApplicationResumeScanResponse {
  scan_token: string;
  expires_at: string;
}
