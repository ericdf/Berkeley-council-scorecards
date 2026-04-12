#!/usr/bin/env bash
# generate.sh — Full artifact generation for the Berkeley City Council Scorecard pipeline
#
# Usage:
#   ./generate.sh                   # incremental: new transcripts only → scores + all PDFs
#   ./generate.sh --all             # re-extract all transcript PDFs, then full pipeline
#   ./generate.sh --scores-only     # re-score without generating PDFs (fast iteration)
#   ./generate.sh --scrape          # refresh annotated agendas + agenda JSONs, then full pipeline
#   ./generate.sh --scrape-only     # refresh data sources only, no scoring
#   ./generate.sh --methodology     # regenerate methodology PDF only
#   ./generate.sh --help            # show this message
#
# Artifact outputs:
#   scores/aggregate.json           — per-member composite scores
#   scores/per_meeting.json         — per-meeting scores for trend tracking
#   scores/linked_votes.json        — roll-call votes linked to agenda items
#   scores/snapshots/               — timestamped aggregate snapshots for delta tracking
#   scores/pdfs/scorecard_*.pdf     — individual member scorecards
#   scores/pdfs/scorecard_SUMMARY.pdf — one-page comparison across all members
#   scores/pdfs/methodology.pdf     — insider methodology document
#
# Prerequisites:
#   brew install poppler             # for pdftotext
#   mkvirtualenv council             # virtualenvwrapper (see README.md)
#   pip install -r requirements.txt

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MINUTES_DIR="$SCRIPT_DIR/minutes"
TEXT_DIR="$SCRIPT_DIR/text"
AMENDMENT_CSV="$SCRIPT_DIR/agendas/amendment_review.csv"
AMENDMENT_SENTINEL="$SCRIPT_DIR/agendas/.amendment_labels_ingested"

# Support both virtualenvwrapper symlink (.venv → ~/.virtualenvs/council) and plain venv
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

# ---- Help ----
if [[ "${1:-}" == "--help" ]]; then
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
fi

# ---- Preflight checks ----
if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "ERROR: virtualenv not found at $SCRIPT_DIR/.venv" >&2
    echo "       Run: mkvirtualenv council && pip install -r requirements.txt" >&2
    echo "       Or:  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

if ! command -v pdftotext &>/dev/null; then
    echo "ERROR: pdftotext not found. Install poppler: brew install poppler" >&2
    exit 1
fi

mkdir -p "$TEXT_DIR"

ARG="${1:-}"

# ---- Scrape-only mode ----
if [[ "$ARG" == "--scrape-only" ]]; then
    echo "=== Refreshing annotated agendas ==="
    "$VENV_PYTHON" "$SCRIPT_DIR/annotated_scraper.py"
    echo "=== Refreshing agenda JSONs ==="
    "$VENV_PYTHON" "$SCRIPT_DIR/agenda_scraper.py"
    echo "Done. Run ./generate.sh to score and regenerate PDFs."
    exit 0
fi

# ---- Methodology PDF only ----
if [[ "$ARG" == "--methodology" ]]; then
    echo "=== Regenerating methodology PDF ==="
    "$VENV_PYTHON" "$SCRIPT_DIR/methodology_pdf.py"
    exit 0
fi

# ---- Scrape before pipeline ----
if [[ "$ARG" == "--scrape" ]]; then
    echo "=== Refreshing annotated agendas ==="
    "$VENV_PYTHON" "$SCRIPT_DIR/annotated_scraper.py"
    echo "=== Refreshing agenda JSONs ==="
    "$VENV_PYTHON" "$SCRIPT_DIR/agenda_scraper.py"
fi

# ---- Step 1: Extract text from transcript PDFs ----
extracted=0
for pdf in "$MINUTES_DIR"/*.pdf; do
    [[ -e "$pdf" ]] || { echo "No PDFs found in $MINUTES_DIR"; exit 1; }
    base="$(basename "$pdf" .pdf)"
    txt="$TEXT_DIR/$base.txt"

    if [[ "$ARG" == "--all" ]] || [[ ! -f "$txt" ]]; then
        echo "Extracting: $base"
        pdftotext -layout "$pdf" "$txt"
        ((extracted++)) || true
    fi
done

if [[ $extracted -eq 0 ]]; then
    echo "No new transcript PDFs to extract (use --all to re-extract everything)."
else
    echo "Extracted $extracted transcript PDF(s)."
fi

# ---- Step 2: Re-ingest amendment labels if CSV has changed ----
# The sentinel file agendas/.amendment_labels_ingested is touched after each
# successful ingest.  If the CSV is newer than the sentinel (or the sentinel
# doesn't exist), re-ingest so that label revisions take effect automatically.
if [[ -f "$AMENDMENT_CSV" ]]; then
    if [[ ! -f "$AMENDMENT_SENTINEL" ]] || [[ "$AMENDMENT_CSV" -nt "$AMENDMENT_SENTINEL" ]]; then
        echo "=== Amendment labels changed — re-ingesting ==="
        "$VENV_PYTHON" "$SCRIPT_DIR/ingest_amendment_labels.py" "$AMENDMENT_CSV"
        touch "$AMENDMENT_SENTINEL"
    fi
fi

# ---- Step 3: Score and generate scorecards ----
if [[ "$ARG" == "--scores-only" ]]; then
    echo "=== Running pipeline (scores only, no PDFs) ==="
    "$VENV_PYTHON" "$SCRIPT_DIR/pipeline.py" --no-pdf
else
    echo "=== Running pipeline (scores + scorecards) ==="
    "$VENV_PYTHON" "$SCRIPT_DIR/pipeline.py"
fi

# ---- Step 4: Always regenerate methodology + incidents + audit findings PDFs ----
echo "=== Regenerating methodology PDF ==="
"$VENV_PYTHON" "$SCRIPT_DIR/methodology_pdf.py"
echo "=== Regenerating incident catalogue PDF ==="
"$VENV_PYTHON" "$SCRIPT_DIR/incidents_pdf.py"
echo "=== Regenerating audit findings PDF ==="
"$VENV_PYTHON" "$SCRIPT_DIR/audit_findings_pdf.py"

echo ""
echo "Done. Artifacts in $SCRIPT_DIR/scores/"
echo "  PDFs:        scores/pdfs/"
echo "  Scores:      scores/aggregate.json"
echo "  Methodology: scores/pdfs/methodology.pdf"
