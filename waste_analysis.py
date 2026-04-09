"""
Quantify time (by word count) spent on core city business vs. posturing/waste
across Berkeley City Council transcripts.

Classification is keyword-based, reflecting a voter's perspective that the
council should focus on:
  CORE: infrastructure, fiscal management, housing/zoning, public safety
        (working with police), economic development, land use
  WASTE: foreign/national policy posturing, police over-surveillance theater,
         tax increases, symbolic/virtue-signal resolutions, fluff programs

Usage:
    python waste_analysis.py [--detail] [--by-speaker]
"""

import argparse
import glob
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

TEXT_DIR = os.path.join(os.path.dirname(__file__), "text")

# ---------------------------------------------------------------------------
# Classification keyword lists
# ---------------------------------------------------------------------------

# Any turn where these appear gets classified as WASTE
WASTE_KEYWORDS = [
    # Foreign / national policy posturing
    "gaza", "israel", "palestine", "palestinian", "ceasefire",
    "arms embargo", "genocide", "apartheid", "boycott", "bds",
    "iran", "sanctions", "ukraine", "russia", "yemen", "nato",
    "foreign policy", "war crimes", "occupied territory",
    "land acknowledgment", "land acknowledgement",
    # Police over-surveillance / accountability theater
    "police accountability board", r"\bpab\b", "flock camera",
    "surveillance technology", "surveillance contract",
    "defund", "cahoots",
    # Symbolic / virtue-signal resolutions
    "sister city", "sanctuary city",   # sanctuary policy = real; resolutions = posturing
    "resolution of solidarity", "resolution condemning",
    "resolution supporting", "hate crime resolution",
    # Tax increases (flagged; not automatically waste, but notable)
    "tax increase", "raise taxes", "new tax", "parcel tax",
    "transfer tax",
]

# Turns where these appear get a CORE credit (counterweight to waste keywords)
CORE_KEYWORDS = [
    # Infrastructure & capital
    "infrastructure", "road", "street", "sidewalk", "pothole",
    "sewer", "storm drain", "capital improvement", "maintenance",
    "gilman", "measure ff", "measure t1",
    # Budget & fiscal
    "budget", "general fund", "reserve fund", "fiscal",
    "deficit", "revenue", "expenditure", "cost savings",
    "cut", "reduce spending", "efficiency",
    # Housing & land use (actual decisions, not posturing)
    "zoning", "density", "housing element", "adu",
    "affordable housing", "middle housing", "permit",
    "development agreement", "environmental review",
    "planning commission", "land use", "appeal",
    # Fire / emergency / public safety
    "fire", "wildfire", "zone zero", "home hardening",
    "vegetation management", "evacuation", "emergency",
    "disaster preparedness",
    # Working with police (cooperative framing)
    "police department", "chief", "crime", "officer",
    "response time", "patrol", "dispatch",
    # Economic development
    "business district", "commercial", "economic development",
    "small business", "downtown", "permit streamlining",
]

# Speakers who are NOT council members — exclude from individual stats
NON_COUNCIL = {
    "CITY CLERK", "CLERK", "CITY MANAGER", "CITY MANAGER BUDDENHAGEN",
    "PUBLIC SPEAKER", "SPEAKER", "CITY ATTORNEY", "STAFF",
    "CITY STAFF", "CITY AUDITOR", "UNIDENTIFIED",
    # add more staff as encountered
}

# Map raw speaker labels → canonical names
COUNCIL_ALIASES = {
    "MAYOR ISHII": "Ishii",
    "MAYOR A. ISHII": "Ishii",
    "A. ISHII": "Ishii",
    "ISHII": "Ishii",
    "R. KESARWANI": "Kesarwani",
    "KESARWANI": "Kesarwani",
    "T. TAPLIN": "Taplin",
    "TAPLIN": "Taplin",
    "B. BARTLETT": "Bartlett",
    "BARTLETT": "Bartlett",
    "I. TREGUB": "Tregub",
    "TREGUB": "Tregub",
    "S. O'KEEFE": "O'Keefe",
    "O'KEEFE": "O'Keefe",
    "B. BLACKABY": "Blackaby",
    "BLACKABY": "Blackaby",
    "C. LUNAPARRA": "LunaParra",
    "LUNAPARRA": "LunaParra",
    "C. LUNA PARRA": "LunaParra",
    "M. HUMBERT": "Humbert",
    "HUMBERT": "Humbert",
    # Zoom/Boardroom-format names (first-name or full)
    "Terry Taplin": "Taplin",
    "Rigel Kesarwani": "Kesarwani",
    "Igor Tregub": "Tregub",
    "Ben Bartlett": "Bartlett",
    "Sophie O'Keefe": "O'Keefe",
    "Mark Humbert": "Humbert",
    "Cecilia LunaParra": "LunaParra",
    "Andy Kelley": "Kelley (staff?)",
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Turn:
    speaker_raw: str
    speaker: Optional[str]      # canonical council name, or None
    is_council: bool
    is_public: bool
    text: str
    words: int
    waste_score: float          # 0-1
    core_score: float           # 0-1
    label: str                  # WASTE / CORE / MIXED / PROCEDURAL


@dataclass
class MeetingStats:
    filename: str
    total_words: int = 0
    council_words: int = 0
    public_words: int = 0
    waste_words: int = 0
    core_words: int = 0
    mixed_words: int = 0
    proc_words: int = 0
    duration_sec: Optional[float] = None
    turns: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _match_keywords(text: str, keywords: list) -> int:
    t = text.lower()
    count = 0
    for kw in keywords:
        if re.search(kw, t):
            count += 1
    return count


def classify_turn(text: str) -> tuple[float, float, str]:
    """Return (waste_score, core_score, label)."""
    waste_hits = _match_keywords(text, WASTE_KEYWORDS)
    core_hits  = _match_keywords(text, CORE_KEYWORDS)

    if waste_hits == 0 and core_hits == 0:
        return 0.0, 0.0, "PROCEDURAL"
    if waste_hits > 0 and core_hits == 0:
        return 1.0, 0.0, "WASTE"
    if core_hits > 0 and waste_hits == 0:
        return 0.0, 1.0, "CORE"
    # Both — lean toward the stronger signal
    total = waste_hits + core_hits
    ws = waste_hits / total
    cs = core_hits / total
    label = "WASTE" if ws >= 0.6 else ("CORE" if cs >= 0.6 else "MIXED")
    return ws, cs, label


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _normalize_text(raw: str) -> str:
    raw = raw.replace("\ufb01", "fi").replace("\ufb02", "fl")
    raw = re.sub(
        r"This information provided by.*?we did not create it\.",
        " ", raw, flags=re.IGNORECASE | re.DOTALL,
    )
    raw = re.sub(r"\f", "\n", raw)
    return raw


def parse_chevron_format(text: str) -> list[dict]:
    """Parse >> SPEAKER: text turns."""
    turns = []
    # Split on >> boundaries; keep delimiter
    segments = re.split(r"(>>)", text)
    combined = []
    i = 0
    while i < len(segments):
        if segments[i] == ">>":
            combined.append(">>" + (segments[i+1] if i+1 < len(segments) else ""))
            i += 2
        else:
            i += 1

    for seg in combined:
        m = re.match(r">>\s*([^:]{1,60}):\s*(.*)", seg, re.DOTALL)
        if m:
            speaker_raw = m.group(1).strip().upper()
            body = m.group(2).strip()
        else:
            speaker_raw = "UNKNOWN"
            body = seg[2:].strip()
        turns.append({"speaker_raw": speaker_raw, "text": body})
    return turns


def parse_boardroom_format(text: str) -> list[dict]:
    """Parse Boardroom: text turns (no timestamps)."""
    turns = []
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z][A-Za-z '\-]{0,40}):\s+(.*)", line)
        if m:
            turns.append({"speaker_raw": m.group(1).strip(), "text": m.group(2).strip()})
    return turns


def parse_vtt_format(text: str) -> list[dict]:
    """Parse WebVTT turns; extract timestamps for real-time durations."""
    turns = []
    # Split into VTT cue blocks
    blocks = re.split(r"\n\s*\n", text)
    ts_re = re.compile(r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})")

    def ts_to_sec(ts):
        ts = ts.replace(",", ".")
        parts = ts.split(":")
        return int(parts[0])*3600 + int(parts[1])*60 + float(parts[2])

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue
        # Find timestamp line
        ts_line = None
        body_lines = []
        for ln in lines:
            m = ts_re.match(ln)
            if m:
                ts_line = m
            elif not re.match(r"^\d+$", ln):  # skip cue numbers
                body_lines.append(ln)

        body = " ".join(body_lines).strip()
        if not body:
            continue

        start_sec = ts_to_sec(ts_line.group(1)) if ts_line else None
        end_sec   = ts_to_sec(ts_line.group(2)) if ts_line else None
        duration  = (end_sec - start_sec) if (start_sec is not None and end_sec is not None) else None

        # Try to parse speaker from "Board Room: text" or "Name: text"
        m2 = re.match(r"^([A-Za-z][A-Za-z '\-]{0,40}):\s+(.*)", body, re.DOTALL)
        if m2:
            speaker_raw = m2.group(1).strip()
            text_body   = m2.group(2).strip()
        else:
            speaker_raw = "Board Room"
            text_body   = body

        turns.append({
            "speaker_raw": speaker_raw,
            "text": text_body,
            "start_sec": start_sec,
            "duration_sec": duration,
        })
    return turns


def detect_format(text: str) -> str:
    if "WEBVTT" in text[:500]:
        return "vtt"
    if re.search(r"^Boardroom:", text, re.MULTILINE):
        return "boardroom"
    if ">>" in text:
        return "chevron"
    return "unknown"


def resolve_speaker(speaker_raw: str) -> tuple[Optional[str], bool, bool]:
    """Return (canonical_name_or_none, is_council, is_public)."""
    raw_upper = speaker_raw.upper().strip()
    # Check alias table (case-insensitive key lookup)
    for alias, canonical in COUNCIL_ALIASES.items():
        if alias.upper() == raw_upper:
            return canonical, True, False
    # Non-council staff
    for nc in NON_COUNCIL:
        if raw_upper == nc.upper():
            return None, False, False
    # Boardroom / Board Room = council (undifferentiated)
    if raw_upper in ("BOARDROOM", "BOARD ROOM"):
        return "Council (undiff.)", True, False
    # Heuristic: ALL-CAPS with COUNCILMEMBER prefix
    m = re.match(r"COUNCILMEMBER[S]?\s+([A-Z']+)", raw_upper)
    if m:
        name = m.group(1).title()
        return name, True, False
    # In Boardroom format, short first-name-only labels = public
    if len(speaker_raw.split()) <= 2 and speaker_raw[0].isupper():
        # Could be public commenter
        return None, False, True
    return None, False, True  # default: public


# ---------------------------------------------------------------------------
# Process a single file
# ---------------------------------------------------------------------------

def process_file(path: str) -> MeetingStats:
    stats = MeetingStats(filename=os.path.basename(path))
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    text = _normalize_text(raw)

    fmt = detect_format(text)
    if fmt == "vtt":
        raw_turns = parse_vtt_format(text)
    elif fmt == "boardroom":
        raw_turns = parse_boardroom_format(text)
    elif fmt == "chevron":
        raw_turns = parse_chevron_format(text)
    else:
        return stats  # can't parse

    # Track total VTT duration if available
    total_dur = 0.0
    has_dur = False

    for rt in raw_turns:
        body = rt["text"]
        if not body.strip():
            continue
        words = len(body.split())
        speaker_raw = rt.get("speaker_raw", "UNKNOWN")
        canonical, is_council, is_public = resolve_speaker(speaker_raw)
        ws, cs, label = classify_turn(body)
        dur = rt.get("duration_sec")
        if dur:
            has_dur = True
            total_dur += dur

        turn = Turn(
            speaker_raw=speaker_raw,
            speaker=canonical,
            is_council=is_council,
            is_public=is_public,
            text=body,
            words=words,
            waste_score=ws,
            core_score=cs,
            label=label,
        )
        stats.turns.append(turn)
        stats.total_words += words
        if is_council:
            stats.council_words += words
            if label == "WASTE":
                stats.waste_words += words
            elif label == "CORE":
                stats.core_words += words
            elif label == "MIXED":
                stats.mixed_words += words
            else:
                stats.proc_words += words
        elif is_public:
            stats.public_words += words

    if has_dur:
        stats.duration_sec = total_dur

    return stats


# ---------------------------------------------------------------------------
# Aggregate speaker stats across all meetings
# ---------------------------------------------------------------------------

def speaker_stats(all_stats: list[MeetingStats]) -> dict:
    by_speaker = defaultdict(lambda: defaultdict(int))
    for ms in all_stats:
        for t in ms.turns:
            if not t.is_council or t.speaker in (None, "Council (undiff.)"):
                continue
            s = t.speaker
            by_speaker[s]["total"] += t.words
            by_speaker[s][t.label] += t.words
    return by_speaker


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def pct(num, denom):
    return f"{100*num/denom:.1f}%" if denom else "N/A"


def print_meeting_summary(all_stats: list[MeetingStats]):
    print("\n" + "=" * 90)
    print(f"{'MEETING':<58} {'COUNCIL WDS':>11} {'WASTE%':>7} {'CORE%':>7} {'PROC%':>7}")
    print("=" * 90)
    total_council = total_waste = total_core = 0
    for ms in all_stats:
        cw = ms.council_words
        if cw == 0:
            continue
        label = ms.filename.replace(" Captioning.txt", "").replace(" Captioning", "")
        label = label.replace(".txt", "")
        print(
            f"  {label:<56} {cw:>11,}"
            f"  {pct(ms.waste_words, cw):>7}"
            f"  {pct(ms.core_words, cw):>7}"
            f"  {pct(ms.proc_words, cw):>7}"
        )
        total_council += cw
        total_waste   += ms.waste_words
        total_core    += ms.core_words
    print("-" * 90)
    print(
        f"  {'TOTAL / AVERAGE':<56} {total_council:>11,}"
        f"  {pct(total_waste, total_council):>7}"
        f"  {pct(total_core, total_council):>7}"
    )


def print_speaker_summary(all_stats: list[MeetingStats]):
    by_spkr = speaker_stats(all_stats)
    if not by_spkr:
        print("\n(No individual speaker data — all meetings used Boardroom: format)")
        return

    print("\n" + "=" * 75)
    print(f"  {'COUNCIL MEMBER':<18} {'TOTAL WDS':>10} {'WASTE WDS':>10} {'WASTE%':>8} {'CORE%':>8}")
    print("=" * 75)
    rows = sorted(by_spkr.items(), key=lambda x: -x[1]["total"])
    for name, d in rows:
        tot = d["total"]
        w   = d.get("WASTE", 0)
        c   = d.get("CORE", 0)
        print(f"  {name:<18} {tot:>10,} {w:>10,} {pct(w, tot):>8} {pct(c, tot):>8}")


def print_waste_examples(all_stats: list[MeetingStats], n=10):
    print(f"\n--- Top {n} longest WASTE turns by council members ---")
    waste_turns = []
    for ms in all_stats:
        for t in ms.turns:
            if t.is_council and t.label == "WASTE":
                waste_turns.append((t.words, ms.filename, t.speaker, t.text[:200]))
    waste_turns.sort(reverse=True)
    for words, fname, speaker, snippet in waste_turns[:n]:
        meeting = fname.replace(" Captioning.txt", "")[:50]
        print(f"\n  [{words} words] {speaker} @ {meeting}")
        print(f"  \"{snippet}...\"")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", action="store_true", help="Print example waste turns")
    args = parser.parse_args()

    paths = sorted(glob.glob(os.path.join(TEXT_DIR, "*.txt")))
    print(f"Processing {len(paths)} transcripts...")

    all_stats = []
    for p in paths:
        ms = process_file(p)
        all_stats.append(ms)
        print(f"  {ms.filename[:60]:<60} {ms.total_words:>8,} words  ({ms.council_words:,} council)")

    print_meeting_summary(all_stats)
    print_speaker_summary(all_stats)

    if args.examples:
        print_waste_examples(all_stats)


if __name__ == "__main__":
    main()
