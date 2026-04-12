#!/usr/bin/env bash
# Usage: ./open_sources.sh <source_type> | sh
# Source types: investments acfr budgets policies
#
# Only opens entries where source_url is non-null and status is pending_review or extracted.
# Skip already-scored entries by default; pass --all to open everything.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ALL=0
TYPE=""

for arg in "$@"; do
  case "$arg" in
    --all) ALL=1 ;;
    *)     TYPE="$arg" ;;
  esac
done

case "$TYPE" in
  investments) JSON="$SCRIPT_DIR/sources/investments/investment_reports.json" ;;
  acfr)        JSON="$SCRIPT_DIR/sources/acfr/acfr_reports.json" ;;
  budgets)     JSON="$SCRIPT_DIR/sources/budgets/budget_documents.json" ;;
  policies)    JSON="$SCRIPT_DIR/sources/policies/policy_statements.json" ;;
  *)
    echo "Usage: $0 <source_type> [--all]" >&2
    echo "Types: investments acfr budgets policies" >&2
    exit 1
    ;;
esac

if [ "$ALL" -eq 1 ]; then
  STATUS_FILTER='.'
else
  STATUS_FILTER='select(.value.status == "pending_review" or .value.status == "extracted" or .value.status == null)'
fi

jq -r --arg all "$ALL" '
  to_entries[]
  | select(.key != "_schema")
  | '"$STATUS_FILTER"'
  | .value.source_url
  | select(type == "string" and length > 0)
  | "open " + (gsub(" "; "%20") | @json)
' "$JSON"
