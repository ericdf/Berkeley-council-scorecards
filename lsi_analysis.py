"""
Legislative Sophistication Index (LSI) + Voter Alignment Ranking
for Berkeley City Council members.

Five LSI components (revised):
  1. Domain Fluency      (20%): Density of relevant technical vocabulary
  2. Fiscal Discipline   (25%): Frequency of cost/trade-off probing
  3. Inquiry Quality     (25%): Operational questions vs. grandstanding
  4. Decisiveness        (20%): Action-oriented vs. hedging language
  5. Procedural Efficiency(10%): Parliamentary mechanics

Voter Alignment Score combines:
  - LSI composite         (35%)
  - Core% from speech     (35%)
  - Inverted Waste%       (30%)

Only council members with ≥ MIN_WORDS words of attributed speech are scored.
(Newer Boardroom-format transcripts can't be attributed to individuals.)
"""

import glob
import math
import os
import re
from collections import defaultdict

TEXT_DIR = os.path.join(os.path.dirname(__file__), "text")
MIN_WORDS = 2000   # minimum attributable words to include in rankings

# ---------------------------------------------------------------------------
# Word / phrase lists
# ---------------------------------------------------------------------------

DOMAIN_TERMS = [
    # Zoning & planning
    "zoning", "density", "setback", "easement", "variance",
    "conditional use permit", r"\bcup\b", "general plan", "specific plan",
    r"\bceqa\b", r"\beir\b", "entitlement", r"\badu\b", "accessory dwelling",
    "floor area ratio", r"\bfar\b", "lot coverage", "height limit",
    "overlay zone", r"\bmlo\b", "rent stabilization", "just cause",
    "transit.oriented development", r"\btod\b", "inclusionary",
    "in.lieu fee", "development agreement", r"\bnexus\b",
    "conditions of approval", "mitigation measure", "categorical exemption",
    "substantial evidence", "planning commission", "landmark",
    "historic preservation", r"\blpc\b",
    # Fiscal & budget
    "general fund", "reserve fund", "appropriation", "encumbrance",
    "fiscal year", r"\bfy\b", r"\bcip\b", "capital improvement",
    "debt service", "fund balance", "operating budget", "unfunded liability",
    r"\bopeb\b", "pension obligation", "tax increment", r"\btif\b",
    "bond measure", "parcel tax", "transfer tax", "actuarial",
    "revenue projection", "expenditure", "carryover",
    # Legal & parliamentary
    "brown act", "urgency ordinance", "first reading", "second reading",
    "effective date", "administrative record", "findings of fact",
    "conflict of interest", r"\brecuse\b", "quasi.judicial",
    "preponderance", "substantial evidence",
]

FISCAL_DISCIPLINE_TERMS = [
    # Cost probing
    r"what.s the cost", r"how much (will|does|would|is)",
    r"cost.benefit", "fiscal impact", "budget impact",
    "where.s the funding", "how (is this|it) funded",
    "what.s the funding source", "ongoing cost",
    # Trade-off framing
    "what are we cutting", "what (do we|would we) (give up|cut|offset)",
    "trade.off", "opportunity cost", "what else could",
    # Reserve & sustainability
    "reserve fund", "general fund (balance|impact)",
    "long.term fiscal", "structurally balanced", "sustainable",
    "can we afford", "unfunded", "fiscal sustainability",
    # Efficiency
    "cost savings", "return on investment", r"\broi\b",
    "staff capacity", "staff time", "more efficient",
    "streamline", "reduce cost",
    # Budget discipline in questions
    r"budget\b.*\?", r"cost\b.*\?", r"fund(ing)?\b.*\?",
]

OPERATIONAL_QUESTION_MARKERS = [
    r"(how|when|who|where) (will|would|does|is|are|can|should)",
    r"what (is|are) the (timeline|process|procedure|mechanism|threshold|criteria|standard|requirement|cost|impact|capacity|status|plan|next step)",
    r"does staff (have|need|recommend|plan|intend|anticipate)",
    r"has (the city|staff|legal|counsel|the attorney)",
    r"(what|how) (many|much|long|often|soon)",
    r"can (staff|the city|counsel|we) (provide|clarify|confirm|report|explain)",
    r"what.s the (legal|fiscal|operational|practical|technical)",
    r"is there (a|any|sufficient|enough) (data|evidence|analysis|study|report|capacity|funding|staff)",
    r"how does this (affect|impact|interact|comply)",
    r"what (happens|is the effect) if",
]

GRANDSTANDING_QUESTION_MARKERS = [
    r"what (message|signal|statement) (does|are we|is this|do we)",
    r"what does this (say|mean|tell) (about|us|our)",
    r"(don.t|isn.t it true that|shouldn.t) (our|we|this|the city)",
    r"what kind of (city|community|place|values)",
    r"(aren.t|isn.t) (we|our residents|our community|our city)",
    r"(don.t|doesn.t) (our (residents|community|city)|this council|we)",
    r"as a (sanctuary|progressive|diverse|inclusive) city",
    r"(what about|and what of) (our values|justice|equity|marginalized|oppressed)",
    r"how (can|could) (we|this council) (in good conscience|justify|support|remain)",
    r"(won.t you|will you) join me in",
]

ACTION_MARKERS = [
    r"\bi (move|second|propose|recommend|suggest|request|direct|ask|call)\b",
    r"\bi.d (like to|want to) (move|second|call|direct|request)\b",
    r"direct (staff|the city manager|the city attorney)",
    r"(call the question|call for a vote|move to (table|continue|adopt|approve|reject|amend))",
    r"(i am |i.m )(voting|in favor|opposed|abstaining)",
    r"(my motion is|the motion (before us|is to))",
    r"(let.s|we should|we need to|we must) (vote|decide|act|move forward|finalize)",
    r"staff (should|needs to|must|shall|will) (report|bring back|prepare|complete|address)",
]

HEDGE_MARKERS = [
    r"\b(perhaps|maybe|possibly|potentially|conceivably)\b",
    r"\b(i.m not sure|i wonder|i.m wondering|i think (we should consider|maybe))\b",
    r"(we might (want to|consider|think about|explore|look at))",
    r"(it (might|could|may) be worth (exploring|considering|looking at|thinking about))",
    r"(i.m (a bit|somewhat|slightly) (concerned|worried|uncertain|hesitant))",
    r"(something to (think about|consider|explore|look into))",
    r"(i (don.t know|.m not sure) if|i (haven.t|don.t) (thought about|had a chance to))",
    r"(we.ll have to see|let.s see how|time will tell)",
]

PROCEDURAL_MARKERS = [
    r"\bi move\b", r"\bi second\b",
    r"\b(call the question|previous question)\b",
    r"\b(table|continue|postpone|refer to committee)\b",
    r"\b(point of order|point of (personal )?privilege)\b",
    r"\b(substitute motion|friendly amendment|amendment to the motion)\b",
    r"\b(roll call vote|voice vote|ayes? (have it|carry)|nays? (have it|prevail))\b",
    r"\b(consent calendar|action calendar|information calendar)\b",
    r"\b(quorum|adjourn|recess)\b",
    r"\b(first reading|second reading|adopt(ed)?|ordinance number)\b",
]

# Boilerplate to strip
BOILERPLATE_RE = re.compile(
    r"This information provided by.*?we did not create it\.",
    re.IGNORECASE | re.DOTALL,
)

# Council member aliases
COUNCIL_ALIASES = {
    "MAYOR ISHII": "Ishii", "MAYOR A. ISHII": "Ishii", "A. ISHII": "Ishii",
    "R. KESARWANI": "Kesarwani", "KESARWANI": "Kesarwani",
    "T. TAPLIN": "Taplin", "TAPLIN": "Taplin",
    "B. BARTLETT": "Bartlett", "BARTLETT": "Bartlett",
    "I. TREGUB": "Tregub", "TREGUB": "Tregub",
    "S. O'KEEFE": "O'Keefe", "O'KEEFE": "O'Keefe",
    "B. BLACKABY": "Blackaby", "BLACKABY": "Blackaby",
    "C. LUNAPARRA": "LunaParra", "LUNAPARRA": "LunaParra",
    "C. LUNA PARRA": "LunaParra",
    "M. HUMBERT": "Humbert", "HUMBERT": "Humbert",
}

NON_COUNCIL = {
    "CITY CLERK", "CLERK", "CITY MANAGER", "CITY MANAGER BUDDENHAGEN",
    "PUBLIC SPEAKER", "SPEAKER", "CITY ATTORNEY", "STAFF",
    "CITY STAFF", "CITY AUDITOR", "UNIDENTIFIED", "INDISCERNIBLE",
}

# Waste / Core keywords (from waste_analysis.py — reproduced here for standalone use)
WASTE_KEYWORDS = [
    "gaza", "israel", "palestine", "palestinian", "ceasefire",
    "arms embargo", "genocide", "apartheid", "boycott", "bds",
    r"\biran\b", "sanctions", "ukraine", "russia", "yemen",
    "foreign policy", "war crimes", "occupied territory",
    "land acknowledgment", "land acknowledgement",
    r"\bpab\b", "police accountability board", "flock camera",
    "surveillance technology", "surveillance contract", "defund",
    "sanctuary city", "resolution of solidarity", "resolution condemning",
    "resolution supporting.*(?:justice|equity|liberation|rights)",
    "tax increase", "raise taxes", "new tax", "parcel tax", "transfer tax",
]

CORE_KEYWORDS = [
    "infrastructure", r"\broad\b", r"\bstreet\b", "sidewalk", "pothole",
    "sewer", "storm drain", "capital improvement", "maintenance", "gilman",
    "measure ff", "measure t",
    "budget", "general fund", "reserve fund", "fiscal",
    "deficit", "revenue", "expenditure", "cost savings", "efficiency",
    "zoning", "density", "housing element", r"\badu\b",
    "affordable housing", "middle housing", r"\bpermit\b",
    "development agreement", "planning commission", "land use", "appeal",
    r"\bfire\b", "wildfire", "zone zero", "home hardening",
    "vegetation management", "evacuation", "emergency",
    "police department", r"\bchief\b", r"\bcrime\b", "response time",
    "patrol", "dispatch",
    "business district", "commercial", "economic development",
    "small business", r"\bdowntown\b",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")
    text = BOILERPLATE_RE.sub(" ", text)
    text = re.sub(r"\f", " ", text)
    return text


def _count_pattern_list(text: str, patterns: list) -> int:
    t = text.lower()
    return sum(1 for p in patterns if re.search(p, t))


def _sentences(text: str) -> list:
    """Rough sentence split."""
    return [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]


def _questions(text: str) -> list:
    """Extract sentences that end in '?'."""
    return [s.strip() for s in re.split(r"[.!]+", text)
            if "?" in s and s.strip()]


# ---------------------------------------------------------------------------
# Parse >> format into per-speaker word buckets
# ---------------------------------------------------------------------------

def parse_chevron(text: str) -> dict:
    """Return dict of canonical_name -> list of turn texts."""
    by_speaker = defaultdict(list)
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
        raw_spkr = m.group(1).strip().upper()
        body = _clean(m.group(2)).strip()
        if not body:
            continue

        # Resolve speaker
        canonical = None
        for alias, name in COUNCIL_ALIASES.items():
            if alias.upper() == raw_spkr:
                canonical = name
                break
        if canonical is None:
            continue  # staff / public / unknown — skip

        by_speaker[canonical].append(body)

    return by_speaker


# ---------------------------------------------------------------------------
# Compute LSI sub-scores for a corpus of turns
# ---------------------------------------------------------------------------

def compute_lsi(turns: list) -> dict:
    full_text = " ".join(turns)
    words = len(full_text.split())
    if words == 0:
        return {}

    per1k = 1000 / words

    # 1. Domain Fluency — domain term density per 1000 words
    domain_hits = _count_pattern_list(full_text, DOMAIN_TERMS)
    domain_raw = domain_hits * per1k

    # 2. Fiscal Discipline — fiscal probe density per 1000 words
    fiscal_hits = _count_pattern_list(full_text, FISCAL_DISCIPLINE_TERMS)
    fiscal_raw = fiscal_hits * per1k

    # 3. Inquiry Quality — operational vs. grandstanding question ratio
    all_q = _questions(full_text)
    op_q   = sum(1 for q in all_q if _count_pattern_list(q, OPERATIONAL_QUESTION_MARKERS) > 0)
    gs_q   = sum(1 for q in all_q if _count_pattern_list(q, GRANDSTANDING_QUESTION_MARKERS) > 0)
    inq_raw = op_q / (op_q + gs_q + 1)  # bounded 0-1

    # 4. Decisiveness — action vs. hedge ratio
    action_hits = _count_pattern_list(full_text, ACTION_MARKERS)
    hedge_hits  = _count_pattern_list(full_text, HEDGE_MARKERS)
    dec_raw = action_hits / (action_hits + hedge_hits + 1)  # bounded 0-1

    # 5. Procedural Efficiency — procedural term density per 1000 words
    proc_hits = _count_pattern_list(full_text, PROCEDURAL_MARKERS)
    proc_raw  = proc_hits * per1k

    # Waste & Core % (for voter alignment)
    waste_hits = _count_pattern_list(full_text, WASTE_KEYWORDS)
    core_hits  = _count_pattern_list(full_text, CORE_KEYWORDS)
    total_kw   = waste_hits + core_hits + 1
    waste_pct  = waste_hits / total_kw
    core_pct   = core_hits / total_kw

    return {
        "words": words,
        "domain_raw":  domain_raw,
        "fiscal_raw":  fiscal_raw,
        "inq_raw":     inq_raw,
        "dec_raw":     dec_raw,
        "proc_raw":    proc_raw,
        "waste_pct":   waste_pct,
        "core_pct":    core_pct,
        # diagnostics
        "domain_hits": domain_hits,
        "fiscal_hits": fiscal_hits,
        "op_q": op_q, "gs_q": gs_q,
        "action_hits": action_hits, "hedge_hits": hedge_hits,
        "proc_hits": proc_hits,
    }


# ---------------------------------------------------------------------------
# Normalize raw scores to 0-1 across all members, then apply weights
# ---------------------------------------------------------------------------

WEIGHTS = {
    "domain":  0.20,
    "fiscal":  0.25,
    "inquiry": 0.25,
    "decisive":0.20,
    "proc":    0.10,
}

VOTER_WEIGHTS = {
    "lsi":   0.35,
    "core":  0.35,
    "clean": 0.30,   # 1 - waste_pct (normalised)
}


def normalize(values: list) -> list:
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    paths = sorted(glob.glob(os.path.join(TEXT_DIR, "*.txt")))

    # Aggregate all turns per member across all files
    all_turns: dict[str, list] = defaultdict(list)

    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as f:
            raw = f.read()
        if ">>" not in raw:
            continue   # Boardroom/VTT format — skip for individual attribution
        turns = parse_chevron(raw)
        for name, t in turns.items():
            all_turns[name].extend(t)

    # Compute raw scores
    raw_scores = {}
    for name, turns in all_turns.items():
        scores = compute_lsi(turns)
        if scores.get("words", 0) >= MIN_WORDS:
            raw_scores[name] = scores

    if not raw_scores:
        print("No members with sufficient attributed speech.")
        return

    members = list(raw_scores.keys())

    # Normalize each LSI dimension
    dims = ["domain_raw", "fiscal_raw", "inq_raw", "dec_raw", "proc_raw"]
    dim_keys = ["domain", "fiscal", "inquiry", "decisive", "proc"]
    norm = {}
    for dim, key in zip(dims, dim_keys):
        vals = [raw_scores[m][dim] for m in members]
        nv = normalize(vals)
        for m, v in zip(members, nv):
            norm.setdefault(m, {})[key] = v

    # LSI composite
    lsi_composite = {}
    for m in members:
        lsi_composite[m] = sum(WEIGHTS[k] * norm[m][k] for k in WEIGHTS)

    # Normalize voter-facing components
    lsi_vals   = [lsi_composite[m] for m in members]
    core_vals  = [raw_scores[m]["core_pct"] for m in members]
    clean_vals = [1 - raw_scores[m]["waste_pct"] for m in members]

    lsi_n   = normalize(lsi_vals)
    core_n  = normalize(core_vals)
    clean_n = normalize(clean_vals)

    voter_score = {}
    for m, l, c, cl in zip(members, lsi_n, core_n, clean_n):
        voter_score[m] = (
            VOTER_WEIGHTS["lsi"]   * l  +
            VOTER_WEIGHTS["core"]  * c  +
            VOTER_WEIGHTS["clean"] * cl
        )

    # ---------------------------------------------------------------------------
    # Print LSI detail table
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 100)
    print(f"  {'MEMBER':<12} {'WORDS':>7}  {'Domain':>7} {'Fiscal':>7} {'Inquiry':>8} {'Decisive':>9} {'Proc':>6}  {'LSI':>6}")
    print(f"  {'':12} {'':>7}  {'(20%)':>7} {'(25%)':>7} {'(25%)':>8} {'(20%)':>9} {'(10%)':>6}  {'':>6}")
    print("=" * 100)
    for m in sorted(members, key=lambda x: -lsi_composite[x]):
        s = raw_scores[m]
        n = norm[m]
        print(
            f"  {m:<12} {s['words']:>7,}"
            f"  {n['domain']:>6.2f}  {n['fiscal']:>6.2f}  {n['inquiry']:>7.2f}"
            f"  {n['decisive']:>8.2f}  {n['proc']:>5.2f}"
            f"  {lsi_composite[m]:>6.3f}"
        )

    # ---------------------------------------------------------------------------
    # Print diagnostics
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 100)
    print(f"  {'MEMBER':<12} {'dom hits':>9} {'fisc hits':>10} {'op_q':>6} {'gs_q':>6} {'act':>5} {'hedge':>6} {'proc':>6}")
    print("=" * 100)
    for m in sorted(members, key=lambda x: -lsi_composite[x]):
        s = raw_scores[m]
        print(
            f"  {m:<12}"
            f"  {s['domain_hits']:>8}"
            f"  {s['fiscal_hits']:>9}"
            f"  {s['op_q']:>5}  {s['gs_q']:>5}"
            f"  {s['action_hits']:>4}  {s['hedge_hits']:>5}"
            f"  {s['proc_hits']:>5}"
        )

    # ---------------------------------------------------------------------------
    # Print voter alignment ranking
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  VOTER ALIGNMENT RANKING")
    print(f"  (LSI 35% + Core% 35% + Inverse Waste% 30%)")
    print("=" * 80)
    ranked = sorted(members, key=lambda x: -voter_score[x])
    for rank, m in enumerate(ranked, 1):
        s = raw_scores[m]
        bar_lsi   = "█" * int(lsi_composite[m] * 20)
        bar_voter = "█" * int(voter_score[m] * 20)
        print(
            f"  #{rank}  {m:<12}"
            f"  Voter: {voter_score[m]:.3f}  [{bar_voter:<20}]"
            f"  LSI: {lsi_composite[m]:.3f}  Core%: {s['core_pct']*100:.0f}%"
            f"  Waste%: {s['waste_pct']*100:.0f}%"
        )

    print(f"\n  Note: scores derived from {sum(raw_scores[m]['words'] for m in members):,} words")
    print(f"  across >> -format transcripts only. Boardroom/VTT-format meetings")
    print(f"  (newer 2026 sessions) are excluded from individual attribution.")


if __name__ == "__main__":
    main()
