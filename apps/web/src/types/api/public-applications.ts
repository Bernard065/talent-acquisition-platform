import type { ApplicationQuestionDefinition } from "./jobs";

export interface ApplicationAnswerInput {
  question_id: string;
  answer: string;
}

export interface SubmitPublicApplicationRequest {
  full_name: string;
  email: string;
  phone?: string | null;
  location?: string | null;
  privacy_consent: true;
  challenge_token?: string;
  answers?: ApplicationAnswerInput[];
}

export interface ApplicationAnswer extends Omit<ApplicationAnswerInput, "question_id"> {
  question_id: string;
  prompt: string;
  question_type: ApplicationQuestionDefinition["question_type"];
}

export interface ApplicationAnswersResponse {
  items: ApplicationAnswer[];
}

export interface PublicApplicationAcceptedResponse {
  message: "Application received.";
}

export interface PublicApplicationResumeScanResponse {
  scan_token: string;
  expires_at: string;
}
