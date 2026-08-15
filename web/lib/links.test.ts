import { describe, expect, it } from "vitest";

import { dict } from "./i18n";
import { linkNotice } from "./links";
import type { ProviderLink } from "./types";

const en = dict("en");
const es = dict("es");

function link(over: Partial<ProviderLink> = {}): ProviderLink {
  return {
    url: "https://example.edu/programs/welding",
    href: "https://example.edu/programs/welding",
    linked: true,
    label: "program_page",
    verdict: "alive",
    reason: "ok",
    checked_on: "2026-08-04",
    notice: null,
    substitution: null,
    redirect: null,
    ...over,
  };
}

/**
 * The property defended here is the one whose failure is invisible: a note appearing beside
 * a provider whose site is perfectly fine. That is a false statement about a named school,
 * printed next to its performance figures, and the reader has no way to tell it from a true
 * one — so silence is the default and every sentence has to be earned.
 */
describe("when nothing has been established", () => {
  it("says nothing about a link nobody checked", () => {
    expect(linkNotice(en, link({ verdict: null, reason: null, checked_on: null }))).toBeNull();
  });

  it("says nothing about a link that answered", () => {
    expect(linkNotice(en, link())).toBeNull();
  });

  it("says nothing about the 177 pages that could not be judged", () => {
    // Mostly hosts that refuse automated requests. A 403 is a statement about the requester.
    for (const reason of ["forbidden", "tls_failure", "timeout", "server_error"]) {
      expect(linkNotice(en, link({ verdict: "indeterminate", reason }))).toBeNull();
    }
  });

  it("says nothing for a notice this build does not recognise", () => {
    // What a dataset written by a newer builder looks like. Guessing at a sentence for
    // evidence this code has never seen is worse than staying quiet.
    const future = link({ notice: "something_added_later" as never, verdict: "dead" });
    expect(linkNotice(en, future)).toBeNull();
  });

  it("says nothing when there is no date to stand behind", () => {
    // A verdict has a shelf life, so a sentence without one is not publishable.
    expect(linkNotice(en, link({ notice: "page_unreachable", checked_on: null }))).toBeNull();
  });
});

describe("when the filed page was not there", () => {
  const dead = link({ verdict: "dead", reason: "not_found", notice: "page_unreachable" });

  it("admits the substitution rather than performing it quietly", () => {
    const note = linkNotice(en, { ...dead, linked: true, href: "https://example.edu/" });
    expect(note).toContain("home page");
    expect(note).toContain("2026-08-04");
  });

  it("says only that we could not reach it when nothing stood in", () => {
    const note = linkNotice(en, { ...dead, linked: false, href: null });
    expect(note).toContain("could not reach");
    expect(note).toContain("2026-08-04");
  });

  it("treats a soft 404 exactly as the 404 it is", () => {
    // A 200 whose own title said "Page Not Found". The reader's situation is identical, so
    // the sentence is too.
    const soft = link({ verdict: "dead", reason: "soft_not_found", notice: "page_unreachable" });
    expect(linkNotice(en, { ...soft, linked: false, href: null })).toBe(
      linkNotice(en, { ...dead, linked: false, href: null }),
    );
  });
});

describe("when the address turned out to be for sale", () => {
  const sold = link({
    verdict: "dead",
    reason: "domain_for_sale",
    notice: "domain_for_sale",
    linked: false,
    href: null,
  });

  it("says what the address did, dated", () => {
    expect(linkNotice(en, sold)).toContain("for sale");
    expect(linkNotice(en, sold)).toContain("2026-08-04");
  });

  it("does not claim we failed to reach it, because we did not fail", () => {
    // The address answered. An advertisement is what answered. Telling a reader we could not
    // reach it invites them to try again, which is the one thing that cannot work.
    expect(linkNotice(en, sold)).not.toContain("could not reach");
    expect(linkNotice(en, sold)).not.toBe(linkNotice(en, { ...sold, notice: "page_unreachable" }));
  });

  it("does not say the school has closed", () => {
    // A lapsed domain is not a closed school. The adult centres behind the largest dead
    // domain in this dataset are open and teaching at a different address.
    for (const forbidden of ["closed", "out of business", "no longer operates", "shut"]) {
      expect(linkNotice(en, sold)?.toLowerCase()).not.toContain(forbidden);
    }
  });

  it("tells the reader what to do instead", () => {
    expect(linkNotice(en, sold)).toContain("name");
    expect(linkNotice(es, sold)).toContain("nombre");
  });
});

describe("when the address now answers from somewhere else", () => {
  const offsite = (
    notice: "redirect_unrelated" | "redirect_unconfirmed",
    redirect: "unrelated" | "unresolved",
  ) =>
    link({
      verdict: "alive",
      reason: "redirected_offsite",
      notice,
      redirect,
      linked: false,
      href: null,
    });

  const hijacked = offsite("redirect_unrelated", "unrelated");
  const unconfirmed = offsite("redirect_unconfirmed", "unresolved");

  it("says the destination is not the provider's, dated", () => {
    // Four program pages linked giligiacollege.com, an Indonesian gambling site, until the
    // 2026-08-15 review. This is the sentence that replaced the link.
    expect(linkNotice(en, hijacked)).toContain("unrelated");
    expect(linkNotice(en, hijacked)).toContain("2026-08-04");
  });

  it("admits uncertainty rather than borrowing the certain sentence", () => {
    // The difference a reader deciding where to spend a year is owed: "this is not them" and
    // "we do not know that this is them" are different claims and must read differently.
    expect(linkNotice(en, unconfirmed)).toContain("could not confirm");
    expect(linkNotice(en, unconfirmed)).not.toBe(linkNotice(en, hijacked));
  });

  it("never tells a reader we could not reach the address, because we reached it", () => {
    for (const each of [hijacked, unconfirmed]) {
      expect(linkNotice(en, each)).not.toContain("could not reach");
      expect(linkNotice(en, each)).not.toBe(
        linkNotice(en, { ...each, notice: "page_unreachable" }),
      );
    }
  });

  it("says nothing about the school itself", () => {
    for (const each of [hijacked, unconfirmed]) {
      for (const forbidden of ["closed", "out of business", "no longer operates", "shut", "gone"]) {
        expect(linkNotice(en, each)?.toLowerCase()).not.toContain(forbidden);
      }
    }
  });

  it("tells the reader what to do instead, in both languages", () => {
    for (const each of [hijacked, unconfirmed]) {
      expect(linkNotice(en, each)).toContain("name");
      expect(linkNotice(es, each)).toContain("nombre");
    }
  });

  it("still says nothing when a confirmed rebrand keeps its link", () => {
    // 86 of the 109 pages in this class. The destination was corroborated, the link stands,
    // and a sentence about it would be noise printed beside a working school.
    const confirmed = link({
      verdict: "alive",
      reason: "redirected_offsite",
      redirect: "same_provider",
    });
    expect(linkNotice(en, confirmed)).toBeNull();
  });
});

describe("both languages carry the same claims", () => {
  it("dates every sentence in Spanish too", () => {
    const cases: ProviderLink[] = [
      link({ verdict: "dead", reason: "not_found", notice: "page_unreachable", linked: false }),
      link({ verdict: "dead", reason: "not_found", notice: "page_unreachable", linked: true }),
      link({ verdict: "dead", reason: "domain_for_sale", notice: "domain_for_sale", linked: false }),
      link({ verdict: "alive", reason: "redirected_offsite", notice: "redirect_unrelated" }),
      link({ verdict: "alive", reason: "redirected_offsite", notice: "redirect_unconfirmed" }),
    ];
    for (const each of cases) {
      expect(linkNotice(es, each)).toContain("2026-08-04");
      expect(linkNotice(es, each)).not.toBe(linkNotice(en, each));
    }
  });
});
