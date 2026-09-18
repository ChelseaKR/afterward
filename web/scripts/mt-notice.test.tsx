import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { MachineTranslationNotice } from "@/components/MachineTranslationNotice";
import {
  MACHINE_TRANSLATED,
  MACHINE_TRANSLATION_ENGLISH_LINK_ID,
  MACHINE_TRANSLATION_NOTICE,
  MACHINE_TRANSLATION_NOTICE_ATTR,
  isMachineTranslated,
} from "@/lib/machineTranslation";

import { ENGLISH_LINK_ID, NOTICE_ATTR, noticeProblems, noticeRequired } from "./mt-notice.mjs";

/**
 * The machine-translation notice and the build audit that requires it (owner decision,
 * 2026-09-18: the Spanish ships labeled as machine-translated).
 *
 * The pages here are built around the *real* component's markup, so the audit is tested
 * against what the site renders and not against a copy of it that could drift.
 */

const NOTICE = renderToStaticMarkup(<MachineTranslationNotice />);

function page(lang: "en" | "es", header: string, body = "<p>Contenido</p>"): string {
  return (
    `<!DOCTYPE html><html lang="${lang}"><body><header>${header}</header>` +
    `<main id="main">${body}</main></body></html>`
  );
}

describe("a Spanish page", () => {
  it("passes with the notice above its main content", () => {
    expect(noticeProblems("es/programs/1/index.html", page("es", NOTICE))).toEqual([]);
  });

  it("fails without the notice", () => {
    expect(noticeProblems("es/programs/1/index.html", page("es", ""))).toEqual([
      "es/programs/1/index.html: shows Spanish without the machine-translation notice",
    ]);
  });

  it("fails when the notice is below the main content rather than near the top", () => {
    const html = page("es", "", `<p>Contenido</p>${NOTICE}`);
    expect(noticeProblems("es/index.html", html)).toEqual([
      "es/index.html: the machine-translation notice is not above the page's main content",
    ]);
  });

  it("fails when the notice has lost its English half", () => {
    const html = page("es", NOTICE.replace(/<p lang="en">[\s\S]*?<\/p>/, ""));
    expect(noticeProblems("es/index.html", html)).toEqual([
      "es/index.html: the machine-translation notice has no English text",
    ]);
  });

  it("fails when the notice has lost its Spanish half", () => {
    const html = page("es", NOTICE.replace(/<p lang="es">[\s\S]*?<\/p>/, ""));
    expect(noticeProblems("es/index.html", html)).toEqual([
      "es/index.html: the machine-translation notice has no Spanish text",
    ]);
  });

  it("fails when the notice does not link to the English", () => {
    const html = page("es", NOTICE.replace('href="/en/"', 'href="/es/"'));
    expect(noticeProblems("es/index.html", html)).toEqual([
      "es/index.html: the machine-translation notice does not link to the English version",
    ]);
  });

  it("fails when the notice appears twice", () => {
    expect(noticeProblems("es/index.html", page("es", NOTICE + NOTICE))).toEqual([
      "es/index.html: carries the machine-translation notice 2 times",
    ]);
  });

  it("is not satisfied by the attribute appearing only in the inlined flight payload", () => {
    const payload = `<script>self.__next_f.push([1,"{\\"${NOTICE_ATTR}\\":\\"\\"}"])</script>`;
    expect(noticeProblems("es/index.html", page("es", "", payload))).toEqual([
      "es/index.html: shows Spanish without the machine-translation notice",
    ]);
  });
});

describe("an English page", () => {
  it("passes without the notice, although it names Spanish in the language toggle", () => {
    const toggle = '<a id="lang-switch" href="/es/" lang="es" hreflang="es">Español</a>';
    expect(noticeProblems("en/index.html", page("en", toggle))).toEqual([]);
  });

  it("fails with the notice, which would call the English machine-translated", () => {
    expect(noticeProblems("en/index.html", page("en", NOTICE))).toEqual([
      "en/index.html: carries the machine-translation notice but shows no machine-translated text",
    ]);
  });
});

describe("a page that belongs to no language", () => {
  it("must carry the notice when it shows Spanish", () => {
    const html = page("en", '<p lang="es">Este sitio no es del estado.</p>');
    expect(noticeRequired("index.html", html)).toBe(true);
    expect(noticeProblems("404.html", html)).toEqual([
      "404.html: shows Spanish without the machine-translation notice",
    ]);
  });

  it("passes when it shows Spanish and carries the notice", () => {
    const html = page("en", `<p lang="es">Este sitio no es del estado.</p>${NOTICE}`);
    expect(noticeProblems("index.html", html)).toEqual([]);
  });
});

describe("the notice", () => {
  it("says it in both languages, and each half is really in its language", () => {
    const { es, en } = MACHINE_TRANSLATION_NOTICE;
    for (const key of ["lead", "body", "link"] as const) {
      expect(es[key].trim()).not.toBe("");
      expect(en[key].trim()).not.toBe("");
      expect(es[key]).not.toBe(en[key]);
    }
    expect(NOTICE).toContain(es.lead);
    expect(NOTICE).toContain(en.lead);
    expect(NOTICE).toContain('<p lang="es">');
    expect(NOTICE).toContain('<p lang="en">');
  });

  it("is required of Spanish and of nothing else", () => {
    expect(isMachineTranslated("es")).toBe(true);
    expect(isMachineTranslated("en")).toBe(false);
    expect([...MACHINE_TRANSLATED]).toEqual(["es"]);
  });

  it("uses the attribute and link id the audit looks for", () => {
    expect(MACHINE_TRANSLATION_NOTICE_ATTR).toBe(NOTICE_ATTR);
    expect(MACHINE_TRANSLATION_ENGLISH_LINK_ID).toBe(ENGLISH_LINK_ID);
  });

  it("has its English link aimed at the page's twin by the layout's masthead script", () => {
    const layout = readFileSync(
      fileURLToPath(new URL("../app/[lang]/layout.tsx", import.meta.url)),
      "utf-8",
    );
    expect(layout).toContain(`document.getElementById("${ENGLISH_LINK_ID}")`);
    expect(layout).toContain('english.setAttribute("href", "/en" + rest');
  });
});
