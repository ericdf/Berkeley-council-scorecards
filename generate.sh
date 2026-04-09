#!/usr/bin/env bash
# generate.sh — Process new council meeting transcripts and regenerate scorecards
#
# Usage:
#   ./generate.sh                  # process any PDFs in minutes/ missing from text/
#   ./generate.sh --all            # re-extract all PDFs (overwrites existing text/)
#   ./generate.sh --scores-only    # re-score without regenerating PDFs
#
# Prerequisites: poppler (pdftotext) and the .venv virtualenv must exist.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MINUTES_DIR="$SCRIPT_DIR/minutes"
TEXT_DIR="$SCRIPT_DIR/text"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "ERROR: virtualenv not found at $SCRIPT_DIR/.venv" >&2
    echo "       Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

if ! command -v pdftotext &>/dev/null; then
    echo "ERROR: pdftotext not found. Install poppler: brew install poppler" >&2
    exit 1
fi

mkdir -p "$TEXT_DIR"

# --- Step 1: Extract text from PDFs ---
extracted=0
for pdf in "$MINUTES_DIR"/*.pdf; do
    [[ -e "$pdf" ]] || { echo "No PDFs found in $MINUTES_DIR"; exit 1; }
    base="$(basename "$pdf" .pdf)"
    txt="$TEXT_DIR/$base.txt"

    if [[ "${1:-}" == "--all" ]] || [[ ! -f "$txt" ]]; then
        echo "Extracting: $base"
        pdftotext -layout "$pdf" "$txt"
        ((extracted++)) || true
    fi
done

if [[ $extracted -eq 0 ]]; then
    echo "No new PDFs to extract (use --all to re-extract everything)."
else
    echo "Extracted $extracted PDF(s)."
fi

# --- Step 2: Score and generate PDFs ---
if [[ "${1:-}" == "--scores-only" ]]; then
    echo "Running pipeline (scores only)..."
    "$VENV_PYTHON" "$SCRIPT_DIR/pipeline.py" --no-pdf
else
    echo "Running pipeline (scores + PDFs)..."
    "$VENV_PYTHON" "$SCRIPT_DIR/pipeline.py"
fi

echo "Done. PDFs in $SCRIPT_DIR/scores/pdfs/"
