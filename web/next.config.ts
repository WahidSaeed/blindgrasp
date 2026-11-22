import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export", // static files; the Python sim server serves them (see Dockerfile)
  devIndicators: false, // keep the demo clean; compile/runtime errors still show
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
