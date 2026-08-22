"use client";

import { useState } from "react";

import { askServiceUrl, postTranslate, type TranslateOutcome } from "@/lib/ask";
import { dict, type Lang } from "@/lib/i18n";

/**
 * "Translate with AI": Spanish on request for text the catalogue carries only in English.
 *
 * Rendered only on Spanish pages, only when a service is configured for this build, and only
 * beside text the Department publishes no Spanish for -- the 70 occupations Mi Próximo Paso
 * does not cover, and every provider-filed program description. Like the ask panel it makes
 * no request until pressed, and what it shows is labelled AI-translated and unreviewed with
 * the English left in place as the record. A translation the service withheld (it changed a
 * number) is reported as withheld, not replaced by anything.
 */
export function TranslateButton({
  lang,
  kind,
  id,
  serviceUrl = askServiceUrl(),
  fetchImpl,
}: {
  lang: Lang;
  kind: "occupation" | "program";
  id: string;
  serviceUrl?: string | null;
  fetchImpl?: typeof fetch;
}) {
  const t = dict(lang);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<TranslateOutcome | null>(null);

  if (serviceUrl === null || lang !== "es") return null;

  async function translate() {
    if (busy) return;
    setBusy(true);
    setOutcome(await postTranslate(serviceUrl as string, { kind, id }, fetchImpl ?? fetch));
    setBusy(false);
  }

  if (outcome === null) {
    return (
      <p className="ask-translate">
        <button type="button" className="linklike" onClick={translate} disabled={busy}>
          {busy ? t.askTranslateWorking : t.askTranslateOpen}
        </button>
      </p>
    );
  }

  if (outcome.kind !== "reply" || outcome.body.status === "unavailable" || outcome.body.status === "not_found") {
    return <p className="ask-translate ask-problem">{t.askTranslateUnavailable}</p>;
  }
  const body = outcome.body;
  if (body.status === "withheld") {
    return <p className="ask-translate ask-problem">{t.askTranslateWithheld}</p>;
  }
  return (
    <div className="ask-translate ask-translated">
      {body.ai_translated && <p className="ask-label">{t.askTranslateLabel}</p>}
      {body.title && <p><strong>{body.title}</strong></p>}
      {body.description && <p>{body.description}</p>}
    </div>
  );
}
