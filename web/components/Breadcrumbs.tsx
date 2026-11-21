import Link from "next/link";

import { dict, type Lang } from "@/lib/i18n";
import { SITE_URL } from "@/lib/site";

/**
 * "Afterward › Providers › {provider}" at the top of program, occupation and provider pages.
 *
 * It replaces "← Back to search". Almost every reader of these pages arrived on them directly,
 * from an assistant or a search result, so "back" named a place they had never been. The
 * trail names where the page sits instead. A program's trail runs through its provider, the
 * one parent every program has; through its first occupation it would often have named a
 * broad code ("Health Specialties Teachers, Postsecondary") the program barely touches.
 *
 * The same names go out as BreadcrumbList JSON-LD, so the trail a search engine reads is the
 * trail the reader sees, from one list.
 *
 * Accessibility: a `nav` with its own name, an ordered list, and `aria-current="page"` on
 * the last item only when that item is this page. On a program page the last item is the
 * provider, a parent, and is a link like the others. The separators are drawn by CSS, so a
 * screen reader does not read them out.
 */
export interface Crumb {
  name: string;
  /** Site-relative, with the language prefix and the trailing slash: `/en/providers/`. */
  href: string;
  /** For a name the feed publishes in English only, on a Spanish page. */
  lang?: "en";
}

export function breadcrumbJsonLd(trail: readonly Crumb[]): string {
  const data = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: trail.map((crumb, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: crumb.name,
      item: `${SITE_URL}${crumb.href}`,
    })),
  };
  // Escaped so a provider name can never close the script element it sits in.
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

export function Breadcrumbs({
  lang,
  trail,
  current,
}: {
  lang: Lang;
  trail: readonly Crumb[];
  /** True when the last crumb is the page being read rather than its parent. */
  current: boolean;
}) {
  const t = dict(lang);
  const last = trail.length - 1;

  return (
    <>
      <nav className="breadcrumbs" aria-label={t.breadcrumbLabel}>
        <ol>
          {trail.map((crumb, index) => (
            <li key={crumb.href}>
              {current && index === last ? (
                <span aria-current="page" lang={crumb.lang}>
                  {crumb.name}
                </span>
              ) : (
                // Unprefetched, for the reason the masthead links are: this sits at the top
                // of thousands of pages and two of its targets are the heaviest indexes.
                <Link href={crumb.href} prefetch={false} lang={crumb.lang}>
                  {crumb.name}
                </Link>
              )}
            </li>
          ))}
        </ol>
      </nav>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: breadcrumbJsonLd(trail) }}
      />
    </>
  );
}
