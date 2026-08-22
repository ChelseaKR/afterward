// @vitest-environment jsdom

/**
 * The promise the panel makes, held by a test: nothing leaves the page until a person opens
 * it and asks. Rendered in a real DOM with `fetch` replaced by a spy, the spy must be
 * untouched after mount, untouched after the opt-in click, and called exactly once after a
 * question is submitted -- to the configured service and nowhere else. With no service
 * configured the panel must not exist at all.
 */

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AskPanel } from "./AskPanel";
import { TranslateButton } from "./TranslateButton";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: unknown }) => (
    <a href={href} {...rest}>
      {children as never}
    </a>
  ),
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const SERVICE = "https://ask.example.test";

const REPLY = {
  status: "ok",
  lang: "en",
  notice: "AI-generated and unofficial.",
  message: null,
  claims: [
    { text: "Completion was 97%.", kind: "data", cites: ["P:u1"] },
    { text: "Talk to the provider.", kind: "guidance", cites: [] },
  ],
  withheld: { count: 2, reasons: { suppressed_as_value: 1, unknown_record: 1 } },
  follow_up_questions: ["Which region?"],
  clarifications_needed: [],
  out_of_scope: null,
  programs: [{ id: "u1", name: "CDL", provider: "School", city: "Fresno", reported: true, path: "/en/programs/u1/" }],
  occupations: [],
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

let container: HTMLDivElement;
let root: Root;
let fetchSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  fetchSpy = vi.fn(async () => new Response(JSON.stringify(REPLY), { status: 200 }));
  vi.stubGlobal("fetch", fetchSpy);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

async function render(element: React.ReactElement) {
  await act(async () => root.render(element));
}

function button(label: string): HTMLButtonElement {
  const found = Array.from(container.querySelectorAll("button")).find((b) => b.textContent === label);
  if (!found) throw new Error(`no button labelled ${label}`);
  return found;
}

describe("AskPanel makes no request until asked", () => {
  it("renders nothing at all when the build has no service", async () => {
    await render(<AskPanel lang="en" serviceUrl={null} />);
    expect(container.innerHTML).toBe("");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("does not call fetch on mount, nor on opening, only on submit", async () => {
    await render(<AskPanel lang="en" programId="u1" serviceUrl={SERVICE} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(container.querySelector("textarea")).toBeNull();

    await act(async () => button("Ask about this data").click());
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(container.textContent).toContain("AI-generated and unofficial");
    expect(container.textContent).toContain("leaves this site");

    const textarea = container.querySelector("textarea") as HTMLTextAreaElement;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
      setter?.call(textarea, "What happened to students?");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container.querySelector("form")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`${SERVICE}/ask`);
    expect(JSON.parse(init.body as string)).toEqual({
      text: "What happened to students?",
      lang: "en",
      history: [],
      program_id: "u1",
    });
  });

  it("shows the reply with its label, the withheld count, and links to the cited records", async () => {
    await render(<AskPanel lang="en" serviceUrl={SERVICE} />);
    await act(async () => button("Ask about this data").click());
    const textarea = container.querySelector("textarea") as HTMLTextAreaElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set?.call(textarea, "q");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container.querySelector("form")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    const text = container.textContent ?? "";
    expect(text).toContain("Completion was 97%.");
    expect(text).toContain("2 statements were removed");
    expect(text).toContain("Which region?");
    expect(text).toContain("Generated by claude-sonnet-4-6 from the dataset published 2026-08-17.");
    expect(container.querySelector('a[href="/en/programs/u1/"]')).not.toBeNull();
    // The notice sits above the claims, not below them.
    expect(text.indexOf("AI-generated and unofficial")).toBeLessThan(text.indexOf("Completion was 97%."));
  });

  it("says busy on a 429 and never shows an answer", async () => {
    fetchSpy.mockImplementation(async () => new Response("{}", { status: 429, headers: { "retry-after": "30" } }));
    await render(<AskPanel lang="es" serviceUrl={SERVICE} />);
    await act(async () => button("Preguntar sobre estos datos").click());
    const textarea = container.querySelector("textarea") as HTMLTextAreaElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set?.call(textarea, "hola");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container.querySelector("form")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    expect(container.textContent).toContain("El asistente está ocupado");
    expect(container.querySelector(".ask-claims")).toBeNull();
  });
});

describe("TranslateButton", () => {
  it("renders nothing without a service or on an English page, and requests nothing until pressed", async () => {
    await render(<TranslateButton lang="es" kind="program" id="u1" serviceUrl={null} />);
    expect(container.innerHTML).toBe("");
    await render(<TranslateButton lang="en" kind="program" id="u1" serviceUrl={SERVICE} />);
    expect(container.innerHTML).toBe("");
    await render(<TranslateButton lang="es" kind="program" id="u1" serviceUrl={SERVICE} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            status: "ok",
            kind: "program",
            id: "u1",
            title: "Título",
            description: "Descripción con 160 horas.",
            label: "Traducido por IA",
            ai_translated: true,
            reviewed: false,
            withheld: [],
          }),
          { status: 200 },
        ),
    );
    await act(async () => button("Traducir con IA").click());
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect((fetchSpy.mock.calls[0] as unknown as [string])[0]).toBe(`${SERVICE}/translate`);
    expect(container.textContent).toContain("Traducido por IA, sin revisión humana");
    expect(container.textContent).toContain("160 horas");
  });

  it("reports a withheld translation rather than showing anything", async () => {
    fetchSpy.mockImplementation(
      async () =>
        new Response(
          JSON.stringify({ status: "withheld", kind: "program", id: "u1", title: null, description: null, label: "", ai_translated: true, reviewed: false, withheld: ["numbers_changed"] }),
          { status: 200 },
        ),
    );
    await render(<TranslateButton lang="es" kind="program" id="u1" serviceUrl={SERVICE} />);
    await act(async () => button("Traducir con IA").click());
    expect(container.textContent).toContain("no se muestra porque no coincidía");
  });
});
