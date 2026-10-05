import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  const accessCode = process.env.DOCUMOUSE_AUTH_TOKEN;
  if (!accessCode) return NextResponse.next();

  const cookieToken = request.cookies.get("documouse_token")?.value;

  // Let API requests reach the backend so the login page can check a code.
  // Images and download links cannot set a bearer header, so forward the
  // configured code when their cookie is valid.
  if (request.nextUrl.pathname.startsWith("/api/")) {
    if (
      (request.method === "GET" || request.method === "HEAD") &&
      cookieToken === accessCode &&
      !request.headers.has("Authorization")
    ) {
      const headers = new Headers(request.headers);
      headers.set("Authorization", `Bearer ${accessCode}`);
      return NextResponse.next({ request: { headers } });
    }
    return NextResponse.next();
  }

  if (cookieToken === accessCode) return NextResponse.next();

  return NextResponse.redirect(new URL("/login", request.url));
}

export const config = {
  matcher: [
    "/((?!login(?:/|$)|_next/|favicon\\.ico|icon\\.svg|.*\\.(?:png|jpg|svg|ico)$).*)",
  ],
};
