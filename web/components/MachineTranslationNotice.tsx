import {
  MACHINE_TRANSLATION_ENGLISH_LINK_ID,
  MACHINE_TRANSLATION_NOTICE,
  MACHINE_TRANSLATION_NOTICE_ATTR,
} from "@/lib/machineTranslation";

/**
 * "Machine-translated, not reviewed by a person", in Spanish and English, with a link to the
 * English page. See `lib/machineTranslation.ts` for why it exists and where it must appear.
 *
 * A plain `div`, not an `aside`: it renders inside the banner landmark, and a complementary
 * landmark nested in another landmark is an axe violation. Placed beside the non-affiliation
 * notice for the same reason that notice sits above the masthead -- it is a fact about the
 * whole page a reader should meet before the content, not after it.
 */
export function MachineTranslationNotice({ englishHref = "/en/" }: { englishHref?: string }) {
  const { es, en } = MACHINE_TRANSLATION_NOTICE;
  const attr = { [MACHINE_TRANSLATION_NOTICE_ATTR]: "" };
  return (
    <div className="mt-notice" {...attr}>
      <div className="shell">
        <p lang="es">
          <strong>{es.lead}</strong> {es.body}
        </p>
        <p lang="en">
          <strong>{en.lead}</strong> {en.body}
        </p>
        <p>
          <a id={MACHINE_TRANSLATION_ENGLISH_LINK_ID} href={englishHref} hrefLang="en">
            <span lang="es">{es.link}</span> · <span lang="en">{en.link}</span>
          </a>
        </p>
      </div>
    </div>
  );
}
