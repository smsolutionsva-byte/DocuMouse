import type { NextConfig } from "next";

// The browser only ever talks to the Next.js origin; API calls are proxied to
// the FastAPI backend so no backend URL or key is exposed to the client.
const apiUrl = process.env.DOCUMOUSE_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  experimental: {
    // Allow the backend's 25 MB uploads plus multipart form overhead.
    proxyClientMaxBodySize: "26mb",
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
