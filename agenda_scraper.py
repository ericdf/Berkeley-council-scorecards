"""
agenda_scraper.py
=================
Fetches Berkeley City Council eAgenda pages and extracts:
  - Consent calendar items: title, authors, sponsors, fiscal claim, dollar amounts
  - Council consent items: discretionary spending with per-member amounts
  - Classification: off-mission, false fiscal impact flag
  - Action calendar items (for cross-reference)

Saves per-meeting JSON to agendas/YYYY-MM-DD-[regular|special].json

Usage:
    python agenda_scraper.py              # fetch all not-yet-cached agendas
    python agenda_scraper.py --refresh    # re-fetch everything
    python agenda_scraper.py --date 2026-03-24   # one date only
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

BASE_URL   = "https://berkeleyca.gov"
AGENDAS_DIR = os.path.join(os.path.dirname(__file__), "agendas")

# ---------------------------------------------------------------------------
# eAgenda URL map — (date, type) → slug
# Built from transcript filenames + listing page
# ---------------------------------------------------------------------------

AGENDA_URL_MAP = {
    # Dec 2024
    ("2024-12-10", "regular"): "/city-council-regular-meeting-eagenda-december-10-2024",
    ("2024-12-10", "special"): "/city-council-special-meeting-eagenda-december-10-2024",
    # Jan 2025
    ("2025-01-21", "regular"): "/city-council-regular-meeting-eagenda-january-21-2025",
    # Feb 2025
    ("2025-02-11", "regular"): "/city-council-regular-meeting-eagenda-february-11-2025",
    ("2025-02-11", "special"): "/city-council-special-meeting-eagenda-february-11-2025",
    ("2025-02-25", "regular"): "/city-council-regular-meeting-eagenda-february-25-2025",
    ("2025-02-25", "special"): "/city-council-special-meeting-eagenda-february-25-2025",
    # Mar 2025
    ("2025-03-11", "regular"): "/city-council-regular-meeting-eagenda-march-11-2025",
    ("2025-03-11", "special"): "/city-council-special-meeting-eagenda-march-11-2025",
    ("2025-03-18", "regular"): "/city-council-regular-meeting-eagenda-march-18-2025",
    ("2025-03-18", "special"): "/city-council-special-meeting-eagenda-march-18-2025",
    ("2025-03-25", "regular"): "/city-council-regular-meeting-eagenda-march-25-2025",
    ("2025-03-25", "special"): "/city-council-special-meeting-eagenda-march-25-2025",
    # Apr 2025
    ("2025-04-15", "regular"): "/city-council-regular-meeting-eagenda-april-15-2025",
    ("2025-04-15", "special"): "/city-council-special-meeting-eagenda-april-15-2025",
    ("2025-04-22", "special"): "/city-council-special-meeting-eagenda-april-22-2025",
    ("2025-04-28", "special"): "/city-council-special-meeting-eagenda-april-28-2025",
    ("2025-04-29", "regular"): "/city-council-regular-meeting-eagenda-april-29-2025",
    # May 2025
    ("2025-05-06", "regular"): "/city-council-regular-meeting-eagenda-may-6-2025",
    ("2025-05-06", "special"): "/city-council-special-meeting-eagenda-may-6-2025",
    ("2025-05-20", "regular"): "/city-council-regular-meeting-eagenda-may-20-2025",
    ("2025-05-20", "special"): "/city-council-special-meeting-eagenda-may-20-2025",
    # Jun 2025
    ("2025-06-03", "regular"): "/city-council-regular-meeting-eagenda-june-3-2025",
    ("2025-06-17", "regular"): "/city-council-regular-meeting-eagenda-june-17-2025",
    ("2025-06-24", "regular"): "/city-council-regular-meeting-eagenda-june-24-2025",
    ("2025-06-24", "special"): "/city-council-special-meeting-eagenda-june-24-2025",
    ("2025-06-26", "special"): "/city-council-special-meeting-eagenda-june-26-2025",
    # Jul 2025
    ("2025-07-08", "regular"): "/city-council-regular-meeting-eagenda-july-8-2025",
    ("2025-07-22", "regular"): "/city-council-regular-meeting-eagenda-july-22-2025",
    ("2025-07-23", "special"): "/city-council-special-meeting-eagenda-july-23-2025",
    ("2025-07-29", "regular"): "/city-council-regular-meeting-eagenda-july-29-2025",
    ("2025-07-29", "special"): "/city-council-special-meeting-eagenda-july-29-2025",
    # Sep 2025
    ("2025-09-09", "regular"): "/city-council-regular-meeting-eagenda-september-9-2025",
    ("2025-09-16", "regular"): "/city-council-regular-meeting-eagenda-september-16-2025",
    ("2025-09-16", "special"): "/city-council-special-meeting-eagenda-september-16-2025",
    ("2025-09-30", "regular"): "/city-council-regular-meeting-eagenda-september-30-2025",
    ("2025-09-30", "special"): "/city-council-special-meeting-eagenda-september-30-2025",
    # Oct 2025
    ("2025-10-14", "regular"): "/city-council-regular-meeting-eagenda-october-14-2025",
    ("2025-10-28", "regular"): "/city-council-regular-meeting-eagenda-october-28-2025",
    ("2025-10-28", "special"): "/city-council-special-meeting-eagenda-october-28-2025",
    # Nov 2025
    ("2025-11-06", "special"): "/city-council-special-meeting-eagenda-november-6-2025",
    ("2025-11-10", "regular"): "/city-council-regular-meeting-eagenda-november-10-2025",
    ("2025-11-18", "regular"): "/city-council-regular-meeting-eagenda-november-18-2025",
    ("2025-11-18", "special"): "/city-council-special-meeting-eagenda-november-18-2025",
    # Dec 2025
    ("2025-12-02", "regular"): "/city-council-regular-meeting-eagenda-december-2-2025",
    ("2025-12-02", "special"): "/city-council-special-meeting-eagenda-december-2-2025",
    # Jan 2026
    ("2026-01-20", "regular"): "/city-council-regular-meeting-eagenda-january-20-2026",
    ("2026-01-27", "regular"): "/city-council-regular-meeting-eagenda-january-27-2026",
    ("2026-01-27", "special"): "/city-council-special-meeting-eagenda-january-27-2026",
    # Feb 2026
    ("2026-02-10", "regular"): "/city-council-regular-meeting-eagenda-february-10-2026",
    ("2026-02-10", "special"): "/city-council-special-meeting-eagenda-february-10-2026",
    ("2026-02-23", "special"): "/city-council-special-meeting-eagenda-february-23-2026",
    ("2026-02-24", "regular"): "/city-council-regular-meeting-eagenda-february-24-2026",
    ("2026-02-24", "special"): "/city-council-special-meeting-eagenda-february-24-2026",
    # Mar 2026
    ("2026-03-10", "regular"): "/city-council-regular-meeting-eagenda-march-10-2026",
    ("2026-03-10", "special"): "/city-council-special-meeting-eagenda-march-10-2026",
    ("2026-03-24", "regular"): "/city-council-regular-meeting-eagenda-march-24-2026",
    ("2026-03-24", "special"): "/city-council-special-meeting-eagenda-march-24-2026",
}

# ---------------------------------------------------------------------------
# Classification — off-mission keywords for agenda titles/recommendations
# ---------------------------------------------------------------------------

# High-confidence off-mission signals
WASTE_AGENDA_KW = [
    # Foreign policy
    r"\bgaza\b", r"\bisrael(?:i)?\b", r"\bpalestine?(?:ian)?\b", r"\bhamas\b",
    r"\bukraine\b", r"\bforeign\s+(?:policy|government|nation|affairs?)\b",
    r"\binternational\s+(?:relations?|affairs?)\b",
    r"\bboycott\b", r"\bdivestment\b", r"\bbds\b",
    r"\bgenocide\b", r"\bceasefire\b",
    # Immigration theater (not city ID/services)
    r"\bsanctuary\s+cit[yi]\b",
    r"\balien\s+enemies?\s+act\b",
    r"\bice\s+(?:agents?|enforcement|detain)\b",
    r"\bdeportation\b",
    r"\bimmigration\s+enforcement\b",
    # Police oversight theater (not operations)
    r"\bpolice\s+accountability\s+board\b",
    r"\bpab\b(?!\s+\w)",  # PAB not followed by other word
    r"\bflock\s+(?:cameras?|safety|alpr)\b",
    # Social justice resolutions
    r"\bfree\s+speech\b",
    r"\bdue\s+process\b.*(?:immigr|deport|detain)",
    r"\bcivil\s+(?:rights?|liberties)\s+(?:resolution|commitment|statement)\b",
    r"\bpeace\s+and\s+justice\s+commission\b",
    # Climate posturing (declarations, not infrastructure)
    r"\bclimate\s+emergency\s+declar\b",
    r"\bclimate\s+action\s+(?:resolution|commitment|pledge)\b",
]

# Commissions that reliably produce off-mission items
OFF_MISSION_COMMISSIONS = {
    "peace and justice commission",
}

# Core city business signals — items with these are NOT off-mission
CORE_AGENDA_KW = [
    r"\binfrastructure\b", r"\bsidewalk\b", r"\bpavement\b", r"\bcurb\b",
    r"\bsewer\b", r"\bwater\b", r"\bstreet\b", r"\bbridge\b",
    r"\bhousing\b", r"\bzoning\b", r"\bpermit\b", r"\bplanning\b",
    r"\bbudget\b", r"\bfiscal\b", r"\brevenue\b", r"\bgrant\b",
    r"\bpolice\s+(?:vehicle|equipment|contract|staff|officer|department)\b",
    r"\bfire\s+(?:department|station|truck|equipment)\b",
    r"\bemergency\s+(?:services?|response|management)\b",
    r"\bpublic\s+works\b", r"\btransit\b", r"\btransportation\b",
    r"\beconomic\s+development\b", r"\bbusiness\b",
    r"\bhealth\s+(?:services?|center|program)\b",
    r"\bcontract\b.*\$",  # contracts with dollar amounts = core operations
]

# Staff referral signals (for false fiscal impact detection)
STAFF_REF_RECOM_RE = re.compile(
    r"refer\s+to\s+the\s+(?:city\s+)?(?:manager|attorney)|"
    r"direct(?:ing)?\s+(?:the\s+)?(?:city\s+)?(?:manager|staff|attorney)|"
    r"request(?:ing)?\s+(?:the\s+)?(?:city\s+)?(?:manager|staff)\s+to|"
    r"staff\s+to\s+(?:study|research|prepare|analyze|bring\s+back|report\s+on|explore|investigate)|"
    r"bring\s+back\s+a\s+(?:staff\s+)?report|"
    r"staff\s+report\s+on\b",
    re.IGNORECASE,
)

NEW_OBLIGATION_RE = re.compile(
    r"establish(?:ing)?\s+(?:a\s+)?(?:new\s+)?(?:commission|program|fund\b|position|department|office\b)|"
    r"creat(?:e|ing)\s+(?:a\s+)?(?:new\s+)?(?:commission|program|fund\b|position)|"
    r"amend(?:ing)?\s+(?:the\s+)?(?:municipal\s+code|berkeley\s+municipal|bmc)\b",
    re.IGNORECASE,
)

# Dollar amount extraction
DOLLAR_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:(million|billion))?",
    re.IGNORECASE,
)

# Per-member discretionary amounts: "$500 from Councilmember Taplin"
MEMBER_AMOUNT_RE = re.compile(
    r"\$([\d,]+)\s+from\s+(?:Councilmember\s+|Mayor\s+|Vice\s*Mayor\s+)([A-Z][A-Za-z']+)",
    re.IGNORECASE,
)

# "not to exceed $X per councilmember" — max per contributor
PER_MEMBER_CAP_RE = re.compile(
    r"not\s+to\s+exceed\s+\$([\d,]+)\s+per\s+councilmember",
    re.IGNORECASE,
)

# From-field person extraction: "Title Name (Role)"
FROM_PERSON_RE = re.compile(
    r"(?:Councilmember|Vice\s*Mayor|Mayor)\s+([A-Z][A-Za-z''\-]+)\s+\(([^)]+)\)",
    re.IGNORECASE,
)

# Section boundary patterns
CONSENT_HEADER_RE  = re.compile(r"^Consent\s+Calendar\s*$", re.IGNORECASE | re.MULTILINE)
COUNCIL_CONSENT_RE = re.compile(r"^Council\s+Consent\s+Items?\s*$", re.IGNORECASE | re.MULTILINE)
ACTION_HEADER_RE   = re.compile(r"^Action\s+Calendar\s*$", re.IGNORECASE | re.MULTILINE)
INFO_HEADER_RE     = re.compile(r"^Information\s+(?:Calendar\s*)?(?:Reports?\s*)?$", re.IGNORECASE | re.MULTILINE)

# Item start: number + period on its own line, then hyphen-prefixed title
ITEM_START_RE = re.compile(r"(?:^|\n)(\d+)\.\n-(.+?)(?=\n(?:\d+\.\n-|Council\s+Consent|Action\s+Calendar|Information\s+(?:Calendar|Report)|$))", re.DOTALL)


# ---------------------------------------------------------------------------
# Name resolution (map agenda names to canonical scorecard names)
# ---------------------------------------------------------------------------

AGENDA_TO_CANONICAL = {
    "ishii":      "Ishii",
    "kesarwani":  "Kesarwani",
    "taplin":     "Taplin",
    "bartlett":   "Bartlett",
    "tregub":     "Tregub",
    "okeefe":     "OKeefe",
    "o'keefe":    "OKeefe",
    "blackaby":   "Blackaby",
    "lunaparra":  "LunaParra",
    "lunapara":   "LunaParra",
    "luna parra": "LunaParra",
    "humbert":    "Humbert",
}

def resolve_agenda_name(raw: str) -> str | None:
    key = raw.lower().strip().replace(" ", "").replace("'", "")
    # Try direct
    if key in AGENDA_TO_CANONICAL:
        return AGENDA_TO_CANONICAL[key]
    # Try with apostrophe variants
    key2 = raw.lower().strip()
    if key2 in AGENDA_TO_CANONICAL:
        return AGENDA_TO_CANONICAL[key2]
    return None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_off_mission(title: str, recommendation: str, from_commission: str) -> tuple[bool, list[str]]:
    """Return (is_off_mission, reasons)."""
    reasons = []
    text = (title + " " + recommendation).lower()

    # Check commission source first — high-confidence signal
    comm_lower = from_commission.lower()
    if any(c in comm_lower for c in OFF_MISSION_COMMISSIONS):
        reasons.append(f"from off-mission commission: {from_commission}")

    # Check waste keywords
    for kw in WASTE_AGENDA_KW:
        if re.search(kw, text, re.IGNORECASE):
            reasons.append(f"keyword: {kw}")

    # If it has strong core signals, override
    if reasons:
        core_hits = sum(1 for kw in CORE_AGENDA_KW if re.search(kw, text, re.IGNORECASE))
        if core_hits >= 2 and not any("commission" in r for r in reasons):
            return False, []  # core signals override keyword hits

    return bool(reasons), reasons


SECOND_READING_RE = re.compile(r"adopt\s+the\s+second\s+reading\b", re.IGNORECASE)

# Broader obligation signals for "staff time" understatement detection
# (NEW_OBLIGATION_RE catches formal legal changes; this catches policy directives too)
# "implement.*" excluded — too broad; matches descriptions of what external agencies do.
# Use "to ban|prohibit" to require a directive form, not a description.
BROAD_OBLIGATION_RE = re.compile(
    r"establish(?:ing)?\s+(?:a\s+)?(?:new\s+)?(?:commission|program|fund\b|position|department|office\b)|"
    r"creat(?:e|ing)\s+(?:a\s+)?(?:new\s+)?(?:commission|program|fund\b|position|permit|process)|"
    r"amend(?:ing)?\s+(?:the\s+)?(?:municipal\s+code|berkeley\s+municipal|bmc)\b|"
    r"\bto\s+(?:ban|prohibit)\b|"
    r"develop.*(?:guidelines?|policy|policies|framework|ordinance|protocol)",
    re.IGNORECASE,
)

def check_false_fiscal(financial_raw: str, recommendation: str) -> bool:
    """
    True if item claims no fiscal impact but clearly has one.

    Two patterns:
    1. "None" claim + staff referral or formal obligation — outright false
    2. "Staff time" claim + broad obligation signal — understates real cost of
       directing staff to create new programs, bans, permitting processes, etc.
    """
    fin = financial_raw.strip().lower()
    # Second readings were already analysed at first reading — not a false claim
    if SECOND_READING_RE.search(recommendation):
        return False

    if fin in ("none", "none."):
        has_staff_ref = bool(STAFF_REF_RECOM_RE.search(recommendation))
        has_obligation = bool(NEW_OBLIGATION_RE.search(recommendation))
        return has_staff_ref or has_obligation

    if "staff time" in fin:
        return bool(BROAD_OBLIGATION_RE.search(recommendation))

    return False


def extract_dollar_total(text: str) -> int:
    """Sum all dollar amounts in text. Returns cents-free integer."""
    total = 0
    for m in DOLLAR_RE.finditer(text):
        raw = m.group(1).replace(",", "")
        multiplier = m.group(2)
        try:
            val = float(raw)
            if multiplier and multiplier.lower() == "million":
                val *= 1_000_000
            elif multiplier and multiplier.lower() == "billion":
                val *= 1_000_000_000
            total += int(val)
        except ValueError:
            pass
    return total


def parse_from_field(from_raw: str) -> tuple[list[str], list[str], str]:
    """
    Parse From: field into (authors, cosponsors, commission_or_dept).
    E.g. "Councilmember Taplin (Author), Mayor Ishii (Co-Sponsor)"
    Returns canonical names where resolvable.
    """
    authors = []
    cosponsors = []
    # Extract named council members
    for m in FROM_PERSON_RE.finditer(from_raw):
        raw_name = m.group(1)
        role     = m.group(2).lower()
        canonical = resolve_agenda_name(raw_name)
        if canonical:
            if "author" in role:
                authors.append(canonical)
            else:
                cosponsors.append(canonical)

    # Commission / department (anything left after removing member entries)
    remainder = FROM_PERSON_RE.sub("", from_raw).strip(" ,")
    commission = remainder.strip(", ") if remainder else ""

    return authors, cosponsors, commission


_TITLE_NAME_RE = re.compile(
    r"(?:Councilmember|Mayor|Vice\s*Mayor)\s+([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+)?)",
    re.IGNORECASE,
)

def _resolve_full_name(raw: str) -> str | None:
    """Try last word first, then full string."""
    parts = raw.strip().split()
    for i in range(len(parts) - 1, -1, -1):
        c = resolve_agenda_name(parts[i])
        if c:
            return c
    return resolve_agenda_name(raw)


def parse_discretionary(recommendation: str, authors: list[str], cosponsors: list[str]) -> dict:
    """
    Extract per-member discretionary amounts from Council Consent Items.
    Handles both:
      - "$500 from Councilmember Taplin, Councilmember Tregub, and Mayor Ishii"  (shared amount)
      - "$500 from CM O'Keefe, $250 from CM Tregub"  (individual amounts)
    Returns {canonical_name: dollars} dict.
    """
    amounts = {}

    # Find all "$X from [list of members]" blocks
    AMOUNT_BLOCK_RE = re.compile(
        r"\$([\d,]+)\s+from\s+((?:(?:Councilmember|Mayor|Vice\s*Mayor)\s+"
        r"[A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+)?\s*(?:[,]?\s*(?:and\s+)?)?)+)",
        re.IGNORECASE,
    )
    for m in AMOUNT_BLOCK_RE.finditer(recommendation):
        try:
            amt = int(m.group(1).replace(",", ""))
        except ValueError:
            continue
        names_text = m.group(2)
        for nm in _TITLE_NAME_RE.finditer(names_text):
            canonical = _resolve_full_name(nm.group(1))
            if canonical and canonical not in amounts:
                amounts[canonical] = amt

    # Fall back: cap × all known participants
    if not amounts:
        cap_m = PER_MEMBER_CAP_RE.search(recommendation)
        if cap_m:
            try:
                cap = int(cap_m.group(1).replace(",", ""))
                for name in authors + cosponsors:
                    amounts[name] = cap
            except ValueError:
                pass

    return amounts


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.find("article") or soup.body
    return main.get_text("\n", strip=True) if main else soup.get_text("\n", strip=True)


def find_section_bounds(text: str) -> dict:
    """Find character offsets for each agenda section."""
    bounds = {}

    # Find the consent header that's actually followed by numbered items
    # (not the boilerplate occurrences). Items start with "\nN." or "\nN.-"
    ITEM_AFTER_RE = re.compile(r"Consent Calendar\n(\d+)\.[\n-]", re.IGNORECASE)
    m = ITEM_AFTER_RE.search(text)
    if m:
        bounds["consent_start"] = m.start() + len("Consent Calendar\n")
    else:
        # Fall back: second occurrence of the standalone header
        consent_matches = list(re.finditer(r"(?m)^Consent Calendar\s*$", text, re.IGNORECASE))
        if len(consent_matches) >= 2:
            bounds["consent_start"] = consent_matches[1].end()
        elif consent_matches:
            bounds["consent_start"] = consent_matches[0].end()

    council_m = COUNCIL_CONSENT_RE.search(text)
    if council_m:
        bounds["council_consent_start"] = council_m.start()

    action_m = ACTION_HEADER_RE.search(text)
    if action_m:
        bounds["action_start"] = action_m.end()

    return bounds


def parse_items_from_section(section_text: str, section_name: str) -> list[dict]:
    """Parse numbered items from a section of text."""
    items = []

    # Trim legal boilerplate that appears after the last real item
    boilerplate_m = re.search(r"\nNOTICE CONCERNING YOUR LEGAL RIGHTS|\nPublic Comment\s*[–-]\s*Items Not Listed", section_text)
    if boilerplate_m:
        section_text = section_text[:boilerplate_m.start()]

    # Split on item boundaries — handle both "\nN.\n-" and "\nN.-" formats
    raw_items = re.split(r"\n(?=\d+\.[\n-])", section_text)

    for chunk in raw_items:
        chunk = chunk.strip()
        if not chunk:
            continue

        # Extract item number + title — handle both "N.\n-Title" and "N.-Title"
        m = re.match(r"^(\d+)\.\n?-(.+?)(?:\n|$)", chunk, re.DOTALL)
        if not m:
            continue

        number = int(m.group(1))
        title  = m.group(2).strip().split("\n")[0].strip()

        # Extract From:
        from_m = re.search(r"\nFrom:\s*(.+?)(?=\nRecommendation:|\nFinancial|\Z)", chunk, re.DOTALL | re.IGNORECASE)
        from_raw = from_m.group(1).strip().replace("\n", " ") if from_m else ""

        # Extract Recommendation:
        rec_m = re.search(r"\nRecommendation:\s*(.+?)(?=\nFinancial Implications:|\nContact:|\Z)", chunk, re.DOTALL | re.IGNORECASE)
        recommendation = rec_m.group(1).strip() if rec_m else ""

        # Extract Financial Implications:
        fin_m = re.search(r"\nFinancial Implications:\s*(.+?)(?=\nContact:|\nFirst Reading|\Z)", chunk, re.DOTALL | re.IGNORECASE)
        financial_raw = fin_m.group(1).strip().split("\n")[0].strip() if fin_m else ""

        # Parse From field
        authors, cosponsors, commission = parse_from_field(from_raw)

        # Dollar amounts
        dollar_total = extract_dollar_total(recommendation)

        # Discretionary amounts (only for Council Consent Items)
        discretionary = {}
        if section_name == "council_consent":
            discretionary = parse_discretionary(recommendation, authors, cosponsors)

        # Classification
        off_mission, reasons = classify_off_mission(title, recommendation, commission)
        false_fiscal = check_false_fiscal(financial_raw, recommendation)

        items.append({
            "number":           number,
            "section":          section_name,
            "title":            title,
            "from_raw":         from_raw,
            "authors":          authors,
            "cosponsors":       cosponsors,
            "commission":       commission,
            "recommendation":   recommendation[:500],  # cap length
            "financial_raw":    financial_raw,
            "financial_none":   financial_raw.lower().strip(" .") == "none",
            "financial_staff_time": "staff time" in financial_raw.lower(),
            "dollar_total":     dollar_total,
            "discretionary":    discretionary,
            "off_mission":      off_mission,
            "off_mission_reasons": reasons,
            "false_fiscal":     false_fiscal,
        })

    return items


def parse_agenda(html: str, date: str, meeting_type: str, url: str) -> dict:
    """Parse full agenda HTML into structured dict."""
    text   = extract_text(html)
    bounds = find_section_bounds(text)

    consent_items = []
    action_items  = []

    if "consent_start" in bounds:
        consent_end = bounds.get("action_start", len(text))

        # Standard consent items (before Council Consent Items subsection)
        if "council_consent_start" in bounds:
            std_end = bounds["council_consent_start"]
        else:
            std_end = consent_end

        std_section = text[bounds["consent_start"]:std_end]
        consent_items += parse_items_from_section(std_section, "consent")

        # Council Consent Items subsection
        if "council_consent_start" in bounds:
            cc_section = text[bounds["council_consent_start"]:consent_end]
            consent_items += parse_items_from_section(cc_section, "council_consent")

    if "action_start" in bounds:
        action_end   = len(text)
        action_section = text[bounds["action_start"]:action_end]
        action_items   = parse_items_from_section(action_section, "action")

    return {
        "date":          date,
        "type":          meeting_type,
        "url":           url,
        "fetched":       datetime.now().isoformat(),
        "consent_items": consent_items,
        "action_items":  action_items,
        "n_consent":     len(consent_items),
        "n_off_mission": sum(1 for i in consent_items if i["off_mission"]),
        "n_false_fiscal": sum(1 for i in consent_items if i["false_fiscal"]),
    }


# ---------------------------------------------------------------------------
# Fetch + save
# ---------------------------------------------------------------------------

def fetch_agenda(slug: str) -> str | None:
    """Fetch eAgenda HTML. Returns text or None on error."""
    url = BASE_URL + slug
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 404:
            print(f"  404: {slug}", file=sys.stderr)
            return None
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  ERROR {slug}: {e}", file=sys.stderr)
        return None


def agenda_path(date: str, meeting_type: str) -> str:
    return os.path.join(AGENDAS_DIR, f"{date}-{meeting_type}.json")


def save_agenda(data: dict):
    path = agenda_path(data["date"], data["type"])
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_agenda(date: str, meeting_type: str) -> dict | None:
    path = agenda_path(date, meeting_type)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(refresh: bool = False, target_date: str | None = None):
    os.makedirs(AGENDAS_DIR, exist_ok=True)
    fetched = skipped = failed = 0

    keys = list(AGENDA_URL_MAP.keys())
    if target_date:
        keys = [(d, t) for d, t in keys if d == target_date]

    for (date, mtype), slug in sorted([(k, AGENDA_URL_MAP[k]) for k in keys]):
        path = agenda_path(date, mtype)
        if not refresh and os.path.exists(path):
            skipped += 1
            continue

        print(f"  Fetching {date} {mtype}...", file=sys.stderr)
        html = fetch_agenda(slug)
        if html is None:
            failed += 1
            time.sleep(0.5)
            continue

        url  = BASE_URL + slug
        data = parse_agenda(html, date, mtype, url)
        save_agenda(data)

        n_items = data["n_consent"]
        n_om    = data["n_off_mission"]
        n_ff    = data["n_false_fiscal"]
        print(f"    → {n_items} consent items, {n_om} off-mission, {n_ff} false fiscal", file=sys.stderr)

        fetched += 1
        time.sleep(1.0)   # be polite to the city's server

    print(f"\nDone: {fetched} fetched, {skipped} cached, {failed} failed", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Re-fetch all (ignore cache)")
    parser.add_argument("--date",    help="Fetch only this date (YYYY-MM-DD)")
    args = parser.parse_args()
    run(refresh=args.refresh, target_date=args.date)
