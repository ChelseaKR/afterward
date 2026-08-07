/**
 * A shortlist of programs, kept on the reader's own device.
 *
 * Someone comparing four programs needs to find them again tonight. That does not need an
 * account, and there is a strong reason not to build one: a list of the training programs a
 * person is considering reveals that they are out of work, roughly what they can afford, where
 * they live, and — by inference from the programs themselves — a good deal more. The users of
 * this site have less power than most. The safest place for that list is their own device, and
 * the safest amount to collect is none.
 *
 * So this stores nothing but program ids and when they were saved, in `localStorage`, and the
 * site never sees any of it.
 *
 * **Shaped for a later sync without needing one.** The stored value is a versioned envelope of
 * plain data, so if cross-device sync is ever added — the one genuine reason to want an
 * account — it is an adapter over this model rather than a rewrite. `savedAt` exists for that:
 * it is what a last-write-wins merge would need, and it costs nothing to record now.
 */

/**
 * Deliberately still `camino.` after the 2026-08-05 rename, and not a leftover.
 *
 * This key names data that belongs to the reader and lives only on their device. Renaming it
 * would not migrate anything — it would make every shortlist saved before the rename
 * unreadable, and the site would show those readers an empty list with no error and no way to
 * get the programs back. A cosmetic rename is not worth silently discarding the four programs
 * somebody spent an evening choosing between.
 *
 * If it is ever worth changing, it is a versioned migration — read the old key, write the new
 * one, delete the old — not an edit to this string.
 */
export const STORAGE_KEY = "camino.shortlist.v1";

/** Deliberately small. A shortlist is for deciding between a few, not for collecting. */
export const MAX_ITEMS = 20;

export interface ShortlistItem {
  /** Program uuid, as it appears in the URL and the dataset. */
  id: string;
  /** Epoch milliseconds. Present for ordering and for a future merge, never displayed raw. */
  savedAt: number;
}

interface Envelope {
  version: 1;
  items: ShortlistItem[];
}

/**
 * Read the shortlist, tolerating anything.
 *
 * `localStorage` is shared with every other script on the origin and survives across versions,
 * so its contents are untrusted input. Corrupt or foreign data yields an empty list rather than
 * an exception: losing a shortlist is a small harm, and a page that will not render is a large
 * one. Private-browsing modes throw on access rather than returning null, which is why the
 * whole read is guarded.
 */
export function readShortlist(storage: Storage | undefined = safeStorage()): ShortlistItem[] {
  if (!storage) return [];
  try {
    const raw = storage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!isEnvelope(parsed)) return [];
    return parsed.items.filter(isItem).slice(0, MAX_ITEMS);
  } catch {
    return [];
  }
}

/** Persist the shortlist. Failure is silent by design — see `readShortlist`. */
export function writeShortlist(
  items: ShortlistItem[],
  storage: Storage | undefined = safeStorage(),
): void {
  if (!storage) return;
  const envelope: Envelope = { version: 1, items: items.slice(0, MAX_ITEMS) };
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(envelope));
  } catch {
    // Quota exceeded, or storage disabled. The in-memory list still works for this session.
  }
}

export function isSaved(items: readonly ShortlistItem[], id: string): boolean {
  return items.some((item) => item.id === id);
}

/**
 * Add or remove a program, returning a new list.
 *
 * At the cap, the oldest saved program is dropped rather than the new one refused: someone who
 * has hit the limit is telling you the new one matters, and silently ignoring a click is worse
 * than quietly making room. The list stays newest-first.
 */
export function toggle(
  items: readonly ShortlistItem[],
  id: string,
  now: number,
): ShortlistItem[] {
  if (isSaved(items, id)) return items.filter((item) => item.id !== id);
  return [{ id, savedAt: now }, ...items].slice(0, MAX_ITEMS);
}

export function clearAll(): ShortlistItem[] {
  return [];
}

/** Program ids, newest first — the order a reader last expressed interest in. */
export function shortlistIds(items: readonly ShortlistItem[]): string[] {
  return [...items].sort((a, b) => b.savedAt - a.savedAt).map((item) => item.id);
}

/**
 * The shortlist as a query parameter, so it can be sent to someone.
 *
 * The same reasoning as a shared search: the person helping you decide should not have to
 * create an account to look at four programs with you.
 */
export const SHORTLIST_PARAM = "saved";

export function idsToParam(ids: readonly string[]): string {
  return ids.join(",");
}

/**
 * Parse shared ids. Shape is validated here; whether a program exists is the caller's job,
 * since only it holds the dataset. An id that does not exist must be dropped rather than
 * rendered as a missing program.
 */
export function idsFromParam(raw: string | null): string[] {
  if (!raw) return [];
  const seen = new Set<string>();
  for (const part of raw.split(",")) {
    const id = part.trim();
    if (id && /^[A-Za-z0-9-]{1,64}$/.test(id)) seen.add(id);
    if (seen.size >= MAX_ITEMS) break;
  }
  return [...seen];
}

function safeStorage(): Storage | undefined {
  // Also the guard for server rendering, where `window` does not exist at all.
  try {
    return typeof window === "undefined" ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
}

function isEnvelope(value: unknown): value is Envelope {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as Envelope).version === 1 &&
    Array.isArray((value as Envelope).items)
  );
}

function isItem(value: unknown): value is ShortlistItem {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as ShortlistItem).id === "string" &&
    (value as ShortlistItem).id.length > 0 &&
    typeof (value as ShortlistItem).savedAt === "number" &&
    Number.isFinite((value as ShortlistItem).savedAt)
  );
}
