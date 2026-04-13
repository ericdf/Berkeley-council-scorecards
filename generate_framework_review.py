#!/usr/bin/env python3
"""
generate_framework_review.py

Classifies all agenda items against fiscal_framework.json using keyword
rules and outputs agendas/framework_review.csv for human review.

Conservative by design: defaults to 'neutral'. Only flags items where
there is clear keyword evidence of a non-neutral classification.
All non-neutral pre-labels should be reviewed before ingestion.

Usage:
    python3 generate_framework_review.py [--dry-run] [--non-neutral-only]

    --dry-run           Print summary without writing CSV
    --non-neutral-only  Only write non-neutral rows to CSV (faster review)
"""

import argparse
import csv
import glob
import json
import os
import re
import sys

AGENDA_GLOB    = "agendas/20*.json"
FRAMEWORK_FILE = "fiscal_framework.json"
OUTPUT_CSV     = "agendas/framework_review.csv"

# ── Keyword patterns ──────────────────────────────────────────────────────────
# Each rule: (classification, framework_category_or_None, pattern, reason_template)
# Rules are evaluated in order; first match wins.
# Be conservative — a wrong non-neutral is worse than a missed one.

F = re.IGNORECASE

RULES = [

    # ── entrenches_cost_premium: labor agreements — MUST be first ────────────────
    # Fire before p1_direct to prevent pension keywords in MOUs from
    # being misclassified as structural reform.
    ("entrenches_cost_premium", "3E", re.compile(
        r"\b(adopt\w*\s+(successor\s+)?(memorandum\s+of\s+(agreement|understanding)|MOU|side\s+letter)"
        r"|side\s+letter\s+(agreement|between|with)"
        r"|successor\s+(MOU|memorandum|agreement)"
        r"|memorandum\s+of\s+(agreement|understanding)\s+(between|with|adopt)"
        r"|collective\s+bargaining\s+agreement"
        r"|(SEIU|IBEW|BFFA|BPA|AFSCME|Teamsters|union)\s+(contract|MOU|agreement|side\s+letter)"
        r"|labor\s+(agreement|contract|MOU)\s+(adopt|approv|ratif)"
        r"|ratif(y|ication)\s+of\s+(the\s+)?(agreement|MOU|contract))\b", F),
     "labor agreement/MOU — locks in compensation and pension carry cost"),

    # ── revenue_seeking ───────────────────────────────────────────────────────
    # Bond measures, tax measures, ballot language — clearly revenue-seeking
    # unless paired with a cut (hard to detect by keyword, so flag all)
    ("revenue_seeking", None, re.compile(
        r"\b(general\s+obligation\s+bond|sales\s+tax|parcel\s+tax|special\s+tax"
        r"|place\s+on\s+(the\s+)?ballot|ballot\s+(measure|language|question)"
        r"|revenue\s+measure|bond\s+measure|tax\s+and\s+revenue\s+anticipation"
        r"|issuance\s+of\s+bonds|bond\s+financing|bond\s+program"
        r"|community\s+survey.*poll|poll.*sales\s+tax|sales\s+tax.*survey)\b", F),
     "bond/tax/ballot measure"),

    # ── p1_direct ─────────────────────────────────────────────────────────────
    # Directly addresses documented P1 problems
    ("p1_direct", None, re.compile(
        r"\b(street\s+(rehab|paving|repair|resurfac|reconstruct|mainten)"
        r"|pavement\s+(rehab|repair|condition|management)"
        r"|sidewalk\s+(repair|rehab|mainten)"
        r"|storm\s+drain\s+(repair|rehab|replace)"
        r"|infrastructure\s+(backlog|deficit|repair|bond)"
        r"|section\s+115\s+trust"
        r"|stabilization\s+reserve|catastrophic\s+reserve"
        r"|reserve\s+(fund|policy|adequacy)"
        r"|structural\s+deficit|long.?term\s+(fiscal|financial)\s+(sustain|balance)"
        r"|CalPERS|OPEB|pension\s+(reform|obligation|fund|sustainab)"
        r"|unfunded\s+(liability|actuarial)"
        r"|city\s+auditor.*recommendation|audit.*finding.*implement)\b", F),
     "directly addresses P1 infrastructure/fiscal problem"),

    # ── adds_non_core: homelessness / housing services ────────────────────────
    ("adds_non_core", "1B", re.compile(
        r"\b(homeless\s+(services|outreach|response|shelter|program|encampment)"
        r"|unhoused\s+(services|outreach|response)"
        r"|housing\s+(navigation|case\s+manag|stability|trust\s+fund\s+loan)"
        r"|rapid\s+re.?housing|permanent\s+support\s+(housing|ive)"
        r"|homeless(ness)?\s+prevention"
        r"|step.?up\s+housing|transitional\s+housing\s+program"
        r"|shelter\s+(contract|services|operations|expansion)"
        r"|BOSS\b|BFHP|coordinated\s+entry)\b", F),
     "homeless/housing services program"),

    # ── adds_non_core: public health overlays ─────────────────────────────────
    ("adds_non_core", "1A", re.compile(
        r"\b(health\s+(outreach|education|program|clinic|equity|access)"
        r"|mental\s+health\s+(services|program|contract|outreach)"
        r"|substance\s+(use|abuse)\s+(treatment|program|services)"
        r"|harm\s+reduction|needle\s+exchange|opioid\s+treatment"
        r"|community\s+health\s+(worker|program|navigator)"
        r"|MHSA\b|behavioral\s+health\s+(program|services|contract)"
        r"|public\s+health\s+(program|contract|grant|outreach))\b", F),
     "public health program/contract"),

    # ── adds_non_core: arts / cultural ────────────────────────────────────────
    ("adds_non_core", "1E", re.compile(
        r"\b(arts?\s+(grant|fund|program|commission|organization|council)"
        r"|cultural\s+(grant|program|organization|center|event)"
        r"|festival\s+(grant|support|fund)"
        r"|nonprofit\s+(grant|arts|cultural)"
        r"|performing\s+arts|public\s+art\s+(fund|grant|program)"
        r"|arts?\s+and\s+culture\s+(grant|fund|program))\b", F),
     "arts/cultural grant or program"),

    # ── adds_non_core: climate / sustainability ────────────────────────────────
    ("adds_non_core", "2C", re.compile(
        r"\b(climate\s+(action|plan|program|fund|staff|coordinator|resilience)"
        r"|electrification\s+(program|rebate|incentive|fund)"
        r"|zero\s+(carbon|emission)\s+program"
        r"|sustainability\s+(program|coordinator|plan|office)"
        r"|green\s+(new\s+deal|infrastructure\s+program|building\s+program)"
        r"|clean\s+energy\s+(program|fund|transition)"
        r"|decarbonization\s+program)\b", F),
     "climate/sustainability program"),

    # ── adds_non_core: workforce / youth ──────────────────────────────────────
    ("adds_non_core", "1C", re.compile(
        r"\b(workforce\s+(development|training|program)"
        r"|job\s+training\s+program|youth\s+(employment|jobs?\s+program)"
        r"|summer\s+(youth|jobs?|employment|program)"
        r"|youthworks?|youth\s+worker|apprenticeship\s+program"
        r"|first\s+source\s+(hiring|program|fund))\b", F),
     "workforce/youth development program"),

    # ── adds_non_core: recreation subsidies ───────────────────────────────────
    ("adds_non_core", "1F", re.compile(
        r"\b(recreation\s+(subsid|scholarship|fee\s+waiver|program\s+fund)"
        r"|camp\s+(scholarship|subsid|fund|program\s+grant)"
        r"|aquatic\s+program\s+(subsid|scholarship)"
        r"|parks?\s+(program\s+subsid|recreation\s+grant))\b", F),
     "recreation subsidy program"),

    # ── adds_non_core: alternative public safety ──────────────────────────────
    ("adds_non_core", "2A", re.compile(
        r"\b(violence\s+prevention\s+(program|fund|contract|grant|coordinator)"
        r"|community\s+ambassador\s+program"
        r"|crisis\s+(response|intervention)\s+(program|team|contract)"
        r"|mental\s+health\s+(crisis|response)\s+(team|unit|program)"
        r"|MACRO\b|alternative\s+(response|crisis\s+response)"
        r"|restorative\s+justice\s+(program|fund|grant))\b", F),
     "alternative public safety program"),

    # ── adds_non_core: equity/targeted programs ────────────────────────────────
    ("adds_non_core", "2E", re.compile(
        r"\b(equity\s+(program|fund|initiative|grant|office)"
        r"|racial\s+(equity|justice)\s+(program|fund|initiative)"
        r"|reparations?\s+(program|fund|study|pilot)"
        r"|targeted\s+(outreach|program|service)\s+for"
        r"|AAHRC|African\s+American\s+Holistic"
        r"|black\s+(community|wellness|resource)\s+(center|program|fund))\b", F),
     "equity/targeted program"),

    # ── entrenches_cost_premium: new in-house positions ───────────────────────
    ("entrenches_cost_premium", "3E", re.compile(
        r"\b(add\s+(\w+\s+)?FTE|new\s+(permanent|full.?time|part.?time)\s+(position|staff)"
        r"|authorize\s+(\w+\s+)?new\s+(position|hire)"
        r"|establish\s+(\w+\s+)?new\s+(position|class(ification)?)"
        r"|(\d+\s+)?new\s+(FTE|position)"
        r"|expand\s+(staffing|staff|workforce)\s+by"
        r"|new\s+class(ification)?\s+(title|spec|establish))\b", F),
     "authorizes new city employee position(s)"),

]

# ── Patterns that PREVENT a non-neutral classification ────────────────────────
# Items matching these are forced to neutral regardless of above rules.
# Catches grant acceptances (city not spending GF), renewals, etc.
NEUTRAL_OVERRIDE_RE = re.compile(
    r"\b(accept\s+(and\s+)?appropriat|accept\s+(the\s+)?grant|grant\s+acceptance"
    r"|receipt\s+of\s+(grant|fund)|grant\s+contract.*accept"
    r"|minutes\s+for\s+approval|formal\s+bid\s+solicitation"
    r"|adjourn|proclamation|certificate\s+of\s+recognition|in\s+memory\s+of"
    r"|appointment\s+to|reappointment|oath\s+of\s+office"
    r"|final\s+map|subdivision|use\s+permit|variance|zoning"
    r"|publicly\s+available\s+pay\s+schedule"  # CalPERS reporting requirement, not P1 action
    r"|pay\s+schedule\s+(adopt|approv|establish))\b",
    F
)

# ── P1 override: street paving contracts are p1_direct, not neutral ───────────
P1_CONTRACT_RE = re.compile(
    r"\b(contract.*street\s+(paving|rehab|mainten|resurfac)"
    r"|street.*paving.*contract"
    r"|paving.*grading.*contract"
    r"|pavement\s+(rehab|management)\s+contract)\b", F
)


def classify(item: dict) -> tuple[str, str | None, str]:
    """Returns (classification, framework_category, reason)."""
    title = item.get("title", "")
    rec   = item.get("recommendation", "")
    text  = (title + " " + rec).strip()

    # P1 contract override before neutral check
    if P1_CONTRACT_RE.search(text):
        return ("p1_direct", None, "street paving/rehab contract")

    # Neutral override — grant acceptances, procedural items
    if NEUTRAL_OVERRIDE_RE.search(text):
        return ("neutral", None, "grant acceptance or procedural item")

    # Keyword rules in priority order
    for classification, category, pattern, reason in RULES:
        if pattern.search(text):
            return (classification, category, reason)

    return ("neutral", None, "no keyword match")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",          action="store_true")
    parser.add_argument("--non-neutral-only", action="store_true",
                        help="Only include non-neutral rows in CSV")
    args = parser.parse_args()

    framework_data = json.load(open(FRAMEWORK_FILE))
    cat_map = {c["id"]: c["label"] for c in framework_data["categories"]}

    rows = []
    counts: dict[str, int] = {}

    for fpath in sorted(glob.glob(AGENDA_GLOB)):
        data = json.load(open(fpath))
        date = data["date"]

        for item in data.get("consent_items", []) + data.get("action_items", []):
            classification, category, reason = classify(item)
            counts[classification] = counts.get(classification, 0) + 1

            if args.non_neutral_only and classification == "neutral":
                continue

            rows.append({
                "date":              date,
                "meeting_file":      os.path.basename(fpath),
                "section":           item.get("section", ""),
                "item_number":       item.get("number", ""),
                "item_title":        item.get("title", "")[:120],
                "authors":           ", ".join(item.get("authors", [])) or item.get("from_raw", ""),
                "dollar_total":      item.get("dollar_total", 0) or 0,
                "recommendation":    item.get("recommendation", "")[:300],
                "prelabel":          classification,
                "framework_category": category or "",
                "category_label":    cat_map.get(category or "", ""),
                "reason":            reason,
                # Human review columns
                "label":             "",
                "override_category": "",
                "notes":             "",
            })

    # Summary
    total = sum(counts.values())
    print(f"\nClassification summary ({total} items):")
    for cls in ["p1_direct", "revenue_seeking", "adds_non_core",
                "entrenches_cost_premium", "addresses_cost_premium",
                "reduces_non_core", "neutral"]:
        n = counts.get(cls, 0)
        print(f"  {cls:28s} {n:4d}  ({n/total*100:.0f}%)")

    non_neutral = total - counts.get("neutral", 0)
    print(f"\n  Non-neutral total: {non_neutral}")

    if args.dry_run:
        print("\nTop non-neutral items:")
        for r in [r for r in rows if r["prelabel"] != "neutral"][:40]:
            print(f"  {r['date']} [{r['section']:7s}] {r['prelabel']:25s} "
                  f"{r['framework_category']:4s}  {r['item_title'][:65]}")
        return

    fieldnames = [
        "date", "meeting_file", "section", "item_number", "item_title",
        "authors", "dollar_total", "recommendation", "prelabel",
        "framework_category", "category_label", "reason",
        "label", "override_category", "notes",
    ]

    with open(OUTPUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"\nWritten: {OUTPUT_CSV}  ({len(rows)} rows)")
    if args.non_neutral_only:
        print("(neutral rows omitted — review non-neutral prelabels, correct in 'label' column)")
    print("Run: python3 ingest_framework_labels.py agendas/framework_review.csv")


if __name__ == "__main__":
    main()
