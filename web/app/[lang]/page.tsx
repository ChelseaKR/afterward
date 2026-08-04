import { notFound } from "next/navigation";

import { SearchApp } from "@/components/SearchApp";
import { getSearchIndex } from "@/lib/data";
import { LANGUAGES, isLang } from "@/lib/i18n";

export function generateStaticParams() {
  return LANGUAGES.map((lang) => ({ lang }));
}

export default async function SearchPage({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();

  // Embedded at build time rather than fetched: the index is ~150 KB gzipped, and shipping
  // it with the document means search works on the first paint instead of after a round trip.
  const { programs } = getSearchIndex();
  return <SearchApp programs={programs} lang={lang} />;
}
