"""
incidents_pdf.py
================
Reads incidents.json and renders a PDF catalogue of documented incidents
per council member.

Usage:
    python incidents_pdf.py
"""

import json
import os
import sys
from datetime import date

from weasyprint import HTML, CSS

HERE     = os.path.dirname(__file__)
SRC      = os.path.join(HERE, "incidents.json")
PDF_DIR  = os.path.join(HERE, "scores", "pdfs")
OUT_PDF  = os.path.join(PDF_DIR, "incidents.pdf")

# Human-readable labels for each category
CATEGORY_META = {
    "constituent_gaslight":   ("Constituent Gaslighting",  False, "Held meetings or sought input after decisions were made; performative not deliberative"),
    "alternatives_dismissed": ("Alternatives Dismissed",   False, "Explicitly closed off alternatives without analysis or evidence"),
    "claimed_ignorance":      ("Claimed Ignorance",        False, "Claimed not to know something they were obligated to know"),
    "atm_behavior":           ("Taxpayer-as-ATM",          False, "Reached for new revenue without first asking what can be cut or done more efficiently"),
    "union_deference":        ("Union Deference",          False, "Sided with city unions without requesting productivity data or efficiency tradeoffs"),
    "fiscal_integrity":       ("Fiscal Integrity",         True,  "Pushed back on spending, demanded cost data, or advocated for cuts"),
    "constituent_service":    ("Constituent Service",      True,  "Genuinely responsive constituent engagement with demonstrated follow-through"),
}

CSS_STYLE = """
@page {
    size: letter;
    margin: 0.85in 0.9in 0.85in 0.9in;
    @bottom-center {
        content: "Berkeley City Council Scorecard · Incident Catalogue · " counter(page) " of " counter(pages);
        font-size: 9pt;
        color: #888;
        font-family: 'Helvetica Neue', sans-serif;
    }
}

body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: #1a1a1a;
}

/* ---- Cover / intro ---- */
.doc-title {
    font-size: 22pt;
    font-weight: 700;
    color: #1a1a1a;
    border-bottom: 3px solid #c0392b;
    padding-bottom: 6pt;
    margin-bottom: 4pt;
}

.doc-meta {
    font-size: 9.5pt;
    color: #666;
    margin-bottom: 6pt;
}

.intro-box {
    background: #fdf5f5;
    border-left: 4px solid #c0392b;
    padding: 10pt 14pt;
    margin: 14pt 0 22pt 0;
    font-size: 10pt;
    color: #333;
}

/* ---- Member section ---- */
.member-header {
    font-size: 16pt;
    font-weight: 700;
    color: #fff;
    background: #2c3e50;
    padding: 8pt 12pt;
    margin-top: 24pt;
    margin-bottom: 0;
    page-break-after: avoid;
}

.member-total {
    font-size: 9pt;
    font-weight: 400;
    float: right;
    padding-top: 3pt;
    opacity: 0.85;
}

.member-block {
    border: 1px solid #ccc;
    border-top: none;
    margin-bottom: 14pt;
}

/* ---- Individual incident card ---- */
.incident-card {
    padding: 10pt 14pt;
    border-bottom: 1px solid #e8e8e8;
    page-break-inside: avoid;
}

.incident-card:last-child {
    border-bottom: none;
}

.incident-card.negative {
    border-left: 4px solid #c0392b;
}

.incident-card.positive {
    border-left: 4px solid #27ae60;
}

.incident-top {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 4pt;
}

.category-label {
    font-size: 9pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5pt;
}

.category-label.negative { color: #c0392b; }
.category-label.positive { color: #27ae60; }

.incident-date {
    font-size: 9pt;
    color: #888;
}

.incident-desc {
    font-size: 10pt;
    color: #1a1a1a;
    margin-bottom: 5pt;
    line-height: 1.5;
}

.incident-footer {
    display: flex;
    justify-content: space-between;
    font-size: 8.5pt;
    color: #888;
    border-top: 1px dotted #ddd;
    padding-top: 4pt;
    margin-top: 4pt;
}

.incident-source {
    font-style: italic;
    flex: 1;
    margin-right: 12pt;
}

.scoring-impact {
    white-space: nowrap;
    font-weight: 600;
}

.scoring-impact.negative { color: #c0392b; }
.scoring-impact.positive { color: #27ae60; }

/* ---- Category legend ---- */
.legend-section {
    margin-top: 28pt;
    page-break-before: always;
}

.legend-title {
    font-size: 13pt;
    font-weight: 700;
    color: #2c3e50;
    border-bottom: 1px solid #ddd;
    padding-bottom: 4pt;
    margin-bottom: 10pt;
}

.legend-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 9.5pt;
}

.legend-table th {
    background: #2c3e50;
    color: #fff;
    padding: 5pt 8pt;
    text-align: left;
    font-weight: 600;
    border: 1px solid #2c3e50;
}

.legend-table td {
    padding: 5pt 8pt;
    border: 1px solid #ddd;
    vertical-align: top;
}

.legend-table tr:nth-child(even) td {
    background: #f8f8f8;
}

.cat-pos { color: #27ae60; font-weight: 700; }
.cat-neg { color: #c0392b; font-weight: 700; }

.note {
    font-size: 9pt;
    color: #666;
    margin-top: 12pt;
    font-style: italic;
}
"""


def _impact_str(val: float) -> str:
    if val >= 0:
        return f"+{val:.2f}"
    return f"{val:.2f}"


def _member_total(incidents: list) -> float:
    return sum(i.get("scoring_impact", 0) for i in incidents)


def build_html(data: dict) -> str:
    today = date.today().strftime("%B %Y")

    # Sort members alphabetically, skip schema key
    members = {k: v for k, v in data.items() if not k.startswith("_")}
    member_names = sorted(members.keys())

    # Build per-member incident blocks
    member_html = ""
    for name in member_names:
        incidents = members[name]
        total = _member_total(incidents)
        total_str = _impact_str(total)
        total_class = "negative" if total < 0 else "positive"

        cards_html = ""
        for inc in incidents:
            cat = inc.get("category", "")
            meta = CATEGORY_META.get(cat, (cat, False, ""))
            label, is_positive, _ = meta
            polarity = "positive" if is_positive else "negative"
            impact = inc.get("scoring_impact", 0)
            impact_str = _impact_str(impact)

            cards_html += f"""
<div class="incident-card {polarity}">
  <div class="incident-top">
    <span class="category-label {polarity}">{label}</span>
    <span class="incident-date">{inc.get('date', '')}</span>
  </div>
  <div class="incident-desc">{inc.get('description', '')}</div>
  <div class="incident-footer">
    <span class="incident-source">Source: {inc.get('source', '')}</span>
    <span class="scoring-impact {polarity}">Scoring impact: {impact_str}</span>
  </div>
</div>"""

        member_html += f"""
<div class="member-header">
  {name}
  <span class="member-total">Net scoring adjustment: {total_str}</span>
</div>
<div class="member-block">{cards_html}
</div>"""

    # Category legend
    legend_rows = ""
    for cat_key, (label, is_positive, desc) in CATEGORY_META.items():
        polarity_label = "POSITIVE" if is_positive else "NEGATIVE"
        polarity_class = "cat-pos" if is_positive else "cat-neg"
        legend_rows += f"""
<tr>
  <td><strong>{label}</strong></td>
  <td class="{polarity_class}">{polarity_label}</td>
  <td>{desc}</td>
</tr>"""

    total_incidents = sum(len(v) for v in members.values())
    total_members   = len(member_names)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Berkeley Council Scorecard — Incident Catalogue</title></head>
<body>

<div class="doc-title">Berkeley City Council Scorecard<br>Incident Catalogue</div>
<div class="doc-meta">Generated {today} &nbsp;·&nbsp; {total_incidents} incidents documented across {total_members} members</div>

<div class="intro-box">
  <strong>What is an incident?</strong><br>
  An incident is a documented behavior or action that reveals something meaningful about a council member, but is not captured in meeting transcripts or agenda records. Examples include: constituent interactions, public statements outside formal meetings, patterns of communication, and observable policy dispositions that have not been raised formally on the dais. Incidents are tracked in a structured log and feed directly into the Taxpayer Alignment component of the composite grade. Each incident carries a scoring impact (negative or positive) capped at ±0.30 per member in aggregate. Sources are documented with each entry.
</div>

{member_html}

<div class="legend-section">
  <div class="legend-title">Category Definitions</div>
  <table class="legend-table">
    <tr>
      <th style="width:22%">Category</th>
      <th style="width:12%">Direction</th>
      <th>Description</th>
    </tr>
    {legend_rows}
  </table>
  <p class="note">Scoring impact range: suggested −0.10 to +0.10 per incident, with a per-member cap of ±0.30.
  Incidents supplement — but do not replace — transcript and agenda-based signals.
  The cap prevents any single member's anecdote record from dominating the composite score.</p>
</div>

</body>
</html>"""
    return html


def main():
    if not os.path.exists(SRC):
        print(f"ERROR: {SRC} not found", file=sys.stderr)
        sys.exit(1)

    os.makedirs(PDF_DIR, exist_ok=True)

    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)

    html = build_html(data)
    HTML(string=html, base_url=HERE).write_pdf(
        OUT_PDF,
        stylesheets=[CSS(string=CSS_STYLE)],
    )
    print(f"  → {OUT_PDF}", file=sys.stderr)


if __name__ == "__main__":
    main()
