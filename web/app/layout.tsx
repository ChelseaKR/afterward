import type { Metadata } from "next";

import { ROOT_DESCRIPTION, ROOT_TITLE } from "@/lib/site";

import "./globals.css";

/**
 * Site-wide defaults. Everything under `/[lang]/` overrides both from the dictionary, so in
 * practice these describe the language chooser at the root and act as the backstop for
 * anything that forgets to.
 *
 * Deliberately no `openGraph` or `twitter` here. This is the root layout, so it is an
 * ancestor of all ~9,000 pages and anything set here reaches every one of them -- which is
 * the hazard `app/[lang]/layout.tsx` records at length. Share tags belong either on the root
 * page, which has no descendants, or in the language layout, which knows which language it
 * is describing.
 */
export const metadata: Metadata = {
  title: ROOT_TITLE,
  description: ROOT_DESCRIPTION,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
