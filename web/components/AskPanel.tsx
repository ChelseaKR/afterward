"use client";

import Link from "next/link";
import { useId, useState, type FormEvent } from "react";

import {
  appendHistory,
  askServiceUrl,
  citedLinks,
  postAsk,
  prepareQuestion,
  type AskHistoryTurn,
  type AskOutcome,
  type AskResponseBody,
} from "@/lib/ask";
import { dict, feedTextLang, type Lang } from "@/lib/i18n";

/**
 * "Ask about this data": the opt-in front of `afterward.ask` (ADR 0003).
 *
 * Three things this component promises, and `AskPanel.test.tsx` holds it to:
 *
 * 1. With no service configured for this build (`NEXT_PUBLIC_ASK_URL` unset) it renders
 *    nothing. The page is the static site it always was.
 * 2. With a service configured it still makes no request -- none -- until the person has
 *    pressed the button and submitted a question. Opening the panel is not a request.
 * 3. Everything it shows is labelled AI-generated, unofficial, and not a recommendation
 *    from the State of California, above the answer and not below it, and the count of
 *    statements the verifier removed is shown beside what survived.
 *
 * It is a client component because it has state; the page that mounts it stays a server
 * component and passes plain props. It reuses the site's existing tokens and classes so the
 * contrast and axe gates see nothing new.
 */
export function AskPanel({
  lang,
  programId,
  socCode,
  serviceUrl = askServiceUrl(),
  fetchImpl,
}: {
  lang: Lang;
  programId?: string;
  socCode?: string;
  /** Overridable so a test can prove the no-request rule; the page passes nothing. */
  serviceUrl?: string | null;
  fetchImpl?: typeof fetch;
}) {
  const t = dict(lang);
  const headingId = useId();
  const inputId = useId();
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<AskHistoryTurn[]>([]);
  const [outcome, setOutcome] = useState<AskOutcome | null>(null);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);

  if (serviceUrl === null) return null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const prepared = prepareQuestion(question);
    if (prepared === null || busy) return;
    setBusy(true);
    setLastQuestion(prepared);
    const body = {
      text: prepared,
      lang,
      history,
      ...(programId ? { program_id: programId } : {}),
      ...(socCode ? { soc_code: socCode } : {}),
    };
    const result = await postAsk(serviceUrl as string, body, fetchImpl ?? fetch);
    setOutcome(result);
    if (result.kind === "reply" && result.body.status === "ok") {
      setHistory((current) => appendHistory(current, prepared, result.body));
    }
    setBusy(false);
  }

  function reset() {
    setQuestion("");
    setHistory([]);
    setOutcome(null);
    setLastQuestion(null);
  }

  if (!open) {
    return (
      <section className="ask ask-closed" aria-labelledby={headingId}>
        <h2 id={headingId} className="ask-heading">
          {t.askHeading}
        </h2>
        <p className="ask-lede">{t.askLede}</p>
        <button type="button" className="ask-button ask-open" onClick={() => setOpen(true)}>
          {t.askOpen}
        </button>
      </section>
    );
  }

  return (
    <section className="ask" aria-labelledby={headingId}>
      <h2 id={headingId} className="ask-heading">
        {t.askHeading}
      </h2>
      <p className="ask-lede">{t.askLede}</p>
      <p className="callout ask-notice">{t.askNotice}</p>
      <p className="ask-privacy">{t.askPrivacy}</p>

      <form onSubmit={submit} className="ask-form">
        <label htmlFor={inputId}>{t.askLabel}</label>
        <textarea
          id={inputId}
          name="question"
          rows={3}
          maxLength={2000}
          value={question}
          placeholder={t.askPlaceholder}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={busy}
        />
        <div className="ask-actions">
          <button type="submit" className="ask-button" disabled={busy || !question.trim()}>
            {busy ? t.askWorking : t.askSubmit}
          </button>
          <button type="button" className="linklike" onClick={reset} disabled={busy}>
            {t.askClear}
          </button>
          <button type="button" className="linklike" onClick={() => setOpen(false)} disabled={busy}>
            {t.askClose}
          </button>
        </div>
      </form>

      <div role="status" aria-live="polite" className="ask-status">
        {busy && <p>{t.askWorking}</p>}
      </div>

      {outcome && !busy && (
        <Outcome outcome={outcome} lang={lang} question={lastQuestion} />
      )}
    </section>
  );
}

function Outcome({
  outcome,
  lang,
  question,
}: {
  outcome: AskOutcome;
  lang: Lang;
  question: string | null;
}) {
  const t = dict(lang);
  if (outcome.kind === "limited") return <p className="ask-problem">{t.askLimited}</p>;
  if (outcome.kind === "failed") return <p className="ask-problem">{t.askFailed}</p>;
  const body = outcome.body;
  if (body.status !== "ok") return <p className="ask-problem">{t.askUnavailable}</p>;
  return <Reply body={body} lang={lang} question={question} />;
}

function Reply({
  body,
  lang,
  question,
}: {
  body: AskResponseBody;
  lang: Lang;
  question: string | null;
}) {
  const t = dict(lang);
  return (
    <div className="ask-reply">
      {question && (
        <p className="ask-question">
          <strong>{t.askLabel}:</strong> {question}
        </p>
      )}
      <p className="ask-label">{body.notice}</p>

      {body.claims.length === 0 ? (
        <p>{t.askNothingShown}</p>
      ) : (
        <ol className="ask-claims">
          {body.claims.map((claim, index) => {
            const links = citedLinks(claim, body.programs, body.occupations);
            return (
              <li key={index} className={claim.kind === "guidance" ? "ask-guidance" : undefined}>
                <p>{claim.text}</p>
                {links.length > 0 && (
                  <p className="ask-sources">
                    <span>{t.askSources}: </span>
                    {links.map((link, i) => (
                      <span key={link.path}>
                        {i > 0 && ", "}
                        <Link href={link.path} prefetch={false} lang={feedTextLang(lang)}>
                          {link.label}
                        </Link>
                      </span>
                    ))}
                  </p>
                )}
              </li>
            );
          })}
        </ol>
      )}

      {body.withheld.count > 0 && <p className="ask-withheld">{t.askWithheld(body.withheld.count)}</p>}

      {body.out_of_scope && (
        <p>
          <strong>{t.askOutOfScope}:</strong> {body.out_of_scope}
        </p>
      )}

      {body.clarifications_needed.length > 0 && (
        <div>
          <p>
            <strong>{t.askClarifications}</strong>
          </p>
          <ul>
            {body.clarifications_needed.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {body.programs.length > 0 && (
        <div>
          <h3>{t.askProgramsFound}</h3>
          <ul>
            {body.programs.map((program) => (
              <li key={program.id}>
                <Link href={program.path} prefetch={false} lang={feedTextLang(lang)}>
                  {program.name}
                </Link>
                <span lang={feedTextLang(lang)}> — {program.provider}</span>
                {program.city && <span>, {program.city}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {body.occupations.length > 0 && (
        <div>
          <h3>{t.askOccupationsFound}</h3>
          <ul>
            {body.occupations.map((occupation) => (
              <li key={occupation.soc_code}>
                <Link
                  href={occupation.path}
                  prefetch={false}
                  lang={lang === "es" && !occupation.spanish_title ? "en" : undefined}
                >
                  {lang === "es" && occupation.spanish_title ? occupation.spanish_title : occupation.title}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {body.follow_up_questions.length > 0 && (
        <div>
          <p>
            <strong>{t.askFollowUps}</strong>
          </p>
          <ul>
            {body.follow_up_questions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {body.provenance && (
        <p className="ask-provenance">
          {t.askProvenance(body.provenance.model, body.provenance.snapshot_date)}
        </p>
      )}
    </div>
  );
}
