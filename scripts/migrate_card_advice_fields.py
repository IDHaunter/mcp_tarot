"""Move meaning_for_today and card_advice into upright/reversed sections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "server" / "data"


def migrate_card_data(data: dict[str, Any]) -> bool:
    """Migrate one card JSON object. Returns True if file was changed."""
    changed = False
    upright: dict[str, Any] = dict(data.get("upright") or {})
    reversed_block: dict[str, Any] = dict(data.get("reversed") or {})

    for key in ("meaning_for_today", "card_advice"):
        if key in data:
            value = data.pop(key)
            changed = True
            if key not in upright:
                upright[key] = value
            if key not in reversed_block:
                reversed_block[key] = upright.get(key, value)

    for key in ("meaning_for_today", "card_advice"):
        if key in upright and key not in reversed_block:
            reversed_block[key] = upright[key]
            changed = True

    if upright:
        data["upright"] = upright
        changed = True
    if reversed_block:
        data["reversed"] = reversed_block
        changed = True

    return changed


def main() -> None:
    """Migrate all card JSON files under server/data."""
    updated = 0
    for path in sorted(DATA_DIR.rglob("*.json")):
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if migrate_card_data(data):
            with path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            updated += 1
            print(f"updated: {path.relative_to(DATA_DIR.parent)}")
    print(f"Done. {updated} file(s) updated.")


if __name__ == "__main__":
    main()
