#!/usr/bin/env bash
# publish.sh — generate HTML scorecards and push to council-scorecards GitHub Pages repo
#
# Usage:  ./publish.sh [path/to/aggregate.json]
#
# Requires:
#   - publish/ directory is populated by generate_html.py
#   - A local clone of the council-scorecards repo (../council-scorecards)
#     OR the script will clone it on first run.
#
# The council-scorecards repo must have GitHub Pages configured to serve
# from the root of the main branch (Settings → Pages → Branch: main / root).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUBLISH_DIR="$SCRIPT_DIR/publish"
PAGES_REPO_DIR="$(dirname "$SCRIPT_DIR")/council-scorecards"
PAGES_REPO_URL="https://github.com/ericdf/council-scorecards.git"

# Use the council virtualenv's Python if available (needed for markdown library)
VENV_PYTHON="$HOME/.virtualenvs/council/bin/python3"
if [ -x "$VENV_PYTHON" ]; then
    PYTHON="$VENV_PYTHON"
else
    PYTHON="python3"
fi

# ── Step 1: generate HTML ────────────────────────────────────────────────────
echo "Generating HTML scorecards..."
if [ -n "${1:-}" ]; then
    "$PYTHON" "$SCRIPT_DIR/generate_html.py" "$1"
else
    "$PYTHON" "$SCRIPT_DIR/generate_html.py"
fi

if [ ! -f "$PUBLISH_DIR/index.html" ]; then
    echo "ERROR: publish/index.html not found — HTML generation may have failed." >&2
    exit 1
fi

# ── Step 2: clone or update the pages repo ───────────────────────────────────
if [ ! -d "$PAGES_REPO_DIR/.git" ]; then
    echo "Cloning council-scorecards repo to $PAGES_REPO_DIR..."
    git clone "$PAGES_REPO_URL" "$PAGES_REPO_DIR"
fi

# ── Step 3: copy HTML files into pages repo ──────────────────────────────────
echo "Copying to $PAGES_REPO_DIR..."
for f in "$PUBLISH_DIR"/*.html; do
    cp "$f" "$PAGES_REPO_DIR/"
    echo "  → $PAGES_REPO_DIR/$(basename "$f")" >&2
done

# ── Step 4: commit and push ──────────────────────────────────────────────────
cd "$PAGES_REPO_DIR"
git add -A

# Only commit if there are changes
if git diff --cached --quiet; then
    echo "No changes — pages repo already up to date."
else
    DATESTAMP="$(date -u '+%Y-%m-%d %H:%M UTC')"
    git commit -m "Scorecard update — $DATESTAMP"
    git push origin main
    echo ""
    echo "Published: https://ericdf.github.io/council-scorecards/"
fi
