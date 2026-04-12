"""
Council Analysis Pipeline
=========================
Orchestrates all scoring, saves per-meeting and aggregate JSON,
then calls the PDF generator.

Usage:
    python pipeline.py              # full run
    python pipeline.py --no-pdf     # skip PDF generation
    python pipeline.py --scores-only # print scores, no files written
"""

import argparse
import glob
import json
import os
import re
import shutil
import sys
from collections import defaultdict
from datetime import date, datetime

# -- local modules --
sys.path.insert(0, os.path.dirname(__file__))
from council_scorecard import (
    TEXT_DIR, CANONICAL_MEMBERS, DISPLAY_NAME,
    load_all, build_scoreboard, score_ishii_facilitator,
    clean, resolve_name, WASTE_KW, CORE_KW, FISCAL_CONCERN_KW, REVENUE_SEEKING_KW,
    HSO_SYMPATHY_KW, HSO_SKEPTIC_KW, P1_TOPIC_KW,
)

# Redefine what we need locally (council_scorecard doesn't export these as constants)
import council_scorecard as _cs

SCORES_DIR     = os.path.join(os.path.dirname(__file__), "scores")
AGGREGATE_PATH = os.path.join(SCORES_DIR, "aggregate.json")
MEETINGS_PATH  = os.path.join(SCORES_DIR, "per_meeting.json")
SNAPSHOTS_DIR  = os.path.join(SCORES_DIR, "snapshots")
AGENDAS_DIR    = os.path.join(os.path.dirname(__file__), "agendas")

# ---------------------------------------------------------------------------
# Vote extraction
# ---------------------------------------------------------------------------

ROLLCALL_RE = re.compile(
    r"(?:[A-Z][a-z']{2,15}\??\s+(?:yes|no|aye|nay|abstain|recuse)[.,]?\s*){2,}",
    re.IGNORECASE,
)
PAIR_RE = re.compile(
    r"([A-Z][a-z']{2,15})\??\s+(yes|no|aye|nay|abstain|recuse)",
    re.IGNORECASE,
)

# Match item references in transcript text — used to link votes to agenda items.
# Ordered by specificity: explicit # beats "number N" beats bare "item N".
ITEM_NUM_RE = re.compile(
    r"\bitem\s+(?:is\s+)?#\s*(\d+)\b"  # ITEM #17 / ITEM IS #17
    r"|\bitem\s+number\s+(\d+)\b"       # item number 17
    r"|\bitem\s+(\d+)\b",               # item 17  (lowest-priority fallback)
    re.IGNORECASE,
)

# Words we know are not member names but appear before vote words
FALSE_VOTE_NAMES = {"January","February","March","April","May","June","July","August",
                    "September","October","November","December","Monday","Tuesday",
                    "Wednesday","Thursday","Friday","Saturday","Sunday",
                    "Item","Motion","Vote","All","That","The","And","Or","But",
                    "Madam","Mayor","Vice","City","Clerk","Staff","Public"}


def _norm_vote(v: str) -> str:
    v = v.lower()
    if v in ("yes", "aye"):  return "yes"
    if v in ("no", "nay"):   return "no"
    return "abstain"


def extract_votes_from_text(text: str) -> list[dict]:
    """Return list of vote-event dicts {canonical_name: 'yes'|'no'|'abstain'}."""
    events = []
    for m in ROLLCALL_RE.finditer(text):
        pairs = PAIR_RE.findall(m.group())
        event = {}
        for raw_name, raw_vote in pairs:
            if raw_name in FALSE_VOTE_NAMES:
                continue
            canonical = resolve_name(raw_name)
            if canonical and canonical in CANONICAL_MEMBERS:
                event[canonical] = _norm_vote(raw_vote)
        if len(event) >= 3:          # need at least 3 members to be meaningful
            events.append(event)
    return events


def aggregate_votes(all_events: list[dict]) -> dict:
    """Summarize per-member vote stats and council-wide block rate."""
    member_counts = defaultdict(lambda: defaultdict(int))
    block_count = 0

    for ev in all_events:
        if len(ev) < 3:
            continue
        votes = list(ev.values())
        is_block = len(set(votes)) == 1
        if is_block:
            block_count += 1
        for name, v in ev.items():
            member_counts[name][v] += 1
            member_counts[name]["total"] += 1
            if not is_block:
                member_counts[name]["independent"] += 1

    total_events = len(all_events)
    block_rate = block_count / total_events if total_events else 0.0

    result = {
        "_council": {
            "total_vote_events": total_events,
            "block_vote_events": block_count,
            "block_vote_rate": block_rate,
        }
    }
    for name in CANONICAL_MEMBERS:
        c = member_counts.get(name, {})
        tot = c.get("total", 0)
        result[name] = {
            "vote_yes":       c.get("yes", 0),
            "vote_no":        c.get("no",  0),
            "vote_abstain":   c.get("abstain", 0),
            "vote_total":     tot,
            "vote_yes_rate":  c.get("yes", 0) / tot if tot else None,
            "vote_abstain_rate": c.get("abstain", 0) / tot if tot else None,
            "vote_independent": c.get("independent", 0),
            "block_vote_rate": block_rate,   # council-wide; same for all
        }

    return result


# ---------------------------------------------------------------------------
# Vote-to-agenda linker
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Chevron-format roll-call: name and vote are on SEPARATE lines
# Pattern:  >> TAPLIN?\n>> YES.   or   >> AND MAYOR ISHII.\n>> YES.
# ---------------------------------------------------------------------------

# Anchors that end a chevron roll-call block.
# Ordered roughly from most to least specific.
_CHEVRON_VOTE_END_RE = re.compile(
    r"motion\s+(?:carries|passes)"
    r"|all\s+ayes"
    r"|unanimously\s+approved"
    r"|if\s+we\s+are\s+all\s+agreed"
    r"|meeting\s+is\s+adjourned"
    r"|vote\s+(?:is\s+)?(\d+.{0,10}to.{0,10}\d+)",
    re.IGNORECASE,
)

# Pattern A: simple alternating lines — >> TAPLIN?\n>> YES.
_CHEV_PAIR_RE = re.compile(
    r">>[ \t]*(?:AND\s+)?(?:MAYOR\s+|COUNCILMEMBER\s+)?([A-Z][A-Z''a-z.\s]{1,20}?)\s*\??\s*\n"
    r"(?:[ \t]*\n)*"                  # optional blank lines
    r">>[ \t]*(?:[A-Z\s.]+:\s*)?"    # optional speaker prefix like "MAYOR ISHII: "
    r"(yes|no|aye|nay|abstain|recuse)[.\s]",
    re.IGNORECASE,
)

# Pattern B: attributed response — >> T. TAPLIN: YES.  or  >> M. HUMBERT: ABSTAIN.
# Content may appear on the same line or on the following line (some transcripts split them).
_CHEV_ATTR_RE = re.compile(
    r">>[ \t]*[A-Z]\.[ \t]+([A-Z][A-Za-z''\-]{2,15}):\s*\n?(?:[ \t]*\n)*\s*"
    r"(yes|no|aye|nay|abstain|recuse)\b",
    re.IGNORECASE,
)

# Pattern C: MAYOR with longer prefix — >> MAYOR A. ISHII: YES.  (same-line or next-line)
_CHEV_MAYOR_RE = re.compile(
    r">>[ \t]*(?:AND\s+)?MAYOR\s+(?:[A-Z]\.[ \t]+)?([A-Z][A-Za-z''\-]{2,15}):\s*\n?(?:[ \t]*\n)*\s*"
    r"(yes|no|aye|nay|abstain|recuse)\b",
    re.IGNORECASE,
)


def _extract_chevron_rollcall(block: str) -> dict:
    """
    Extract {canonical: vote} from a chevron-format roll-call block.

    Tries three strategies in order, keeping whichever yields the most members:

    A  Simple alternating lines:   >> TAPLIN?\n>> YES.
    B  Attributed responses:       >> T. TAPLIN: YES.  (same or next line)
    C  State-machine (Clerk calls name, member answers bare YES/NO on next line):
           >> CLERK: TAPLIN.\n>> YES.
    """
    votes_a: dict[str, str] = {}
    for m in _CHEV_PAIR_RE.finditer(block):
        raw_name = re.sub(r"[.\s]+$", "", m.group(1).strip())
        if raw_name.upper() in {n.upper() for n in FALSE_VOTE_NAMES}:
            continue
        canonical = resolve_name(raw_name.split()[-1])
        if canonical and canonical in CANONICAL_MEMBERS:
            votes_a[canonical] = _norm_vote(m.group(2))

    votes_b: dict[str, str] = {}
    for m in _CHEV_ATTR_RE.finditer(block):
        canonical = resolve_name(m.group(1))
        if canonical and canonical in CANONICAL_MEMBERS:
            votes_b[canonical] = _norm_vote(m.group(2))
    for m in _CHEV_MAYOR_RE.finditer(block):
        canonical = resolve_name(m.group(1))
        if canonical and canonical in CANONICAL_MEMBERS:
            votes_b[canonical] = _norm_vote(m.group(2))

    votes_c = _clerk_calls_name_rollcall(block)

    # Return the strategy that identifies the most council members
    best = max([votes_a, votes_b, votes_c], key=len)
    return best


# Matches a Clerk line that calls a single member's name:
#   >> CLERK: TAPLIN.   >> CITY CLERK: COUNCILMEMBER KESARWANI.   >> CITY CLERK: AND MAYOR ISHII.
_CLERK_CALL_RE = re.compile(
    r">>[ \t]*(?:CITY\s+)?(?:CLERK|City\s+Clerk)[:,]?\s+"
    r"(?:COUNCILMEMBER\s+|AND\s+(?:MAYOR\s+)?)?([A-Z][A-Za-z''\-]{2,15})\s*[.?]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# A bare vote on its own chevron line (possibly with a speaker prefix already caught by B)
_BARE_VOTE_RE = re.compile(
    r"^[ \t]*>>[ \t]*(?:[A-Z]\.[ \t]+[A-Za-z''\-]{2,15}:\s*)?"
    r"(yes|no|aye|nay|abstain|recuse)\b",
    re.IGNORECASE | re.MULTILINE,
)


def _clerk_calls_name_rollcall(block: str) -> dict:
    """
    State-machine: scan lines in sequence.
    When the Clerk explicitly names a member, the *next* bare YES/NO line
    (within 4 lines) belongs to that member.
    """
    lines = block.split("\n")
    votes: dict[str, str] = {}
    pending: str | None = None   # canonical name waiting for a vote response
    lines_since_call = 0

    for line in lines:
        cm = _CLERK_CALL_RE.match(line)
        if cm:
            raw = cm.group(1).strip()
            canonical = resolve_name(raw.split()[-1])
            if canonical and canonical in CANONICAL_MEMBERS:
                pending = canonical
                lines_since_call = 0
            continue

        if pending is not None:
            lines_since_call += 1
            vm = _BARE_VOTE_RE.match(line)
            if vm:
                votes[pending] = _norm_vote(vm.group(1))
                pending = None
            elif lines_since_call > 4:
                pending = None   # gave up waiting

    return votes


# Start anchors: "CALLING THE ROLL/ROLE" or "TAKE THE ROLL"
_CHEVRON_VOTE_START_RE = re.compile(
    r"calling\s+the\s+r(?:oll|ole)\b"
    r"|take\s+(?:the\s+)?roll\b",
    re.IGNORECASE,
)


def _make_vote_event(block: str, pos: int, item_refs: list) -> dict | None:
    """
    Given a text block surrounding a roll-call, extract votes + item context.
    Returns None if fewer than 3 members identified.
    """
    votes = _extract_chevron_rollcall(block)
    if len(votes) < 3:
        return None
    local_item = _extract_item_number(block)
    if local_item is not None:
        item_num = local_item
    else:
        prior = [n for ref_pos, n in item_refs if ref_pos < pos]
        item_num = prior[-1] if prior else None
    return {"votes": votes, "item_number": item_num, "pos": pos}


def extract_chevron_votes_with_context(text: str) -> list[dict]:
    """
    Chevron-format vote extractor.

    Uses two complementary strategies to find roll-call blocks:
      • End-anchors  (MOTION CARRIES/PASSES, IF WE ARE ALL AGREED, …):
        look back 1 500 chars from the anchor.
      • Start-anchors (CALLING THE ROLL/ROLE):
        scan forward 1 000 chars from the anchor.

    Deduplicates by proximity: if two anchors yield blocks whose vote sets
    overlap by ≥ 80 %, keep only the one with more members.

    Item-number assignment uses a two-pass forward scan so long debates don't
    break the link.
    """
    item_refs = [(m.start(), int(m.group(1) or m.group(2) or m.group(3)))
                 for m in ITEM_NUM_RE.finditer(text)]

    raw_events: list[dict] = []

    # Strategy 1: end-anchors
    for anchor in _CHEVRON_VOTE_END_RE.finditer(text):
        vote_pos = anchor.start()
        block = text[max(0, vote_pos - 1500): vote_pos]
        ev = _make_vote_event(block, vote_pos, item_refs)
        if ev:
            raw_events.append(ev)

    # Strategy 2: start-anchors (catches rolls that end without a standard phrase)
    for anchor in _CHEVRON_VOTE_START_RE.finditer(text):
        vote_pos = anchor.start()
        block = text[vote_pos: vote_pos + 1000]
        ev = _make_vote_event(block, vote_pos, item_refs)
        if ev:
            raw_events.append(ev)

    if not raw_events:
        return []

    # Deduplicate: merge events within 3 000 chars of each other that share
    # ≥ 80 % of the same members, keeping the one with the most members.
    raw_events.sort(key=lambda e: e["pos"])
    kept: list[dict] = []
    for ev in raw_events:
        merged = False
        for existing in kept:
            if abs(ev["pos"] - existing["pos"]) > 3000:
                continue
            overlap = len(set(ev["votes"]) & set(existing["votes"]))
            union   = len(set(ev["votes"]) | set(existing["votes"]))
            if union and overlap / union >= 0.8:
                # Keep whichever has more members; prefer a named item
                if len(ev["votes"]) > len(existing["votes"]) or (
                    ev["item_number"] is not None and existing["item_number"] is None
                ):
                    existing.update(ev)
                merged = True
                break
        if not merged:
            kept.append(dict(ev))

    return kept


def _extract_item_number(ctx: str) -> int | None:
    """Return the last item number mentioned in ctx (most-recent-before-vote wins)."""
    matches = list(ITEM_NUM_RE.finditer(ctx))
    if not matches:
        return None
    m = matches[-1]
    raw = m.group(1) or m.group(2) or m.group(3)
    return int(raw)


def extract_votes_with_context(text: str, fmt: str = "boardroom") -> list[dict]:
    """
    Extract roll-call vote events with surrounding item context.
    Uses chevron-specific extractor for chevron format; falls back to ROLLCALL_RE
    for boardroom/vtt (where multiple name-vote pairs appear on a single line).

    Each returned dict:
      votes       — {canonical_name: 'yes'|'no'|'abstain'}
      item_number — agenda item number inferred from context, or None
      pos         — character offset for debugging
    """
    if fmt == "chevron":
        return extract_chevron_votes_with_context(text)

    # boardroom / vtt: multiple pairs on same line
    events = []
    for m in ROLLCALL_RE.finditer(text):
        pairs = PAIR_RE.findall(m.group())
        votes = {}
        for raw_name, raw_vote in pairs:
            if raw_name in FALSE_VOTE_NAMES:
                continue
            canonical = resolve_name(raw_name)
            if canonical and canonical in CANONICAL_MEMBERS:
                votes[canonical] = _norm_vote(raw_vote)
        if len(votes) < 3:
            continue
        ctx = text[max(0, m.start() - 2500): m.start()]
        item_num = _extract_item_number(ctx)
        events.append({"votes": votes, "item_number": item_num, "pos": m.start()})
    return events


def _build_agenda_index() -> dict:
    """
    Return {date: {item_number: item_dict}} merged across regular + special agendas.
    Item numbers are ints; each item_dict retains its 'section' field.
    """
    index: dict[str, dict[int, dict]] = defaultdict(dict)
    for path in sorted(glob.glob(os.path.join(AGENDAS_DIR, "*.json"))):
        try:
            with open(path) as f:
                agenda = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        date = agenda.get("date")
        if not date:
            continue
        for item in agenda.get("consent_items", []):
            n = item.get("number")
            if n is not None:
                index[date][int(n)] = item
        for item in agenda.get("action_items", []):
            n = item.get("number")
            if n is not None:
                index[date][int(n)] = item
    return dict(index)


def link_votes_to_agenda() -> list[dict]:
    """
    Parse every transcript, extract vote roll-calls, and join each to its
    agenda item using the meeting date + item number found in surrounding text.

    Returns a list of dicts, one per matched vote event:
      date, meeting_type, item_number, section, title,
      dollar_total, off_mission, false_fiscal, authors, cosponsors,
      votes  {canonical_name: 'yes'|'no'|'abstain'}
    """
    from council_scorecard import detect_format
    agenda_index = _build_agenda_index()
    linked: list[dict] = []

    for path in sorted(glob.glob(os.path.join(TEXT_DIR, "*.txt"))):
        raw = clean(open(path, encoding="utf-8", errors="replace").read())
        meta = parse_filename(os.path.basename(path))
        date = meta.get("date")
        if not date:
            continue
        day_items = agenda_index.get(date, {})
        if not day_items:
            continue

        fmt = detect_format(raw)
        vote_events = extract_votes_with_context(raw, fmt=fmt)

        for ev in vote_events:
            n = ev["item_number"]
            if n is None or n not in day_items:
                continue
            item = day_items[n]
            linked.append({
                "date":         date,
                "meeting_type": meta["type"],
                "item_number":  n,
                "section":      item.get("section"),
                "title":        item.get("title", ""),
                "dollar_total": item.get("dollar_total") or 0,
                "off_mission":  item.get("off_mission", False),
                "false_fiscal": item.get("false_fiscal", False),
                "authors":      item.get("authors", []),
                "cosponsors":   item.get("cosponsors", []),
                "votes":        ev["votes"],
            })

    return linked


def aggregate_spending_votes(linked_votes: list[dict]) -> dict:
    """
    Summarise each member's voting record on items that carry a dollar value.

    Returns {canonical_name: {
        spending_yes_total:   int   — sum of dollars on items they voted YES
        spending_no_total:    int   — sum of dollars on items they voted NO
        spending_abstain_total: int — sum of dollars on items they abstained
        spending_votes_n:     int   — number of spending vote events seen
        spending_yes_pct:     float — yes / (yes+no+abstain), or None
        largest_yes_item:     dict  — {title, dollar_total, date} for biggest YES vote
    }}
    """
    from collections import defaultdict
    totals: dict[str, dict] = defaultdict(lambda: {
        "spending_yes_total":     0,
        "spending_no_total":      0,
        "spending_abstain_total": 0,
        "spending_votes_n":       0,
        "_largest_yes":           0,
        "largest_yes_item":       None,
    })

    for rec in linked_votes:
        dollars = rec.get("dollar_total") or 0
        if dollars == 0:
            continue
        for member, vote in rec["votes"].items():
            t = totals[member]
            t["spending_votes_n"] += 1
            if vote == "yes":
                t["spending_yes_total"] += dollars
                if dollars > t["_largest_yes"]:
                    t["_largest_yes"] = dollars
                    t["largest_yes_item"] = {
                        "title":       rec["title"],
                        "dollar_total": dollars,
                        "date":        rec["date"],
                        "item_number": rec["item_number"],
                    }
            elif vote == "no":
                t["spending_no_total"] += dollars
            else:
                t["spending_abstain_total"] += dollars

    result = {}
    for name, t in totals.items():
        voted = t["spending_yes_total"] + t["spending_no_total"] + t["spending_abstain_total"]
        result[name] = {
            "spending_yes_total":     t["spending_yes_total"],
            "spending_no_total":      t["spending_no_total"],
            "spending_abstain_total": t["spending_abstain_total"],
            "spending_votes_n":       t["spending_votes_n"],
            "spending_yes_pct":       round(t["spending_yes_total"] / voted, 3) if voted else None,
            "largest_yes_item":       t["largest_yes_item"],
        }
    return result


def build_vote_hypocrisy_incidents(
    linked_votes: list[dict],
    aggregate: dict,
    min_dollars: int = 100_000,
) -> list[dict]:
    """
    Cross-reference roll-call votes against members' fiscal-concern rhetoric.

    Returns one incident record per (member, agenda-item) pair where:
      • the member voted YES on a spending item worth ≥ min_dollars, AND
      • that member's fiscal_concern_rate ≥ 0.5 (mentions per 10k words).

    Each record:
      member, date, item_number, title, dollar_total, vote,
      fiscal_concern_rate, fiscal_concern_hits
    """
    incidents: list[dict] = []
    for rec in linked_votes:
        dollars = rec["dollar_total"]
        if dollars < min_dollars:
            continue
        for member, vote in rec["votes"].items():
            if vote != "yes":
                continue
            s = aggregate.get(member, {})
            concern_rate = s.get("fiscal_concern_rate") or 0.0
            if concern_rate < 0.5:
                continue
            incidents.append({
                "member":               member,
                "date":                 rec["date"],
                "item_number":          rec["item_number"],
                "title":                rec["title"],
                "dollar_total":         dollars,
                "vote":                 vote,
                "fiscal_concern_rate":  round(concern_rate, 3),
                "fiscal_concern_hits":  s.get("fiscal_concern_hits") or 0,
            })
    return incidents


# ---------------------------------------------------------------------------
# Sponsorship and staff-referral extraction
# ---------------------------------------------------------------------------

SPONSOR_RE = re.compile(
    r"(?:"
    r"i\s+(?:authored?|wrote|brought\s+forward|introduced|co.authored?|am\s+bringing|drafted?|am\s+co.author(?:ing)?)\s+(?:this\s+)?(?:item|motion|resolution|ordinance|referral)|"
    r"this\s+is\s+my\s+(?:item|motion|resolution)|"
    r"(?:on|for)\s+my\s+item\b|"
    r"i.m\s+the\s+(?:author|sponsor)\s+of\s+(?:this|item)|"
    r"i\s+want\s+to\s+thank\s+(?:my\s+)?co.sponsors?|"
    r"(?:i\s+)?(?:bring|bringing)\s+(?:this\s+(?:item|motion|resolution)|(?:item|motion|resolution)\s+forward)"
    r")",
    re.IGNORECASE,
)

STAFF_REF_RE = re.compile(
    r"(?:"
    r"direct\s+(?:the\s+)?(?:city\s+)?(?:manager|staff|attorney)\s+to\s+\w.{5,60}|"
    r"(?:i.d\s+like|i\s+(?:want|move|ask)|can\s+we)\s+(?:to\s+)?(?:refer|ask|request|have)\s+staff\s+(?:to\s+)?\w.{5,60}|"
    r"(?:get|prepare|bring\s+back|receive)\s+a\s+staff\s+report\s+(?:on\s+)?\w.{3,50}|"
    r"staff\s+(?:to\s+)?(?:study|research|prepare|report\s+on|look\s+into|analyze|explore)\s+\w.{3,50}|"
    r"referral\s+to\s+(?:the\s+)?(?:city\s+manager|staff)"
    r")",
    re.IGNORECASE,
)


def extract_sponsorships(members: dict) -> dict:
    """Count sponsorship and staff referral signals per member."""
    result = {}
    for name in CANONICAL_MEMBERS:
        md = members.get(name)
        if not md:
            result[name] = {"sponsorships": 0, "staff_referrals": 0,
                            "staff_ref_waste": 0, "staff_ref_core": 0}
            continue
        text = md.full_text()
        sponsors = len(SPONSOR_RE.findall(text))
        refs = list(STAFF_REF_RE.finditer(text))
        # Classify each referral as waste/core/neutral by surrounding context
        ref_waste = ref_core = 0
        for m in refs:
            ctx = text[max(0, m.start()-100): m.end()+100].lower()
            wh = sum(1 for p in WASTE_KW if re.search(p, ctx))
            ch = sum(1 for p in CORE_KW  if re.search(p, ctx))
            if wh > ch:   ref_waste += 1
            elif ch > wh: ref_core  += 1
        result[name] = {
            "sponsorships":   sponsors,
            "staff_referrals": len(refs),
            "staff_ref_waste": ref_waste,
            "staff_ref_core":  ref_core,
        }
    return result


# ---------------------------------------------------------------------------
# Efficiency metrics
# ---------------------------------------------------------------------------

def extract_efficiency(members: dict) -> dict:
    result = {}
    for name in CANONICAL_MEMBERS:
        md = members.get(name)
        if not md or not md.turns:
            result[name] = {}
            continue
        lens = [len(t.split()) for t in md.turns]
        avg  = sum(lens) / len(lens)
        pct_long     = sum(1 for l in lens if l > 200) / len(lens)
        pct_concise  = sum(1 for l in lens if l <= 50)  / len(lens)
        # Efficiency score: reward concise turns, penalise long monologues
        efficiency = pct_concise * 0.6 + (1 - pct_long) * 0.4
        result[name] = {
            "turn_count":    len(lens),
            "avg_turn_len":  round(avg, 1),
            "pct_long":      round(pct_long * 100, 1),
            "pct_concise":   round(pct_concise * 100, 1),
            "efficiency":    round(efficiency, 3),
        }
    return result


# ---------------------------------------------------------------------------
# Per-meeting scoring  (date + meeting type extracted from filename)
# ---------------------------------------------------------------------------

DATE_RE = re.compile(r"BCC (\d{4}-\d{2}-\d{2}) (Special|Regular|Special and Regular)", re.IGNORECASE)


def parse_filename(fname: str) -> dict:
    m = DATE_RE.search(fname)
    if m:
        return {"date": m.group(1), "type": m.group(2)}
    return {"date": None, "type": "Unknown"}


def score_all_meetings(members_per_file: dict) -> list[dict]:
    """Score each meeting individually for temporal tracking."""
    meetings = []
    for fname, member_turns in sorted(members_per_file.items()):
        meta = parse_filename(fname)
        meeting = {"filename": fname, **meta, "members": {}}
        for name, turns in member_turns.items():
            if not turns:
                continue
            md_tmp = _cs.MemberData(name)
            for t in turns:
                md_tmp.add(t)
            s = _cs.score_member(md_tmp)
            if s:
                lens = [len(t.split()) for t in turns]
                s["avg_turn_len"] = round(sum(lens)/len(lens), 1) if lens else 0
                meeting["members"][name] = s
        meetings.append(meeting)
    return meetings


# ---------------------------------------------------------------------------
# Normalise efficiency for ranking
# ---------------------------------------------------------------------------

def add_efficiency_ranks(aggregate: dict) -> None:
    names = [n for n in CANONICAL_MEMBERS if n in aggregate and "efficiency" in aggregate[n]]
    if not names:
        return
    ranked = sorted(names, key=lambda n: -aggregate[n]["efficiency"])
    for rank, n in enumerate(ranked, 1):
        aggregate[n]["efficiency_rank"] = rank


# ---------------------------------------------------------------------------
# Load per-file turn data (needed for per-meeting scoring)
# ---------------------------------------------------------------------------

def load_per_file() -> dict:
    """Return {filename: {member_name: [turn_texts]}}."""
    from council_scorecard import (
        detect_format, parse_chevron, parse_boardroom, parse_vtt,
        CANONICAL_MEMBERS as CM,
    )
    result = {}
    for path in sorted(glob.glob(os.path.join(TEXT_DIR, "*.txt"))):
        raw = clean(open(path, encoding="utf-8", errors="replace").read())
        fmt = detect_format(raw)
        fname = os.path.basename(path)
        file_turns = defaultdict(list)

        if fmt == "chevron":
            turns = parse_chevron(raw)
            for canonical, body in turns:
                if canonical in CM:
                    file_turns[canonical].append(body)
        elif fmt == "boardroom":
            turns = parse_boardroom(raw)
            for canonical, body in turns:
                if canonical in CM:
                    file_turns[canonical].append(body)
        elif fmt == "vtt":
            turns = parse_vtt(raw)
            for canonical, body, _dur in turns:
                if canonical in CM:
                    file_turns[canonical].append(body)

        result[fname] = dict(file_turns)
    return result


# ---------------------------------------------------------------------------
# Trend detection  (last 90 days vs all time)
# ---------------------------------------------------------------------------

def compute_trends(meetings: list[dict]) -> dict:
    """Return {member: {'waste_trend': float, 'core_trend': float}}."""
    cutoff = date.today().replace(day=1)  # approximate 90-day cutoff
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=90)

    recent = defaultdict(list)
    overall = defaultdict(list)

    for m in meetings:
        d = m.get("date")
        if not d:
            continue
        try:
            meeting_date = date.fromisoformat(d)
        except ValueError:
            continue
        for name, s in m["members"].items():
            wp = s.get("waste_pct", 0)
            cp = s.get("core_pct",  0)
            overall[name].append((wp, cp))
            if meeting_date >= cutoff:
                recent[name].append((wp, cp))

    trends = {}
    for name in CANONICAL_MEMBERS:
        ov = overall.get(name, [])
        re_ = recent.get(name, [])
        if len(ov) >= 3 and len(re_) >= 1:
            avg_waste_all  = sum(x[0] for x in ov)  / len(ov)
            avg_core_all   = sum(x[1] for x in ov)  / len(ov)
            avg_waste_rec  = sum(x[0] for x in re_) / len(re_)
            avg_core_rec   = sum(x[1] for x in re_) / len(re_)
            trends[name] = {
                "waste_trend": round(avg_waste_rec - avg_waste_all, 3),  # + = getting worse
                "core_trend":  round(avg_core_rec  - avg_core_all,  3),  # + = getting better
                "recent_meetings": len(re_),
            }
    return trends


# ---------------------------------------------------------------------------
# Snapshot + delta tracking
# ---------------------------------------------------------------------------

# Keys where a *higher* value is better (delta > 0 = improvement)
_DELTA_HIGHER_BETTER = {"voter", "lsi", "beer", "n_fiscal", "efficiency", "core_pct",
                        "composite_grade", "composite_taxpayer"}
# Keys where a *lower* value is better (delta > 0 = worsening)
_DELTA_LOWER_BETTER  = {"waste_pct", "recall"}
DELTA_KEYS = _DELTA_HIGHER_BETTER | _DELTA_LOWER_BETTER


def save_snapshot() -> str | None:
    """Copy current aggregate.json → snapshots/aggregate_YYYY-MM-DD_HHMMSS.json."""
    if not os.path.exists(AGGREGATE_PATH):
        return None
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    ts   = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest = os.path.join(SNAPSHOTS_DIR, f"aggregate_{ts}.json")
    shutil.copy2(AGGREGATE_PATH, dest)
    return dest


def load_latest_snapshot() -> dict | None:
    """Return the most recent snapshot dict, or None if none exist."""
    snaps = sorted(glob.glob(os.path.join(SNAPSHOTS_DIR, "aggregate_*.json")))
    if not snaps:
        return None
    with open(snaps[-1]) as f:
        return json.load(f)


def compute_deltas(current: dict, previous: dict) -> dict:
    """
    Return {member: {key: delta}} for all DELTA_KEYS.
    delta > 0 means the raw value went up since last snapshot —
    callers must know which direction is good for each key.
    """
    deltas = {}
    for name, scores in current.items():
        if name.startswith("_"):
            continue
        prev = previous.get(name, {})
        member_deltas = {}
        for key in DELTA_KEYS:
            curr_val = scores.get(key)
            prev_val = prev.get(key)
            if curr_val is not None and prev_val is not None:
                member_deltas[key] = round(curr_val - prev_val, 4)
        if member_deltas:
            deltas[name] = member_deltas
    return deltas


# ---------------------------------------------------------------------------
# Consent calendar scoring
# ---------------------------------------------------------------------------

def _load_agenda_classifications() -> dict:
    """
    Load the hand-curated agenda item classifications from CSVs.
    Returns {(date, item_num_str): class_str} e.g. {('2025-04-28', '1'): '9'}.
    Covers both consent and action calendars.
    """
    import csv as _csv
    result: dict[tuple, str] = {}
    csv_paths = [
        os.path.join(AGENDAS_DIR, "classified", "consent_items_classified.csv"),
        os.path.join(AGENDAS_DIR, "classified", "action_items.csv"),
    ]
    for path in csv_paths:
        if not os.path.exists(path):
            continue
        with open(path, newline="", encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                date = (row.get("date") or "").strip()
                item = (row.get("item") or "").strip()
                cls  = (row.get("classification") or "").strip()
                if date and item and cls:
                    result[(date, item)] = cls
    return result


def load_agenda_scores() -> tuple[dict, dict]:
    """
    Read all agendas/*.json and compute per-member scores for both calendars.
    Returns (member_scores, ishii_meta).

    Consent calendar keys:
      agenda_off_mission_authored      — off-mission consent items authored
      agenda_off_mission_cosponsored   — off-mission consent items co-sponsored
      agenda_false_fiscal_authored     — items claiming "None" fiscal when obligations exist (authored)
      agenda_false_fiscal_cosponsored  — same, co-sponsored
      agenda_discretionary_total       — total $ relinquished from council office budget
      agenda_discretionary_items       — count of discretionary spending items

    Action calendar keys (explicitly debated items; heavier signal than consent):
      action_off_mission_authored      — off-mission items brought to action calendar by member
      action_off_mission_cosponsored   — off-mission action items co-sponsored
      action_budget_referral_total     — total $ in budget referrals authored on action calendar
      action_budget_referral_items     — count of those referrals

    Ishii facilitation meta:
      agenda_consent_meetings          — meetings with a non-empty consent calendar
      agenda_off_mission_meetings      — meetings where ≥1 off-mission consent item passed unchallenged
      agenda_off_mission_total         — total off-mission consent items across all meetings
    """
    classifications = _load_agenda_classifications()

    member_scores: dict[str, dict] = defaultdict(lambda: {
        # consent
        "agenda_off_mission_authored":    0,
        "agenda_off_mission_cosponsored": 0,
        "agenda_false_fiscal_authored":   0,
        "agenda_false_fiscal_cosponsored":0,
        "agenda_discretionary_total":     0,
        "agenda_discretionary_items":     0,
        # action calendar
        "action_off_mission_authored":    0,
        "action_off_mission_cosponsored": 0,
        "action_budget_referral_total":   0,
        "action_budget_referral_items":   0,
        # P1/P2/P3/9 classification-based counters (consent + action combined)
        "cls1_authored": 0,   # P1 core — directly addresses a structural crisis
        "cls2_authored": 0,   # P2 delivery — legitimate function, clear deliverable
        "cls3_authored": 0,   # P3 discretionary — low-priority / performative
        "cls9_authored": 0,   # class 9 — questionable scope / city shouldn't be doing this
        "cls9_action_authored": 0,  # class 9 on action calendar (explicit choice, heavier signal)
        "cls1_action_authored": 0,  # class 1 on action calendar (heavier positive signal)
    })

    meetings_with_off_mission = 0
    total_off_mission_items   = 0
    total_consent_meetings    = 0

    for path in sorted(glob.glob(os.path.join(AGENDAS_DIR, "*.json"))):
        try:
            with open(path) as f:
                agenda = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        date = agenda.get("date", "")

        # --- Consent calendar ---
        consent_items = agenda.get("consent_items", [])
        if consent_items:
            total_consent_meetings += 1
            meeting_off_mission = 0

            for item in consent_items:
                authors    = item.get("authors", [])
                cosponsors = item.get("cosponsors", [])
                off_mission   = item.get("off_mission", False)
                false_fiscal  = item.get("false_fiscal", False)
                discretionary = item.get("discretionary", {})
                item_cls = classifications.get((date, str(item.get("number", ""))), "")

                if off_mission:
                    meeting_off_mission   += 1
                    total_off_mission_items += 1
                    for m in authors:
                        if m in CANONICAL_MEMBERS:
                            member_scores[m]["agenda_off_mission_authored"] += 1
                    for m in cosponsors:
                        if m in CANONICAL_MEMBERS:
                            member_scores[m]["agenda_off_mission_cosponsored"] += 1

                if false_fiscal:
                    for m in authors:
                        if m in CANONICAL_MEMBERS:
                            member_scores[m]["agenda_false_fiscal_authored"] += 1
                    for m in cosponsors:
                        if m in CANONICAL_MEMBERS:
                            member_scores[m]["agenda_false_fiscal_cosponsored"] += 1

                for m, amt in discretionary.items():
                    if m in CANONICAL_MEMBERS:
                        member_scores[m]["agenda_discretionary_total"] += amt
                        member_scores[m]["agenda_discretionary_items"] += 1

                # Classification-based counters (authors only — cosponsors are passive)
                if item_cls and authors:
                    for m in authors:
                        if m in CANONICAL_MEMBERS:
                            if   item_cls == "1": member_scores[m]["cls1_authored"] += 1
                            elif item_cls == "2": member_scores[m]["cls2_authored"] += 1
                            elif item_cls == "3": member_scores[m]["cls3_authored"] += 1
                            elif item_cls == "9": member_scores[m]["cls9_authored"] += 1

            if meeting_off_mission > 0:
                meetings_with_off_mission += 1

        # --- Action calendar ---
        for item in agenda.get("action_items", []):
            authors    = item.get("authors", [])
            cosponsors = item.get("cosponsors", [])
            off_mission  = item.get("off_mission", False)
            dollar_total = item.get("dollar_total", 0) or 0
            item_cls = classifications.get((date, str(item.get("number", ""))), "")

            if off_mission:
                for m in authors:
                    if m in CANONICAL_MEMBERS:
                        member_scores[m]["action_off_mission_authored"] += 1
                for m in cosponsors:
                    if m in CANONICAL_MEMBERS:
                        member_scores[m]["action_off_mission_cosponsored"] += 1

            # Track budget referrals authored on action calendar (reveals spending priorities)
            if dollar_total > 0 and authors:
                for m in authors:
                    if m in CANONICAL_MEMBERS:
                        member_scores[m]["action_budget_referral_total"] += dollar_total
                        member_scores[m]["action_budget_referral_items"] += 1

            # Classification-based counters — action items are heavier (explicit floor choice)
            if item_cls and authors:
                for m in authors:
                    if m in CANONICAL_MEMBERS:
                        if item_cls == "1":
                            member_scores[m]["cls1_authored"] += 1
                            member_scores[m]["cls1_action_authored"] += 1
                        elif item_cls == "2":
                            member_scores[m]["cls2_authored"] += 1
                        elif item_cls == "3":
                            member_scores[m]["cls3_authored"] += 1
                        elif item_cls == "9":
                            member_scores[m]["cls9_authored"] += 1
                            member_scores[m]["cls9_action_authored"] += 1

    ishii_meta = {
        "agenda_consent_meetings":     total_consent_meetings,
        "agenda_off_mission_meetings": meetings_with_off_mission,
        "agenda_off_mission_total":    total_off_mission_items,
    }

    return dict(member_scores), ishii_meta


# ---------------------------------------------------------------------------
# Fiscal hypocrisy detection
# ---------------------------------------------------------------------------

# Large action-calendar item titles that indicate the council approved significant spending,
# regardless of which member authored them (City Manager items that required council vote).
_LARGE_SPEND_TITLE_RE = re.compile(
    r"appropriations ordinance|"
    r"tax.and.revenue anticipation|"
    r"lease revenue (note|bond)|"
    r"general obligation bond|"
    r"measure\s+[a-z]\b.*bond|"
    r"master (lease|agreement)\b.*(\bservice|\bhousing|\bshelter)|"
    r"contract:?\s+.{5,60}\s+(for|to provide)\b",
    re.IGNORECASE,
)


def _flag_fiscal_hypocrisy(aggregate: dict) -> None:
    """
    For each member, compare their fiscal-concern rhetoric (FISCAL_CONCERN_KW hits
    from transcripts) against their budget actions from agendas.
    Adds fiscal_hypocrisy_score (0–1) and fiscal_hypocrisy_detail to each member.

    Logic:
      - concern_hits  = how many times member invoked fiscal-concern language in speeches
      - action_spend  = total $ in budget referrals they authored on the action calendar
      - off_action    = off-mission items they brought to the action calendar (explicit choice)
      - A member scores high on hypocrisy if they frequently voice budget concern BUT
        also author expensive proposals or off-mission action items.
    """
    for name, s in aggregate.items():
        if name.startswith("_") or name == "Ishii":
            continue
        concern   = s.get("fiscal_concern_hits", 0) or 0
        spend     = s.get("action_budget_referral_total", 0) or 0
        off_action = s.get("action_off_mission_authored", 0) or 0

        # Normalize: concern_rate = mentions per 10k words (so volume doesn't penalise big talkers)
        words = s.get("words", 1) or 1
        concern_rate = concern / words * 10_000

        # Score: rhetoric is credible if it comes without large spending actions.
        # We penalise when concern_rate is high AND spend/off_action are also high.
        hypocrisy = 0.0
        details   = []
        waste_pct = s.get("waste_pct", 0) or 0

        if concern_rate >= 0.5 and spend >= 500_000:
            # Claimed restraint + authored large spending
            hypocrisy = min(1.0, (concern_rate / 2.0) * (spend / 1_000_000) * 0.1)
            details.append(f"{concern} fiscal-concern mentions in speeches")
            details.append(f"${spend:,.0f} in budget referrals authored on action calendar")
        elif concern_rate >= 0.5 and off_action >= 1:
            # Claimed restraint + explicitly brought off-mission items to debate
            hypocrisy = min(0.5, concern_rate * 0.2)
            details.append(f"{concern} fiscal-concern mentions")
            details.append(f"{off_action} off-mission items brought to action calendar")
        elif concern == 0 and spend >= 250_000:
            # Spender with no fiscal acknowledgment (not hypocritical, but notable)
            hypocrisy = 0.0   # not scored as hypocrisy — flagged separately below
            details.append(f"${spend:,.0f} in budget referrals authored — no fiscal-concern rhetoric detected")

        s["fiscal_concern_hits"]    = concern
        s["fiscal_concern_rate"]    = round(concern_rate, 3)
        s["fiscal_hypocrisy_score"] = round(hypocrisy, 3)
        if details:
            s["fiscal_hypocrisy_detail"] = "; ".join(details)

        # Revenue-seeking rate: new-tax/bond advocacy rhetoric per 10k words.
        # Computed here so it's available to compute_composite_grade.
        revenue_seeking = s.get("revenue_seeking_hits", 0) or 0
        revenue_seeking_rate = revenue_seeking / words * 10_000
        s["revenue_seeking_hits"] = revenue_seeking
        s["revenue_seeking_rate"] = round(revenue_seeking_rate, 3)


# ---------------------------------------------------------------------------
# Homeless Services Orthodoxy (HSO) scoring
# ---------------------------------------------------------------------------

# Regex to identify agenda items related to the homeless services apparatus
_HSO_ITEM_RE = re.compile(
    r"\bhomeless(?:ness)?\b"
    r"|\bencampment\b"
    r"|\bunhoused\b"
    r"|\bshelter\s+(?:plus\s+care|program|bed|site|capacity)\b"
    r"|\bhousing\s+response\s+team\b|\bhrt\b"
    r"|\bstreet\s+medicine\b"
    r"|\bnavigation\s+center\b"
    r"|\bmotel.*(?:shelter|housing)|campus\s+motel\b"
    r"|\balternative\s+housing\s+options\b"
    r"|\bsupport(?:ive)\s+housing\b",
    re.IGNORECASE,
)

# Meetings that were primarily about homeless policy/programs
_HSO_FOCUSED_DATES = {
    "2025-09-16",   # Special session: HRT audit + homeless response review
}


def score_homeless_orthodoxy(members: dict, linked_votes: list[dict]) -> dict:
    """
    Compute per-member Homeless Services Orthodoxy (HSO) signals.

    Measures how strongly each member is invested in the prevailing homeless
    services apparatus — $21.7M+/yr across 33 programs, Housing First mandate,
    low-barrier ideology — vs. demanding accountability and reform.

    Returns {canonical_name: {
        hso_sympathy_hits  — raw count of orthodoxy-aligned rhetoric in attributed speech
        hso_skeptic_hits   — raw count of accountability/reform rhetoric
        hso_sympathy_rate  — hits per 10k words (normalised for volume)
        hso_skeptic_rate   — hits per 10k words
        hso_net_rate       — sympathy_rate − skeptic_rate (+ = more orthodox)
        hso_items_cosponsored — agenda items related to homeless services that member cosponsored
        hso_spending_yes   — $ voted YES on homeless-services spending items
        hso_spending_no    — $ voted NO on homeless-services spending items
        hso_score          — composite 0–100 (0 = reform-oriented, 100 = status-quo aligned)
    }}
    """
    # --- Rhetoric signals from member-attributed speech ---
    rhetoric: dict[str, dict] = {}
    for name in CANONICAL_MEMBERS:
        md = members.get(name)
        if not md:
            rhetoric[name] = {}
            continue
        text = md.full_text()
        words = md.words or 1
        # Use DOTALL so .{} and [\s\S]{} cross line breaks in raw transcripts
        _flags = re.IGNORECASE | re.DOTALL
        sym = sum(len(re.findall(kw, text, _flags)) for kw in HSO_SYMPATHY_KW)
        ske = sum(len(re.findall(kw, text, _flags)) for kw in HSO_SKEPTIC_KW)
        rhetoric[name] = {
            "hso_sympathy_hits": sym,
            "hso_skeptic_hits":  ske,
            "hso_sympathy_rate": round(sym / words * 10_000, 3),
            "hso_skeptic_rate":  round(ske / words * 10_000, 3),
            "hso_net_rate":      round((sym - ske) / words * 10_000, 3),
        }

    # --- Agenda cosponsorship of homeless-services items ---
    cospon_counts: dict[str, int] = defaultdict(int)
    for path in sorted(glob.glob(os.path.join(AGENDAS_DIR, "*.json"))):
        try:
            agenda = json.load(open(path))
        except (json.JSONDecodeError, OSError):
            continue
        for item in agenda.get("consent_items", []) + agenda.get("action_items", []):
            title = (item.get("title") or "") + " " + (item.get("description") or "")
            if _HSO_ITEM_RE.search(title):
                for m in item.get("cosponsors", []):
                    if m in CANONICAL_MEMBERS:
                        cospon_counts[m] += 1
                for m in item.get("authors", []):
                    if m in CANONICAL_MEMBERS:
                        cospon_counts[m] += 1

    # --- Vote record on homeless-services spending items ---
    hso_yes: dict[str, int] = defaultdict(int)
    hso_no:  dict[str, int] = defaultdict(int)
    for rec in linked_votes:
        title = rec.get("title", "")
        if not _HSO_ITEM_RE.search(title):
            continue
        dollars = rec.get("dollar_total") or 0
        for member, vote in rec["votes"].items():
            if vote == "yes":
                hso_yes[member] += dollars
            elif vote == "no":
                hso_no[member] += dollars

    # --- Composite score ---
    # Primary driver: hso_net_rate (sympathy − skeptic per 10k words).
    # Normalised min→0 / max→100 across the cohort so the full range is visible.
    # Cosponsorship of homeless-services spending items adds a small bonus (+5/item, max +15)
    # because authoring agenda items reveals active promotion beyond passive speech.
    # Vote record is tracked but NOT added to the score —
    # consent-calendar items dominate and the signal is too sparse to be reliable.
    net_rates = [rhetoric[n].get("hso_net_rate", 0.0) for n in CANONICAL_MEMBERS if rhetoric.get(n)]
    if net_rates:
        min_r = min(net_rates)
        max_r = max(net_rates)
        span  = (max_r - min_r) or 1.0
    else:
        min_r, span = 0.0, 1.0

    # Cosponsorship: only count items that also have dollar_total > 0
    hso_spend_cospon: dict[str, int] = defaultdict(int)
    for path in sorted(glob.glob(os.path.join(AGENDAS_DIR, "*.json"))):
        try:
            agenda = json.load(open(path))
        except (json.JSONDecodeError, OSError):
            continue
        for item in agenda.get("consent_items", []) + agenda.get("action_items", []):
            title = (item.get("title") or "") + " " + (item.get("description") or "")
            if _HSO_ITEM_RE.search(title) and (item.get("dollar_total") or 0) > 0:
                for m in item.get("cosponsors", []) + item.get("authors", []):
                    if m in CANONICAL_MEMBERS:
                        hso_spend_cospon[m] += 1

    result = {}
    for name in CANONICAL_MEMBERS:
        r = rhetoric.get(name, {})
        net = r.get("hso_net_rate", 0.0)
        rhetoric_score = ((net - min_r) / span) * 85
        cospon_score = min(hso_spend_cospon.get(name, 0) * 5, 15)
        score = round(rhetoric_score + cospon_score, 1)

        result[name] = {
            **r,
            "hso_items_cosponsored": cospon_counts.get(name, 0),
            "hso_spend_items_cosponsored": hso_spend_cospon.get(name, 0),
            "hso_spending_yes":  hso_yes.get(name, 0),
            "hso_spending_no":   hso_no.get(name, 0),
            "hso_score":         score,
        }

    return result


# ---------------------------------------------------------------------------
# Procurement integrity scoring (from packet_scraper report JSONs)
# ---------------------------------------------------------------------------

REPORTS_DIR = os.path.join(AGENDAS_DIR, "reports")


def load_report_signals() -> dict:
    """
    Read all cached staff report JSONs from agendas/reports/.
    Returns dict: (date, item_num_int) → signals dict.
    """
    index = {}
    if not os.path.isdir(REPORTS_DIR):
        return index
    for path in glob.glob(os.path.join(REPORTS_DIR, "*.json")):
        try:
            with open(path) as f:
                r = json.load(f)
        except Exception:
            continue
        date_str = r.get("date")
        item_num = r.get("item_num")
        if date_str and item_num is not None:
            index[(date_str, int(item_num))] = r.get("signals", {})
    return index


def score_procurement_integrity(linked_votes: list[dict]) -> dict:
    """
    For each council member, count how many yes votes they cast on items
    with red-flag procurement signals from staff reports:
      - waived_competitive_bid
      - backdated (retroactive contract)
      - alternatives_none (on a spending item)

    Returns per-member dict with counts and a composite score (0-100,
    higher = more votes on problematic procurement items).
    """
    signals_index = load_report_signals()
    if not signals_index:
        return {}

    waived_yes: dict[str, int]    = defaultdict(int)
    backdated_yes: dict[str, int] = defaultdict(int)
    alt_none_yes: dict[str, int]  = defaultdict(int)
    total_flagged_yes: dict[str, int] = defaultdict(int)
    flagged_items: dict[str, list]    = defaultdict(list)

    # Deduplicate: same (date, item_number, member) should only count once
    # (transcripts sometimes contain multiple roll-calls for the same item)
    seen: set[tuple] = set()

    for rec in linked_votes:
        key = (rec["date"], rec.get("item_number"))
        if key not in signals_index:
            continue
        sigs = signals_index[key]
        # Only count items that have at least one red flag AND involve spending
        red_flags = []
        if sigs.get("waived_competitive_bid"):
            red_flags.append("waived_bid")
        if sigs.get("backdated"):
            red_flags.append("backdated")
        # alternatives_none on a zero-dollar item is often just a procedural note;
        # only flag it when there's also a spending signal
        if sigs.get("alternatives_none") and (
            sigs.get("general_fund") or sigs.get("grant_funded")
            or (rec.get("dollar_total") or 0) > 0
        ):
            red_flags.append("alt_none")

        if not red_flags:
            continue

        for member, vote in rec.get("votes", {}).items():
            if _norm_vote(vote) != "yes":
                continue
            dedup_key = (rec["date"], rec.get("item_number"), member)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            if "waived_bid" in red_flags:
                waived_yes[member] += 1
            if "backdated" in red_flags:
                backdated_yes[member] += 1
            if "alt_none" in red_flags:
                alt_none_yes[member] += 1
            total_flagged_yes[member] += 1
            flagged_items[member].append({
                "date":       rec["date"],
                "item_number": rec.get("item_number"),
                "title":      rec.get("title", "")[:80],
                "flags":      red_flags,
                "dollar_total": rec.get("dollar_total", 0),
            })

    if not total_flagged_yes:
        return {}

    # Min-max normalize total_flagged_yes to 0-100
    counts = list(total_flagged_yes.values())
    min_c, max_c = min(counts), max(counts)
    span = (max_c - min_c) or 1

    result = {}
    for name in CANONICAL_MEMBERS:
        total = total_flagged_yes.get(name, 0)
        score = round((total - min_c) / span * 100, 1)
        result[name] = {
            "procurement_waived_bid_yes": waived_yes.get(name, 0),
            "procurement_backdated_yes":  backdated_yes.get(name, 0),
            "procurement_alt_none_yes":   alt_none_yes.get(name, 0),
            "procurement_flagged_yes":    total,
            "procurement_score":          score,
            "procurement_flagged_items":  sorted(
                flagged_items.get(name, []),
                key=lambda x: -x.get("dollar_total", 0),
            )[:10],
        }
    return result


# ---------------------------------------------------------------------------
# Attendance scoring (from annotated agenda PDFs)
# ---------------------------------------------------------------------------

ANNOTATED_DIR = os.path.join(AGENDAS_DIR, "annotated")

# Canonical name map for annotated agenda names
_ANNOT_CANONICAL = {
    "kesarwani": "Kesarwani", "taplin": "Taplin", "bartlett": "Bartlett",
    "tregub": "Tregub", "okeefe": "OKeefe", "o'keefe": "OKeefe",
    "blackaby": "Blackaby", "lunaparra": "LunaParra", "lunapara": "LunaParra",
    "humbert": "Humbert", "ishii": "Ishii",
}

def _annot_canonical(name: str) -> str | None:
    return _ANNOT_CANONICAL.get(name.lower().strip().replace("'", "").replace("\u2019", ""))


def score_attendance(annotated_dir: str = ANNOTATED_DIR) -> dict:
    """
    Load annotated agenda JSONs and compute per-member attendance stats:
      - sessions_total: number of meeting sessions in dataset
      - sessions_absent_at_roll: listed absent at roll call
      - sessions_fully_absent: absent + never arrived
      - sessions_late: absent at roll but arrived during meeting
      - attendance_rate: (total - fully_absent) / total
      - punctuality_rate: (total - any_absent) / total
    """
    if not os.path.isdir(annotated_dir):
        return {}

    member_stats = {m: {"total": 0, "absent_at_roll": 0, "fully_absent": 0, "late": 0}
                    for m in CANONICAL_MEMBERS}

    for path in sorted(glob.glob(os.path.join(annotated_dir, "*.json"))):
        try:
            with open(path) as f:
                d = json.load(f)
        except Exception:
            continue

        absent_names = set()
        for n in d.get("absent", []):
            c = _annot_canonical(n) if isinstance(n, str) else None
            if c:
                absent_names.add(c)

        late_names = set()
        for entry in d.get("arrived_late", []):
            n = entry.get("name", "")
            c = _annot_canonical(n) if isinstance(n, str) else None
            if c:
                late_names.add(c)

        for m in CANONICAL_MEMBERS:
            member_stats[m]["total"] += 1
            if m in absent_names:
                member_stats[m]["absent_at_roll"] += 1
                if m in late_names:
                    member_stats[m]["late"] += 1
                else:
                    member_stats[m]["fully_absent"] += 1

    result = {}
    for m in CANONICAL_MEMBERS:
        s = member_stats[m]
        total = s["total"]
        fully_absent = s["fully_absent"]
        absent_at_roll = s["absent_at_roll"]
        result[m] = {
            "sessions_total":         total,
            "sessions_absent_at_roll": absent_at_roll,
            "sessions_fully_absent":   fully_absent,
            "sessions_late":           s["late"],
            "attendance_rate":         (total - fully_absent) / total if total else 1.0,
            "punctuality_rate":        (total - absent_at_roll) / total if total else 1.0,
        }
    return result


# ---------------------------------------------------------------------------
# Major fiscal votes scoring
# ---------------------------------------------------------------------------

# Curated list of major binding fiscal decisions.
# Each entry: (date, meeting_type, item_number, classification, dollar_amount, description)
# attendance source: annotated agenda vote records.
# Absent at roll + absent on item vote = dereliction.
# Budget adoptions: a YES is endorsement of status quo, not a neutral act.
MAJOR_FISCAL_VOTES = [
    # date         mtype      item  classification        amount        short_title
    ("2025-01-21", "regular",  23,   "TEFRA_BOND",         44_957_471,   "CMFA Bond – 2001 Ashby Ave"),
    ("2025-05-20", "special",   1,   "LEASE_BOND",         11_000_000,   "Lease Revenue Notes – Fire HQ"),
    ("2025-05-20", "special",   2,   "GO_BOND",            35_000_000,   "$35M GO Bonds – Measure O Housing"),
    ("2025-05-20", "regular",   2,   "BUDGET_AMENDMENT",   85_720_135,   "FY2025 Budget Amendment 1st Reading"),
    ("2025-06-03", "regular",   1,   "BUDGET_AMENDMENT",  143_999_781,   "FY2025 Budget Amendment 2nd Reading"),
    ("2025-06-24", "regular",  25,   "BUDGET_ADOPTION", 1_452_682_310,   "FY2026 Budget Adoption 1st Reading"),
    ("2025-07-08", "regular",   4,   "BUDGET_ADOPTION", 1_516_977_821,   "FY2026 Budget Adoption 2nd Reading"),
]

# Fiscal referral / survey direction items — tracked for taxpayer alignment penalty.
# These are upstream steps in bond/tax campaigns: authoring or unanimously supporting
# a referral to study new revenue is a deliberate agenda-setting choice, not a passive vote.
FISCAL_REFERRAL_VOTES = [
    ("2025-06-17", "regular",  None, "FISCAL_REFERRAL",   0, "Fire Revenue Measures Referral (Taplin)"),
    ("2025-11-18", "regular",  26,   "FISCAL_REFERRAL",   0, "Advanced Fiscal Policies – Bond Schedule (Taplin)"),
    ("2025-12-02", "special",  None, "SURVEY_DIRECTION",  0, "$300M Bond Survey Direction (unanimous)"),
    ("2026-01-27", "regular",  17,   "TAX_SURVEY",        0, "Sales Tax Poll Referral (Kesarwani)"),
    ("2026-03-17", "special",  1,    "SURVEY_DIRECTION",  0, "$300M Bond + Half-Cent Sales Tax: 2nd Survey Direction (unanimous)"),
]


def _load_annotated_item_vote(date: str, mtype: str, item_num: int | None) -> dict | None:
    """
    Load the vote record for a specific item from the annotated agenda.
    Returns {ayes, noes, abstain, absent} with canonical names, or None.
    """
    path = os.path.join(ANNOTATED_DIR, f"{date}-{mtype}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception:
        return None

    if item_num is None:
        # No item number — use overall attendance as proxy
        absent = [_annot_canonical(n) for n in d.get("absent", []) if _annot_canonical(n)]
        late   = {_annot_canonical(e["name"]) for e in d.get("arrived_late", []) if _annot_canonical(e.get("name",""))}
        # Fully absent = absent and never arrived
        fully_absent = [n for n in absent if n not in late]
        present = [m for m in CANONICAL_MEMBERS if m not in fully_absent]
        return {"ayes": present, "noes": [], "abstain": [], "absent": fully_absent}

    # Helper: resolve "all ayes" or explicit name list using meeting attendance
    def _c_list(lst, absent_at_roll, late_names):
        if lst == ["all"]:
            fully_absent = [n for n in absent_at_roll if n not in late_names]
            return [m for m in CANONICAL_MEMBERS if m not in fully_absent]
        return [_annot_canonical(n) for n in lst if _annot_canonical(n)]

    absent_at_roll = [_annot_canonical(n) for n in d.get("absent", []) if _annot_canonical(n)]
    late_names = {_annot_canonical(e["name"]) for e in d.get("arrived_late", []) if _annot_canonical(e.get("name", ""))}
    fully_absent = [n for n in absent_at_roll if n not in late_names]

    # Collect all items with this number — sections restart numbering
    matching = [item for item in d.get("items", []) if item.get("number") == item_num]
    if not matching:
        return None

    # Prefer items that have an explicit vote record
    with_vote    = [item for item in matching if item.get("vote")]
    without_vote = [item for item in matching if not item.get("vote")]

    if with_vote:
        vote = with_vote[0]["vote"]
        return {
            "ayes":    _c_list(vote.get("ayes", []),    absent_at_roll, late_names),
            "noes":    _c_list(vote.get("noes", []),    absent_at_roll, late_names),
            "abstain": _c_list(vote.get("abstain", []), absent_at_roll, late_names),
            "absent":  _c_list(vote.get("absent", []),  absent_at_roll, late_names),
        }

    # Item found but no individual vote (e.g., consent calendar voted en bloc).
    # Fall back: present = everyone not fully absent; absent = fully absent.
    return {
        "ayes":    [m for m in CANONICAL_MEMBERS if m not in fully_absent],
        "noes":    [],
        "abstain": [],
        "absent":  fully_absent,
    }


def score_major_fiscal_votes(annotated_dir: str = ANNOTATED_DIR) -> dict:
    """
    Score each member's presence and vote direction on MAJOR_FISCAL_VOTES.
    Returns per-member dict with:
      - fiscal_vote_total: number of binding fiscal votes in dataset
      - fiscal_vote_present: present and voting
      - fiscal_vote_absent: absent (missed binding fiscal vote)
      - fiscal_vote_yes: voted yes (supports spending)
      - fiscal_vote_no: voted no (opposed spending)
      - fiscal_dollars_voted_yes: total dollars of measures they voted yes on
      - fiscal_dollars_absent: total dollars of measures they were absent for
      - fiscal_vote_records: list of per-vote detail dicts
    """
    result = {m: {
        "fiscal_vote_total":        len(MAJOR_FISCAL_VOTES),
        "fiscal_vote_present":      0,
        "fiscal_vote_absent":       0,
        "fiscal_vote_yes":          0,
        "fiscal_vote_no":           0,
        "fiscal_dollars_voted_yes": 0,
        "fiscal_dollars_absent":    0,
        "fiscal_vote_records":      [],
    } for m in CANONICAL_MEMBERS}

    for date, mtype, item_num, classification, amount, title in MAJOR_FISCAL_VOTES:
        vote = _load_annotated_item_vote(date, mtype, item_num)
        for m in CANONICAL_MEMBERS:
            rec = {
                "date":           date,
                "classification": classification,
                "amount":         amount,
                "title":          title,
                "position":       None,
            }
            if vote is None:
                rec["position"] = "unknown"
            elif m in (vote.get("absent") or []):
                rec["position"] = "absent"
                result[m]["fiscal_vote_absent"] += 1
                result[m]["fiscal_dollars_absent"] += amount
            elif m in (vote.get("noes") or []):
                rec["position"] = "no"
                result[m]["fiscal_vote_present"] += 1
                result[m]["fiscal_vote_no"] += 1
            elif m in (vote.get("ayes") or []):
                rec["position"] = "yes"
                result[m]["fiscal_vote_present"] += 1
                result[m]["fiscal_vote_yes"] += 1
                result[m]["fiscal_dollars_voted_yes"] += amount
            elif m in (vote.get("abstain") or []):
                rec["position"] = "abstain"
                result[m]["fiscal_vote_present"] += 1
            else:
                rec["position"] = "unknown"
            result[m]["fiscal_vote_records"].append(rec)

    return result


# ---------------------------------------------------------------------------
# Fiscal referral / survey direction scoring
# ---------------------------------------------------------------------------

def score_fiscal_referral_votes() -> dict:
    """
    Score each member's involvement in FISCAL_REFERRAL_VOTES.

    These are upstream steps in bond/tax campaigns. Authoring a referral is a
    deliberate agenda-setting choice; showing up for a unanimous direction vote
    is participation. Both count against taxpayer alignment.

    Penalties (additive):
      -0.03 per item authored
      -0.01 per item cosponsored or voted aye on (not as author)
    Cap: -0.09 per member.

    Returns {canonical_name: {
        fiscal_referral_authored:  int   — items authored
        fiscal_referral_supported: int   — items cosponsored/supported (not as author)
        fiscal_referral_penalty:   float — penalty (≤ 0, capped at -0.09)
        fiscal_referral_records:   list  — [{date, title, role}]
    }}
    """
    agenda_index = _build_agenda_index()

    authored:  dict[str, int]  = defaultdict(int)
    supported: dict[str, int]  = defaultdict(int)
    records:   dict[str, list] = defaultdict(list)

    for date, mtype, item_num, classification, amount, title in FISCAL_REFERRAL_VOTES:
        # Look up authors / cosponsors from agenda JSON
        item_authors:    list[str] = []
        item_cosponsors: list[str] = []
        if item_num is not None:
            item = agenda_index.get(date, {}).get(item_num, {})
            item_authors    = [m for m in item.get("authors",    []) if m in CANONICAL_MEMBERS]
            item_cosponsors = [m for m in item.get("cosponsors", []) if m in CANONICAL_MEMBERS]

        for m in item_authors:
            authored[m] += 1
            records[m].append({"date": date, "title": title, "role": "author"})
        for m in item_cosponsors:
            supported[m] += 1
            records[m].append({"date": date, "title": title, "role": "cosponsor"})

        # Anyone who voted aye (and isn't already counted as author/cosponsor)
        vote = _load_annotated_item_vote(date, mtype, item_num)
        if vote:
            author_set = set(item_authors) | set(item_cosponsors)
            for m in (vote.get("ayes") or []):
                if m not in author_set:
                    supported[m] += 1
                    records[m].append({"date": date, "title": title, "role": "aye"})

    result = {}
    for name in CANONICAL_MEMBERS:
        auth = authored.get(name, 0)
        supp = supported.get(name, 0)
        penalty = max(-0.09, -(auth * 0.03 + supp * 0.01))
        result[name] = {
            "fiscal_referral_authored":  auth,
            "fiscal_referral_supported": supp,
            "fiscal_referral_penalty":   round(penalty, 4),
            "fiscal_referral_records":   records.get(name, []),
        }
    return result


# ---------------------------------------------------------------------------
# Full annotated-agenda vote statistics (all sessions, all items)
# ---------------------------------------------------------------------------

def score_annotated_votes(annotated_dir: str = ANNOTATED_DIR) -> dict:
    """
    Read every annotated agenda JSON and tally per-member voting stats.

    For each item that has an explicit vote record (not "All Ayes" without
    a name list), record each member's position: yes / no / abstain / absent.

    Returns per-member dict:
      annot_vote_total          — items with a parseable vote where member was involved
      annot_vote_yes            — yes/aye votes
      annot_vote_no             — no/nay votes
      annot_vote_abstain        — abstentions
      annot_vote_absent         — absent when item was voted
      annot_vote_yes_rate       — yes / (yes+no+abstain+absent)
      annot_abstain_rate        — abstain / total
      annot_contested_abstain   — abstentions on items where ≥1 member voted no
                                  (masked disagreement signal)
    """
    if not os.path.isdir(annotated_dir):
        return {}

    counts: dict[str, dict] = {m: {
        "yes": 0, "no": 0, "abstain": 0, "absent": 0,
        "contested_abstain": 0,
    } for m in CANONICAL_MEMBERS}

    for path in sorted(glob.glob(os.path.join(annotated_dir, "*.json"))):
        try:
            with open(path) as f:
                d = json.load(f)
        except Exception:
            continue

        # Resolve meeting-level attendance for "All Ayes" expansion
        absent_at_roll = [_annot_canonical(n) for n in d.get("absent", []) if _annot_canonical(n)]
        late_names     = {_annot_canonical(e["name"]) for e in d.get("arrived_late", [])
                          if _annot_canonical(e.get("name", ""))}
        fully_absent   = [n for n in absent_at_roll if n not in late_names]

        def _resolve_vote_list(lst: list) -> list[str]:
            """Expand ['all'] or canonical name strings."""
            if lst == ["all"]:
                return [m for m in CANONICAL_MEMBERS if m not in fully_absent]
            return [c for c in (_annot_canonical(n) for n in lst) if c]

        for item in d.get("items", []):
            vote = item.get("vote")
            if not vote:
                continue

            ayes    = _resolve_vote_list(vote.get("ayes",    []))
            noes    = _resolve_vote_list(vote.get("noes",    []))
            abstain = _resolve_vote_list(vote.get("abstain", []))
            absent  = _resolve_vote_list(vote.get("absent",  []))

            # Skip items with no vote participants at all (parsing artifact)
            if not ayes and not noes and not abstain and not absent:
                continue

            contested = bool(noes)   # at least one "no" vote

            for m in CANONICAL_MEMBERS:
                if m in ayes:
                    counts[m]["yes"] += 1
                elif m in noes:
                    counts[m]["no"] += 1
                elif m in abstain:
                    counts[m]["abstain"] += 1
                    if contested:
                        counts[m]["contested_abstain"] += 1
                elif m in absent:
                    counts[m]["absent"] += 1
                # Not listed in any category: skip (item may pre-date member)

    result = {}
    for m in CANONICAL_MEMBERS:
        c = counts[m]
        total = c["yes"] + c["no"] + c["abstain"] + c["absent"]
        result[m] = {
            "annot_vote_total":        total,
            "annot_vote_yes":          c["yes"],
            "annot_vote_no":           c["no"],
            "annot_vote_abstain":      c["abstain"],
            "annot_vote_absent":       c["absent"],
            "annot_vote_yes_rate":     round(c["yes"] / total, 3) if total else None,
            "annot_abstain_rate":      round(c["abstain"] / total, 3) if total else None,
            "annot_contested_abstain": c["contested_abstain"],
        }
    return result


# ---------------------------------------------------------------------------
# Incident / anecdote loading
# ---------------------------------------------------------------------------

INCIDENTS_PATH      = os.path.join(os.path.dirname(__file__), "incidents.json")
AUDIT_FINDINGS_PATH = os.path.join(os.path.dirname(__file__), "audit_findings.json")

def load_incidents() -> dict:
    """
    Load incidents.json and return per-member adjustment values.
    Returns {canonical_name: {
        incident_score_adj:   float  — sum of scoring_impact values (capped ±0.30)
        incident_count:       int    — total incidents documented
        incident_records:     list   — raw incident dicts for display
    }}
    """
    if not os.path.exists(INCIDENTS_PATH):
        return {}
    try:
        with open(INCIDENTS_PATH) as f:
            data = json.load(f)
    except Exception:
        return {}

    TIER_WEIGHTS = {"A": 1.00, "B": 0.75, "C": 0.50}

    result = {}
    for name, incidents in data.items():
        if name.startswith("_") or not isinstance(incidents, list):
            continue
        if name not in CANONICAL_MEMBERS:
            continue
        total_adj = 0.0
        for inc in incidents:
            raw = inc.get("scoring_impact", 0)
            tier = inc.get("evidence_tier", "B")   # default B if field absent
            weight = TIER_WEIGHTS.get(tier, 0.75)
            if inc.get("audit_ref"):
                weight *= 0.50   # audit channel already penalizes this behavior
            total_adj += raw * weight
        total_adj = max(-0.30, min(0.30, total_adj))   # cap so no single member is dominated
        result[name] = {
            "incident_score_adj": round(total_adj, 4),
            "incident_count":     len(incidents),
            "incident_records":   incidents,
        }
    return result


# ---------------------------------------------------------------------------
# Audit silence penalty
# ---------------------------------------------------------------------------

def load_audit_silence() -> dict:
    """
    For each audit that was formally presented to council and received/filed
    without substantive follow-up, penalize members who were present but whose
    response is uncharacterized: no incident with a matching audit_ref, and not
    listed in follow_up_authored_by.

    Members with an existing audit_ref incident are already individually
    scored — their behavior (positive or negative) is on record. The silence
    penalty is for everyone else who sat in the room, voted receive-and-file,
    and did nothing documentable afterward.

    Returns {canonical_name: {
        audit_silence_adj:    float — cumulative penalty (negative)
        audit_silence_events: list  — audit_ref keys that triggered it
    }}
    """
    if not os.path.exists(AUDIT_FINDINGS_PATH) or not os.path.exists(INCIDENTS_PATH):
        return {}
    try:
        with open(AUDIT_FINDINGS_PATH) as f:
            audits = json.load(f)
        with open(INCIDENTS_PATH) as f:
            incidents_raw = json.load(f)
    except Exception:
        return {}

    # (member, audit_ref) pairs already covered by an incident
    characterized: set = set()
    for member, inc_list in incidents_raw.items():
        if member.startswith("_") or not isinstance(inc_list, list):
            continue
        for inc in inc_list:
            ar = inc.get("audit_ref", "")
            if ar:
                characterized.add((member, ar))

    SILENCE_PENALTY = -0.04

    result: dict = {m: {"audit_silence_adj": 0.0, "audit_silence_events": []}
                    for m in CANONICAL_MEMBERS}

    for audit_key, audit in audits.items():
        if audit_key.startswith("_") or not isinstance(audit, dict):
            continue
        agenda_date = audit.get("council_agenda_date")
        status      = audit.get("status", "")
        if not agenda_date:
            continue
        # Only audits that were formally received with no structural follow-up
        if status not in ("received_filed", "response_documented"):
            continue

        follow_up_by = set(audit.get("follow_up_authored_by") or [])

        # Load annotated attendance for the presentation meeting
        ann_path = os.path.join(ANNOTATED_DIR, f"{agenda_date}-regular.json")
        if not os.path.exists(ann_path):
            continue
        try:
            with open(ann_path) as f:
                ann = json.load(f)
        except Exception:
            continue

        absent_names: set = set()
        for n in ann.get("absent", []):
            c = _annot_canonical(n) if isinstance(n, str) else None
            if c:
                absent_names.add(c)

        for member in CANONICAL_MEMBERS:
            if member in absent_names:
                continue  # wasn't there
            if member in follow_up_by:
                continue  # gave a substantive response
            if (member, audit_key) in characterized:
                continue  # behavior already individually documented
            result[member]["audit_silence_adj"]    += SILENCE_PENALTY
            result[member]["audit_silence_events"].append(audit_key)

    return {m: v for m, v in result.items() if v["audit_silence_events"]}


# ---------------------------------------------------------------------------
# Newsletter P1 silence penalty
# ---------------------------------------------------------------------------

NEWSLETTER_INDEX_PATH   = os.path.join(os.path.dirname(__file__), "newsletter_index.json")
NEWSLETTER_RHETORIC_PEN = -0.025   # acknowledges fiscal difficulty, zero P1 content
NEWSLETTER_SILENT_PEN   = -0.015   # no fiscal language at all
NEWSLETTER_SILENCE_CAP  = -0.06    # per-member cap
FISCAL_CRISIS_START     = "2024-07-01"   # FY25-26 budget adopted; "not sustainable" on record


def score_newsletter_p1_silence() -> dict:
    """
    For each regular constituent newsletter published on or after FISCAL_CRISIS_START:
      - p1_hit              → no penalty (member engaged with documented P1 fiscal problems)
      - rhetoric_no_substance → NEWSLETTER_RHETORIC_PEN (named the crisis, did nothing)
      - silent              → NEWSLETTER_SILENT_PEN (complete omission)
      - atm_framing / existing_incident → 0 (already scored as incident; avoid double-count)
      - skip                → 0

    Returns {member: {newsletter_silence_adj: float, newsletter_events: list}}
    """
    if not os.path.exists(NEWSLETTER_INDEX_PATH):
        return {}

    try:
        data = json.load(open(NEWSLETTER_INDEX_PATH, encoding="utf-8"))
    except Exception:
        return {}

    result: dict = {}
    for entry in data.get("newsletters", []):
        member = entry.get("member")
        if not member or member not in CANONICAL_MEMBERS:
            continue
        date = entry.get("date", "")
        if date < FISCAL_CRISIS_START:
            continue
        if entry.get("existing_incident"):
            continue

        classification = entry.get("classification", "silent")
        if classification == "rhetoric_no_substance":
            pen = NEWSLETTER_RHETORIC_PEN
        elif classification == "silent":
            pen = NEWSLETTER_SILENT_PEN
        else:
            continue   # p1_hit, atm_framing, skip → no penalty here

        if member not in result:
            result[member] = {"newsletter_silence_adj": 0.0, "newsletter_events": []}
        result[member]["newsletter_silence_adj"] += pen
        result[member]["newsletter_events"].append({
            "date":           date,
            "subject":        entry.get("subject", ""),
            "classification": classification,
            "penalty":        pen,
        })

    # Apply cap
    for member, v in result.items():
        v["newsletter_silence_adj"] = max(
            NEWSLETTER_SILENCE_CAP,
            v["newsletter_silence_adj"],
        )

    return result


# ---------------------------------------------------------------------------
# Taxpayer alignment + Tier 1 composite grade
# ---------------------------------------------------------------------------

def compute_composite_grade(s: dict) -> dict:
    """
    Tier 1 letter grade — explicit taxpayer-aligned composite.

    Three pillars:
      Taxpayer Alignment  45%  — HSO inverse, fiscal rhetoric vs. action, off-mission authorship,
                                  bond/tax referral authorship, incident adjustments
      Focus               35%  — waste% and core topic share from transcripts
      Attendance          20%  — on-time rate + presence at major fiscal votes

    Returns dict with composite score (0-1) and pillar breakdown.
    """
    fv_total  = s.get("fiscal_vote_total",  7) or 7
    fv_absent = s.get("fiscal_vote_absent", 0) or 0

    # ── Taxpayer Alignment ──────────────────────────────────────────────────
    # HSO: 0=reform, 100=status-quo. Invert, then apply steep power curve.
    # HSO is not a mild preference — it is an active harm multiplier:
    # crime, displaced merchants, unaccountable spending, litigation, and
    # the ability of neighboring cities to offload problems onto Berkeley.
    # San Francisco's Lurie-era reversal is the A/B test showing the alternative works.
    # Use explicit None check — hso_score = 0.0 is Kesarwani's perfect score, not missing data.
    # The `or 50` idiom would incorrectly treat 0.0 as falsy and substitute the default.
    hso_raw   = s.get("hso_score") if s.get("hso_score") is not None else 50
    hso_part  = ((100 - hso_raw) / 100) ** 2.0   # quadratic — 85→0.022, 62→0.145, 28→0.518

    # Off-mission / out-of-scope items authored.
    # Primary signal: CSV classifications (class 9 = city shouldn't be doing this).
    # Action items weighted 1.5x consent — floor debate is an explicit choice, not a slip.
    # Legacy off_mission flag used only when no CSV classification exists (fallback).
    cls9_authored        = s.get("cls9_authored",        0) or 0
    cls9_action_authored = s.get("cls9_action_authored", 0) or 0
    cls9_consent_authored = max(0, cls9_authored - cls9_action_authored)
    cls9_signal   = cls9_consent_authored * 0.06 + cls9_action_authored * 0.09
    legacy_off    = (s.get("agenda_off_mission_authored", 0) or 0) + \
                    (s.get("action_off_mission_authored",  0) or 0)
    off_penalty   = min(0.20, max(cls9_signal, legacy_off * 0.07))

    # Fiscal rhetoric without dissent — penalise financially literate members who
    # invoke fiscal-concern language while aligned with the status-quo spending apparatus.
    # Condition: HSO ≥ 45 (complicit) OR serially absent from fiscal votes (derelict).
    concern_rate = s.get("fiscal_concern_rate", 0) or 0
    ann_no       = s.get("annot_vote_no",      0) or 0
    ann_total    = s.get("annot_vote_total",   0) or 0
    if concern_rate >= 0.5 and ann_no == 0 and ann_total >= 50 and hso_raw >= 45:
        rhetoric_penalty = min(0.25, concern_rate / 5.0)
    elif concern_rate >= 0.5 and ann_no == 0 and ann_total >= 50 and fv_absent >= 3:
        rhetoric_penalty = min(0.20, concern_rate / 6.0)
    else:
        rhetoric_penalty = 0.0

    # Incident adjustments (capped ±0.30 in load_incidents)
    incident_adj  = s.get("incident_score_adj", 0.0) or 0.0

    # Audit silence: present at audit presentation, no follow-up, no characterized incident
    audit_silence_adj = s.get("audit_silence_adj", 0.0) or 0.0

    # Newsletter P1 silence: constituent newsletters that acknowledge fiscal difficulty
    # but contain zero structural deficit / CalPERS / OPEB / streets-backlog content
    newsletter_silence_adj = s.get("newsletter_silence_adj", 0.0) or 0.0

    # Fiscal referral / bond-campaign direction penalty (capped -0.09 in score_fiscal_referral_votes)
    fiscal_ref_penalty = s.get("fiscal_referral_penalty", 0.0) or 0.0

    # Revenue-seeking rhetoric penalty (P1 Layer 3: new revenue before reprioritization).
    # Penalizes members who propose taxes/bonds without accompanying cut-seeking questions.
    # Partial credit if they also use FISCAL_KW "what would we cut?" probing language
    # (fiscal_raw per-1k-words is a proxy for cut-seeking engagement).
    revenue_seeking_rate = s.get("revenue_seeking_rate", 0.0) or 0.0
    if revenue_seeking_rate >= 0.3:
        fiscal_raw   = s.get("fiscal_raw", 0.0) or 0.0   # FISCAL_KW hits per 1k words
        # If member probes costs AND seeks revenue, partial credit — they at least ask the question.
        # If they only seek revenue without cost-probing, full penalty applies.
        cut_credit   = min(1.0, fiscal_raw * 0.4)
        revenue_seeking_penalty = min(0.10, revenue_seeking_rate * 0.04 * (1.0 - cut_credit * 0.5))
    else:
        revenue_seeking_penalty = 0.0

    taxpayer_raw  = hso_part * 0.75 + (1.0 - off_penalty) * 0.25
    taxpayer_unclamped = (
        taxpayer_raw - rhetoric_penalty - revenue_seeking_penalty
        + incident_adj + fiscal_ref_penalty + audit_silence_adj
        + newsletter_silence_adj
    )
    taxpayer_alignment = max(0.0, min(1.0, taxpayer_unclamped))

    # ── Focus ────────────────────────────────────────────────────────────────
    waste_pct = s.get("waste_pct", 0) or 0
    core_pct  = s.get("core_pct",  0) or 0

    # Agenda-classification waste: P3 items authored as a share of total policy items.
    # P3 (discretionary/ceremonial) is within-scope but signals misplaced priorities.
    # Only penalises when the member has authored enough items to be meaningful (≥3).
    cls3_authored = s.get("cls3_authored", 0) or 0
    cls1_authored = s.get("cls1_authored", 0) or 0
    cls2_authored = s.get("cls2_authored", 0) or 0
    total_policy  = cls1_authored + cls2_authored + cls3_authored + cls9_authored
    if total_policy >= 3:
        p3_share = cls3_authored / total_policy
        agenda_waste_signal = min(0.10, p3_share * 0.10)
    else:
        agenda_waste_signal = 0.0

    focus = max(0.0, min(1.0, (1 - waste_pct) * 0.60 + core_pct * 0.40 - agenda_waste_signal))

    # ── Attendance — penalty only ────────────────────────────────────────────
    # Showing up is the minimum bar, not a virtue. Good attendance contributes
    # nothing positive. Dereliction (missed fiscal votes, chronic absence) subtracts.
    fv_pres    = (fv_total - fv_absent) / fv_total if fv_total else 1.0
    punct_rate = s.get("punctuality_rate", 1.0) or 1.0

    # Fiscal vote dereliction: nonlinear — each additional missed vote hurts more than the last.
    # Missing 1/7 is excusable; missing 5/7 is dereliction of the core duty of the office.
    # Convex curve (x^1.5): lenient at 1-2 absences, severe at 4+.
    # 1/7→0.013, 2/7→0.038, 3/7→0.070, 5/7→0.151, 7/7→0.250
    fv_ratio       = fv_absent / fv_total if fv_total else 0.0
    fv_dereliction = (fv_ratio ** 1.5) * 0.25
    # Chronic absence: well below 70% on-time rate → penalise
    punct_penalty  = max(0.0, 0.70 - punct_rate) * 0.15       # up to −0.105 for 0% on-time
    attendance_deduction = min(0.30, fv_dereliction + punct_penalty)

    # ── Lightweight penalty (P1 tourist test) ───────────────────────────────
    # A member who never originates P1 work is a passenger, not a driver.
    # Gate: no P1 items authored per CSV classification AND no fiscal referral.
    # Using cls1_authored is more accurate than fiscal_referral_authored alone —
    # it covers any classified P1 agenda item, not just the curated referral list.
    fiscal_referral_authored = s.get("fiscal_referral_authored", 0) or 0
    p1_authored = cls1_authored + fiscal_referral_authored
    if p1_authored == 0:
        concern_rate  = s.get("fiscal_concern_rate", 0.0) or 0.0
        # engagement: weighted average of fiscal-vote presence + fiscal-concern rhetoric
        # both capped at 1.0 to prevent outsized speech volume from masking inaction
        engagement = min(1.0, fv_pres * 0.5 + min(concern_rate, 1.0) * 0.5)
        if engagement < 0.6:
            # Tapers from 0.10 (pure tourist) to 0 at engagement = 0.6
            lightweight_penalty = 0.10 * (1.0 - engagement / 0.6)
        else:
            lightweight_penalty = 0.0
    else:
        lightweight_penalty = 0.0

    # ── Composite ────────────────────────────────────────────────────────────
    # Taxpayer alignment dominates; focus captures rhetorical alignment.
    # Attendance and lightweight are penalty-only — showing up and doing P1 work
    # is the minimum bar, not a virtue.
    composite = max(0.0,
        taxpayer_alignment * 0.70 + focus * 0.30
        - attendance_deduction
        - lightweight_penalty
    )

    return {
        "composite_grade":              round(composite, 4),
        "composite_taxpayer":           round(taxpayer_alignment, 4),
        "composite_focus":              round(focus, 4),
        "composite_attendance_ded":     round(attendance_deduction, 4),
        "composite_rhetoric_penalty":   round(rhetoric_penalty, 4),
        "composite_hso_part":           round(hso_part, 4),
        "composite_off_penalty":        round(off_penalty, 4),
        "composite_taxpayer_raw":       round(taxpayer_raw, 4),
        "composite_fiscal_ref_penalty": round(fiscal_ref_penalty, 4),
        "composite_revenue_seeking_pen":round(revenue_seeking_penalty, 4),
        "composite_lightweight_pen":    round(lightweight_penalty, 4),
        "composite_audit_silence_pen":      round(-audit_silence_adj, 4),
        "composite_newsletter_silence_pen": round(-newsletter_silence_adj, 4),
        "composite_agenda_waste_signal":round(agenda_waste_signal, 4),
        "composite_cls9_signal":        round(cls9_signal, 4),
        # P1/P2/P3/9 authorship counts for display and debugging
        "cls1_authored":                cls1_authored,
        "cls2_authored":                cls2_authored,
        "cls3_authored":                cls3_authored,
        "cls9_authored":                cls9_authored,
        "cls9_action_authored":         cls9_action_authored,
        "p1_authored":                  p1_authored,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-pdf",      action="store_true")
    parser.add_argument("--scores-only", action="store_true")
    args = parser.parse_args()

    print("Loading and attributing transcripts...", file=sys.stderr)
    members = load_all()
    for n, md in members.items():
        print(f"  {DISPLAY_NAME.get(n,n):<13} {md.words:>9,} words  "
              f"{len(md.turns):>5} turns", file=sys.stderr)

    print("\nComputing base scores...", file=sys.stderr)
    scores = build_scoreboard(members)
    ishii_fac = score_ishii_facilitator(members.get("Ishii", _cs.MemberData("Ishii")))

    print("Extracting votes...", file=sys.stderr)
    all_vote_events = []
    for path in sorted(glob.glob(os.path.join(TEXT_DIR, "*.txt"))):
        raw = clean(open(path, encoding="utf-8", errors="replace").read())
        all_vote_events.extend(extract_votes_from_text(raw))
    vote_stats = aggregate_votes(all_vote_events)
    council_vote_meta = vote_stats.pop("_council")
    print(f"  {council_vote_meta['total_vote_events']} vote events, "
          f"{council_vote_meta['block_vote_rate']*100:.0f}% block votes", file=sys.stderr)

    print("Extracting sponsorships and referrals...", file=sys.stderr)
    sponsor_stats = extract_sponsorships(members)

    print("Computing efficiency...", file=sys.stderr)
    eff_stats = extract_efficiency(members)

    print("Per-meeting scoring...", file=sys.stderr)
    per_file = load_per_file()
    meetings = score_all_meetings(per_file)

    print("Computing trends...", file=sys.stderr)
    trends = compute_trends(meetings)

    print("Loading agenda scores (consent + action)...", file=sys.stderr)
    consent_scores, ishii_consent_meta = load_agenda_scores()
    n_agendas = len(glob.glob(os.path.join(AGENDAS_DIR, "*.json")))
    print(f"  {n_agendas} agendas · {ishii_consent_meta['agenda_consent_meetings']} with consent items · "
          f"{ishii_consent_meta['agenda_off_mission_total']} off-mission items total", file=sys.stderr)

    # --- Merge everything ---
    aggregate = {}
    for name in CANONICAL_MEMBERS:
        s = scores.get(name, {})
        s.update(vote_stats.get(name, {}))
        s.update(sponsor_stats.get(name, {}))
        s.update(eff_stats.get(name, {}))
        s.update(trends.get(name, {}))
        s.update(consent_scores.get(name, {}))
        s["display_name"] = DISPLAY_NAME.get(name, name)
        s["canonical"] = name
        aggregate[name] = s

    # Ishii separate
    aggregate["Ishii"] = {
        **aggregate.get("Ishii", {}),
        "facilitator": ishii_fac,
        "display_name": "Ishii",
        "canonical": "Ishii",
        "is_mayor": True,
        **ishii_consent_meta,
        **consent_scores.get("Ishii", {}),
    }

    dated = sorted([m["date"] for m in meetings if m.get("date")])
    earliest_meeting = dated[0]  if dated else None
    latest_meeting   = dated[-1] if dated else None

    aggregate["_meta"] = {
        "generated": datetime.now().isoformat(),
        "transcripts": len(per_file),
        "total_vote_events": council_vote_meta["total_vote_events"],
        "block_vote_rate": council_vote_meta["block_vote_rate"],
        "block_vote_events": council_vote_meta["block_vote_events"],
        "earliest_meeting": earliest_meeting,
        "latest_meeting":   latest_meeting,
        "agendas_loaded":   n_agendas,
        **ishii_consent_meta,
    }

    add_efficiency_ranks(aggregate)

    print("Linking vote roll-calls to agenda items...", file=sys.stderr)
    linked_votes = link_votes_to_agenda()
    print(f"  {len(linked_votes)} votes matched to agenda items", file=sys.stderr)

    # Merge spending vote record into aggregate before hypocrisy scoring
    # (hypocrisy flag reads fiscal_concern_rate which is already set)
    spending_votes = aggregate_spending_votes(linked_votes)
    for name in CANONICAL_MEMBERS:
        if name in spending_votes:
            aggregate[name].update(spending_votes[name])

    _flag_fiscal_hypocrisy(aggregate)

    # Enhance hypocrisy with vote-level incidents
    hypocrisy_incidents = build_vote_hypocrisy_incidents(linked_votes, aggregate)
    if hypocrisy_incidents:
        print(f"  {len(hypocrisy_incidents)} vote-level fiscal hypocrisy incidents", file=sys.stderr)
        # Attach per-member incident lists
        by_member: dict[str, list] = defaultdict(list)
        for inc in hypocrisy_incidents:
            by_member[inc["member"]].append({k: v for k, v in inc.items() if k != "member"})
        for name, incidents in by_member.items():
            if name in aggregate:
                aggregate[name]["fiscal_hypocrisy_votes"] = sorted(
                    incidents, key=lambda x: -x["dollar_total"]
                )

    # Homeless Services Orthodoxy scoring
    print("Scoring Homeless Services Orthodoxy...", file=sys.stderr)
    hso_scores = score_homeless_orthodoxy(members, linked_votes)
    for name in CANONICAL_MEMBERS:
        if name in hso_scores:
            aggregate[name].update(hso_scores[name])
    hso_sorted = sorted(
        [(n, hso_scores[n]["hso_score"]) for n in CANONICAL_MEMBERS if n in hso_scores],
        key=lambda x: -x[1],
    )
    print(f"  HSO ranking: " +
          ", ".join(f"{DISPLAY_NAME.get(n,n)} ({s:.0f})" for n, s in hso_sorted),
          file=sys.stderr)

    # Attendance scoring (from annotated agenda PDFs)
    print("Scoring attendance...", file=sys.stderr)
    attendance_scores = score_attendance()
    if attendance_scores:
        for name in CANONICAL_MEMBERS:
            if name in attendance_scores:
                aggregate[name].update(attendance_scores[name])
        bartlett_absent = attendance_scores.get("Bartlett", {}).get("sessions_fully_absent", 0)
        print(f"  Attendance loaded · Bartlett fully absent: {bartlett_absent} sessions",
              file=sys.stderr)
    else:
        print("  No annotated agendas (run annotated_scraper.py)", file=sys.stderr)

    # Major fiscal votes scoring
    print("Scoring major fiscal votes...", file=sys.stderr)
    fiscal_scores = score_major_fiscal_votes()
    for name in CANONICAL_MEMBERS:
        if name in fiscal_scores:
            aggregate[name].update(fiscal_scores[name])
    bar_fsc = fiscal_scores.get("Bartlett", {})
    print(f"  Fiscal votes · Bartlett absent: {bar_fsc.get('fiscal_vote_absent',0)}/{len(MAJOR_FISCAL_VOTES)} "
          f"(${bar_fsc.get('fiscal_dollars_absent',0):,.0f} missed)",
          file=sys.stderr)

    # Fiscal referral / bond-campaign direction scoring
    print("Scoring fiscal referral votes...", file=sys.stderr)
    referral_scores = score_fiscal_referral_votes()
    for name in CANONICAL_MEMBERS:
        if name in referral_scores:
            aggregate[name].update(referral_scores[name])
    ref_authored = [(n, referral_scores[n]["fiscal_referral_authored"])
                    for n in CANONICAL_MEMBERS if referral_scores.get(n, {}).get("fiscal_referral_authored", 0) > 0]
    if ref_authored:
        print(f"  Referral authors: " +
              ", ".join(f"{DISPLAY_NAME.get(n,n)} ({v})" for n, v in sorted(ref_authored, key=lambda x: -x[1])),
              file=sys.stderr)
    else:
        print(f"  No referral authorship found in agenda JSONs (data may be missing for some dates)",
              file=sys.stderr)

    # Annotated-agenda vote statistics (all sessions — includes abstention tracking)
    print("Scoring annotated vote record...", file=sys.stderr)
    annot_vote_scores = score_annotated_votes()
    if annot_vote_scores:
        for name in CANONICAL_MEMBERS:
            if name in annot_vote_scores:
                aggregate[name].update(annot_vote_scores[name])
        abstain_leaders = sorted(
            [(n, annot_vote_scores[n]["annot_vote_abstain"]) for n in CANONICAL_MEMBERS],
            key=lambda x: -x[1],
        )[:3]
        print(f"  Abstention leaders: " +
              ", ".join(f"{DISPLAY_NAME.get(n,n)} ({v})" for n, v in abstain_leaders),
              file=sys.stderr)

    # Procurement integrity (requires packet_scraper reports to be cached)
    proc_scores = score_procurement_integrity(linked_votes)
    if proc_scores:
        for name in CANONICAL_MEMBERS:
            if name in proc_scores:
                aggregate[name].update(proc_scores[name])
        n_flagged = sum(1 for s in proc_scores.values() if s.get("procurement_flagged_yes", 0) > 0)
        print(f"  Procurement signals loaded ({n_flagged} members with flagged-item votes)",
              file=sys.stderr)
    else:
        print("  No staff report cache (run packet_scraper.py for procurement signals)",
              file=sys.stderr)

    # Incidents / anecdotes
    print("Loading incident records...", file=sys.stderr)
    incidents = load_incidents()
    for name in CANONICAL_MEMBERS:
        if name in incidents:
            aggregate[name].update(incidents[name])
    if incidents:
        print(f"  {sum(v['incident_count'] for v in incidents.values())} incidents across "
              f"{len(incidents)} members", file=sys.stderr)

    # Audit silence penalty
    audit_silence = load_audit_silence()
    for name in CANONICAL_MEMBERS:
        if name in audit_silence:
            aggregate[name].update(audit_silence[name])
    if audit_silence:
        print(f"  Audit silence: {sum(len(v['audit_silence_events']) for v in audit_silence.values())} "
              f"events across {len(audit_silence)} members", file=sys.stderr)

    # Newsletter P1 silence penalty
    newsletter_silence = score_newsletter_p1_silence()
    for name in CANONICAL_MEMBERS:
        if name in newsletter_silence:
            aggregate[name].update(newsletter_silence[name])
    if newsletter_silence:
        n_newsletters = sum(len(v["newsletter_events"]) for v in newsletter_silence.values())
        print(f"  Newsletter P1 silence: {n_newsletters} newsletters penalized "
              f"across {len(newsletter_silence)} members", file=sys.stderr)

    # Tier 1 composite grade
    print("Computing Tier 1 composite grade...", file=sys.stderr)
    for name in CANONICAL_MEMBERS:
        cg = compute_composite_grade(aggregate[name])
        aggregate[name].update(cg)
    grade_summary = sorted(
        [(n, aggregate[n]["composite_grade"]) for n in CANONICAL_MEMBERS],
        key=lambda x: -x[1],
    )
    print("  Composite grades: " +
          ", ".join(f"{DISPLAY_NAME.get(n,n)} ({v:.3f})" for n, v in grade_summary),
          file=sys.stderr)

    # Cohort percentile rank (1 = best in cohort; 100th percentile = top)
    ranked = sorted(CANONICAL_MEMBERS, key=lambda n: aggregate[n].get("composite_grade", 0))
    n_m = len(ranked)
    for rank_idx, name in enumerate(ranked):
        pct = round(rank_idx / (n_m - 1) * 100) if n_m > 1 else 50
        aggregate[name]["cohort_rank"]       = n_m - rank_idx   # 1 = best
        aggregate[name]["cohort_percentile"] = pct              # 0 = worst, 100 = best

    # --- Snapshot + deltas ---
    print("Computing iteration deltas...", file=sys.stderr)
    prev_snapshot = load_latest_snapshot()
    if prev_snapshot:
        deltas = compute_deltas(aggregate, prev_snapshot)
        for name, d in deltas.items():
            if name in aggregate and d:
                aggregate[name]["_delta"] = d
        snap_ts = prev_snapshot.get("_meta", {}).get("generated", "unknown")[:10]
        print(f"  Deltas vs snapshot from {snap_ts}", file=sys.stderr)
    else:
        print("  No prior snapshot — this run will become the baseline", file=sys.stderr)

    if args.scores_only:
        _print_summary(aggregate, council_vote_meta)
        return

    # --- Save ---
    os.makedirs(SCORES_DIR, exist_ok=True)
    with open(AGGREGATE_PATH, "w") as f:
        json.dump(aggregate, f, indent=2, default=str)
    print(f"\nSaved aggregate scores → {AGGREGATE_PATH}", file=sys.stderr)
    snap_path = save_snapshot()
    if snap_path:
        print(f"Snapshot saved → {snap_path}", file=sys.stderr)

    with open(MEETINGS_PATH, "w") as f:
        json.dump(meetings, f, indent=2, default=str)
    print(f"Saved per-meeting scores → {MEETINGS_PATH}", file=sys.stderr)

    linked_votes_path = os.path.join(SCORES_DIR, "linked_votes.json")
    with open(linked_votes_path, "w") as f:
        json.dump(linked_votes, f, indent=2, default=str)
    print(f"Saved linked votes → {linked_votes_path}", file=sys.stderr)

    _print_summary(aggregate, council_vote_meta)

    if not args.no_pdf:
        print("\nGenerating PDF scorecards...", file=sys.stderr)
        from scorecard_pdf import generate_all
        generate_all(aggregate, council_vote_meta)


def _print_summary(aggregate: dict, council_meta: dict):
    members = {n: s for n, s in aggregate.items()
               if not n.startswith("_") and n != "Ishii"
               and s.get("words", 0) >= _cs.MIN_WORDS}

    print(f"\n{'='*110}")
    print(f"  {'MEMBER':<13} {'GRADE':>7} {'RNK':>4} {'TAXPYR':>7} {'FOCUS':>7} {'ATTEND':>8} "
          f"{'WASTE%':>8} {'P1%':>5} {'EFF':>8} {'REFS':>6} {'SPONS':>7}")
    print(f"{'='*110}")
    for n in sorted(members, key=lambda x: -members[x].get("composite_grade", 0)):
        s = members[n]
        dn = DISPLAY_NAME.get(n, n)
        att_ded  = s.get("composite_attendance_ded", 0) or 0
        lw_pen   = s.get("composite_lightweight_pen", 0) or 0
        att_disp = f"-{(att_ded + lw_pen)*100:.0f}%" if (att_ded + lw_pen) > 0.005 else "  ok"
        rank     = s.get("cohort_rank", "-")
        rank_str = f"{rank}/{len(CANONICAL_MEMBERS)}" if isinstance(rank, int) else "-"
        print(
            f"  {dn:<13}"
            f"  {s.get('composite_grade',0):>6.3f}"
            f"  {rank_str:>5}"
            f"  {s.get('composite_taxpayer',0):>6.3f}"
            f"  {s.get('composite_focus',0):>6.3f}"
            f"  {att_disp:>7}"
            f"  {s.get('waste_pct',0)*100:>7.1f}%"
            f"  {s.get('p1_speech_pct',0)*100:>4.1f}%"
            f"  {s.get('avg_turn_len',0):>7.1f}w"
            f"  {s.get('staff_referrals',0):>5}"
            f"  {s.get('sponsorships',0):>6}"
        )
    print(f"\n  Council block-vote rate: {council_meta['block_vote_rate']*100:.0f}%  "
          f"({council_meta['block_vote_events']} of {council_meta['total_vote_events']} events)")


if __name__ == "__main__":
    main()
