import { notFound } from "next/navigation";

import { AskPanel } from "@/components/AskPanel";
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
  const { programs, altTitles } = getSearchIndex();
  return (
    <>
      <SearchApp programs={programs} altTitles={altTitles} lang={lang} />
      {/*
        * The assistant, below the search: "I work in a warehouse in Fresno and want something
        * that pays more" is a question the filter form cannot take. Renders nothing unless this
        * build has a service (ADR 0003); with one, nothing leaves the page until asked.
        */}
      <div className="shell">
        <AskPanel lang={lang} />
      </div>
    </>
  );
}
