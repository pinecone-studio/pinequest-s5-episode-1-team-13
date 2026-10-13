import type { NextConfig } from "next";

// API-г өөрийн домэйнээр (proxy) дамжуулна: cookie first-party болно (Safari 3rd-party cookie-г хориглодог)
const BACKEND_URL = (process.env.BACKEND_URL ?? "http://localhost:8001").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
  cacheComponents: true,
  partialPrefetching: true,
  reactCompiler: true,
  // Dashboard бүхэлдээ client-side SPA (нэвтрэлт шаарддаг) тул dev-ийн auto 'instant' validation шаардлагагүй
  experimental: { instantInsights: { validationLevel: "manual-warning" } },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
