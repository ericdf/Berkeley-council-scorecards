"""
packet_scraper.py
=================
Downloads individual item staff report PDFs from Berkeley eAgenda pages,
extracts text, parses standard sections, and derives procurement signals.

Outputs per-item JSON to agendas/reports/YYYY-MM-DD_item_NN.json

Usage:
    python packet_scraper.py                  # fetch all uncached items
    python packet_scraper.py --date 2025-04-15
    python packet_scraper.py --date 2025-04-15 --refresh
    python packet_scraper.py --flagged-only   # only items flagged in agenda JSON
    python packet_scraper.py --list           # list available items without downloading
"""

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from agenda_scraper import AGENDA_URL_MAP, BASE_URL

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

AGENDAS_DIR = os.path.join(os.path.dirname(__file__), "agendas")
REPORTS_DIR = os.path.join(AGENDAS_DIR, "reports")
PDF_CACHE_DIR = os.path.join(AGENDAS_DIR, "pdf_cache")

os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(PDF_CACHE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Standard staff report section headers (case-insensitive)
# ---------------------------------------------------------------------------

def _sec(pattern: str) -> re.Pattern:
    """Compile a section header pattern: anchored to line start + optional colon/spaces + newline."""
    # (?:^|\n) ensures the header is at the start of a line, preventing
    # substring matches like "RECOMMENDATION" inside "FISCAL IMPACTS OF RECOMMENDATION"
    return re.compile(r"(?:^|\n)" + pattern + r":?\s*[\r\n]", re.IGNORECASE)

SECTION_PATTERNS = [
    ("recommendation",    _sec(r"RECOMMENDATION[S]?")),
    ("fiscal_impacts",    _sec(r"FISCAL\s+IMPACT[S]?(?:\s+OF\s+RECOMMENDATION[S]?)?")),
    ("current_situation", _sec(r"CURRENT\s+SITUATION(?:\s+AND\s+ITS\s+EFFECTS?)?")),
    ("background",        _sec(r"BACKGROUND")),
    ("rationale",         _sec(r"RATIONALE\s+FOR\s+RECOMMENDATION[S]?")),
    ("alternatives",      _sec(r"ALTERNATIVE\s+ACTIONS?\s+CONSIDERED")),
    ("environmental",     _sec(r"ENVIRONMENTAL\s+SUSTAINABILITY")),
    ("attachments",       _sec(r"ATTACHMENTS?")),
]

# ---------------------------------------------------------------------------
# Signal extraction patterns
# ---------------------------------------------------------------------------

# Waived competitive bidding
WAIVED_BID_RE = re.compile(
    r"waiv(?:e[sd]?|ing)\s+(?:the\s+)?(?:competitive\s+)?(?:bid|solicit|RFP|RFQ|procurement)"
    r"|bid\s+waiver"
    r"|waiver\s+of\s+(?:competitive\s+)?(?:bid|solicit)",
    re.IGNORECASE,
)

# Backdated / retroactive contract
# Note: "effective [month] [date]" is intentionally excluded — fee schedules routinely
# carry a future/past effective date that is not a procurement integrity issue.
# Only "retroactive", "backdated", and "nunc pro tunc" signal a true after-the-fact contract.
BACKDATED_RE = re.compile(
    r"retroactive(?:ly)?"
    r"|backdated?"
    r"|nunc\s+pro\s+tunc",
    re.IGNORECASE,
)

# "ALTERNATIVE ACTIONS CONSIDERED: None" pattern
ALT_NONE_RE = re.compile(
    r"ALTERNATIVE\s+ACTIONS?\s+CONSIDERED[\s\S]{0,300}?\bNone\b",
    re.IGNORECASE,
)

# Dollar amounts
DOLLAR_RE = re.compile(r"\$[\d,]+(?:\.\d+)?(?:\s*(?:million|M|thousand|K))?\b")

# Grant vs general fund
GRANT_RE = re.compile(
    r"\bgrant\b|\bfederal\s+fund|\bstate\s+fund|\bHUD\b|\bFEMA\b|\bCDBG\b|\bESG\b"
    r"|\bMeasure\s+[A-Z]\b|\bprop(?:osition)?\s+[A-Z0-9]+\b",
    re.IGNORECASE,
)
GENERAL_FUND_RE = re.compile(
    r"\bgeneral\s+fund\b|\bGF\b|\bgeneral\s+purpose\s+fund\b",
    re.IGNORECASE,
)

# Vendor / contractor name (rough heuristic: first proper noun after "with" or "to" near "contract")
VENDOR_RE = re.compile(
    r"(?:contract|agreement|MOU)\s+with\s+([A-Z][A-Za-z0-9\s,\.]{2,60}?)(?:\s+to\s+|\s+for\s+|,|\n)",
)

# Cost per unit
COST_PER_RE = re.compile(
    r"\$[\d,]+(?:\.\d+)?\s+per\s+(?:client|person|individual|bed|unit|night|month|year)",
    re.IGNORECASE,
)

# URL pattern for item PDFs on the Berkeley site
ITEM_PDF_RE = re.compile(
    r'href=["\']([^"\']*(?:Item[%20_-]*\d+|item[%20_-]*\d+)[^"\']*\.pdf)["\']',
    re.IGNORECASE,
)
# Broader fallback
DOC_PDF_RE = re.compile(
    r'href=["\']([^"\']*\/sites\/default\/files\/documents\/[^"\']+\.pdf)["\']',
    re.IGNORECASE,
)

# Item number from URL or filename — captures digit + optional letter suffix (e.g. "11a")
ITEM_NUM_RE = re.compile(r'[Ii]tem[%20_\s-]*(\d+[a-zA-Z]?)', re.IGNORECASE)


# ---------------------------------------------------------------------------
# HTML fetching
# ---------------------------------------------------------------------------

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Berkeley Council Researcher / contact@example.com"})


def fetch_html(url: str) -> str:
    resp = SESSION.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def fetch_pdf_bytes(url: str) -> bytes:
    resp = SESSION.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content


# ---------------------------------------------------------------------------
# PDF link extraction from eAgenda page
# ---------------------------------------------------------------------------

def extract_item_pdf_links(html: str) -> list[dict]:
    """
    Returns list of {item_num, title, url} for each item PDF found on an eAgenda page.
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Must be a PDF in the documents path
        if "/sites/default/files/documents/" not in href and not href.lower().endswith(".pdf"):
            continue
        if href in seen_urls:
            continue

        # Decode percent-encoding for display
        decoded = urllib.parse.unquote(href)

        # Extract item number (string, preserving suffix like "11a")
        m = ITEM_NUM_RE.search(decoded)
        if not m:
            continue  # skip non-item PDFs (e.g. full packet)

        item_key = m.group(1).lower()  # e.g. "04", "11a", "11b"
        item_num = int(re.match(r"\d+", item_key).group())  # integer part for sorting

        # Build absolute URL
        url = href if href.startswith("http") else BASE_URL + href

        # Title: use link text, or derive from filename
        text = a.get_text(strip=True)
        if not text:
            # Derive from URL filename
            filename = decoded.split("/")[-1].replace(".pdf", "")
            # Strip date + item prefix
            filename = re.sub(r"^\d{4}-\d{2}-\d{2}\s+Item\s+\d+[a-z]?\s*", "", filename, flags=re.IGNORECASE)
            text = filename

        seen_urls.add(href)
        links.append({
            "item_num": item_num,
            "item_key": item_key,
            "title": text,
            "url": url,
        })

    links.sort(key=lambda x: (x["item_num"], x["item_key"]))
    return links


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_pdf_text(pdf_bytes: bytes) -> str:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber not installed — run: pip install pdfplumber")
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = []
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
    return "\n".join(pages)


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------

def parse_sections(text: str) -> dict[str, str]:
    """
    Splits staff report text into standard sections.
    Returns dict of {section_name: section_text}.
    """
    # Find all section header positions
    hits = []
    for name, pat in SECTION_PATTERNS:
        for m in pat.finditer(text):
            hits.append((m.start(), m.end(), name))

    if not hits:
        return {"full_text": text}

    hits.sort(key=lambda x: x[0])

    sections = {}
    for i, (start, end, name) in enumerate(hits):
        next_start = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        sections[name] = text[end:next_start].strip()

    # Capture preamble (before first section)
    sections["preamble"] = text[: hits[0][0]].strip()

    return sections


# ---------------------------------------------------------------------------
# Signal derivation
# ---------------------------------------------------------------------------

def derive_signals(sections: dict[str, str], full_text: str) -> dict:
    """
    Returns a dict of derived procurement / fiscal signals.
    """
    rec   = sections.get("recommendation", "")
    fiscal = sections.get("fiscal_impacts", "")
    alts  = sections.get("alternatives", "")
    bg    = sections.get("background", "")
    rat   = sections.get("rationale", "")

    # Combine text blocks for broad searches
    all_text = full_text

    signals = {}

    # Competitive bid waived?
    signals["waived_competitive_bid"] = bool(WAIVED_BID_RE.search(all_text))

    # Backdated / retroactive contract?
    # Only check the recommendation section (not background, which can use "retroactive"
    # in a policy/legal context unrelated to contract timing).
    # Also require proximity to contract-related language.
    _CONTRACT_CONTEXT_RE = re.compile(
        r"(?:contract|agreement|MOU|resolution|purchase\s+order).{0,200}?"
        r"(?:retroactive(?:ly)?|backdated?|nunc\s+pro\s+tunc)"
        r"|(?:retroactive(?:ly)?|backdated?|nunc\s+pro\s+tunc).{0,200}?"
        r"(?:contract|agreement|MOU|resolution|purchase\s+order)",
        re.IGNORECASE | re.DOTALL,
    )
    signals["backdated"] = bool(_CONTRACT_CONTEXT_RE.search(rec))

    # Alternatives: None?
    signals["alternatives_none"] = bool(ALT_NONE_RE.search(alts) or
                                        re.search(r"^\s*None\.?\s*$", alts, re.IGNORECASE | re.MULTILINE))

    # Funding source
    signals["grant_funded"]   = bool(GRANT_RE.search(fiscal))
    signals["general_fund"]   = bool(GENERAL_FUND_RE.search(fiscal))

    # Dollar amounts mentioned in fiscal section
    dollar_hits = DOLLAR_RE.findall(fiscal + "\n" + rec)
    signals["dollar_amounts"] = dollar_hits[:10]  # cap for storage

    # Vendor
    vendor_m = VENDOR_RE.search(rec + "\n" + bg)
    signals["vendor"] = vendor_m.group(1).strip() if vendor_m else None

    # Cost per unit
    cpu_hits = COST_PER_RE.findall(all_text)
    signals["cost_per_unit"] = cpu_hits[:5] if cpu_hits else []

    # Raw funding source text (first 300 chars of fiscal section)
    signals["funding_source_text"] = fiscal[:300].strip() or None

    return signals


# ---------------------------------------------------------------------------
# Per-meeting agenda JSON: load flagged items
# ---------------------------------------------------------------------------

def load_flagged_titles(date: str, meeting_type: str) -> list[str]:
    """
    Load the agenda JSON for a meeting and return titles of items flagged
    (off_mission or false_fiscal_claim or dollar_total > 0).
    Agenda JSONs use 'consent_items' and 'action_items', not 'items'.
    item_num is not stored in agenda JSONs, so we match by title.
    """
    path = os.path.join(AGENDAS_DIR, f"{date}-{meeting_type}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)

    flagged_titles = []
    for item in data.get("consent_items", []) + data.get("action_items", []):
        if (item.get("off_mission")
                or item.get("false_fiscal_claim")
                or (item.get("dollar_total") or 0) > 0):
            title = item.get("title", "")
            if title:
                flagged_titles.append(title.lower())
    return flagged_titles


def _title_is_flagged(pdf_title: str, flagged_titles: list[str]) -> bool:
    """Fuzzy match: check if pdf_title shares ≥6 consecutive words with any flagged title."""
    pdf_words = re.sub(r"[^a-z0-9 ]", "", pdf_title.lower()).split()
    for ft in flagged_titles:
        ft_words = re.sub(r"[^a-z0-9 ]", "", ft).split()
        # Check 6-gram overlap
        pdf_grams = {" ".join(pdf_words[i:i+6]) for i in range(max(1, len(pdf_words)-5))}
        ft_grams  = {" ".join(ft_words[i:i+6])  for i in range(max(1, len(ft_words)-5))}
        if pdf_grams & ft_grams:
            return True
    return False


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def report_path(date: str, item_key: str) -> str:
    # item_key is e.g. "4", "11a", "11b" — zero-pad the leading digits
    num_part = re.match(r"(\d+)(.*)", item_key)
    if num_part:
        key = f"{int(num_part.group(1)):02d}{num_part.group(2)}"
    else:
        key = item_key
    return os.path.join(REPORTS_DIR, f"{date}_item_{key}.json")


def pdf_cache_path(date: str, item_key: str) -> str:
    num_part = re.match(r"(\d+)(.*)", item_key)
    if num_part:
        key = f"{int(num_part.group(1)):02d}{num_part.group(2)}"
    else:
        key = item_key
    return os.path.join(PDF_CACHE_DIR, f"{date}_item_{key}.pdf")


def load_cached_report(date: str, item_key: str) -> dict | None:
    path = report_path(date, item_key)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def save_report(date: str, item_key: str, data: dict):
    path = report_path(date, item_key)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Core: process one item PDF
# ---------------------------------------------------------------------------

def process_item(date: str, meeting_type: str, item: dict, refresh: bool = False) -> dict | None:
    """
    Download (or use cached), extract, parse, and save one item.
    Returns the report dict, or None on failure.
    """
    item_key = item["item_key"]
    item_num = item["item_num"]
    url = item["url"]

    # Check JSON cache
    if not refresh:
        cached = load_cached_report(date, item_key)
        if cached:
            return cached

    # Load PDF bytes — check file cache first
    pdf_path = pdf_cache_path(date, item_key)
    if os.path.exists(pdf_path) and not refresh:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        print(f"    [cache] {date} item {item_key}", file=sys.stderr)
    else:
        print(f"    [fetch] {date} item {item_key}  {url}", file=sys.stderr)
        try:
            pdf_bytes = fetch_pdf_bytes(url)
        except Exception as e:
            print(f"    [ERROR] fetch failed: {e}", file=sys.stderr)
            return None
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        time.sleep(0.5)

    # Extract text
    try:
        full_text = extract_pdf_text(pdf_bytes)
    except Exception as e:
        print(f"    [ERROR] PDF extract failed: {e}", file=sys.stderr)
        return None

    # Parse sections
    sections = parse_sections(full_text)

    # Derive signals
    signals = derive_signals(sections, full_text)

    report = {
        "date": date,
        "meeting_type": meeting_type,
        "item_num": item_num,
        "item_key": item_key,
        "title": item.get("title", ""),
        "url": url,
        "word_count": len(full_text.split()),
        "sections": {k: v[:2000] for k, v in sections.items() if k != "full_text"},  # truncate for storage
        "signals": signals,
    }

    save_report(date, item_key, report)
    return report


# ---------------------------------------------------------------------------
# Core: process one meeting
# ---------------------------------------------------------------------------

def process_meeting(date: str, meeting_type: str,
                    refresh: bool = False,
                    flagged_only: bool = False,
                    list_only: bool = False) -> list[dict]:
    """
    Fetch the eAgenda page, discover item PDFs, and process each one.
    Returns list of report dicts.
    """
    slug = AGENDA_URL_MAP.get((date, meeting_type))
    if not slug:
        print(f"  No URL for {date} {meeting_type}", file=sys.stderr)
        return []

    url = BASE_URL + slug
    print(f"\n  {date} {meeting_type}  →  {url}", file=sys.stderr)

    try:
        html = fetch_html(url)
    except Exception as e:
        print(f"  [ERROR] fetch page failed: {e}", file=sys.stderr)
        return []
    time.sleep(0.3)

    items = extract_item_pdf_links(html)
    if not items:
        print(f"  No item PDFs found on page", file=sys.stderr)
        return []

    print(f"  Found {len(items)} item PDFs", file=sys.stderr)

    if list_only:
        for it in items:
            print(f"    item {it['item_key']:>4}  {it['title'][:80]}")
        return []

    # Filter to flagged items if requested
    if flagged_only:
        flagged_titles = load_flagged_titles(date, meeting_type)
        if flagged_titles:
            items = [it for it in items if _title_is_flagged(it["title"], flagged_titles)]
            print(f"  Filtered to {len(items)} flagged items", file=sys.stderr)

    reports = []
    for item in items:
        report = process_item(date, meeting_type, item, refresh=refresh)
        if report:
            reports.append(report)

    return reports


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_signals_summary(reports: list[dict]):
    # Deduplicate by URL (same PDF may appear under multiple item_keys if page lists it twice)
    seen = set()
    unique_reports = []
    for r in reports:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique_reports.append(r)
    reports = unique_reports

    flagged = [r for r in reports if (
        r["signals"].get("waived_competitive_bid")
        or r["signals"].get("backdated")
        or r["signals"].get("alternatives_none")
        or r["signals"].get("general_fund")
    )]
    if not flagged:
        return
    print(f"\n{'='*70}")
    print(f"PROCUREMENT SIGNALS ({len(flagged)} items flagged)")
    print(f"{'='*70}")
    for r in flagged:
        s = r["signals"]
        flags = []
        if s.get("waived_competitive_bid"): flags.append("WAIVED-BID")
        if s.get("backdated"):              flags.append("BACKDATED")
        if s.get("alternatives_none"):      flags.append("ALT=NONE")
        if s.get("general_fund"):           flags.append("GEN-FUND")
        if s.get("grant_funded"):           flags.append("grant-funded")
        vendor = s.get("vendor") or ""
        dollars = " ".join(s.get("dollar_amounts", [])[:3])
        print(f"  {r['date']} item {r['item_num']:02d}  [{' '.join(flags)}]")
        print(f"    {r['title'][:70]}")
        if vendor:
            print(f"    vendor: {vendor[:60]}")
        if dollars:
            print(f"    $: {dollars}")
        cpu = s.get("cost_per_unit", [])
        if cpu:
            print(f"    cost/unit: {', '.join(cpu[:3])}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Fetch and parse Berkeley agenda item staff reports")
    p.add_argument("--date", help="Process only this date (YYYY-MM-DD)")
    p.add_argument("--type", choices=["regular", "special", "both"], default="both",
                   help="Meeting type (default: both)")
    p.add_argument("--refresh", action="store_true", help="Re-fetch even if cached")
    p.add_argument("--flagged-only", action="store_true",
                   help="Only process items flagged in agenda JSON (off-mission/fiscal/spending)")
    p.add_argument("--list", action="store_true", help="List available items without downloading")
    return p.parse_args()


def main():
    args = parse_args()

    # Build list of (date, type) to process
    if args.date:
        if args.type == "both":
            pairs = [(args.date, t) for t in ("regular", "special")
                     if (args.date, t) in AGENDA_URL_MAP]
        else:
            pairs = [(args.date, args.type)] if (args.date, args.type) in AGENDA_URL_MAP else []
    else:
        if args.type == "both":
            pairs = list(AGENDA_URL_MAP.keys())
        else:
            pairs = [(d, t) for (d, t) in AGENDA_URL_MAP if t == args.type]

    pairs.sort()

    if not pairs:
        print("No matching meetings found.", file=sys.stderr)
        sys.exit(1)

    print(f"Processing {len(pairs)} meeting(s)...", file=sys.stderr)

    all_reports = []
    for date, mtype in pairs:
        reports = process_meeting(
            date, mtype,
            refresh=args.refresh,
            flagged_only=args.flagged_only,
            list_only=args.list,
        )
        all_reports.extend(reports)

    if not args.list:
        print(f"\nTotal items processed: {len(all_reports)}", file=sys.stderr)
        print_signals_summary(all_reports)


if __name__ == "__main__":
    main()
