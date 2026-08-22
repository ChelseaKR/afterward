/**
 * The browser side of `afterward.ask` (ADR 0003): what the panel sends, what it receives,
 * and the one rule that matters here — nothing leaves the page until a person chooses.
 *
 * The service origin is a build-time constant, `NEXT_PUBLIC_ASK_URL`. When it is unset,
 * which is every build until the owner decides to deploy the service, `askServiceUrl()` is
 * null and the panel renders nothing at all: the page is byte-for-byte the static site it
 * was. When it is set, the panel still makes no request until the person opens it and
 * submits a question; `AskPanel.test.tsx` holds that line.
 *
 * Separate from the component so the request/response handling can be tested without a DOM.
 */

import type { Lang } from "./i18n";

export interface AskHistoryTurn {
  role: "user" | "assistant";
  text: string;
}

export interface AskRequestBody {
  text: string;
  lang: Lang;
  history: AskHistoryTurn[];
  program_id?: string;
  soc_code?: string;
}

export interface AskClaim {
  text: string;
  kind: "data" | "guidance";
  cites: string[];
}

export interface AskProgram {
  id: string;
  name: string;
  provider: string;
  city: string | null;
  reported: boolean;
  path: string;
}

export interface AskOccupation {
  soc_code: string;
  title: string;
  spanish_title: string | null;
  percent_change: number | null;
  path: string;
}

export interface AskProvenance {
  provider: string;
  model: string;
  prompt_version: string;
  snapshot_date: string;
  is_fixture: boolean;
  generated_at: string;
}

export interface AskResponseBody {
  status: "ok" | "unavailable";
  lang: Lang;
  notice: string;
  message: string | null;
  claims: AskClaim[];
  withheld: { count: number; reasons: Record<string, number> };
  follow_up_questions: string[];
  clarifications_needed: string[];
  out_of_scope: string | null;
  programs: AskProgram[];
  occupations: AskOccupation[];
  notes: string[];
  provenance: AskProvenance | null;
}

export interface TranslateResponseBody {
  status: "ok" | "published" | "withheld" | "unavailable" | "not_found";
  kind: "occupation" | "program";
  id: string;
  title: string | null;
  description: string | null;
  label: string;
  ai_translated: boolean;
  reviewed: boolean;
  withheld: string[];
}

/** What the panel shows after a request: a reply, a limit, or a failure. Never a guess. */
export type AskOutcome =
  | { kind: "reply"; body: AskResponseBody }
  | { kind: "limited"; retryAfter: number | null }
  | { kind: "failed" };

export type TranslateOutcome =
  | { kind: "reply"; body: TranslateResponseBody }
  | { kind: "limited"; retryAfter: number | null }
  | { kind: "failed" };

/** Hard caps, matching the service's own. A longer question is cut here, not there. */
export const MAX_QUESTION_CHARS = 2000;
export const MAX_HISTORY_TURNS = 6;

/**
 * The service origin, or null when this build has none.
 *
 * Read from `process.env` at build time — Next inlines `NEXT_PUBLIC_*` — and normalised to
 * no trailing slash. A non-https origin is refused outside local development, because the
 * question a person types is the one piece of personal text this site ever handles.
 */
export function askServiceUrl(raw: string | undefined = process.env.NEXT_PUBLIC_ASK_URL): string | null {
  const trimmed = (raw ?? "").trim().replace(/\/+$/, "");
  if (!trimmed) return null;
  if (/^https:\/\//.test(trimmed)) return trimmed;
  if (/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(trimmed)) return trimmed;
  return null;
}

/** Trim a question to what the service accepts, and refuse an empty one. */
export function prepareQuestion(text: string): string | null {
  const trimmed = text.trim().slice(0, MAX_QUESTION_CHARS);
  return trimmed.length > 0 ? trimmed : null;
}

/**
 * The request the panel makes. `fetchImpl` is injectable so a test can prove when it is
 * and is not called; the component passes `fetch`.
 */
export async function postAsk(
  serviceUrl: string,
  body: AskRequestBody,
  fetchImpl: typeof fetch = fetch,
): Promise<AskOutcome> {
  return post(`${serviceUrl}/ask`, body, fetchImpl);
}

export async function postTranslate(
  serviceUrl: string,
  body: { kind: "occupation" | "program"; id: string },
  fetchImpl: typeof fetch = fetch,
): Promise<TranslateOutcome> {
  return post(`${serviceUrl}/translate`, body, fetchImpl);
}

async function post<T>(
  url: string,
  body: unknown,
  fetchImpl: typeof fetch,
): Promise<{ kind: "reply"; body: T } | { kind: "limited"; retryAfter: number | null } | { kind: "failed" }> {
  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      // No cookies, no credentials: the service has no accounts and must never learn of one.
      credentials: "omit",
    });
  } catch {
    return { kind: "failed" };
  }
  if (response.status === 429) {
    const header = response.headers.get("retry-after");
    const retryAfter = header === null ? null : Number.parseInt(header, 10);
    return { kind: "limited", retryAfter: Number.isFinite(retryAfter) ? retryAfter : null };
  }
  if (!response.ok) return { kind: "failed" };
  try {
    return { kind: "reply", body: (await response.json()) as T };
  } catch {
    return { kind: "failed" };
  }
}

/**
 * Turn a claim's record ids into the links the reader can follow.
 *
 * The service's claims cite `P:<uuid>`, `O:<soc>` and `PEERS`. Only the first two are pages;
 * PEERS is the site's own comparison basis and is explained by the notice, not linked.
 */
export function citedLinks(
  claim: AskClaim,
  programs: AskProgram[],
  occupations: AskOccupation[],
): { label: string; path: string }[] {
  const links: { label: string; path: string }[] = [];
  for (const cite of claim.cites) {
    if (cite.startsWith("P:")) {
      const program = programs.find((p) => p.id === cite.slice(2));
      if (program) links.push({ label: program.name, path: program.path });
    } else if (cite.startsWith("O:")) {
      const occupation = occupations.find((o) => o.soc_code === cite.slice(2));
      if (occupation) links.push({ label: occupation.title, path: occupation.path });
    }
  }
  return links;
}

/** Keep the conversation the service sees short, and never longer than it accepts. */
export function appendHistory(
  history: AskHistoryTurn[],
  question: string,
  reply: AskResponseBody,
): AskHistoryTurn[] {
  const assistantText = reply.claims.map((c) => c.text).join(" ").slice(0, MAX_QUESTION_CHARS);
  const next = [...history, { role: "user" as const, text: question }];
  if (assistantText) next.push({ role: "assistant" as const, text: assistantText });
  return next.slice(-MAX_HISTORY_TURNS);
}
