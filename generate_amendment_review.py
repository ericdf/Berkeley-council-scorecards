#!/usr/bin/env python3
"""
generate_amendment_review.py
============================
Scans all council transcripts for amendment and substitute-motion turns,
enriches each with surrounding context and agenda metadata, and writes
a CSV for manual labeling.

Output: agendas/amendment_review.csv

Labeling workflow
-----------------
Open the CSV in a spreadsheet.  For each row:

  label column values:
    positive  — amendment introduces accountability/metrics, finds cost-neutral
                funding, or redirects from non-P1 to P1 without new taxes.
                These will become incidents (fiscal_integrity category).
    negative  — amendment cuts P1 (fire/police/streets) to fund non-P1,
                or games the budget (unfilled positions, salary lapse tricks).
                These will become incidents (atm_behavior category).
    neutral   — procedural tweak, language fix, no fiscal/P1 significance.
                Discarded.
    skip      — context insufficient; opening the agenda URL is required
                and reviewer decided not to.

  scoring_impact column (fill only for positive/negative rows):
    Suggested: +0.04 for a clear accountability amendment, +0.03 for a
    modest improvement, -0.03 to -0.05 for a gaming amendment.

  notes column:
    Free text.  Quote the specific language that justifies the label.

After labeling, run:
    python3 ingest_amendment_labels.py agendas/amendment_review.csv
to append the labeled rows as new incidents into incidents.json.
"""

import csv
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from council_scorecard import (
    clean, detect_format, parse_chevron, parse_boardroom, parse_vtt,
    CANONICAL_MEMBERS, DISPLAY_NAME,
)
from pipeline import TEXT_DIR, AGENDAS_DIR

OUTPUT_PATH = os.path.join(AGENDAS_DIR, "amendment_review.csv")

# ── Amendment motion detection ────────────────────────────────────────────────
# Captures council members MAKING an amendment or substitute motion (not just
# discussing or asking about one).  Real council usage is more varied than
# formal parliamentary language, so we cast wide and rely on the CANONICAL_MEMBERS
# guard below to exclude staff/public-comment turns.
AMEND_PAT = re.compile(
    # formal "I move to amend / I move a substitute/friendly"
    r"(i\s+move\s+(?:to\s+amend|a\s+(?:substitute|friendly))"
    # "I [will|can|shall] [make|offer|create|introduce] a substitute/friendly [motion|amendment]"
    r"|i\s+(?:will|can|shall|'ll)\s+(?:make|offer|create|introduce)\s+a\s+(?:substitute|friendly)\s+(?:motion|amendment)"
    # "I would like to [make|offer|create|introduce] a substitute/friendly"
    r"|i\s+would\s+like\s+to\s+(?:make|offer|create|introduce)\s+a\s+(?:substitute|friendly)\s+(?:motion|amendment)"
    # "I [will|can|'ll] amend my/the motion/proposal"
    r"|i\s+(?:will|can|'ll)\s+amend\s+(?:my|the|this)\s+(?:motion|proposal|item)"
    # "I would like to amend / I want to amend"
    r"|i\s+(?:would\s+like\s+to|want\s+to)\s+amend\s+(?:my|the|this)\s+(?:motion|proposal|item)"
    # "offer a/an friendly/substitute amendment"
    r"|i\s+(?:would\s+like\s+to\s+)?offer\s+(?:a|an)\s+(?:friendly\s+|substitute\s+)?amendment"
    # "introduce a/an friendly amendment"
    r"|i\s+(?:would\s+like\s+to\s+)?introduce\s+(?:a|an)\s+(?:friendly\s+)?amendment"
    # "this [would be|is] my substitute motion" — speaker claiming ownership
    r"|(?:this\s+(?:would\s+be|is)\s+my\s+substitute\s+motion)"
    # "I'm going to [try and] substitute motion" (unusual but real)
    r"|i\s+'?m\s+going\s+to\s+(?:try\s+and\s+)?substitute\s+motion"
    # "FRIENDLY AMENDMENT" at the very start of a turn (speaker is proposing)
    r"|^(?:a\s+)?friendly\s+amendment[,\s]"
    # "substitute motion to [adopt/accept/include...]"
    r"|substitute\s+motion\s+to\s+(?:adopt|accept|include|exclude|keep|remove|change|add|delete))",
    re.I,
)

# ── Loose pre-classification hints (for reviewer triage only — not scored) ────
POS_HINT = re.compile(
    r"(require\s+(?:staff|the\s+city|department|city\s+manager)\s+to\s+(?:report|track|measure|provide|submit)"
    r"|add\s+(?:a\s+)?(?:reporting|accountability|performance|outcome|metric)"
    r"|condition\s+(?:the\s+funding|approval|this)\s+on"
    r"|cost.neutral"
    r"|offset\s+(?:the\s+cost|this|by)"
    r"|reprioritize\s+within"
    r"|(?:redirect|reallocate)\s+(?:existing|current|appropriated)"
    r"|no\s+(?:new|additional)\s+(?:tax|revenue|cost)"
    r"|within\s+existing\s+(?:budget|appropriation|fund))",
    re.I,
)

NEG_HINT = re.compile(
    r"(unfilled\s+(?:position|role|slot)"
    r"|vacant\s+position"
    r"|salary\s+(?:saving|lapse|reversion)"
    r"|position\s+lapse"
    r"|cut\s+(?:police|fire|paramedic|ems|street|infrastructure|maintenance)"
    r"(?!.*no\s+cut))",  # avoid false positives from "no cuts to fire"
    re.I,
)


# ── Agenda index: date → {url, items: {number: title}} ───────────────────────
def _build_agenda_index() -> dict:
    index = {}
    for path in sorted(glob.glob(os.path.join(AGENDAS_DIR, "*.json"))):
        try:
            d = json.load(open(path))
        except Exception:
            continue
        date = d.get("date")
        if not date:
            continue
        items = {}
        for item in d.get("consent_items", []) + d.get("action_items", []):
            n = item.get("number")
            t = item.get("title") or item.get("description") or ""
            if n is not None:
                items[int(n)] = t[:120]
        index[date] = {"url": d.get("url", ""), "items": items}
    return index


# ── Extract best-guess item number from preceding turns ──────────────────────
_ITEM_NUM_RE = re.compile(r"\bitem\s+#?(\d+)\b", re.I)

def _guess_item(preceding_turns: list[str]) -> int | None:
    for body in reversed(preceding_turns):
        m = _ITEM_NUM_RE.search(body)
        if m:
            return int(m.group(1))
    return None


# ── Parse filename to date + meeting_type ────────────────────────────────────
def _parse_fname(fname: str) -> tuple[str, str]:
    # e.g. "BCC 2025-10-28 Regular.txt" or "BCC 2025-03-11 Special.txt"
    m = re.search(r"(\d{4}-\d{2}-\d{2})", fname)
    date = m.group(1) if m else ""
    mtype = "Special" if "special" in fname.lower() else "Regular"
    return date, mtype


# ── Main ──────────────────────────────────────────────────────────────────────
def generate():
    agenda_index = _build_agenda_index()
    rows = []

    for path in sorted(glob.glob(os.path.join(TEXT_DIR, "*.txt"))):
        raw = clean(open(path, encoding="utf-8", errors="replace").read())
        fmt = detect_format(raw)
        date, mtype = _parse_fname(os.path.basename(path))

        if fmt == "chevron":
            turns = list(parse_chevron(raw))
        elif fmt == "boardroom":
            turns = list(parse_boardroom(raw))
        elif fmt == "vtt":
            turns = [(c, b) for c, b, _ in parse_vtt(raw)]
        else:
            continue

        meta = agenda_index.get(date, {})
        agenda_url = meta.get("url", "")
        agenda_items = meta.get("items", {})

        for i, (canonical, body) in enumerate(turns):
            if not canonical or not AMEND_PAT.search(body):
                continue
            if canonical not in CANONICAL_MEMBERS:
                continue

            # Surrounding context
            before = turns[max(0, i - 3): i]          # up to 3 turns before
            after  = turns[i + 1: min(len(turns), i + 3)]  # up to 2 turns after

            def _fmt_ctx(ctx_turns):
                return " | ".join(
                    f"[{DISPLAY_NAME.get(c, c) if c else '?'}] {b[:120]}"
                    for c, b in ctx_turns
                )

            before_ctx = _fmt_ctx(before)
            after_ctx  = _fmt_ctx(after)

            # Item number + title
            item_num = _guess_item([b for _, b in before])
            item_title = agenda_items.get(item_num, "") if item_num else ""

            # Pre-classification hint for triage
            window = body + " " + " ".join(b for _, b in after)
            if POS_HINT.search(window):
                prelabel = "LIKELY_POS"
            elif NEG_HINT.search(window):
                prelabel = "LIKELY_NEG"
            else:
                prelabel = ""

            rows.append({
                "date":           date,
                "meeting_type":   mtype,
                "item_number":    item_num or "",
                "item_title":     item_title,
                "member":         DISPLAY_NAME.get(canonical, canonical),
                "amendment_turn": body.strip(),
                "before_context": before_ctx,
                "after_context":  after_ctx,
                "agenda_url":     agenda_url,
                "prelabel":       prelabel,
                # reviewer fills these:
                "label":          "",
                "scoring_impact": "",
                "notes":          "",
            })

    rows.sort(key=lambda r: (r["date"], r["member"]))

    fieldnames = [
        "date", "meeting_type", "item_number", "item_title",
        "member", "amendment_turn", "before_context", "after_context",
        "agenda_url", "prelabel",
        "label", "scoring_impact", "notes",
    ]
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} amendment turns → {OUTPUT_PATH}")
    likely_pos  = sum(1 for r in rows if r["prelabel"] == "LIKELY_POS")
    likely_neg  = sum(1 for r in rows if r["prelabel"] == "LIKELY_NEG")
    print(f"  Pre-classified: {likely_pos} LIKELY_POS, {likely_neg} LIKELY_NEG, "
          f"{len(rows) - likely_pos - likely_neg} unlabeled")
    print()
    print("Next step: open agendas/amendment_review.csv in a spreadsheet,")
    print("fill in label / scoring_impact / notes columns, then run:")
    print("  python3 ingest_amendment_labels.py agendas/amendment_review.csv")


if __name__ == "__main__":
    generate()
