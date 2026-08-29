// @vitest-environment jsdom

/**
 * An axe pass over the assistant panel, in the one state no gate has ever seen it in: open.
 *
 * `npm run a11y` reads the static export, where the panel is not present -- it renders
 * nothing without `NEXT_PUBLIC_ASK_URL`, which no build sets. `npm run a11y:rendered` drives
 * the export in Chromium and looks for the panel's button, does not find it, and until
 * 2026-08-28 printed `skip  Assistant panel (English): not in this build` and then a verdict
 * claiming "no violations in the rendered search results, comparison table, or assistant
 * panel". So the newest interface in the repository had no accessibility coverage anywhere,
 * under a sentence saying it did.
 *
 * That gap is closed here rather than by building the site a second time with a service
 * origin set: the panel is a client component with no server dependency, mounting it open in
 * jsdom is a second of test time rather than a minute of Next build, and it puts the check in
 * the suite that runs on every change to the component.
 *
 * Layout-dependent rules are excluded for the reason `a11y-audit.mjs` excludes them from its
 * jsdom pass: jsdom has no layout engine, so contrast and target size are not answerable
 * here. They are answered for the rest of the site by `npm run contrast` and the Chromium
 * pass, and will be answered for this panel by the same Chromium pass the day a build carries
 * one -- which is now a failure rather than a skip if it does not.
 */

import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AskPanel } from "./AskPanel";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: unknown }) => (
    <a href={href} {...rest}>
      {children as never}
    </a>
  ),
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const SERVICE = "https://ask.example.test";

/** The rules jsdom cannot answer, excluded here and answered elsewhere. */
const LAYOUT_DEPENDENT = new Set(["color-contrast", "color-contrast-enhanced", "target-size"]);

const REPLY = {
  status: "ok",
  lang: "en",
  notice: "AI-generated and unofficial.",
  message: null,
  claims: [
    { text: "Completion was 97%.", kind: "data", cites: ["P:u1"] },
    { text: "Median earnings are not reported.", kind: "data", cites: ["P:u1"] },
    { text: "Talk to the provider.", kind: "guidance", cites: [] },
  ],
  withheld: { count: 2, reasons: { suppressed_as_value: 1, unknown_record: 1 } },
  follow_up_questions: ["Which region?"],
  clarifications_needed: [],
  out_of_scope: null,
  programs: [
    { id: "u1", name: "CDL", provider: "School", city: "Fresno", reported: true, path: "/en/programs/u1/" },
  ],
  occupations: [
    {
      soc_code: "53-3032",
      title: "Heavy and Tractor-Trailer Truck Drivers",
      spanish_title: null,
      percent_change: 4.1,
      path: "/en/occupations/53-3032/",
    },
  ],
  notes: [],
  provenance: {
    provider: "bedrock",
    model: "claude-sonnet-4-6",
    prompt_version: "v",
    snapshot_date: "2026-08-17",
    is_fixture: false,
    generated_at: "2026-08-21T00:00:00+00:00",
  },
};

let container: HTMLElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("main");
  document.body.appendChild(container);
  root = createRoot(container);
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(REPLY), { status: 200 })),
  );
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

/** Every rule axe ships, including the sixteen it disables by default. */
function everyRule(): Record<string, { enabled: boolean }> {
  return Object.fromEntries(axe.getRules().map((rule) => [rule.ruleId, { enabled: true }]));
}

async function violations(): Promise<string[]> {
  const results = await axe.run(container, {
    resultTypes: ["violations"],
    rules: everyRule(),
  });
  return results.violations
    .filter((v) => !LAYOUT_DEPENDENT.has(v.id))
    .map((v) => `[${v.impact}] ${v.id}: ${v.help} -- ${v.nodes[0]?.html?.slice(0, 160) ?? ""}`);
}

async function open(lang: "en" | "es" = "en") {
  await act(async () => root.render(<AskPanel lang={lang} programId="u1" serviceUrl={SERVICE} />));
  const trigger = Array.from(container.querySelectorAll("button")).find((b) =>
    b.className.includes("ask-open"),
  );
  if (!trigger) throw new Error("no ask-open button to press");
  await act(async () => trigger.click());
}

async function ask() {
  const textarea = container.querySelector("textarea");
  if (!textarea) throw new Error("the panel is not open");
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set?.call(
      textarea,
      "What happened to students?",
    );
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => {
    container
      .querySelector("form")
      ?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
}

describe("the assistant panel passes axe in the states a reader puts it in", () => {
  it("has no violations closed, which is the state every page ships in", async () => {
    await act(async () => root.render(<AskPanel lang="en" programId="u1" serviceUrl={SERVICE} />));
    expect(await violations()).toEqual([]);
  });

  it("has no violations open, in English", async () => {
    await open("en");
    expect(container.querySelector(".ask-form textarea")).not.toBeNull();
    expect(await violations()).toEqual([]);
  });

  it("has no violations open, in Spanish", async () => {
    await open("es");
    expect(await violations()).toEqual([]);
  });

  it("has no violations showing an answer, which is the densest state", async () => {
    await open("en");
    await ask();
    expect(container.textContent).toContain("Completion was 97%.");
    expect(await violations()).toEqual([]);
  });
});
