/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    // Next.js's proxy layer (used for our /api/* rewrite below) truncates
    // any request body past this size - it's a streaming cutoff, not an
    // in-memory buffer, so raising it is safe even for multi-GB movie files.
    // Default is 10MB, which a real video upload blows past immediately.
    proxyClientMaxBodySize: "20gb",
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        // Server-side only - the browser never talks to the FastAPI backend
        // directly, only to this Next.js server, which forwards here. That
        // means only this port needs to be reachable (LAN/tunnel/etc.); the
        // backend stays localhost-only regardless of how this is exposed.
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
