import { describe, expect, it, vi } from "vitest";

import {
  MAX_HISTORY_TURNS,
  appendHistory,
  askServiceUrl,
  citedLinks,
  postAsk,
  postTranslate,
  prepareQuestion,
  type AskResponseBody,
} from "./ask";

function reply(overrides: Partial<AskResponseBody> = {}): AskResponseBody {
  return {
    status: "ok",
    lang: "en",
    notice: "AI-generated.",
    message: null,
    claims: [],
    withheld: { count: 0, reasons: {} },
    follow_up_questions: [],
    clarifications_needed: [],
    out_of_scope: null,
    programs: [],
    occupations: [],
    notes: [],
    provenance: null,
    ...overrides,
  };
}

function fetchReturning(status: number, body: unknown, headers: Record<string, string> = {}) {
  return vi.fn(async () => new Response(JSON.stringify(body), { status, headers }));
}

/**
 * The service origin is a build-time decision, and an unset one means the panel does not
 * exist. A plain-http origin is refused anywhere but localhost: the question a person types
 * is the one piece of personal text this site ever handles.
 */
describe("askServiceUrl", () => {
  it("is null when the build has no service", () => {
    expect(askServiceUrl(undefined)).toBeNull();
    expect(askServiceUrl("")).toBeNull();
    expect(askServiceUrl("   ")).toBeNull();
  });

  it("normalises an https origin and allows local development over http", () => {
    expect(askServiceUrl("https://ask.example.test/")).toBe("https://ask.example.test");
    expect(askServiceUrl("http://localhost:8765")).toBe("http://localhost:8765");
    expect(askServiceUrl("http://127.0.0.1:8765/")).toBe("http://127.0.0.1:8765");
  });

  it("refuses plain http anywhere else", () => {
    expect(askServiceUrl("http://ask.example.test")).toBeNull();
    expect(askServiceUrl("ftp://x")).toBeNull();
  });
});

describe("prepareQuestion", () => {
  it("trims, caps, and refuses an empty question", () => {
    expect(prepareQuestion("  hello  ")).toBe("hello");
    expect(prepareQuestion("   ")).toBeNull();
    expect(prepareQuestion("x".repeat(3000))?.length).toBe(2000);
  });
});

describe("postAsk", () => {
  const body = { text: "q", lang: "en" as const, history: [] };

  it("posts JSON to /ask without credentials and returns the reply", async () => {
    const fetchImpl = fetchReturning(200, reply({ claims: [{ text: "x", kind: "data", cites: [] }] }));
    const outcome = await postAsk("https://svc.test", body, fetchImpl);
    expect(outcome.kind).toBe("reply");
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://svc.test/ask");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("omit");
    expect(JSON.parse(init.body as string)).toEqual(body);
  });

  it("reports a 429 as limited, with the Retry-After when given", async () => {
    expect(await postAsk("https://svc.test", body, fetchReturning(429, {}, { "retry-after": "42" }))).toEqual({
      kind: "limited",
      retryAfter: 42,
    });
    expect(await postAsk("https://svc.test", body, fetchReturning(429, {}))).toEqual({
      kind: "limited",
      retryAfter: null,
    });
  });

  it("reports any other failure as failed, never as an answer", async () => {
    expect(await postAsk("https://svc.test", body, fetchReturning(500, {}))).toEqual({ kind: "failed" });
    const broken = vi.fn(async () => new Response("not json", { status: 200 }));
    expect(await postAsk("https://svc.test", body, broken)).toEqual({ kind: "failed" });
    const offline = vi.fn(async () => {
      throw new TypeError("network");
    });
    expect(await postAsk("https://svc.test", body, offline)).toEqual({ kind: "failed" });
  });

  it("posts translations to /translate", async () => {
    const fetchImpl = fetchReturning(200, { status: "ok" });
    await postTranslate("https://svc.test", { kind: "program", id: "u" }, fetchImpl);
    expect((fetchImpl.mock.calls[0] as unknown as [string])[0]).toBe("https://svc.test/translate");
  });
});

describe("citedLinks", () => {
  it("links programs and occupations and ignores PEERS", () => {
    const programs = [{ id: "u1", name: "P", provider: "X", city: null, reported: true, path: "/en/programs/u1/" }];
    const occupations = [
      { soc_code: "11-1011", title: "O", spanish_title: null, percent_change: 1, path: "/en/occupations/11-1011/" },
    ];
    const links = citedLinks({ text: "", kind: "data", cites: ["P:u1", "O:11-1011", "PEERS", "P:zz"] }, programs, occupations);
    expect(links).toEqual([
      { label: "P", path: "/en/programs/u1/" },
      { label: "O", path: "/en/occupations/11-1011/" },
    ]);
  });
});

describe("appendHistory", () => {
  it("keeps the conversation short and within the service's cap", () => {
    let history = appendHistory([], "q1", reply({ claims: [{ text: "a1", kind: "data", cites: [] }] }));
    expect(history).toEqual([
      { role: "user", text: "q1" },
      { role: "assistant", text: "a1" },
    ]);
    for (let i = 0; i < 10; i++) history = appendHistory(history, `q${i}`, reply());
    expect(history.length).toBeLessThanOrEqual(MAX_HISTORY_TURNS);
  });
});
