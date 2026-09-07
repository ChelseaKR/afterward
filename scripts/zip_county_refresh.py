#!/usr/bin/env python3
"""Re-derive the vendored ZIP-to-county extract from the Census relationship file (D8).

Network-bound and run by hand, never by a build. The extract it writes is a snapshot of a
decennial product that does not move until the 2030 geography is published, so this exists
to make the extract *reproducible* rather than to keep it current: anyone can run it and
diff the result against what is committed.

Everything the retrieval record claims is recomputed here. Nothing in it is typed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from afterward.sources import zip_county  # noqa: E402


def main() -> int:
    print(f"downloading {zip_county.RELATIONSHIP_URL}", file=sys.stderr)
    text = zip_county.fetch_relationship_file()
    upstream = text.encode("utf-8")

    rows = zip_county.california_subset(zip_county.parse_relationship_file(text))
    extract = zip_county.render_csv(rows)

    previous = (
        zip_county.VENDORED_PATH.read_text(encoding="utf-8")
        if zip_county.VENDORED_PATH.exists()
        else None
    )
    zip_county.VENDORED_PATH.write_text(extract, encoding="utf-8")

    record = json.loads(zip_county.VENDORED_PROVENANCE_PATH.read_text(encoding="utf-8"))
    record["retrieved"] = datetime.now(tz=UTC).date().isoformat()
    record["sha256"] = hashlib.sha256(extract.encode("utf-8")).hexdigest()
    record["upstream_sha256"] = hashlib.sha256(upstream).hexdigest()
    record["upstream_bytes"] = len(upstream)
    record["rows"] = len(rows)
    record["zctas"] = len({row.zcta for row in rows})
    record["california_counties"] = len({row.county_geoid for row in rows if row.is_california})
    record["out_of_state_rows"] = sum(1 for row in rows if not row.is_california)
    zip_county.VENDORED_PROVENANCE_PATH.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    if previous is not None and previous != extract:
        print("EXTRACT CHANGED -- read the diff before committing it", file=sys.stderr)
    print(
        f"{len(rows)} rows, {record['zctas']} ZCTAs, "
        f"{record['out_of_state_rows']} cross-border rows, sha256 {record['sha256']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
