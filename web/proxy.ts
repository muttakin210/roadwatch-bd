import { NextResponse, type NextRequest } from "next/server";

// Forwards /api/* to the FastAPI backend (PLAN §8.4), same-origin for the browser, so no CORS and the
// session cookie belongs to this site. On Vercel the backend runs elsewhere (e.g. this PC behind a tunnel):
//   ROADWATCH_API           backend base URL (default http://127.0.0.1:8000 for local dev)
//   ROADWATCH_PROXY_SECRET  shared secret; the backend refuses requests without it and only then trusts
//                           the client IP / protocol headers set here (for rate limits and Secure cookies)
const OWN = ["x-roadwatch-secret", "x-roadwatch-client-ip", "x-roadwatch-proto"];

export function proxy(request: NextRequest) {
  const api = process.env.ROADWATCH_API ?? "http://127.0.0.1:8000";
  const target = new URL(request.nextUrl.pathname + request.nextUrl.search, api);
  const headers = new Headers(request.headers);
  for (const h of OWN) headers.delete(h); // never forward client-supplied copies
  const secret = process.env.ROADWATCH_PROXY_SECRET;
  if (secret) {
    headers.set("x-roadwatch-secret", secret);
    // Vercel sets x-forwarded-for to the real client address (it replaces any client-sent value)
    const ip = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
    if (ip) headers.set("x-roadwatch-client-ip", ip);
    headers.set("x-roadwatch-proto", request.nextUrl.protocol.replace(":", ""));
  }
  return NextResponse.rewrite(target, { request: { headers } });
}

export const config = { matcher: "/api/:path*" };
