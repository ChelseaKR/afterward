import Link from "next/link";

import { dict, type Lang } from "@/lib/i18n";

/**
 * The "Before you decide" box under a program page's cost, length and outcome strip.
 *
 * Almost everyone who reads a program page arrived on it directly, read it, and left: no
 * program page linked to another program, and the section on who may pay started about 4,900
 * pixels down on a 390-pixel phone. This puts the reader's next steps on the first screen as
 * plain links. It makes no claim of its own. Each link goes somewhere the site already says
 * something: the list of other programs for the same jobs nearby, the funding section on this
 * page, the provider's page, the provider's own site.
 *
 * Every link is conditional on its destination existing, and the box is not rendered at all
 * when none does. A heading over an empty list would be a promise of next steps with none in
 * it.
 *
 * Not sticky and not a dialog: it sits in the document flow, so it can never cover the
 * control that has keyboard focus (WCAG 2.4.11).
 */
export interface NextStepsProps {
  lang: Lang;
  /**
   * The program's city, when the page lists at least one other program for the same jobs in
   * the same area under `id="nearby"`. Null otherwise: a link promising programs nearby must
   * not lead to a sentence saying there are none.
   */
  nearby: { city: string } | null;
  /** True when the page renders its funding section, which carries `id="funding"`. */
  funding: boolean;
  /** The provider's page on this site, and its display name, or null when unnamed. */
  provider: { href: string; name: string } | null;
  /**
   * The provider's own site, exactly as the page's provider link renders it, or null when
   * there is nothing linkable. The label is the existing "Provider's website" string or its
   * home-page variant, so the box says the same thing as the link further down.
   */
  website: { href: string; label: string } | null;
}

export function NextSteps({ lang, nearby, funding, provider, website }: NextStepsProps) {
  const t = dict(lang);
  if (nearby === null && !funding && provider === null && website === null) return null;

  return (
    <nav className="next-steps" aria-labelledby="next-steps-heading">
      <h2 id="next-steps-heading">{t.nextStepsHeading}</h2>
      <ul>
        {nearby !== null && (
          <li>
            <a href="#nearby">{t.nextStepsNearby(nearby.city)}</a>
          </li>
        )}
        {funding && (
          <li>
            <a href="#funding">{t.nextStepsFunding}</a>
          </li>
        )}
        {provider !== null && (
          <li>
            <Link href={provider.href}>{t.nextStepsProviderPrograms(provider.name)}</Link>
          </li>
        )}
        {website !== null && (
          <li>
            <a href={website.href} rel="nofollow noopener noreferrer" target="_blank">
              {website.label}
            </a>
          </li>
        )}
      </ul>
    </nav>
  );
}
