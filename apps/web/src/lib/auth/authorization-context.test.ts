import { describe, expect, it } from "vitest";
import {
  getAuthorizationContext,
  hasAuthenticatedIdentityChanged,
} from "@/lib/auth/authorization-context";

describe("authorization cache context", () => {
  it("clears at sign-in and sign-out but not during token refresh", () => {
    expect(hasAuthenticatedIdentityChanged(null, "user-1")).toBe(true);
    expect(hasAuthenticatedIdentityChanged("user-1", "user-1")).toBe(false);
    expect(hasAuthenticatedIdentityChanged("user-1", null)).toBe(true);
  });

  it("changes when identity API roles or tenant change", () => {
    expect(
      getAuthorizationContext("subject-1", ["recruiter"], "tenant-1"),
    ).not.toBe(
      getAuthorizationContext("subject-1", ["tenant_admin"], "tenant-1"),
    );
    expect(
      getAuthorizationContext("subject-1", ["recruiter"], "tenant-1"),
    ).not.toBe(
      getAuthorizationContext("subject-1", ["recruiter"], "tenant-2"),
    );
  });
});
