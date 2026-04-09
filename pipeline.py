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
    clean, resolve_name, WASTE_KW, CORE_KW, FISCAL_CONCERN_KW,
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
_DELTA_HIGHER_BETTER = {"voter", "lsi", "beer", "n_fiscal", "efficiency", "core_pct"}
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

            if meeting_off_mission > 0:
                meetings_with_off_mission += 1

        # --- Action calendar ---
        for item in agenda.get("action_items", []):
            authors    = item.get("authors", [])
            cosponsors = item.get("cosponsors", [])
            off_mission  = item.get("off_mission", False)
            dollar_total = item.get("dollar_total", 0) or 0

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
    _flag_fiscal_hypocrisy(aggregate)

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

    _print_summary(aggregate, council_vote_meta)

    if not args.no_pdf:
        print("\nGenerating PDF scorecards...", file=sys.stderr)
        from scorecard_pdf import generate_all
        generate_all(aggregate, council_vote_meta)


def _print_summary(aggregate: dict, council_meta: dict):
    members = {n: s for n, s in aggregate.items()
               if not n.startswith("_") and n != "Ishii"
               and s.get("words", 0) >= _cs.MIN_WORDS}

    print(f"\n{'='*90}")
    print(f"  {'MEMBER':<13} {'VOTER':>7} {'BEER':>7} {'RECALL':>8} {'WASTE%':>8} "
          f"{'EFF':>8} {'REFS':>6} {'SPONS':>7} {'ABS%':>7}")
    print(f"{'='*90}")
    for n in sorted(members, key=lambda x: -members[x].get("voter", 0)):
        s = members[n]
        dn = DISPLAY_NAME.get(n, n)
        print(
            f"  {dn:<13}"
            f"  {s.get('voter',0):>6.3f}"
            f"  {s.get('beer',0):>6.3f}"
            f"  {s.get('recall',0):>7.3f}"
            f"  {s.get('waste_pct',0)*100:>7.1f}%"
            f"  {s.get('avg_turn_len',0):>7.1f}w"
            f"  {s.get('staff_referrals',0):>5}"
            f"  {s.get('sponsorships',0):>6}"
            f"  {(s.get('vote_abstain_rate') or 0)*100:>6.1f}%"
        )
    print(f"\n  Council block-vote rate: {council_meta['block_vote_rate']*100:.0f}%  "
          f"({council_meta['block_vote_events']} of {council_meta['total_vote_events']} events)")


if __name__ == "__main__":
    main()
