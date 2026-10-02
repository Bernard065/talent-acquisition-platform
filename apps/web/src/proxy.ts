import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function proxy(request: NextRequest) {
  // We only want to inject the Authorization header for our proxied API requests.
  if (request.nextUrl.pathname.startsWith("/api/v1/")) {
    const token = request.cookies.get("auth_token")?.value;

    if (token) {
      // Clone the request headers and set the Authorization header
      const requestHeaders = new Headers(request.headers);
      requestHeaders.set("Authorization", `Bearer ${token}`);

      // Forward the modified request
      return NextResponse.next({
        request: {
          headers: requestHeaders,
        },
      });
    }
  }

  return NextResponse.next();
}

// Ensure the middleware only runs for paths that need it
export const config = {
  matcher: ["/api/v1/:path*"],
};
