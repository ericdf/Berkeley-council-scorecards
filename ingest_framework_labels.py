#!/usr/bin/env python3
"""
ingest_framework_labels.py

Reads agendas/framework_review.csv (after human review) and writes
framework_classification back into each agenda JSON item.

Usage:
    python3 ingest_framework_labels.py [agendas/framework_review.csv] [--dry-run]
"""

import argparse
import csv
import json
import glob
import os
import sys
from collections import defaultdict

DEFAULT_CSV = "agendas/framework_review.csv"
AGENDA_GLOB = "agendas/20*.json"

VALID_CLASSIFICATIONS = {
    "adds_non_core", "reduces_non_core", "addresses_cost_premium",
    "entrenches_cost_premium", "p1_direct", "neutral", "revenue_seeking",
}


def load_labels(csv_path: str) -> dict:
    """
    Returns dict: (date, section, item_number) -> {classification, framework_category, notes}
    Uses 'label' column if filled; falls back to 'prelabel'.
    Skips rows where both are empty or 'neutral' (neutral is the default, not stored).
    """
    labels = {}
    skipped = 0
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            label = (row.get("label") or "").strip()
            prelabel = (row.get("prelabel") or "").strip()
            effective = label if label else prelabel
            if not effective or effective == "neutral":
                skipped += 1
                continue
            if effective not in VALID_CLASSIFICATIONS:
                print(f"  WARN: unknown classification '{effective}' on {row['date']} item {row['item_number']} — skipping",
                      file=sys.stderr)
                continue
            key = (row["date"], row["section"], str(row["item_number"]))
            cat = (row.get("override_category") or row.get("framework_category") or "").strip()
            labels[key] = {
                "framework_classification": effective,
                "framework_category":       cat or None,
                "framework_notes":          (row.get("notes") or "").strip() or None,
                "framework_reason":         (row.get("reason") or "").strip() or None,
            }
    print(f"Loaded {len(labels)} non-neutral labels ({skipped} neutral/empty skipped)",
          file=sys.stderr)
    return labels


def ingest(csv_path: str, dry_run: bool = False):
    labels = load_labels(csv_path)
    if not labels:
        print("No non-neutral labels found — nothing to write.", file=sys.stderr)
        return

    # Build index: date -> filepath
    date_to_file: dict[str, list[str]] = defaultdict(list)
    for fpath in glob.glob(AGENDA_GLOB):
        date = os.path.basename(fpath)[:10]
        date_to_file[date].append(fpath)

    updated_items = 0
    updated_files = 0

    for fpath in sorted(glob.glob(AGENDA_GLOB)):
        data = json.load(open(fpath))
        date = data["date"]
        changed = False

        for calendar in ("consent_items", "action_items"):
            for item in data.get(calendar, []):
                key = (date, item.get("section", ""), str(item.get("number", "")))
                if key in labels:
                    for field, val in labels[key].items():
                        if val is not None:
                            item[field] = val
                        elif field in item:
                            del item[field]
                    changed = True
                    updated_items += 1
                else:
                    # Clear any stale classification from a previous run
                    for field in ("framework_classification", "framework_category",
                                  "framework_notes", "framework_reason"):
                        item.pop(field, None)

        if changed:
            updated_files += 1
            if not dry_run:
                with open(fpath, "w") as f:
                    json.dump(data, f, indent=2)
                    f.write("\n")
            else:
                print(f"  [dry-run] would update {os.path.basename(fpath)}")

    print(f"{'[dry-run] ' if dry_run else ''}Updated {updated_items} items across {updated_files} files.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?", default=DEFAULT_CSV)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"CSV not found: {args.csv}", file=sys.stderr)
        sys.exit(1)

    ingest(args.csv, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
