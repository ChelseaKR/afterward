import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { AskPanel } from "@/components/AskPanel";
import { SearchApp } from "@/components/SearchApp";
import { getSearchIndex } from "@/lib/data";
import { LANGUAGES, isLang } from "@/lib/i18n";
import { homeDescription, homeTitle, pageMetadata } from "@/lib/site";

export function generateStaticParams() {
  return LANGUAGES.map((lang) => ({ lang }));
}

/**
 * There was no `generateMetadata` here, because there was nothing this page needed to say
 * that `app/[lang]/layout.tsx` was not already saying for it: it is `/{lang}/`, the layout
 * describes `/{lang}/`, and the title and card it inherited were correct.
 *
 * That stopped being true once a page's metadata had to include its own URL. The layout
 * cannot declare a canonical, for the reason recorded at length in it -- every one of the
 * ~9,000 pages beneath it would inherit the same one -- so the only file that can say
 * `/{lang}/` is canonical and `/{other}/` is its twin is this one. `homeTitle` and
 * `homeDescription` are the layout's own strings, imported rather than repeated, so
 * restating the words in order to add the URL cannot change the words.
 *
 * This is also the page the `x-default` on every other page in the site points at, by way of
 * `DEFAULT_LANG`: it had better be the page that names itself canonical.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ lang: string }>;
}): Promise<Metadata> {
  const { lang } = await params;
  if (!isLang(lang)) return {};

  return pageMetadata(lang, "", homeTitle(lang), homeDescription(lang));
}

export default async function SearchPage({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();

  // Embedded at build time rather than fetched: the index is ~150 KB gzipped, and shipping
  // it with the document means search works on the first paint instead of after a round trip.
  const { programs, altTitles, esTitles } = getSearchIndex();
  return (
    <>
      <SearchApp programs={programs} altTitles={altTitles} esTitles={esTitles} lang={lang} />
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
