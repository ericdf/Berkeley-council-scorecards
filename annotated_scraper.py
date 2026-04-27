"""
annotated_scraper.py
====================
Downloads Berkeley City Council Annotated Agenda PDFs and extracts:
  - Per-meeting attendance: present, absent, arrived-late
  - Per-item votes: ayes, noes, abstain, absent

URL patterns:
  Regular:  https://berkeleyca.gov/sites/default/files/city-council-meetings/YYYY-MM-DD Annotated Agenda - Council.pdf
  Special:  https://berkeleyca.gov/sites/default/files/city-council-meetings/YYYY-MM-DD Special Annotated Agenda - Council.pdf

Saves per-meeting JSON to agendas/annotated/YYYY-MM-DD-[regular|special].json

Usage:
    python annotated_scraper.py              # fetch all not-yet-cached
    python annotated_scraper.py --refresh    # re-fetch everything
    python annotated_scraper.py --date 2026-01-27
"""

import argparse
import io
import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import quote

import pdfplumber
import requests

BASE_URL    = "https://berkeleyca.gov/sites/default/files/city-council-meetings/"
ANNOT_DIR   = os.path.join(os.path.dirname(__file__), "agendas", "annotated")

# All dates that have meetings (from agenda_scraper.py AGENDA_URL_MAP)
ALL_DATES = [
    "2024-12-10",
    "2025-01-21",
    "2025-02-11", "2025-02-25",
    "2025-03-11", "2025-03-18", "2025-03-25",
    "2025-04-15", "2025-04-22", "2025-04-28", "2025-04-29",
    "2025-05-06", "2025-05-20",
    "2025-06-03", "2025-06-17", "2025-06-24", "2025-06-26",
    "2025-07-08", "2025-07-22", "2025-07-23", "2025-07-29",
    "2025-09-09", "2025-09-16", "2025-09-30",
    "2025-10-14", "2025-10-28",
    "2025-11-06", "2025-11-10", "2025-11-18",
    "2025-12-02",
    "2026-01-20", "2026-01-27",
    "2026-02-10", "2026-02-23", "2026-02-24",
    "2026-03-10", "2026-03-17", "2026-03-24",
    "2026-04-14", "2026-04-21", "2026-04-28",
    "2026-06-02",
]

# Canonical name mapping for names as they appear in annotated agendas
CANONICAL = {
    "kesarwani":  "Kesarwani",
    "taplin":     "Taplin",
    "bartlett":   "Bartlett",
    "tregub":     "Tregub",
    "o'keefe":    "OKeefe",
    "okeefe":     "OKeefe",
    "blackaby":   "Blackaby",
    "lunaparra":  "LunaParra",
    "lunapara":   "LunaParra",
    "humbert":    "Humbert",
    "ishii":      "Ishii",
}

def resolve(name: str) -> str | None:
    key = name.lower().strip().replace(" ", "").replace("'", "").replace("\u2019", "")
    return CANONICAL.get(key)

def resolve_list(raw: str) -> list[str]:
    """Parse 'Kesarwani, Taplin, O\u2019Keefe' → ['Kesarwani', 'Taplin', 'OKeefe']"""
    names = []
    for part in re.split(r"[,;]+", raw):
        part = part.strip()
        if not part:
            continue
        c = resolve(part)
        if c:
            names.append(c)
    return names


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_text(pdf_bytes: bytes) -> str:
    """Extract full text from PDF bytes using pdfplumber."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = []
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
        return "\n".join(pages)


# ---------------------------------------------------------------------------
# Attendance parsing
# ---------------------------------------------------------------------------

ROLL_CALL_RE   = re.compile(r"Roll\s+Call:\s*(\d+:\d+\s*[ap]\.m\.)", re.IGNORECASE)
PRESENT_RE     = re.compile(r"Present:\s*(.+?)(?=\nAbsent:|\nCouncilmember|\nLand\s+Acknowledge|\nCeremonial|\Z)", re.DOTALL | re.IGNORECASE)
ABSENT_RE      = re.compile(r"Absent:\s*(.+?)(?=\nCouncilmember\s+\w+\s+present|\nLand\s+Acknowledge|\nCeremonial|\nAction:|\Z)", re.DOTALL | re.IGNORECASE)
LATE_RE        = re.compile(r"Councilmember\s+(\w+)\s+present\s+at\s+(\d+:\d+\s*[ap]\.m\.)", re.IGNORECASE)


def parse_attendance(text: str) -> dict:
    """Extract roll call, present, absent, arrived_late from full PDF text."""
    result = {
        "roll_call_time": None,
        "present": [],
        "absent": [],
        "arrived_late": [],
    }

    # Roll call time
    m = ROLL_CALL_RE.search(text)
    if m:
        result["roll_call_time"] = m.group(1).strip()

    # Present list
    m = PRESENT_RE.search(text)
    if m:
        raw = m.group(1).replace("\n", " ").strip()
        if raw.lower() not in ("none", "none."):
            result["present"] = resolve_list(raw)

    # Absent list
    m = ABSENT_RE.search(text)
    if m:
        raw = m.group(1).replace("\n", " ").strip()
        # Trim trailing boilerplate
        raw = re.split(r"Land\s+Acknowledge|Ceremonial|Action:", raw, flags=re.IGNORECASE)[0].strip()
        if raw.lower() not in ("none", "none."):
            result["absent"] = resolve_list(raw)

    # Late arrivals
    for m in LATE_RE.finditer(text):
        name = resolve(m.group(1))
        if name:
            result["arrived_late"].append({
                "name": name,
                "time": m.group(2).strip(),
            })

    return result


# ---------------------------------------------------------------------------
# Vote line parsing
# ---------------------------------------------------------------------------

# Matches: "Ayes – Name, Name; Noes – None; Abstain – Name."
# "Absent –" is optional: Berkeley omits it when nobody is absent.
VOTE_BLOCK_RE = re.compile(
    r"(?:Vote:|First\s+Reading\s+Vote:)\s*"
    r"Ayes?\s*[–\-]\s*(.+?)\s*;\s*"
    r"Noes?\s*[–\-]\s*(.+?)\s*;\s*"
    r"Abstain\s*[–\-]\s*(.+?)"
    r"(?:\s*;\s*Absent\s*[–\-]\s*(.+?))?(?:\.|;|$)",
    re.IGNORECASE | re.DOTALL,
)

# Simpler "All Ayes" pattern
ALL_AYES_RE = re.compile(r"Vote:\s*All\s+Ayes", re.IGNORECASE)

# Speaker/correspondence counts in action text
SPEAKERS_RE = re.compile(r"\b(\d+)\s+speakers?\b", re.IGNORECASE)
LETTERS_RE  = re.compile(
    r"\b(\d+)\s+(?:form\s+)?(?:letters?|written\s+communications?|similarly\s+worded)",
    re.IGNORECASE,
)
# Late-night meeting extension votes
EXTENSION_RE = re.compile(r"extend\s+the\s+meeting|suspend\s+the\s+rules", re.IGNORECASE)


def _parse_names(raw: str) -> list[str]:
    raw = raw.replace("\n", " ").strip()
    if raw.lower() in ("none", "none.", ""):
        return []
    return resolve_list(raw)


def parse_vote_block(text: str) -> dict | None:
    """
    Parse vote blocks from text, returning the first one found.
    For multi-motion items, the first vote is the primary policy vote;
    subsequent votes tend to be procedural (extend meeting, continue item).
    """
    m = VOTE_BLOCK_RE.search(text)
    if not m:
        return None
    return {
        "ayes":    _parse_names(m.group(1)),
        "noes":    _parse_names(m.group(2)),
        "abstain": _parse_names(m.group(3)),
        "absent":  _parse_names(m.group(4)) if m.group(4) else [],
    }


# ---------------------------------------------------------------------------
# Item parsing
# ---------------------------------------------------------------------------

# Each item block starts with a number + period on its own line
ITEM_SPLIT_RE = re.compile(r"(?m)^(\d+)\s*[.\u00b7]\s*(.+?)(?=\n\d+\s*[.\u00b7]|\Z)", re.DOTALL)

# Extract just the "Action:" and vote lines from an item block
ACTION_RE = re.compile(r"Action:\s*(.+?)(?=\nContact:|\nFinancial|\nFrom:|\Z)", re.DOTALL | re.IGNORECASE)


def parse_items(text: str) -> list[dict]:
    """Parse per-item action and vote records from full agenda text."""
    items = []

    for m in ITEM_SPLIT_RE.finditer(text):
        number = int(m.group(1))
        chunk  = m.group(0)

        # Title: first line of chunk after "N. "
        title_m = re.match(r"^\d+\s*[.\u00b7]\s*(.+?)$", chunk, re.MULTILINE)
        title = title_m.group(1).strip() if title_m else ""

        # Action text \u2014 no length limit; votes may appear deep in multi-motion items
        action_text = ""
        action_m = ACTION_RE.search(chunk)
        if action_m:
            action_text = action_m.group(1).replace("\n", " ").strip()

        # Vote: last explicit breakdown wins (final disposition for multi-motion items)
        vote = parse_vote_block(chunk)
        if vote is None and ALL_AYES_RE.search(chunk):
            vote = {"ayes": ["all"], "noes": [], "abstain": [], "absent": []}

        # Constituent engagement signals
        speakers = 0
        sm = SPEAKERS_RE.search(chunk)
        if sm:
            speakers = int(sm.group(1))

        letters = 0
        lm = LETTERS_RE.search(chunk)
        if lm:
            letters = int(lm.group(1))

        item = {
            "number":   number,
            "title":    title[:120],
            "action":   action_text,
            "speakers": speakers,
            "letters":  letters,
        }
        if vote:
            item["vote"] = vote
        if EXTENSION_RE.search(chunk):
            item["extension_vote"] = True

        # First-reading vote (ordinances that pass in two readings)
        fr_m = re.search(r"First\s+Reading\s+Vote:\s*Ayes", chunk, re.IGNORECASE)
        if fr_m:
            fr_vote = parse_vote_block(
                chunk[fr_m.start():].replace("First Reading Vote:", "Vote:")
            )
            if fr_vote:
                item["first_reading_vote"] = fr_vote

        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Fetch + parse pipeline
# ---------------------------------------------------------------------------

def make_url(date: str, meeting_type: str) -> str:
    if meeting_type == "special":
        fname = f"{date} Special Annotated Agenda - Council.pdf"
    else:
        fname = f"{date} Annotated Agenda - Council.pdf"
    return BASE_URL + quote(fname)


def fetch_pdf(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"  ERROR {url}: {e}", file=sys.stderr)
        return None


def annotated_path(date: str, meeting_type: str) -> str:
    return os.path.join(ANNOT_DIR, f"{date}-{meeting_type}.json")


def process_meeting(date: str, meeting_type: str) -> dict | None:
    url = make_url(date, meeting_type)
    pdf_bytes = fetch_pdf(url)
    if pdf_bytes is None:
        return None

    text = extract_text(pdf_bytes)
    attendance = parse_attendance(text)
    items = parse_items(text)

    return {
        "date":         date,
        "meeting_type": meeting_type,
        "url":          url,
        "fetched":      datetime.now().isoformat(),
        **attendance,
        "items":        items,
    }


def save(data: dict):
    path = annotated_path(data["date"], data["meeting_type"])
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(refresh: bool = False, target_date: str | None = None):
    os.makedirs(ANNOT_DIR, exist_ok=True)
    fetched = skipped = not_found = 0

    dates = [target_date] if target_date else ALL_DATES

    for date in sorted(dates):
        for mtype in ("regular", "special"):
            path = annotated_path(date, mtype)
            if not refresh and os.path.exists(path):
                skipped += 1
                continue

            data = process_meeting(date, mtype)
            if data is None:
                not_found += 1
                time.sleep(0.3)
                continue

            save(data)
            n_present = len(data["present"])
            n_absent  = len(data["absent"])
            n_late    = len(data["arrived_late"])
            n_items   = len(data["items"])
            print(
                f"  {date} {mtype:7s}: {n_present} present, {n_absent} absent, "
                f"{n_late} late, {n_items} items",
                file=sys.stderr,
            )
            fetched += 1
            time.sleep(0.8)

    print(
        f"\nDone: {fetched} fetched, {skipped} cached, {not_found} not found",
        file=sys.stderr,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--date", help="YYYY-MM-DD")
    args = parser.parse_args()
    run(refresh=args.refresh, target_date=args.date)
