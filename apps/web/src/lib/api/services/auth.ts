import { get, type RequestOptions } from "../client";
import type { CurrentIdentityResponse } from "@/types/api";

/**
 * Retrieve the verified identity and roles of the currently authenticated caller.
 */
export async function getCurrentIdentity(
  options?: RequestOptions,
): Promise<CurrentIdentityResponse> {
  return get<CurrentIdentityResponse>("/identity/me", options);
}
