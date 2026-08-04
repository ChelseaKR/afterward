import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Camino — California training programs and their outcomes",
  description:
    "Search California training programs and see what they cost, what happened to the people who took them, and what the jobs they lead to actually pay. Built from public data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
