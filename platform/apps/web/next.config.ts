import type { NextConfig } from "next";

const orch = process.env.ORCH_URL ?? "http://127.0.0.1:8090";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/orch/:path*", destination: `${orch}/:path*` },
    ];
  },
};

export default nextConfig;
