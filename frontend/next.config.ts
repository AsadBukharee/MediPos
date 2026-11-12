import type { NextConfig } from "next";

// Vercel builds this app natively (Root Directory = `frontend`) and needs no output mode.
// The Docker image needs the self-contained server bundle, so its build sets DOCKER_BUILD=1.
const nextConfig: NextConfig = {
  ...(process.env.DOCKER_BUILD === "1" ? { output: "standalone" as const } : {}),
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
