import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // Next's CLI type-check mode loses TypeScript's short --showConfig output in
  // this project. The CI workflow runs tsc directly; build uses the stable API.
  experimental: {
    useTypeScriptCli: false,
  },
};

export default nextConfig;
