#!/usr/bin/env python
"""Regenerate the cost-table snapshot from upstream aoe2techtree.

    python scripts/refresh_cost_tables.py [--version v2]

Costs change with game patches, so the snapshot is versioned rather than
overwritten: existing analyses keep the table they were computed against.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

UPSTREAM = "https://raw.githubusercontent.com/SiegeEngineers/aoe2techtree/master/data/data.json"
OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "services" / "costs" / "data"


def extract(section: dict) -> dict:
    out = {}
    for entity_id, value in section.items():
        cost = value.get("Cost") or {}
        if not cost:
            continue
        entry = {
            "name": value.get("internal_name") or "",
            "cost": {k.lower(): int(n) for k, n in cost.items()},
        }
        if value.get("TrainTime"):
            entry["train_time"] = value["TrainTime"]
        if value.get("ResearchTime"):
            entry["research_time"] = value["ResearchTime"]
        out[str(entity_id)] = entry
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()

    with urllib.request.urlopen(UPSTREAM, timeout=120) as response:
        payload = response.read()

    raw = json.loads(payload)
    data = raw["data"]
    snapshot = {
        "source": "https://github.com/SiegeEngineers/aoe2techtree",
        "source_file": "data/data.json",
        "note": "Extracted cost/name/time fields only. Game data is Microsoft's.",
        "snapshot_taken": datetime.date.today().isoformat(),
        "upstream_sha256": hashlib.sha256(payload).hexdigest(),
        "units": extract(data["Unit"]),
        "buildings": extract(data["Building"]),
        "techs": extract(data["Tech"]),
    }

    out = OUT_DIR / f"costs_{args.version}.json"
    out.write_text(json.dumps(snapshot, indent=1, sort_keys=True))
    print(
        f"wrote {out} - {len(snapshot['units'])} units, "
        f"{len(snapshot['buildings'])} buildings, {len(snapshot['techs'])} techs"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
