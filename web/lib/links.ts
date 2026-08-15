/**
 * What to say, if anything, underneath a program's provider link.
 *
 * The link itself is decided in `afterward.sources.link_check.decide` and arrives already
 * resolved — where to point, whether to link at all, and what was established on what date.
 * All that is left here is choosing the sentence, and that is worth its own tested module
 * because the wrong sentence is the failure this feature can actually cause.
 *
 * The rule, which every branch below obeys: what is printed is a statement about what this
 * project observed on a date, never about the provider. "We could not reach this page when
 * we checked on 4 August 2026" is true and checkable. "This provider's website is down" is a
 * claim about a named school, printed beside that school's performance figures, that nothing
 * here can support.
 */

import type { Copy } from "./i18n";
import type { ProviderLink } from "./types";

/**
 * The note for one provider link, or null when there is nothing established to say.
 *
 * Null in four situations, and the last one is the one worth guarding:
 *
 * - the link was never checked — a dataset built before link checking says nothing;
 * - it answered normally;
 * - it is `indeterminate` — 177 program pages, mostly hosts that dislike automated
 *   requests. A 403 is a statement about the requester, and telling a reader that a working
 *   UC Davis certificate page is unreachable would be a false claim about a real
 *   institution. Those render exactly as an unchecked link does;
 * - the notice is one this build does not recognise, which is what a dataset from a newer
 *   builder looks like. Silence is the only safe default: a fallback sentence would be
 *   chosen by code that never saw the evidence for it.
 */
export function linkNotice(t: Copy, link: ProviderLink): string | null {
  if (link.checked_on === null) return null;
  switch (link.notice) {
    case "page_unreachable":
      // `linked` is the whole difference. With a front page standing in, the reader is being
      // sent somewhere other than where the federal record pointed, and that has to be
      // admitted rather than performed quietly.
      return link.linked ? t.linkSubstituted(link.checked_on) : t.linkUnreachable(link.checked_on);
    case "domain_for_sale":
      // Measured on 10 URLs across 12 program pages: the address answered, and an
      // advertisement to buy the domain is what answered. "We could not reach it" would be
      // false and would send someone back to retry an address that is never coming back.
      return t.linkForSale(link.checked_on);
    case "redirect_unrelated":
      // A hand review found somebody else's live site at the filed address — gambling,
      // lottery and charity sites sit behind three of them. Never phrased as a claim about
      // the school: what changed hands is an address.
      return t.linkRedirectUnrelated(link.checked_on);
    case "redirect_unconfirmed":
      // The address goes somewhere else and nothing established where. This sentence is an
      // admission rather than a finding, which is why it is separate from the one above: a
      // reader deciding where to spend a year is owed the difference between "this is not
      // them" and "we do not know that this is them".
      return t.linkRedirectUnconfirmed(link.checked_on);
    default:
      return null;
  }
}
