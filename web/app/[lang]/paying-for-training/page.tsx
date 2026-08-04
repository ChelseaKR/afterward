import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Citations, Questions, stepCopy } from "@/components/funding";
import { getCoverage } from "@/lib/data";
import { LANGUAGES, dict, isLang, type Lang } from "@/lib/i18n";

/*
 * The funding guidance, once.
 *
 * This text used to be printed in full on every program page. It is identical on all 6,532 of
 * them: it describes a federal program, not a course, and the only program-specific things in
 * it were one dated sentence and the list of nearby offices, both of which stay behind. Folding
 * it into a disclosure hid the bulk but still shipped it 6,532 times, and left a reader with no
 * single address to send someone who asked "how does this get paid for?".
 */

export function generateStaticParams() {
  return LANGUAGES.map((lang) => ({ lang }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ lang: string }>;
}): Promise<Metadata> {
  const { lang } = await params;
  if (!isLang(lang)) return {};
  const t = dict(lang);
  return { title: t.fundingGuideTitle, description: t.fundingGuideIntro };
}

export default async function PayingForTraining({
  params,
}: {
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const t = dict(lang as Lang);
  const localHelp = getCoverage().local_help;
  if (!localHelp) notFound();

  const steps = localHelp.guidance.steps;
  const questions = localHelp.guidance.questions;

  return (
    <div className="shell detail">
      <p>
        <Link href={`/${lang}/`}>← {t.backToSearch}</Link>
      </p>

      <h1>{t.fundingGuideTitle}</h1>

      {/*
        Spanish only, and above everything rather than under it. This page is about money and
        eligibility, its readers are the ones an error hurts most, and it has not had a native
        reviewer. A reader is entitled to know that before they read it, not after.
      */}
      {lang === "es" && <p className="funding-translation-note">{t.fundingTranslationNote}</p>}

      <p className="funding-lede">{t.fundingGuideIntro}</p>

      {steps.map((step) => {
        const copy = stepCopy(step, t);
        return (
          <section key={step.id} className="funding-step">
            <h2>{copy.heading}</h2>
            <p>{copy.detail}</p>
            <Citations citations={step.citations} label={t.fundingRuleLabel} />
          </section>
        );
      })}

      <h2>{t.fundingQuestionsHeading}</h2>
      <Questions
        questions={questions.filter((q) => q.audience === "job_center")}
        heading={t.fundingQuestionsJobCenter}
        lang={lang}
      />
      <Questions
        questions={questions.filter((q) => q.audience === "provider")}
        heading={t.fundingQuestionsProvider}
        lang={lang}
      />

      {/* Never inside a disclosure, never in the footer: this is the sentence that says none
          of the above is an offer, and it is the last thing read. */}
      <p className="who-decides">{t.fundingWhoDecides}</p>
      <p className="compare-note">{t.fundingEnglishSources}</p>
    </div>
  );
}
