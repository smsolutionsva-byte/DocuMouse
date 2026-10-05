import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  // No token configured → open access.
  if (!process.env.DOCUMOUSE_AUTH_TOKEN) {
    return NextResponse.next();
  }

  const token = request.cookies.get("documouse_token")?.value;
  if (token) {
    return NextResponse.next();
  }

  // Not authenticated — redirect to login.
  const loginUrl = new URL("/login", request.url);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: [
    /*
     * Match all paths except:
     * - /login (the login page itself)
     * - /_next/ (Next.js internals)
     * - /favicon.ico, /icon.svg, static files
     */
    "/((?!login|_next/|favicon\\.ico|icon\\.svg|.*\\.(?:png|jpg|svg|ico)$).*)",
  ],
};
