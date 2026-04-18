"""
Comprehensive Berkeley City Council Member Scorecard

Produces four scored dimensions per member:
  1. LSI      — Legislative Sophistication Index (revised 5-component)
  2. Character — Ego / Collegiality / Intellectual Humility
  3. Alignment — Voter alignment (core focus, low waste)
  4. Summary   — "Civic Temperament" and "Clarity" composite scores

Handles all three transcript formats:
  - >> SPEAKER: text           (older captioner format — full attribution)
  - Boardroom: text            (Zoom boardroom — state-machine attribution)
  - HH:MM:SS VTT Board Room:   (Zoom VTT with timestamps — state-machine + time)

Usage:
    python council_scorecard.py [--csv] [--examples MEMBER]
"""

import argparse
import csv
import glob
import os
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Optional

TEXT_DIR = os.path.join(os.path.dirname(__file__), "text")
MIN_WORDS = 1500

# ---------------------------------------------------------------------------
# Council member canonical names + OCR override table
# ---------------------------------------------------------------------------

CANONICAL_MEMBERS = [
    "Ishii", "Kesarwani", "Taplin", "Bartlett",
    "Tregub", "OKeefe", "Blackaby", "LunaParra", "Humbert",
]

# Hard-coded OCR fixes that fuzzy matching misses
OCR_OVERRIDES = {
    "treykop": "Tregub", "trajka": "Tregub", "trago": "Tregub",
    "traum": "Tregub", "tregra": "Tregub", "treyka": "Tregub",
    "trekup": "Tregub", "tregup": "Tregub", "treykov": "Tregub",
    "tregob": "Tregub", "treyko": "Tregub", "tregim": "Tregub",
    "tragib": "Tregub", "tregub": "Tregub", "tregib": "Tregub",
    "tregam": "Tregub", "trego": "Tregub", "tregru": "Tregub",
    "triggum": "Tregub", "traeger": "Tregub", "treygub": "Tregub",
    "tracob": "Tregub", "trogroup": "Tregub", "treygubb": "Tregub",
    "trangum": "Tregub", "tregum": "Tregub", "trekob": "Tregub",
    "trajub": "Tregub", "triggup": "Tregub",
    "kisserwine": "Kesarwani", "kiserwani": "Kesarwani",
    "kisnerwani": "Kesarwani", "kesterwani": "Kesarwani",
    "casserone": "Kesarwani", "cassarwani": "Kesarwani",
    "kasarwani": "Kesarwani",
    "trajka": "Tregub",
    "okeefe": "OKeefe", "o'keefe": "OKeefe",
    "lunaparo": "LunaParra", "lunapar": "LunaParra",
    "lunopara": "LunaParra",
    "blackbee": "Blackaby", "bacabee": "Blackaby",
    "backelby": "Blackaby", "blackby": "Blackaby", "backaby": "Blackaby",
}

DISPLAY_NAME = {
    "Ishii": "Ishii", "Kesarwani": "Kesarwani", "Taplin": "Taplin",
    "Bartlett": "Bartlett", "Tregub": "Tregub", "OKeefe": "O'Keefe",
    "Blackaby": "Blackaby", "LunaParra": "LunaParra", "Humbert": "Humbert",
}

BOILERPLATE_RE = re.compile(
    r"This information provided by.*?we did not create it\.",
    re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# Name resolution
# ---------------------------------------------------------------------------

def resolve_name(raw: str) -> Optional[str]:
    """Map a raw extracted name to a canonical member name, or None."""
    key = raw.lower().replace("'", "").replace(" ", "").strip(".,?")
    if key in OCR_OVERRIDES:
        return OCR_OVERRIDES[key]
    # Try fuzzy match
    best, best_score = None, 0.0
    for c in CANONICAL_MEMBERS:
        c_key = c.lower().replace("'", "")
        s = SequenceMatcher(None, key, c_key).ratio()
        if s > best_score:
            best_score = s
            best = c
    return best if best_score >= 0.55 else None


# Direct alias table for >> format
CHEVRON_ALIASES: dict[str, str] = {
    "MAYOR ISHII": "Ishii", "MAYOR A. ISHII": "Ishii", "A. ISHII": "Ishii",
    "R. KESARWANI": "Kesarwani", "KESARWANI": "Kesarwani",
    "T. TAPLIN": "Taplin", "TAPLIN": "Taplin",
    "B. BARTLETT": "Bartlett", "BARTLETT": "Bartlett",
    "I. TREGUB": "Tregub", "TREGUB": "Tregub",
    "S. O'KEEFE": "OKeefe", "O'KEEFE": "OKeefe",
    "B. BLACKABY": "Blackaby", "BLACKABY": "Blackaby",
    "C. LUNAPARRA": "LunaParra", "LUNAPARRA": "LunaParra",
    "C. LUNA PARRA": "LunaParra",
    "M. HUMBERT": "Humbert", "HUMBERT": "Humbert",
}

NON_COUNCIL_UPPER = {
    "CITY CLERK", "CLERK", "CITY MANAGER", "CITY MANAGER BUDDENHAGEN",
    "PUBLIC SPEAKER", "SPEAKER", "CITY ATTORNEY", "STAFF",
    "CITY STAFF", "CITY AUDITOR", "UNIDENTIFIED",
}

# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

def clean(text: str) -> str:
    text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")
    text = BOILERPLATE_RE.sub(" ", text)
    text = re.sub(r"\f", " ", text)
    return text

# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def detect_format(text: str) -> str:
    if "WEBVTT" in text[:500]:
        return "vtt"
    if re.search(r"^Boardroom:", text, re.MULTILINE):
        return "boardroom"
    if ">>" in text:
        return "chevron"
    return "unknown"

# ---------------------------------------------------------------------------
# State-machine speaker attribution (Boardroom / VTT formats)
# ---------------------------------------------------------------------------

# Tier-1: directional call-ons — high-confidence "floor goes to NAME"
_GOTO_RE = re.compile(
    r"(?:going to|go to|move(?:ing)?\s+(?:on\s+)?to|turn(?:ing)?\s+to"
    r"|starting with|I'll go to|we'll go to|back to|return(?:ing)?\s+to)\s+"
    r"(?:Council\s*[Mm]ember|Vice\s*[Mm]ayor|CM\s*)?"
    r"([A-Z][A-Za-z''\-]{2,15})\b",
    re.IGNORECASE,
)

# Tier-2: standalone title+name call-on at sentence boundary
_STANDALONE_RE = re.compile(
    r"(?:^|[.!?]\s+)"
    r"(?:Council\s*[Mm]ember|Vice\s*[Mm]ayor)\s+"
    r"([A-Z][A-Za-z''\-]{2,15})\s*[?.]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Tier-3: invitation phrase immediately after title+name
_INVITE_RE = re.compile(
    r"(?:Council\s*[Mm]ember|Vice\s*[Mm]ayor)\s+"
    r"([A-Z][A-Za-z''\-]{2,15})\s*,\s*"
    r"(?:please|go ahead|can you|could you|would you|did you|have you)\b",
    re.IGNORECASE,
)

# Self-identification: "This is Councilmember X" / "I'm Councilmember X"
_SELF_ID_RE = re.compile(
    r"(?:^|[.]\s+)"
    r"(?:(?:this is|i.m)\s+(?:Council\s*[Mm]ember\s+)?|Council\s*[Mm]ember\s+)"
    r"([A-Z][A-Za-z''\-]{2,15})\b"
    r"(?:\s*[.,]|\s+(?:here|speaking|from district))",
    re.IGNORECASE,
)

# Context that means the name is a reference, NOT a call-on — suppress all tiers
_NOT_CALLON_CTX = re.compile(
    r"(?:thank(?:ing)?|agree(?:ing)?|support(?:ing)?|mention(?:ing)?"
    r"|said|noted|suggest(?:ed)?|raise[ds]?|co.sponsor|co.author"
    r"|colleague|point(?:ed)?|item|motion|amendment|question|concern"
    r"|'s\s+|of\s+Council|with\s+Council)",
    re.IGNORECASE,
)

# Roll-call context — suppress attribution during attendance
_ROLLCALL_RE = re.compile(
    r"(?:call(?:ing)?\s+the\s+roll|take\s+the\s+roll|calling\s+roll"
    r"|present|here|absent)\b",
    re.IGNORECASE,
)

# "Thank you, Councilmember X[.,]" as a complete closing sentence
_THANKS_CLOSE_RE = re.compile(
    r"^Thank you,?\s*(?:very much,?)?\s*(?:Council\s*[Mm]ember|Vice\s*[Mm]ayor)?\s*"
    r"([A-Z][A-Za-z''\-]{3,15})[.,]?\s*$",
    re.IGNORECASE,
)

# "Thank you, Councilmember X" followed by new content (inline thanks, not close)
_THANKS_INLINE_RE = re.compile(
    r"Thank you,?\s*(?:very much,?)?\s*(?:Council\s*[Mm]ember|Vice\s*[Mm]ayor)?\s*"
    r"([A-Z][A-Za-z''\-]{3,15})\b[.,]?\s*(?:and|I|we|for)\b",
    re.IGNORECASE,
)

# Start of turn thanking the mayor — speaker was just called on
THANKS_MAYOR_RE = re.compile(
    r"^(?:Thank you,?\s*(?:very much,?)?\s*(?:Madam\s*)?Mayor|"
    r"Thank you,?\s*(?:very much,?)?\s*Acting\s*Mayor)",
    re.IGNORECASE,
)


def _find_callon(body: str) -> Optional[str]:
    """
    Return the canonical name of whoever is being called on in this turn,
    or None if no confident call-on is found.
    Uses tiered matching: directional > invitation > standalone.
    Suppresses any match whose surrounding context looks like a reference mention.
    """
    # Suppress entirely if this looks like a roll-call block
    if _ROLLCALL_RE.search(body):
        return None

    # Check each tier, last confident match wins within tier
    for pattern in (_GOTO_RE, _INVITE_RE, _STANDALONE_RE):
        matches = list(pattern.finditer(body))
        for m in reversed(matches):
            name_token = m.group(1)
            # Grab 60 chars of context before the match to check for reference signals
            ctx_start = max(0, m.start() - 60)
            ctx = body[ctx_start:m.end()]
            if _NOT_CALLON_CTX.search(ctx):
                continue
            candidate = resolve_name(name_token)
            if candidate:
                return candidate

    return None


def attribute_blocks(lines: list[str]) -> list[tuple[str, str]]:
    """
    Given a list of (raw_speaker, text) pairs where raw_speaker may be
    'Boardroom' / 'Board Room', apply state-machine attribution.
    Returns list of (canonical_member_or_None, text) tuples.
    """
    results = []
    current = "Ishii"   # Mayor runs meetings by default

    for raw_spkr, body in lines:
        spkr_norm = raw_spkr.lower().replace(" ", "").replace("'", "")

        # Named (non-boardroom) speaker — direct attribution
        if spkr_norm not in ("boardroom", "boardroom"):
            resolved = resolve_name(raw_spkr)
            if resolved:
                results.append((resolved, body))
                current = resolved
            else:
                results.append((None, body))  # public / staff
            continue

        # --- Boardroom turn: apply state machine ---

        # Check for self-identification at turn start
        self_id = _SELF_ID_RE.match(body)
        if self_id:
            candidate = resolve_name(self_id.group(1))
            if candidate:
                current = candidate

        # Closing thanks: "Thank you, Councilmember X." as standalone sentence
        thanks_close_m = _THANKS_CLOSE_RE.search(body)

        # Directional call-on anywhere in body
        next_speaker = _find_callon(body)

        # Emit this turn attributed to current speaker
        results.append((current, body))

        # Update state for next turn
        if next_speaker:
            current = next_speaker
        elif thanks_close_m:
            # Mayor just closed out a member's turn — floor returns to mayor
            thanked = resolve_name(thanks_close_m.group(1))
            if thanked:
                current = "Ishii"

    return results


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_chevron(text: str) -> list[tuple[str, str]]:
    """>> SPEAKER: text → [(canonical_name, text), ...]"""
    result = []
    segs = re.split(r"(>>)", text)
    combined = []
    i = 0
    while i < len(segs):
        if segs[i] == ">>":
            combined.append(">>" + (segs[i+1] if i+1 < len(segs) else ""))
            i += 2
        else:
            i += 1
    for seg in combined:
        m = re.match(r">>\s*([^:]{1,60}):\s*(.*)", seg, re.DOTALL)
        if not m:
            continue
        raw = m.group(1).strip().upper()
        body = clean(m.group(2)).strip()
        if not body:
            continue
        canonical = CHEVRON_ALIASES.get(raw)
        if canonical is None and raw not in NON_COUNCIL_UPPER:
            canonical = None  # public / staff
        result.append((canonical, body))
    return result


def parse_boardroom(text: str) -> list[tuple[str, str]]:
    """Boardroom: text → attributed [(canonical_name, text), ...]"""
    raw_lines = []
    for line in text.splitlines():
        m = re.match(r"^(Board\s*[Rr]oom|[A-Za-z][A-Za-z '\-]{0,40}):\s+(.*)", line)
        if m:
            raw_lines.append((m.group(1).strip(), clean(m.group(2)).strip()))
    return attribute_blocks(raw_lines)


def parse_vtt(text: str) -> list[tuple[str, str, Optional[float]]]:
    """VTT → attributed [(canonical_name, text, duration_sec), ...]"""
    blocks = re.split(r"\n\s*\n", text)
    ts_re = re.compile(
        r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})"
    )

    def ts2s(ts):
        ts = ts.replace(",", ".")
        h, mi, s = ts.split(":")
        return int(h) * 3600 + int(mi) * 60 + float(s)

    raw_lines = []
    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue
        ts_match = None
        body_parts = []
        for ln in lines:
            if ts_re.match(ln):
                ts_match = ts_re.match(ln)
            elif not re.match(r"^\d+$", ln):
                body_parts.append(ln)
        body = clean(" ".join(body_parts)).strip()
        if not body:
            continue
        dur = None
        if ts_match:
            dur = ts2s(ts_match.group(2)) - ts2s(ts_match.group(1))
        m2 = re.match(r"^(Board\s*[Rr]oom|[A-Za-z][A-Za-z '\-]{0,40}):\s+(.*)", body, re.DOTALL)
        if m2:
            raw_lines.append((m2.group(1).strip(), clean(m2.group(2)).strip(), dur))
        else:
            raw_lines.append(("Board Room", body, dur))

    # Run attribution on (speaker, text) pairs, then reattach duration
    pairs = [(r[0], r[1]) for r in raw_lines]
    attributed = attribute_blocks(pairs)
    return [(attributed[i][0], attributed[i][1], raw_lines[i][2]) for i in range(len(attributed))]


# ---------------------------------------------------------------------------
# Keyword lists
# ---------------------------------------------------------------------------

WASTE_KW = [
    r"\bgaza\b", r"\bisrael\b", r"\bpalestine\b", r"\bpalestinian\b",
    r"\bceasefire\b", r"arms embargo", r"\bgenocide\b", r"\bapartheid\b",
    r"\bboycott\b", r"\bbds\b", r"\biran\b", r"\bukraine\b", r"\brussian?\b",
    r"\byemen\b", r"foreign policy", r"war crimes", r"occupied territory",
    r"land acknowledgment", r"land acknowledgement",
    r"police accountability board", r"\bpab\b", r"flock camera",
    r"surveillance (technology|contract)", r"\bdefund\b",
    r"sanctuary city",
    r"resolution (of solidarity|condemning|supporting.*(?:justice|equity|liberation))",
    r"tax increase", r"raise taxes", r"new tax", r"parcel tax", r"transfer tax",
]

CORE_KW = [
    r"\binfrastructure\b", r"\broad\b", r"\bstreet\b", r"\bsidewalk\b",
    r"\bpothole\b", r"\bsewer\b", r"storm drain", r"capital improvement",
    r"\bmaintenance\b", r"\bgilman\b", r"measure ff",
    r"\bbudget\b", r"general fund", r"reserve fund", r"\bfiscal\b",
    r"\bdeficit\b", r"\brevenue\b", r"\bexpenditure\b", r"cost savings",
    r"\befficiency\b",
    r"\bzoning\b", r"\bdensity\b", r"housing element", r"\badu\b",
    r"affordable housing", r"middle housing", r"\bpermit\b",
    r"development agreement", r"planning commission", r"land use", r"\bappeal\b",
    r"\bfire\b", r"\bwildfire\b", r"zone zero", r"home hardening",
    r"vegetation management", r"\bevacuation\b", r"\bemergency\b",
    r"police department", r"\bchief\b", r"\bcrime\b", r"response time",
    r"\bpatrol\b", r"\bdispatch\b",
    r"business district", r"\bcommercial\b", r"economic development",
    r"small business", r"\bdowntown\b",
]

# LSI sub-components

DOMAIN_KW = [
    r"\bzoning\b", r"\bdensity\b", r"\bsetback\b", r"\beasement\b",
    r"\bvariance\b", r"conditional use permit", r"\bceqa\b", r"\beir\b",
    r"\bentitlement\b", r"\badu\b", r"floor area ratio", r"\bfar\b",
    r"lot coverage", r"\boverlay\b", r"\bmlo\b", r"rent stabilization",
    r"just cause", r"transit.oriented", r"\btod\b", r"inclusionary",
    r"in.lieu fee", r"development agreement", r"\bnexus\b",
    r"conditions of approval", r"mitigation measure", r"categorical exemption",
    r"substantial evidence", r"\blpc\b", r"historic preservation",
    r"general fund", r"reserve fund", r"\bappropriation\b", r"\bencumbrance\b",
    r"\bfiscal year\b", r"\bcip\b", r"capital improvement program",
    r"debt service", r"fund balance", r"unfunded liability", r"\bopeb\b",
    r"pension obligation", r"bond measure", r"tax increment",
    r"brown act", r"urgency ordinance", r"first reading", r"second reading",
    r"administrative record", r"conflict of interest", r"\brecuse\b",
    r"quasi.judicial", r"preponderance",
]

# Fiscal concern rhetoric — member CLAIMS budget restraint in speech
# Distinct from FISCAL_KW (which measures probing fiscal impact of items).
# High score here + large spending actions = fiscal hypocrisy signal.
FISCAL_CONCERN_KW = [
    # Deficit / shortfall framing
    r"structural(ly)? deficit",
    r"structural(ly)? (im)?balanced",
    r"\$\s*\d[\d,.]+\s*(million|billion|M|B)\s+(budget\s+)?deficit",
    r"budget (shortfall|gap|crisis|hole|challenge|pressure|strain)",
    r"budgetary (challenge|pressure|strain|gap|shortfall)",
    r"(the\s+)?city.s?\s+(budget\s+)?(deficit|shortfall|gap)\b",
    r"we (have|are facing|face|are in) a (budget\s+)?deficit",
    r"fiscal (cliff|crisis|emergency|pressure|strain|sustainability)",
    r"\$\s*\d[\d,.]+\s*(million|billion|M)\s+(structural\s+)?deficit",
    # Restraint claims
    r"(can.t|cannot|can not|don.t|do not) afford (to\b|this\b|it\b|these\b|more\b)",
    r"we.re (spending|borrowing) (too much|more than)",
    r"tighten(ing)? (our )?belt",
    r"liv(e|ing) within our means",
    r"(un)?sustainable (spending|budget|costs?)",
    r"(scarce|limited)\s+(resources|funds|dollars)",
]

# Revenue-seeking rhetoric — proposing new taxes or bonds as the mechanism for
# addressing fiscal problems, without first asking what can be cut or reprioritized.
# Under the P1 framework (Layer 3), this scores NEGATIVELY: reaching for new revenue
# before exhausting reprioritization is the wrong methodology regardless of whether
# the underlying problem is real. Distinguished from FISCAL_CONCERN_KW (which measures
# genuine fiscal problem awareness) and FISCAL_KW (which measures probing cost questions).
REVENUE_SEEKING_KW = [
    # Direct new-revenue proposals — explicit advocacy for new tax or bond instrument
    r"rais(e|ing) (the\s+)?taxes? (to pay|to fund|to cover|for)",
    r"homeowners? (are being|will be|are) (taxed|burdened|asked|hit)",
    r"(need|propose|consider|explore).{0,30}(new|a)\s+(tax|bond|levy|assessment|parcel tax|measure)",
    # Requires explicit ballot/voters framing — avoids matching "Measure U1 and Measure M" (two mentions)
    r"(put|place|bring|consider|explore)\s+.{0,15}(bond|tax|levy|measure|parcel tax).{0,20}(ballot|voters)",

    # Exploring / considering revenue as the solution framing
    # Reveals that the default mental model is "find more money" — the thinking, not just the vote
    r"(explore|look at|consider|examine|discuss)\s+(revenue|funding|tax|bond|financing)\s+(option|source|stream|approach|alternative|measure|solution)",
    r"(additional|new|more|other)\s+revenue\s+(source|stream|option|approach|tool|measure)",
    r"(revenue|funding)\s+(option|alternative|solution|approach|strategy)\b",

    # Asking voters to approve new revenue — ballot framing
    # Negative lookahead excludes "go to public comment" (procedural, not revenue advocacy)
    r"(ask|go to|bring to|take to)\s+(the\s+)?(voters?|taxpayers?|public|community)\b(?!\s+comment)",
    r"(voters?|taxpayers?|the\s+community|the\s+public)\s+(could|would|might|should|can)\s+(approve|support|pass|fund|weigh in)",
    r"(go|come|return|back)\s+(to\s+)?the\s+ballot",
    r"(put|place|bring)\s+.{0,20}\s+(on|before)\s+(the\s+)?ballot",

    # Bond/tax advocacy in soft form — "a bond could help," "we could look at a parcel tax"
    r"(bond\s+measure|general\s+obligation|revenue\s+bond|parcel\s+tax|sales\s+tax)\s+(could|would|might|should|can|will)\s+(help|provide|fund|address|allow|generate)",
    r"(consider|explore|look at|discuss|examine)\s+(a\s+)?(bond|parcel\s+tax|sales\s+tax|tax\s+measure|levy)",
    r"(an?\s+)?(infrastructure|facilities?|capital|general)\s+(bond|measure)\b",

    # "We need more money" as solution framing — without corresponding cut proposal
    r"(we\s+)?(need|require)\s+(more|additional|new|increased)\s+(money|funding|resources|dollars|revenue)\b",
    r"(can.t|cannot)\s+(do|address|fund|tackle|fix|solve)\s+.{0,25}\s+without\s+(more|additional|new)\s+(revenue|funding|money|resources)",
    r"(we\s+)?(need|must|have)\s+to\s+find\s+(the\s+)?(money|funding|resources|revenue)\b",

    # Investment-before-cuts framing
    r"(we\s+)?(need|must|should|have to)\s+(invest|fund|prioritize).{0,30}(before|instead of).{0,20}cut",
    # "raise/increase revenue" as council tax-seeking — exclude "without putting a burden" (earned income framing)
    r"(we\s+)?(can|should|must|need to)\s+(raise|increase|find|generate)\s+(more\s+)?(revenue|money|funding)(?!\s+without\s+putting)",
]

# ---------------------------------------------------------------------------
# P1 topic keywords — turn-level signal for engagement with documented structural problems
# ---------------------------------------------------------------------------
# Intentionally tight: these require the specific vocabulary of each documented failure,
# not general budget or policy language. A member who says "structural deficit," "CalPERS,"
# "pavement condition index," or "LAIF" is engaging with a documented structural problem.
# A member who says "budget" or "roads" generically is not.
#
# Used in score_member() to compute p1_speech_pct: share of total words spoken
# in turns that contain at least one P1 keyword. Display only — not yet scored.

P1_TOPIC_KW = [
    # ── Structural fiscal deficit ──────────────────────────────────────────
    # "not sustainable" is exact language from three consecutive City Manager budget messages
    r"structural.{0,10}deficit",
    r"structural.{0,10}(?:im)?balance",
    r"structural\s+gap",
    r"one.time\s+(?:measure|revenue|source|draw(?:down)?|fund|solution|fix)",
    r"not\s+sustainable",                    # verbatim from budget messages
    r"recurring.{0,25}(?:expenditure|cost|revenue|imbalance|gap)",
    r"\bGFOA\b",                             # Government Finance Officers Association standard
    r"fiscal\s+sustainability",
    r"structural(?:ly)?\s+balanced",

    # ── Infrastructure backlog ─────────────────────────────────────────────
    r"pavement\s+condition\s+index",
    r"\bPCI\s+\d",                           # "PCI 57" — requires a number to avoid false positives
    r"deferred\s+maintenance",
    r"infrastructure\s+backlog",
    r"five.year\s+paving\s+plan",
    r"rocky\s+road\s+(?:audit|report|finding)",
    r"street.{0,15}funding\s+gap",

    # ── Pension and OPEB ───────────────────────────────────────────────────
    r"\bcalpers\b",
    r"\bopeb\b",
    r"pension\s+(?:liability|obligation|unfunded|funding\s+ratio|funded\s+ratio|shortfall)",
    r"unfunded\s+(?:pension|liability|accrued)",
    r"section\s+115",                        # pension pre-funding trust (also structural deficit)
    r"workers.?\s*comp(?:ensation)?\s+(?:reserve|fund|non.fund|underfund|deferred)",

    # ── Investment policy non-compliance ──────────────────────────────────
    r"\blaif\b",                             # Local Agency Investment Fund benchmark
    r"investment\s+policy\b",               # the specific policy document
    r"(?:underperform|benchmark|rate\s+of\s+return).{0,30}(?:investment|portfolio)",

    # ── Reserve policy ────────────────────────────────────────────────────
    r"reserve\s+(?:target|policy|floor|minimum|requirement|goal)",
    r"stability\s+reserve",
    r"catastrophic\s+reserve",
    r"rainy.day\s+(?:fund|reserve)",
]

# ---------------------------------------------------------------------------
# Audit alignment signal keywords (financial_condition_2026)
# ---------------------------------------------------------------------------
# AUDIT_SIGNAL_KEYWORDS: vocabulary presence — one list per audit finding category.
# AUDIT_EVENT_PATTERNS: stance-detection patterns (supports/opposes/acknowledges).
# score_member() returns raw hit counts; pipeline.py computes rates and sub-scores.

AUDIT_SIGNAL_KEYWORDS = {
    "structural_balance": [
        r"structural\s+deficit",
        r"structural\s+(?:im)?balance",
        r"recurring\s+revenues?",
        r"recurring\s+expenditures?",
        r"baseline\s+budget",
    ],
    "one_time_balancing": [
        r"\bone.time\b",
        r"(?:inter)?fund\s+transfer\b",
        r"\bsection\s+115\b",
        r"workers.?\s*comp(?:ensation)?\s+(?:reserve|fund)",
        r"plug\s+the\s+gap",
    ],
    "cross_subsidy": [
        r"general\s+fund\s+support\b",
        r"cross.subsid",
        r"parking\s+(?:meter|fund|revenue)\b",
        r"marina\s+fund\b",
        r"off.street\s+parking\b",
    ],
    "personnel_cost": [
        r"\bheadcount\b",
        r"\bfte\b",
        r"overtime\s+(?:cost|rate|spend|budget)",
        r"benefits?\s+cost",
        r"healthcare\s+cost",
        r"pension\s+cost",
    ],
    "program_growth": [
        r"health\s+and\s+welfare\b",
        r"community\s+development\b",
        r"housing\s+spending\b",
        r"program\s+expansion\b",
        r"service\s+expansion\b",
    ],
    "revenue_quality": [
        r"one.time\s+revenue",
        r"temporary\s+funding",
        r"\barpa\b",
        r"investment\s+earnings?\b",
        r"volatile\s+revenue",
    ],
    "revenue_operations": [
        r"lease\s+revenue\b",
        r"city\s+lease\b",
        r"\bholdover\b",
        r"rent\s+collection\b",
        r"city.owned\s+propert",
    ],
    "capital_planning": [
        r"capital\s+improvement\s+program\b",
        r"\bcip\b",
        r"deferred\s+maintenance",
        r"capital\s+financing\s+plan\b",
        r"infrastructure\s+backlog\b",
    ],
    "pension": [
        r"\bcalpers\b",
        r"pension\s+(?:liability|obligation|unfunded|funded\s+ratio)\b",
        r"section\s+115\s+trust\b",
        r"pension\s+contribution\b",
        r"\bprefund\b",
    ],
    "policy": [
        r"fiscal\s+polic(?:y|ies)\b",
        r"budget\s+polic(?:y|ies)\b",
        r"reserve\s+polic(?:y|ies)\b",
        r"require\s+recurring\s+revenues?\b",
        r"annual\s+investment\s+report\b",
    ],
}

# Stance patterns for specific events — conservative (high precision over recall).
# A single match = event count +1.
AUDIT_EVENT_PATTERNS = {
    "acknowledges_structural_deficit": [
        r"(?:we|the city|berkeley)\b.{0,40}\bstructural\s+deficit\b",
        r"structural\s+deficit.{0,40}(?:serious|real|significant|problem|face)\b",
        r"not\s+sustainable.{0,30}(?:budget|spending|trajectory)\b",
        r"(?:budget|spending|trajectory).{0,30}not\s+sustainable\b",
    ],
    "supports_structural_balance_policy": [
        r"(?:adopt|require|implement|establish)\s+.{0,30}structural\s+balance\s+polic",
        r"(?:adopt|require|implement)\s+.{0,40}recurring\s+revenues?.{0,30}recurring\s+expenditures?",
        r"\bgfoa\b.{0,40}(?:best\s+practice|recommend|polic|standard)\b",
        r"require\s+.{0,20}recurring\s+revenues?\s+(?:match|cover|equal|exceed)",
    ],
    "supports_one_time_transfer": [
        r"(?:support|vote|approve|move|favor)\s+.{0,30}one.time\s+(?:transfer|measure|solution)\b",
        r"use\s+.{0,30}(?:workers.?\s*comp|section\s+115)\s+.{0,20}(?:balance|fund)\s+(?:the\s+)?budget\b",
    ],
    "opposes_one_time_transfer": [
        r"(?:concern|oppos|problem|wrong|bad|caution)\w*\s+.{0,30}one.time\s+(?:transfer|measure|fix)\b",
        r"(?:shouldn.t|should\s+not|must\s+not)\s+.{0,20}one.time\s+(?:transfer|measure)\b",
        r"one.time\s+(?:transfer|measure).{0,30}(?:concern|problem|wrong|not\s+address)\b",
    ],
    "supports_cross_fund_transfer": [
        r"(?:support|approve|move|favor)\s+.{0,30}(?:transfer\s+from|cross.?fund|general\s+fund\s+subsid)\b",
        r"(?:parking|marina|enterprise)\s+fund.{0,30}(?:transfer\s+to|support|subsid).{0,20}general\s+fund\b",
    ],
    "opposes_cross_fund_transfer": [
        r"(?:concern|oppos|problem|wrong)\w*\s+.{0,30}(?:cross.?fund|general\s+fund\s+subsid|transfer\s+from\s+(?:parking|marina))\b",
        r"(?:parking|marina)\s+fund.{0,30}(?:shouldn.t|should\s+not)\s+.{0,20}(?:subsid|support|transfer\s+to)\s+general\s+fund\b",
    ],
    "supports_115_withdrawal": [
        r"(?:support|approve|vote|move|favor)\s+.{0,30}section\s+115\s+withdrawal\b",
        r"withdraw\s+(?:from\s+)?(?:the\s+)?section\s+115\b",
    ],
    "opposes_115_withdrawal": [
        r"(?:concern|oppos|problem|wrong)\w*\s+.{0,30}section\s+115\s+withdrawal\b",
        r"section\s+115.{0,40}(?:shouldn.t|should\s+not)\s+(?:be\s+)?(?:used|raided|drawn)\b",
    ],
    "supports_115_contribution": [
        r"(?:contribute|fund|restore|replenish|build\s+up)\s+.{0,20}section\s+115\b",
        r"section\s+115.{0,40}(?:contribute|fund|restore|replenish|meet.{0,10}goal)\b",
    ],
    "supports_cip_extension": [
        r"extend\s+.{0,20}(?:cip|capital\s+improvement\s+plan)\b",
        r"(?:longer|10.year|fifteen.year|20.year)\s+.{0,20}(?:cip|capital\s+plan)\b",
        r"(?:cip|capital\s+plan).{0,30}(?:longer|extend|horizon|10.year)\b",
    ],
    "supports_capital_financing_plan": [
        r"(?:long.term|comprehensive)\s+capital\s+(?:financing|funding)\s+plan\b",
        r"capital\s+financing\s+plan.{0,30}(?:adopt|develop|create|need|require)\b",
        r"(?:need|require|develop)\s+.{0,25}capital\s+financing\s+plan\b",
    ],
    "supports_enterprise_fee_update": [
        r"(?:raise|update|increase|review)\s+.{0,20}(?:parking|marina)\s+fees?\b",
        r"(?:parking|marina)\s+fees?.{0,25}(?:raise|update|cover|cost)\b",
        r"fee\s+(?:study|review).{0,25}(?:parking|marina|enterprise)\b",
    ],
    "supports_enterprise_reserve_policy": [
        r"reserve\s+polic.{0,25}(?:parking|marina|enterprise)\b",
        r"(?:parking|marina|enterprise)\s+fund.{0,25}reserve\s+polic\b",
    ],
    "supports_investment_reporting": [
        r"(?:require|annual|regular|publish)\s+.{0,20}investment\s+report\b",
        r"investment\s+report.{0,25}(?:annual|require|publish|present|council)\b",
    ],
    "supports_lease_management_fix": [
        r"(?:fix|improve|reform|address)\s+.{0,20}lease\s+(?:management|revenue|collection)\b",
        r"lease\s+(?:management|collection).{0,25}(?:fix|improve|reform|system)\b",
        r"city.owned\s+propert.{0,25}(?:lease|revenue|collect|track)\b",
    ],
    "questions_personnel_costs": [
        r"(?:why|what).{0,30}(?:fte|headcount|staffing?)\s+.{0,10}(?:grow|increas|expand)\b",
        r"(?:how|what).{0,30}productivity.{0,20}(?:staff|fte)\b",
        r"(?:staff|fte|headcount).{0,25}(?:too\s+many|overstaff|grow)\b",
    ],
    "questions_program_growth": [
        r"(?:why|what).{0,30}(?:housing|health|welfare|community\s+development).{0,20}(?:budget|spending)\s+.{0,10}(?:grow|increas|doubl)\b",
        r"program\s+growth.{0,25}(?:sustain|afford|concern|why)\b",
    ],
    "raises_revenue_quality_concern": [
        r"\barpa\b.{0,40}(?:expir|end|gone|declin|one.time|what\s+happens)\b",
        r"one.time\s+revenue.{0,30}(?:expir|end|concern|rely|depend)\b",
        r"investment\s+(?:earnings?|income|revenue).{0,25}(?:volatile|reliable|concern)\b",
    ],
}

# ---------------------------------------------------------------------------
# Homeless Services Orthodoxy (HSO) rhetoric signals
# ---------------------------------------------------------------------------

# Language that signals ideological alignment with the prevailing homeless services orthodoxy.
# "Unhoused neighbors" is a reliable orthodoxy marker: council members who adopt this
# framing are expressing orthodoxy regardless of whether the surrounding sentence
# is sympathetic or fiscal — the city's own manager has acknowledged the population
# is largely imported, so calling them "neighbors" is a telling framing choice.
HSO_SYMPATHY_KW = [
    # "punches/punching above its/our weight" in homeless context
    # Use [\s\S] instead of . so the pattern crosses line breaks in transcripts.
    r"\bpunch(?:es|ing)?\b[\s\S]{0,30}\babove[\s\S]{0,15}\bweight\b",
    r"\bharm.reduction\b",                                    # Harm reduction policy frame
    r"\btrauma.?informed\b",                                  # Trauma-informed approach
    r"\blow.barrier\s+(?:shelter|housing|option|bed)\b",      # Low-barrier ideology
    r"\bwrap.?around\s+serv",                                 # Wrap-around services
    # "unhoused neighbors" — orthodoxy framing marker (see note above)
    r"\bunhoused\s+neighbors?\b",
    r"\bhousing.?first.{0,30}(?:work|effective|success)\b",  # Defending Housing First
]

# Language that signals skepticism or accountability orientation toward the orthodoxy:
# questioning costs, demanding enforcement, challenging the mandate.
HSO_SKEPTIC_KW = [
    r"\bgrants?\s+pass\b",                                    # Grants Pass SCOTUS ruling
    r"\bcost\s+per\s+(?:client|person|individual)\b",         # Cost-per-client accountability
    r"\bare\s+we\s+(?:still\s+)?required\s+to\s+implement",  # Questioning Housing First mandate
    r"\bhousing\s+first\s+(?:is\s+state\s+law|required|model|mandate)\b",  # Mandate skepticism
    r"\breinstate\b.{0,15}\b(?:rv|recreational\s+vehicle)\b", # RV ordinance reinstatement
    r"\bencampment\b.{0,30}\b(?:enforcement|clearanc|sweep|removal)\b",  # Enforcement framing
    r"\bhomeless(?:ness)?\b.{0,30}\baccountability\b",        # Demanding accountability
    r"\bfiscal\s+cliff\b.{0,30}\b(?:homeless|shelter|program)\b",  # Fiscal cliff + homeless programs
    r"\bmetrics?\b.{0,30}\boutcomes?\b|\boutcomes?\b.{0,30}\bmetrics?\b",  # Accountability framing
]

FISCAL_KW = [
    r"what.s the cost", r"how much (will|does|would|is)\b",
    r"cost.benefit", r"fiscal impact", r"budget impact",
    r"where.s the funding", r"how (is this|it) funded",
    r"what.s the funding source", r"ongoing cost",
    r"what are we cutting", r"what (do we|would we) (give up|cut|offset)",
    r"trade.off", r"opportunity cost", r"what else could",
    r"reserve fund", r"general fund (balance|impact)",
    r"long.term fiscal", r"structurally balanced", r"can we afford",
    r"\bunfunded\b", r"fiscal sustainability",
    r"cost savings", r"return on investment", r"\broi\b",
    r"staff capacity", r"staff time", r"more efficient",
    r"\bstreamline\b", r"reduce cost",
    r"budget\b.*\?", r"cost\b.*\?", r"fund(ing)?\b.*\?",
]

# Operational questions — probe HOW things work
OP_QUESTION_KW = [
    r"(how|when|who|where) (will|would|does|is|are|can|should)\b",
    r"what (is|are) the (timeline|process|procedure|mechanism|threshold|criteria|standard|requirement|cost|impact|capacity|status|plan|next step)",
    r"does staff (have|need|recommend|plan|intend|anticipate)",
    r"has (the city|staff|legal|counsel|the attorney)",
    r"(what|how) (many|much|long|often|soon)\b",
    r"can (staff|the city|counsel|we) (provide|clarify|confirm|report|explain|analyze)",
    r"what.s the (legal|fiscal|operational|practical|technical)",
    r"is there (a|any|sufficient|enough) (data|evidence|analysis|study|report|capacity|funding|staff)",
    r"how does this (affect|impact|interact|comply|fit|align)",
    r"what (happens|is the effect) if",
    r"(what is|what are) (the|our) (options|alternatives|tradeoffs|implications)",
]

# Value-laden / political questions — signal grandstanding
GS_QUESTION_KW = [
    r"what (message|signal|statement) (does|are we|is this|do we|should we)",
    r"what does this (say|mean|tell) (about|us|our|to)",
    r"(don.t|shouldn.t|isn.t it) (our|we|this city|the council|berkeley)\b",
    r"what kind of (city|community|place|society)",
    r"(aren.t|isn.t) (we|our residents|our community|our city)\b",
    r"as a (sanctuary|progressive|diverse|inclusive|caring) city",
    r"(what about|and what of) (our values|justice|equity|marginalized|oppressed|liberation)",
    r"how (can|could) (we|this council) (in good conscience|justify|sit by)",
    r"(won.t you|will you) join me in\b",
    r"(our|berkeley.s|the city.s) (values|commitment to|legacy of) (equity|justice|diversity|inclusion|liberation)",
    r"(justice|equity|liberation|oppression|marginalized|coloni[sz])",
]

ACTION_KW = [
    r"\bi (move|second|propose|recommend|suggest|request|direct|call)\b",
    r"\bi.d (like to|want to) (move|second|call|direct|request)\b",
    r"direct (staff|the city manager|the city attorney)",
    r"(call the question|call for a vote|move to (table|continue|adopt|approve|reject|amend))",
    r"(i am |i.m )(voting|in favor|opposed|abstaining)",
    r"(the motion (before us|is to)|my motion is)\b",
    r"staff (should|needs to|must|shall|will) (report|bring back|prepare|complete|address)",
]

HEDGE_KW = [
    r"\b(perhaps|maybe|possibly|potentially|conceivably)\b",
    r"\bi.m not sure\b", r"\bi wonder\b", r"\bi.m wondering\b",
    r"we might (want to|consider|think about|explore|look at)",
    r"it (might|could|may) be worth (exploring|considering|looking at)",
    r"i.m (a bit|somewhat|slightly) (concerned|uncertain|hesitant)",
    r"something to (think about|consider|explore)",
    r"we.ll have to see", r"time will tell",
]

PROC_KW = [
    r"\bi move\b", r"\bi second\b",
    r"\b(call the question|previous question)\b",
    r"\b(table|continue|postpone|refer to committee)\b",
    r"\b(point of order|point of (personal )?privilege)\b",
    r"\b(substitute motion|friendly amendment|amendment to the motion)\b",
    r"\b(consent calendar|action calendar|information calendar)\b",
    r"\b(quorum|adjourn|recess)\b",
    r"\b(first reading|second reading|adopt(ed)?|ordinance number)\b",
]

# --- Character index ---

CREDENTIAL_KW = [
    # First-person only — avoids false positives from reading tributes or quoting others.
    # Patterns require "I" or first-person possessive to be nearby.
    r"\bi.m a nuclear engineer\b",
    r"\bi am a (nuclear|civil|mechanical|electrical|software|chemical|structural) engineer\b",
    r"\bas a (nuclear|civil|mechanical|electrical|software|structural) engineer,? i\b",
    r"\bi.m (also )?a (doctor|physician|attorney|lawyer|scientist|professor|academic)\b",
    r"\bmy (own |personal )?(professional |engineering |legal |scientific |technical )?background\b",
    r"\bmy (training|expertise) as (a|an)\b",
    r"\bin my (professional |expert )?experience,? i\b",
    r"\bi have (worked|spent|practiced) (in|as|for) .{0,30} (years|decades)\b",
    r"\bmy \d+ years (of|in|as)\b",
]

SELF_POSITION_KW = [
    r"as i.ve (long |always )?(said|argued|maintained|advocated|believed|known|noted)",
    r"as i (noted|said|mentioned|argued|advocated) (last|at|in|before|previously)",
    r"(my (item|proposal|amendment|suggestion|recommendation)|i (wrote|authored|drafted|introduced) this)",
    r"(i have (long|always|consistently|repeatedly) (said|argued|believed|maintained))",
    r"(my (years|decade|long) of (experience|service|work|advocacy))",
]

COLLEGIALITY_KW = [
    r"(as|what) (councilmember|my colleague|vice mayor) \w+ (said|noted|mentioned|raised|pointed out|suggested)",
    r"building on (what|councilmember)",
    r"i (agree|concur|support) with (councilmember|my colleague|the vice mayor|the mayor)",
    r"(great|good|excellent|important|helpful|thoughtful|useful) (point|question|comment|suggestion|observation)",
    r"thank you (councilmember|vice mayor|mayor|madam mayor|mr\.|ms\.) \w+ for (that|your|the)",
    r"councilmember \w+.s (point|comment|question|concern|suggestion) is (well.taken|valid|important|right)",
]

HUMILITY_KW = [
    r"(you.ve|that.s) convinced me",
    r"i (changed|reconsidered|updated|revised) my (position|view|mind|vote)",
    r"(fair point|good point|you.re right|that.s a good (point|correction|catch))",
    r"i (defer|deferred) to (staff|the experts|the city attorney|counsel|the professionals)",
    r"i (was|am) (wrong|mistaken|incorrect)",
    r"i (hadn.t|haven.t|didn.t) (thought about|considered|realized|appreciated)",
    r"(i learned from|i appreciate the correction|thank you for correcting me)",
]

WARMTH_KW = [
    r"congratulat(e|ions|ing)",
    r"(i am|i.m|i was|we are|we.re) (proud|grateful|honored|moved|touched|inspired)",
    r"(my heart|deeply moved|truly grateful|really appreciate)",
    r"(you.ve done|your (work|service|contribution|dedication|commitment) (is|has been|means))",
    r"(thank you (so much|very much|deeply|genuinely|sincerely) for)",
]


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def hit(text: str, patterns: list) -> int:
    t = text.lower()
    return sum(1 for p in patterns if re.search(p, t))


def questions(text: str) -> list:
    return [s.strip() for s in re.split(r"[.!]+", text) if "?" in s and s.strip()]


def normalize(vals: list) -> list:
    lo, hi = min(vals), max(vals)
    return [(v - lo) / (hi - lo) if hi > lo else 0.5 for v in vals]


# ---------------------------------------------------------------------------
# Per-member data accumulation
# ---------------------------------------------------------------------------

class MemberData:
    def __init__(self, name: str):
        self.name = name
        self.turns: list[str] = []
        self.words = 0

    def add(self, text: str):
        self.turns.append(text)
        self.words += len(text.split())

    def full_text(self) -> str:
        return " ".join(self.turns)


# ---------------------------------------------------------------------------
# Compute all scores from accumulated turns
# ---------------------------------------------------------------------------

def score_member(md: MemberData) -> dict:
    if md.words == 0:
        return {}
    text = md.full_text()
    w = md.words
    per1k = 1000 / w

    # --- LSI ---
    domain_raw  = hit(text, DOMAIN_KW) * per1k
    fiscal_raw  = hit(text, FISCAL_KW) * per1k
    proc_raw    = hit(text, PROC_KW) * per1k
    action_hits = hit(text, ACTION_KW)
    hedge_hits  = hit(text, HEDGE_KW)
    dec_raw     = action_hits / (action_hits + hedge_hits + 1)

    all_q = questions(text)
    op_q  = sum(1 for q in all_q if hit(q, OP_QUESTION_KW) > 0)
    gs_q  = sum(1 for q in all_q if hit(q, GS_QUESTION_KW) > 0)
    inq_raw = op_q / (op_q + gs_q + 1)

    # --- Waste / Core ---
    waste_hits = hit(text, WASTE_KW)
    core_hits  = hit(text, CORE_KW)
    tot_kw     = waste_hits + core_hits + 1
    waste_pct  = waste_hits / tot_kw
    core_pct   = core_hits / tot_kw

    # --- P1 share of speech (turn-level) ---
    # A turn is P1 if it contains ≥1 P1_TOPIC_KW hit; all its words count as P1 speech.
    # Counts engagement with the five documented structural failures, not just topic adjacency.
    p1_words = sum(len(t.split()) for t in md.turns if hit(t, P1_TOPIC_KW) > 0)
    p1_speech_pct = p1_words / md.words if md.words > 0 else 0.0

    # --- Character ---
    cred_raw     = hit(text, CREDENTIAL_KW) * per1k
    position_raw = hit(text, SELF_POSITION_KW) * per1k
    sra_raw      = cred_raw + position_raw * 0.5   # combined self-referential appeals score

    coll_raw  = hit(text, COLLEGIALITY_KW) * per1k
    hum_raw   = hit(text, HUMILITY_KW) * per1k
    warm_raw  = hit(text, WARMTH_KW) * per1k

    # First-person ratio: "I " vs "we " (self-centeredness proxy)
    i_count  = len(re.findall(r"\bi\b", text.lower()))
    we_count = len(re.findall(r"\bwe\b", text.lower()))
    i_ratio  = i_count / (i_count + we_count + 1)

    return {
        "words": md.words,
        # raw LSI components
        "domain_raw": domain_raw,
        "fiscal_raw": fiscal_raw,
        "inq_raw":    inq_raw,
        "dec_raw":    dec_raw,
        "proc_raw":   proc_raw,
        # diagnostic counts
        "op_q": op_q, "gs_q": gs_q,
        "action_hits": action_hits, "hedge_hits": hedge_hits,
        # waste/core
        "waste_pct": waste_pct,
        "core_pct":  core_pct,
        # character
        "sra_raw":   sra_raw,
        "coll_raw":  coll_raw,
        "hum_raw":   hum_raw,
        "warm_raw":  warm_raw,
        "i_ratio":   i_ratio,
        # diagnostics
        "cred_hits":     hit(text, CREDENTIAL_KW),
        "position_hits": hit(text, SELF_POSITION_KW),
        "coll_hits": hit(text, COLLEGIALITY_KW),
        "hum_hits":  hit(text, HUMILITY_KW),
        # fiscal concern rhetoric (distinct from fiscal discipline)
        "fiscal_concern_hits": hit(text, FISCAL_CONCERN_KW),
        # revenue-seeking rhetoric — penalized under P1 Layer 3: new revenue before reprioritization
        "revenue_seeking_hits": hit(text, REVENUE_SEEKING_KW),
        # P1 share of speech — words in turns engaging with documented structural failures
        "p1_speech_pct":   round(p1_speech_pct, 4),
        "p1_speech_words": p1_words,
        # Audit alignment: raw hit counts for financial_condition_2026 signals.
        # Rates and sub-scores computed in pipeline.py compute_audit_alignment().
        **{f"audit_sig_{k}_hits": hit(text, patterns)
           for k, patterns in AUDIT_SIGNAL_KEYWORDS.items()},
        **{f"audit_ev_{k}_hits": hit(text, patterns)
           for k, patterns in AUDIT_EVENT_PATTERNS.items()},
    }


# ---------------------------------------------------------------------------
# Load all transcripts and aggregate
# ---------------------------------------------------------------------------

def load_all() -> dict[str, MemberData]:
    members: dict[str, MemberData] = {}
    for name in CANONICAL_MEMBERS:
        members[name] = MemberData(name)

    paths = sorted(glob.glob(os.path.join(TEXT_DIR, "*.txt")))
    for path in paths:
        raw = open(path, encoding="utf-8", errors="replace").read()
        raw = clean(raw)
        fmt = detect_format(raw)

        if fmt == "chevron":
            turns = parse_chevron(raw)
            for canonical, body in turns:
                if canonical in members:
                    members[canonical].add(body)

        elif fmt == "boardroom":
            turns = parse_boardroom(raw)
            for canonical, body in turns:
                if canonical in members:
                    members[canonical].add(body)

        elif fmt == "vtt":
            turns = parse_vtt(raw)
            for canonical, body, _dur in turns:
                if canonical in members:
                    members[canonical].add(body)

    return members


# ---------------------------------------------------------------------------
# Ishii facilitator analysis (separate scoring)
# ---------------------------------------------------------------------------

def score_ishii_facilitator(md: MemberData) -> dict:
    text = md.full_text()
    w = md.words
    if w == 0:
        return {}
    per1k = 1000 / w

    # Facilitation signals
    callons = len(re.findall(
        r"(?:go(?:ing)? to|I'll go to|turn(?:ing)? to|moving on to|starting with|we'll go to)\s+"
        r"(?:councilmember|vice\s*mayor)", text, re.IGNORECASE))

    thanks_cm = len(re.findall(
        r"thank you,?\s*(?:very much,?)?\s*(?:councilmember|vice\s*mayor)", text, re.IGNORECASE))

    # Meeting management: does she move items forward?
    agenda_moves = len(re.findall(
        r"(?:moving on|next item|go to item|move to|we.ll now|turning to|proceed to|we.re going to)\b",
        text, re.IGNORECASE))

    # Balance: mentions each member roughly equally?
    member_mentions = {}
    for m in CANONICAL_MEMBERS:
        if m == "Ishii":
            continue
        pattern = DISPLAY_NAME.get(m, m)
        member_mentions[m] = len(re.findall(pattern, text, re.IGNORECASE))

    vals = list(member_mentions.values())
    if vals and max(vals) > 0:
        balance = 1 - (max(vals) - min(vals)) / max(vals)
    else:
        balance = 0.5

    # Waste facilitation: how much of Ishii's speech is in waste context?
    waste_h = hit(text, WASTE_KW)
    core_h  = hit(text, CORE_KW)
    tot = waste_h + core_h + 1
    waste_frac = waste_h / tot

    return {
        "words":       w,
        "callons_per1k":    callons * per1k,
        "thanks_per1k":     thanks_cm * per1k,
        "agenda_per1k":     agenda_moves * per1k,
        "balance":          balance,
        "waste_frac":       waste_frac,
        "member_mentions":  member_mentions,
    }


# ---------------------------------------------------------------------------
# Normalize and combine
# ---------------------------------------------------------------------------

LSI_WEIGHTS   = {"domain": .20, "fiscal": .25, "inquiry": .25, "decisive": .20, "proc": .10}
VOTER_WEIGHTS = {"lsi": .30, "core": .35, "clean": .35}
CHARACTER_WEIGHTS         = {"coll": .35, "hum": .25, "warm": .20, "low_sra": .20}
VOTER_DISCONNECT_WEIGHTS  = {"waste": .40, "sra": .30, "low_fiscal": .30}

def build_scoreboard(members: dict[str, MemberData]) -> dict:
    raw = {n: score_member(m) for n, m in members.items() if m.words >= MIN_WORDS}
    names = list(raw.keys())
    if not names:
        return {}

    def norm_dim(key):
        vals = [raw[n][key] for n in names]
        nv = normalize(vals)
        return {n: v for n, v in zip(names, nv)}

    # Normalize each LSI dimension
    nd = norm_dim("domain_raw")
    nf = norm_dim("fiscal_raw")
    ni = norm_dim("inq_raw")
    ndc= norm_dim("dec_raw")
    np_ = norm_dim("proc_raw")

    # Normalize character dimensions
    n_sra  = norm_dim("sra_raw")    # higher = more self-referential appeals
    n_coll = norm_dim("coll_raw")
    n_hum  = norm_dim("hum_raw")
    n_warm = norm_dim("warm_raw")
    n_i    = norm_dim("i_ratio")    # higher = higher first-person ratio

    n_waste = norm_dim("waste_pct")
    n_core  = norm_dim("core_pct")
    n_fiscal= norm_dim("fiscal_raw")  # reuse

    scores = {}
    for n in names:
        lsi = (LSI_WEIGHTS["domain"]   * nd[n] +
               LSI_WEIGHTS["fiscal"]   * nf[n] +
               LSI_WEIGHTS["inquiry"]  * ni[n] +
               LSI_WEIGHTS["decisive"] * ndc[n]+
               LSI_WEIGHTS["proc"]     * np_[n])

        voter = (VOTER_WEIGHTS["lsi"]   * lsi +
                 VOTER_WEIGHTS["core"]  * n_core[n] +
                 VOTER_WEIGHTS["clean"] * (1 - n_waste[n]))

        character        = (CHARACTER_WEIGHTS["coll"]    * n_coll[n] +
                            CHARACTER_WEIGHTS["hum"]     * n_hum[n]  +
                            CHARACTER_WEIGHTS["warm"]    * n_warm[n] +
                            CHARACTER_WEIGHTS["low_sra"] * (1 - (n_sra[n] * 0.7 + n_i[n] * 0.3)))

        voter_disconnect = (VOTER_DISCONNECT_WEIGHTS["waste"]      * n_waste[n] +
                            VOTER_DISCONNECT_WEIGHTS["sra"]        * (n_sra[n] * 0.7 + n_i[n] * 0.3) +
                            VOTER_DISCONNECT_WEIGHTS["low_fiscal"] * (1 - n_fiscal[n]))

        scores[n] = {
            **raw[n],
            "lsi":              lsi,
            "voter":            voter,
            "character":        character,
            "voter_disconnect": voter_disconnect,
            # normalized sub-scores for display
            "n_domain": nd[n],  "n_fiscal": nf[n],
            "n_inq":    ni[n],  "n_dec":    ndc[n], "n_proc": np_[n],
            "n_sra":    n_sra[n], "n_coll": n_coll[n],
            "n_hum":    n_hum[n], "n_warm": n_warm[n],
        }

    return scores


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def bar(v, w=16):
    filled = int(v * w)
    return "█" * filled + "░" * (w - filled)


def print_scorecard(scores: dict, ishii_fac: dict):
    print("\n" + "=" * 95)
    print("  LEGISLATIVE SOPHISTICATION INDEX")
    print(f"  {'Member':<13} {'Words':>7}  {'Domain':>6} {'Fiscal':>6} {'Inquiry':>7} {'Decisive':>8} {'Proc':>5}  {'LSI':>6}")
    print("=" * 95)
    for n in sorted(scores, key=lambda x: -scores[x]["lsi"]):
        s = scores[n]
        dn = DISPLAY_NAME.get(n, n)
        print(f"  {dn:<13} {s['words']:>7,}"
              f"  {s['n_domain']:>5.2f}  {s['n_fiscal']:>5.2f}"
              f"  {s['n_inq']:>6.2f}  {s['n_dec']:>7.2f}  {s['n_proc']:>4.2f}"
              f"  {s['lsi']:>6.3f}")

    print("\n" + "=" * 95)
    print("  CHARACTER & CONDUCT")
    print(f"  {'Member':<13} {'SRA↓':>7} {'I-ratio↓':>9} {'Collegiality↑':>14} {'Humility↑':>10} {'Warmth↑':>8}  | Credential  Position  Colleg  Humble")
    print("=" * 95)
    for n in sorted(scores, key=lambda x: scores[x]["character"], reverse=True):
        s = scores[n]
        dn = DISPLAY_NAME.get(n, n)
        print(f"  {dn:<13}"
              f"  {s['n_sra']:>6.2f}  {s['i_ratio']:>8.2f}"
              f"  {s['n_coll']:>13.2f}  {s['n_hum']:>9.2f}  {s['n_warm']:>7.2f}"
              f"  | {s['cred_hits']:>5}       {s['position_hits']:>5}   {s['coll_hits']:>5}   {s['hum_hits']:>5}")

    print("\n" + "=" * 85)
    print("  VOTER ALIGNMENT RANKING  (LSI 30% + Core% 35% + Inverse Waste% 35%)")
    print("=" * 85)
    for rank, n in enumerate(sorted(scores, key=lambda x: -scores[x]["voter"]), 1):
        s = scores[n]
        dn = DISPLAY_NAME.get(n, n)
        print(f"  #{rank}  {dn:<13}  {bar(s['voter'])}  {s['voter']:.3f}"
              f"  core={s['core_pct']*100:.0f}%  waste={s['waste_pct']*100:.0f}%  lsi={s['lsi']:.2f}")

    print("\n" + "=" * 85)
    print("  CHARACTER & CONDUCT")
    print("  High collegiality, humility, warmth; low self-referential appeals and first-person ratio")
    print("=" * 85)
    for rank, n in enumerate(sorted(scores, key=lambda x: -scores[x]["character"]), 1):
        s = scores[n]
        dn = DISPLAY_NAME.get(n, n)
        print(f"  #{rank}  {dn:<13}  {bar(s['character'])}  {s['character']:.3f}")

    print("\n" + "=" * 85)
    print("  VOTER DISCONNECT  (high waste + high self-referential appeals + avoids fiscal accountability)")
    print("=" * 85)
    for rank, n in enumerate(sorted(scores, key=lambda x: -scores[x]["voter_disconnect"]), 1):
        s = scores[n]
        dn = DISPLAY_NAME.get(n, n)
        print(f"  #{rank}  {dn:<13}  {bar(s['voter_disconnect'])}  {s['voter_disconnect']:.3f}"
              f"  waste={s['waste_pct']*100:.0f}%  sra={s['n_sra']:.2f}  cred_hits={s['cred_hits']}")

    # Ishii facilitator summary
    if ishii_fac:
        print("\n" + "=" * 85)
        print("  MAYOR ISHII — FACILITATOR SCORE")
        print(f"  Words: {ishii_fac['words']:,}  |  Call-ons/1k: {ishii_fac['callons_per1k']:.2f}"
              f"  |  Agenda moves/1k: {ishii_fac['agenda_per1k']:.2f}"
              f"  |  Balance: {ishii_fac['balance']:.2f}"
              f"  |  Waste facilitated: {ishii_fac['waste_frac']*100:.0f}%")
        print("  Member mentions (floor time distribution):")
        for m, cnt in sorted(ishii_fac["member_mentions"].items(), key=lambda x: -x[1]):
            print(f"    {DISPLAY_NAME.get(m, m):<13} {cnt:>4}  {bar(cnt/max(ishii_fac['member_mentions'].values()), 12)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", action="store_true", help="Output CSV to stdout")
    args = parser.parse_args()

    print("Loading and attributing transcripts...", file=sys.stderr)
    members = load_all()

    for n, md in members.items():
        print(f"  {DISPLAY_NAME.get(n,n):<13} {md.words:>8,} words", file=sys.stderr)

    print("\nScoring...", file=sys.stderr)
    scores = build_scoreboard(members)

    # Ishii is a facilitator — score separately
    ishii_fac = score_ishii_facilitator(members.get("Ishii", MemberData("Ishii")))
    if "Ishii" in scores:
        del scores["Ishii"]   # remove from main ranking

    print_scorecard(scores, ishii_fac)

    if args.csv:
        writer = csv.DictWriter(sys.stdout, fieldnames=[
            "member", "words", "lsi", "voter", "character", "voter_disconnect",
            "waste_pct", "core_pct", "cred_hits", "position_hits",
            "coll_hits", "hum_hits", "op_q", "gs_q",
        ])
        writer.writeheader()
        for n, s in scores.items():
            writer.writerow({k: s.get(k, "") for k in writer.fieldnames
                             if k != "member"} | {"member": DISPLAY_NAME.get(n, n)})


if __name__ == "__main__":
    main()
