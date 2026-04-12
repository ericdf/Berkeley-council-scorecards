#!/usr/bin/env python3
"""
ingest_amendment_labels.py
==========================
Reads a labeled amendment_review.csv produced by generate_amendment_review.py
and appends positive/negative rows as new incidents into incidents.json.

Usage:
    python3 ingest_amendment_labels.py agendas/amendment_review.csv [--dry-run]

Only rows with label == "positive" or label == "negative" are ingested.
Rows with label "neutral" or "skip" are silently skipped.

Incident format written:
  {
    "date":           "YYYY-MM-DD",
    "category":       "fiscal_integrity"  (positive) | "atm_behavior" (negative),
    "evidence_tier":  "A",                # vote-record level: amendment is on-record
    "description":    "<notes field>  [Amendment text: <first 300 chars of amendment_turn>]",
    "source":         "Amendment motion — <meeting_type> meeting <date>; item <n>: <title>",
    "scoring_impact": <float from scoring_impact column>,
    "_from_amendment_review": true        # sentinel so these can be audited/re-ingested
  }

Re-ingestion safety:
  Before writing, the script removes any incidents previously written by this
  tool (identified by _from_amendment_review == true) for the same member,
  then writes the new set.  This means you can re-run after re-labeling without
  accumulating duplicates.
"""

import csv
import json
import os
import sys

INCIDENTS_PATH = os.path.join(os.path.dirname(__file__), "incidents.json")
SENTINEL = "_from_amendment_review"

LABEL_CATEGORY = {
    "positive": "fiscal_integrity",
    "negative": "atm_behavior",
}

# Members as stored in DISPLAY_NAME → key used in incidents.json
# We need to map display names back to the incidents.json top-level keys,
# which use last names.  Build this from council_scorecard constants.
import sys as _sys
_sys.path.insert(0, os.path.dirname(__file__))
from council_scorecard import CANONICAL_MEMBERS, DISPLAY_NAME

# Invert: display_name → canonical_key (last name / incidents key)
_DISPLAY_TO_KEY = {v: k for k, v in DISPLAY_NAME.items()}


def _incidents_key(display: str) -> str | None:
    """Return the incidents.json top-level key for a display name."""
    return _DISPLAY_TO_KEY.get(display)


def _load_incidents() -> dict:
    with open(INCIDENTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_incidents(data: dict, dry_run: bool) -> None:
    if dry_run:
        return
    with open(INCIDENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _build_incident(row: dict) -> dict:
    """Convert a labeled CSV row to an incident dict."""
    notes = row.get("notes", "").strip()
    amendment_text = row.get("amendment_turn", "").strip()[:300]
    if amendment_text and not amendment_text.endswith((".", "?", "!")):
        amendment_text += "..."

    if notes:
        description = f"{notes}  [Amendment text: {amendment_text}]"
    else:
        description = f"Amendment motion.  [Amendment text: {amendment_text}]"

    item_num   = row.get("item_number", "").strip()
    item_title = row.get("item_title", "").strip()
    mtype      = row.get("meeting_type", "Regular").strip()
    date       = row.get("date", "").strip()

    if item_num and item_title:
        source = f"Amendment motion — {mtype} meeting {date}; item {item_num}: {item_title}"
    elif item_num:
        source = f"Amendment motion — {mtype} meeting {date}; item {item_num}"
    else:
        source = f"Amendment motion — {mtype} meeting {date}"

    agenda_url = row.get("agenda_url", "").strip()
    if agenda_url:
        source += f"  ({agenda_url})"

    raw_impact = row.get("scoring_impact", "").strip()
    try:
        impact = float(raw_impact)
    except (ValueError, TypeError):
        label = row.get("label", "").strip().lower()
        impact = 0.04 if label == "positive" else -0.04

    inc = {
        "date":          date,
        "category":      LABEL_CATEGORY[row["label"].strip().lower()],
        "evidence_tier": "A",
        "description":   description,
        "source":        source,
        "scoring_impact": impact,
        SENTINEL:        True,
    }
    return inc


def ingest(csv_path: str, dry_run: bool = False) -> None:
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    labeled = [r for r in rows if r.get("label", "").strip().lower() in LABEL_CATEGORY]
    if not labeled:
        print("No positive/negative rows found — nothing to ingest.")
        return

    data = _load_incidents()

    # Group rows by member key
    by_member: dict[str, list[dict]] = {}
    skipped = []
    for row in labeled:
        display = row.get("member", "").strip()
        key = _incidents_key(display)
        if key is None:
            skipped.append(display)
            continue
        by_member.setdefault(key, []).append(row)

    if skipped:
        print(f"WARNING: could not map display names to incident keys: {set(skipped)}")

    added = replaced = 0
    for key, member_rows in by_member.items():
        existing: list = data.get(key, [])

        # Remove previously auto-ingested incidents (re-ingestion safety)
        pre_count = len(existing)
        existing = [inc for inc in existing if not inc.get(SENTINEL)]
        replaced += pre_count - len(existing)

        new_incidents = [_build_incident(r) for r in member_rows]
        existing.extend(new_incidents)
        added += len(new_incidents)

        data[key] = existing

    _save_incidents(data, dry_run)

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Ingested {added} amendment incidents into {INCIDENTS_PATH}")
    if replaced:
        print(f"{prefix}Replaced {replaced} previously auto-ingested incidents")
    print()

    # Summary by member
    for key, member_rows in sorted(by_member.items()):
        pos = sum(1 for r in member_rows if r["label"].strip().lower() == "positive")
        neg = sum(1 for r in member_rows if r["label"].strip().lower() == "negative")
        display = DISPLAY_NAME.get(key, key)
        parts = []
        if pos:
            parts.append(f"+{pos} positive")
        if neg:
            parts.append(f"{neg} negative")
        print(f"  {display}: {', '.join(parts)}")

    print()
    print("Next step: run pipeline.py (--no-pdf) to recompute scores.")


if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    paths = [a for a in args if not a.startswith("--")]

    if not paths:
        print("Usage: python3 ingest_amendment_labels.py agendas/amendment_review.csv [--dry-run]")
        sys.exit(1)

    ingest(paths[0], dry_run=dry_run)
