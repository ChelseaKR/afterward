import { describe, expect, it } from "vitest";

import {
  MAX_ITEMS,
  STORAGE_KEY,
  idsFromParam,
  idsToParam,
  isSaved,
  readShortlist,
  shortlistIds,
  toggle,
  writeShortlist,
  type ShortlistItem,
} from "./shortlist";

/** Minimal in-memory Storage, so these tests never touch a real browser store. */
function fakeStorage(initial?: string): Storage {
  const map = new Map<string, string>();
  if (initial !== undefined) map.set(STORAGE_KEY, initial);
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (k: string) => map.get(k) ?? null,
    key: (i: number) => [...map.keys()][i] ?? null,
    removeItem: (k: string) => void map.delete(k),
    setItem: (k: string, v: string) => void map.set(k, v),
  };
}

const item = (id: string, savedAt: number): ShortlistItem => ({ id, savedAt });

describe("toggle", () => {
  it("adds a program and removes it again", () => {
    const once = toggle([], "a", 1000);
    expect(once.map((i) => i.id)).toEqual(["a"]);
    expect(toggle(once, "a", 2000)).toEqual([]);
  });

  it("puts the newest first", () => {
    const list = toggle(toggle([], "a", 1000), "b", 2000);
    expect(list.map((i) => i.id)).toEqual(["b", "a"]);
  });

  it("records when a program was saved", () => {
    expect(toggle([], "a", 1234)[0]?.savedAt).toBe(1234);
  });

  it("drops the oldest at the cap rather than refusing the click", () => {
    // Someone at the limit is telling you the new one matters. Ignoring a click is worse
    // than quietly making room, and it is invisible.
    let list: ShortlistItem[] = [];
    for (let n = 0; n < MAX_ITEMS; n += 1) list = toggle(list, `p${n}`, n);
    expect(list).toHaveLength(MAX_ITEMS);

    const after = toggle(list, "newest", 9999);
    expect(after).toHaveLength(MAX_ITEMS);
    expect(after[0]?.id).toBe("newest");
    expect(after.some((i) => i.id === "p0")).toBe(false);
  });

  it("does not mutate the list it was given", () => {
    const original = [item("a", 1)];
    toggle(original, "b", 2);
    expect(original).toEqual([item("a", 1)]);
  });
});

describe("isSaved and ordering", () => {
  it("reports membership", () => {
    expect(isSaved([item("a", 1)], "a")).toBe(true);
    expect(isSaved([item("a", 1)], "b")).toBe(false);
  });

  it("orders ids by when they were saved, newest first", () => {
    expect(shortlistIds([item("old", 1), item("new", 9), item("mid", 5)])).toEqual([
      "new",
      "mid",
      "old",
    ]);
  });
});

describe("reading storage, which is untrusted input", () => {
  it("reads back what was written", () => {
    const storage = fakeStorage();
    writeShortlist([item("a", 1), item("b", 2)], storage);
    expect(readShortlist(storage).map((i) => i.id)).toEqual(["a", "b"]);
  });

  it("returns empty for absent, corrupt, or foreign data", () => {
    // localStorage is shared with everything on the origin and outlives versions. Losing a
    // shortlist is a small harm; a page that will not render is a large one.
    for (const raw of ["", "{not json", "null", "[]", '{"version":99,"items":[]}', '{"version":1}']) {
      expect(readShortlist(fakeStorage(raw))).toEqual([]);
    }
  });

  it("drops individual malformed entries but keeps the good ones", () => {
    const raw = JSON.stringify({
      version: 1,
      items: [{ id: "good", savedAt: 5 }, { id: "" }, { savedAt: 3 }, { id: "x", savedAt: "no" }],
    });
    expect(readShortlist(fakeStorage(raw)).map((i) => i.id)).toEqual(["good"]);
  });

  it("survives storage being unavailable", () => {
    // Private browsing throws on access rather than returning null.
    const hostile = {
      ...fakeStorage(),
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
    } as unknown as Storage;
    expect(readShortlist(hostile)).toEqual([]);
    expect(() => writeShortlist([item("a", 1)], hostile)).not.toThrow();
  });

  it("is a no-op with no storage at all, as during server rendering", () => {
    expect(readShortlist(undefined)).toEqual([]);
    expect(() => writeShortlist([item("a", 1)], undefined)).not.toThrow();
  });

  it("never writes more than the cap", () => {
    const storage = fakeStorage();
    writeShortlist(
      Array.from({ length: MAX_ITEMS + 10 }, (_, n) => item(`p${n}`, n)),
      storage,
    );
    expect(readShortlist(storage)).toHaveLength(MAX_ITEMS);
  });

  it("stores ids and timestamps and nothing else", () => {
    // What someone saves reveals a great deal about them. The stored shape is the privacy
    // guarantee, so it is asserted rather than assumed.
    const storage = fakeStorage();
    writeShortlist([item("a", 1)], storage);
    const parsed = JSON.parse(storage.getItem(STORAGE_KEY) ?? "{}");
    expect(Object.keys(parsed).sort()).toEqual(["items", "version"]);
    expect(Object.keys(parsed.items[0]).sort()).toEqual(["id", "savedAt"]);
  });
});

describe("sharing a shortlist", () => {
  it("round-trips through a parameter", () => {
    expect(idsFromParam(idsToParam(["a", "b", "c"]))).toEqual(["a", "b", "c"]);
  });

  it("returns empty for nothing", () => {
    expect(idsFromParam(null)).toEqual([]);
    expect(idsFromParam("")).toEqual([]);
  });

  it("drops ids that are not shaped like one", () => {
    expect(idsFromParam("f6900f55-31e5,../../etc/passwd,<script>,ok-1")).toEqual([
      "f6900f55-31e5",
      "ok-1",
    ]);
  });

  it("de-duplicates and respects the cap", () => {
    expect(idsFromParam("a,a,b")).toEqual(["a", "b"]);
    const many = Array.from({ length: MAX_ITEMS + 5 }, (_, n) => `p${n}`).join(",");
    expect(idsFromParam(many)).toHaveLength(MAX_ITEMS);
  });

  it("tolerates whitespace and empty segments", () => {
    expect(idsFromParam(" a , , b ")).toEqual(["a", "b"]);
  });
});
