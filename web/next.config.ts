import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export: no server, no database, no accounts. The whole site is files, which is
  // what lets it be free to host and impossible to take down by accident.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
