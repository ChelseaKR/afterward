import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export: no server, no database, no accounts. The whole site is files, which is
  // what lets it be free to host and impossible to take down by accident.
  //
  // The bill for that is duplication, and it is large: ~9,000 pages come out as ~49,000
  // files and ~715 MiB, because every page's RSC payload is written up to four times — once
  // inline in index.html for hydration, once as index.txt for un-prefetched navigation,
  // once as __next._full.txt, and once more as the page segment for the client segment
  // cache. Three of those four are load-bearing; __next._full.txt exists only so a running
  // Next server could answer a segment-prefetch for a whole page, and nothing a browser
  // runs ever asks a static export for it.
  //
  // There is no config switch for any of this — Next 16 has no knob for the segment cache,
  // and `_full` is written unconditionally by the server renderer. So the one safe
  // reduction happens after the build instead: `npm run build` chains
  // `scripts/size-report.mjs --prune`, which measures the export by category and removes
  // __next._full.txt where it is byte-identical to the index.txt beside it. See that file
  // for the full reasoning and the interlocks.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
