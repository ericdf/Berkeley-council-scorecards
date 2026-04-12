#!/usr/bin/env python3
"""
add_newsletter.py
=================
Adds a council member newsletter to newsletter_index.json with auto-computed
P1 keyword coverage classification.

Usage:
    # Add from Gmail message ID
    python3 add_newsletter.py --gmail <message_id> --member Tregub

    # Add from a text file (e.g. Substack post pasted to a file)
    python3 add_newsletter.py --file /path/to/newsletter.txt --member Blackaby \
        --date 2026-03-15 --subject "March 2026 Hills Update" \
        --source "substack.com/blackaby"

    # Add manually (body via stdin)
    python3 add_newsletter.py --stdin --member Kesarwani \
        --date 2026-04-10 --subject "April Update" --source "rkesarwani@berkeleyca.gov"

    # Dry run (print classification without writing)
    python3 add_newsletter.py --gmail <id> --member Tregub --dry-run

The script classifies each newsletter as:
  p1_hit              — one or more P1_TOPIC_KW matches found → no penalty
  rhetoric_no_substance — acknowledges fiscal difficulty but zero P1 keywords → -0.025
  silent              — no fiscal language at all → -0.015
  atm_framing         — promotes bond/tax as solution without cut alternative → mark manually
  skip                — not a regular constituent newsletter

After adding, run ./generate.sh --scores-only to recompute scores.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from council_scorecard import P1_TOPIC_KW

INDEX_PATH = os.path.join(os.path.dirname(__file__), "newsletter_index.json")
FISCAL_CRISIS_START = "2024-07-01"

# Phrases that constitute rhetorical fiscal acknowledgment without substance
RHETORIC_PAT = re.compile(
    r"(challeng\w+\s+budget\w*(?:\s+year)?"
    r"|difficult\w*\s+(?:budget\w*|fiscal|financial|year)"
    r"|difficult\w*\s+times?\s+(?:in\s+the\s+city|for\s+the\s+city|fiscally)"
    r"|fiscally\s+difficult"
    r"|balancing\s+(?:our|the|a)\s+(?:ledger|budget)"
    r"|tight\w*\s+budget"
    r"|budget\w*\s+(?:gap|shortfall|deficit|pressure|constraint|crunch)"
    r"|(?:raise|increase)\s+revenue\s+(?:as\s+a\s+city|for\s+the\s+city)"
    r"|cut\w*\s+(?:expenses|spending|costs?)\s+(?:as\s+a\s+city|for\s+the\s+city)"
    r"|difficult\w*\s+(?:year|times?|period)\s+for\s+(?:the\s+)?(?:city|Berkeley)"
    r"|one\s+of\s+the\s+more\s+difficult)",
    re.I,
)


def _check_p1(text: str) -> list[str]:
    """Return list of P1_TOPIC_KW patterns that match in text."""
    hits = []
    for pat in P1_TOPIC_KW:
        if re.search(pat, text, re.I):
            hits.append(pat)
    return hits


def _check_rhetoric(text: str) -> tuple[bool, list[str]]:
    """Return (has_rhetoric, list_of_matching_quotes)."""
    quotes = []
    for m in RHETORIC_PAT.finditer(text):
        # grab a little context around the match
        start = max(0, m.start() - 20)
        end = min(len(text), m.end() + 60)
        quotes.append(text[start:end].replace("\n", " ").strip())
    return bool(quotes), quotes[:3]  # cap at 3 example quotes


def classify(body: str) -> tuple[str, list[str], bool, list[str]]:
    """
    Returns (classification, p1_keywords_found, fiscal_rhetoric, rhetoric_quotes).
    """
    p1_hits = _check_p1(body)
    has_rhetoric, rhetoric_quotes = _check_rhetoric(body)

    if p1_hits:
        classification = "p1_hit"
    elif has_rhetoric:
        classification = "rhetoric_no_substance"
    else:
        classification = "silent"

    return classification, p1_hits, has_rhetoric, rhetoric_quotes


def _load_index() -> dict:
    with open(INDEX_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_index(data: dict, dry_run: bool) -> None:
    if dry_run:
        return
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _is_duplicate(newsletters: list, member: str, date: str, subject: str) -> bool:
    for n in newsletters:
        if n["member"] == member and n["date"] == date:
            return True
        if n["member"] == member and n.get("subject", "").strip() == subject.strip():
            return True
    return False


def add_from_body(
    body: str,
    member: str,
    date: str,
    subject: str,
    source: str,
    source_type: str = "unknown",
    gmail_id: str | None = None,
    existing_incident: bool = False,
    existing_incident_ref: str = "",
    notes: str = "",
    dry_run: bool = False,
) -> dict:
    classification, p1_hits, has_rhetoric, rhetoric_quotes = classify(body)

    entry = {
        "member":              member,
        "date":                date,
        "source":              source,
        "source_type":         source_type,
        "subject":             subject,
        "p1_keywords_found":   p1_hits,
        "fiscal_rhetoric":     has_rhetoric,
        "fiscal_rhetoric_quotes": rhetoric_quotes,
        "classification":      classification,
        "existing_incident":   existing_incident,
        "notes":               notes,
    }
    if gmail_id:
        entry["gmail_id"] = gmail_id
    if existing_incident_ref:
        entry["existing_incident_ref"] = existing_incident_ref

    data = _load_index()
    newsletters = data.get("newsletters", [])

    if _is_duplicate(newsletters, member, date, subject):
        print(f"WARNING: duplicate entry for {member} {date} — skipping.")
        return entry

    newsletters.append(entry)
    data["newsletters"] = newsletters
    _save_index(data, dry_run)

    prefix = "[DRY RUN] " if dry_run else ""
    penalty_map = {
        "p1_hit":               "no penalty",
        "rhetoric_no_substance": "-0.025",
        "silent":               "-0.015",
        "atm_framing":          "0 (incident handles it)",
        "skip":                 "no penalty",
    }
    print(f"{prefix}Added: {member} {date} — {classification} ({penalty_map.get(classification, '?')})")
    if p1_hits:
        print(f"  P1 keywords: {', '.join(p1_hits[:5])}")
    if rhetoric_quotes:
        print(f"  Fiscal rhetoric: {rhetoric_quotes[0][:100]}")
    return entry


def _read_gmail(message_id: str) -> tuple[str, str, str, str]:
    """
    Read a Gmail message.  Returns (body, date, subject, from_address).
    Requires the MCP Gmail tool — not available as a plain Python call.
    Print instructions instead.
    """
    print(f"To add a Gmail newsletter, run this in a Claude session:")
    print(f"  gmail_read_message('{message_id}')")
    print(f"Then pipe the body text to this script via --stdin.")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Add a newsletter to newsletter_index.json")
    parser.add_argument("--member", required=True,
                        help="Member key (e.g. Tregub, Blackaby)")
    parser.add_argument("--date",
                        help="Date YYYY-MM-DD (required for --file and --stdin)")
    parser.add_argument("--subject",
                        help="Newsletter subject/title")
    parser.add_argument("--source",
                        help="Source email address or URL")
    parser.add_argument("--source-type", default="unknown",
                        choices=["gmail", "substack", "city_email", "unknown"])
    parser.add_argument("--gmail",
                        help="Gmail message ID (prints instructions for fetching)")
    parser.add_argument("--file",
                        help="Path to text file containing newsletter body")
    parser.add_argument("--stdin", action="store_true",
                        help="Read newsletter body from stdin")
    parser.add_argument("--existing-incident", action="store_true",
                        help="Newsletter already has a scored incident — skip silence penalty")
    parser.add_argument("--existing-incident-ref",
                        help="Reference to the existing incident (e.g. 'incidents.json Tregub 2026-04-11')")
    parser.add_argument("--notes", default="",
                        help="Free-text notes about this newsletter")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print classification without writing to index")
    args = parser.parse_args()

    if args.gmail:
        _read_gmail(args.gmail)
        return

    if args.file:
        body = open(args.file, encoding="utf-8").read()
    elif args.stdin:
        print("Paste newsletter body, then press Ctrl+D:")
        body = sys.stdin.read()
    else:
        parser.error("Provide --gmail, --file, or --stdin")
        return

    if not args.date:
        parser.error("--date is required with --file or --stdin")

    add_from_body(
        body=body,
        member=args.member,
        date=args.date,
        subject=args.subject or "",
        source=args.source or "",
        source_type=args.source_type,
        existing_incident=args.existing_incident,
        existing_incident_ref=args.existing_incident_ref or "",
        notes=args.notes,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
