/**
 * What the rendered accessibility gate is allowed to say it audited, and how it decides
 * whether this build should carry an assistant panel.
 *
 * Its own module because `a11y-rendered.mjs` starts a server and a browser at import time,
 * and these two answers are worth asserting without either. `a11y-verdict.test.ts` holds
 * them, including the part that cannot be checked by reading one file: that
 * `askServiceConfigured` and `lib/ask.ts`'s `askServiceUrl` agree, since a build's panel and
 * this gate's expectation of one have to be decided by the same rule or the gate is wrong in
 * exactly the cases nobody tried.
 */

/**
 * Whether a build made with this environment carries the assistant panel.
 *
 * The rule `askServiceUrl` applies, because it is the rule that decides: `AskPanel` renders
 * `null` for any origin that function rejects, so an origin rejected there is a build with no
 * panel. Kept as a predicate rather than returning the origin, because that is the only
 * question this gate has.
 */
export function askServiceConfigured(raw) {
  const trimmed = (raw ?? "").trim().replace(/\/+$/, "");
  if (!trimmed) return false;
  if (/^https:\/\//.test(trimmed)) return true;
  return /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(trimmed);
}

/**
 * The line the gate ends on.
 *
 * It names `audited` and nothing else. The sentence this replaces was a string literal
 * naming three surfaces -- "the rendered search results, comparison table, or assistant
 * panel" -- one of which the gate had just printed `skip` for on every build anybody ever
 * ran it on. A verdict is a claim about what was read; building it from anything other than
 * what was read is how a gate comes to be wrong precisely where it is quoted.
 */
export function verdict({ failures, audited }) {
  if (failures > 0) return `a11y-rendered: ${failures} node(s) failing`;
  if (audited.length === 0) {
    return "a11y-rendered: nothing was audited, which is a result and not a pass";
  }
  return `a11y-rendered: no violations in ${audited.join(", ")}`;
}
