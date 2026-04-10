"""
audit_findings_pdf.py
=====================
Reads audit_findings.json and renders a PDF documenting each City Auditor
report: what was found, what action was warranted, and what the council
actually did. This is a separate stream from incidents — audits establish
ground truth; the council's response reveals the pattern.

Usage:
    python audit_findings_pdf.py
"""

import json
import os
import sys
from datetime import date

from weasyprint import HTML, CSS

HERE    = os.path.dirname(__file__)
SRC     = os.path.join(HERE, "audit_findings.json")
PDF_DIR = os.path.join(HERE, "scores", "pdfs")
OUT_PDF = os.path.join(PDF_DIR, "audit_findings.pdf")

STATUS_META = {
    "pending_council_action": ("Pending Council Action", "#e67e22"),
    "received_filed":         ("Received & Filed — No Substantive Follow-Up", "#c0392b"),
    "substantive_response":   ("Substantive Response Taken", "#27ae60"),
    "response_documented":    ("Response Documented", "#2c3e50"),
}

CSS_STYLE = """
@page {
    size: letter;
    margin: 0.85in 0.9in 0.85in 0.9in;
    @bottom-center {
        content: "Berkeley City Council Scorecard · Audit Findings Registry · " counter(page) " of " counter(pages);
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

.doc-title {
    font-size: 22pt;
    font-weight: 700;
    color: #1a1a1a;
    border-bottom: 3px solid #2980b9;
    padding-bottom: 6pt;
    margin-bottom: 4pt;
}

.doc-meta {
    font-size: 9.5pt;
    color: #666;
    margin-bottom: 6pt;
}

.intro-box {
    background: #f0f6fb;
    border-left: 4px solid #2980b9;
    padding: 10pt 14pt;
    margin: 14pt 0 22pt 0;
    font-size: 10pt;
    color: #333;
}

/* ---- Audit entry ---- */
.audit-entry {
    margin-bottom: 28pt;
    page-break-inside: avoid;
}

.audit-header {
    background: #1a1a2e;
    color: #fff;
    padding: 10pt 14pt 8pt 14pt;
}

.audit-title {
    font-size: 13pt;
    font-weight: 700;
    margin-bottom: 3pt;
}

.audit-meta-row {
    font-size: 9pt;
    opacity: 0.75;
    display: flex;
    gap: 20pt;
}

.audit-body {
    border: 1px solid #ccc;
    border-top: none;
}

.audit-section {
    padding: 9pt 14pt;
    border-bottom: 1px solid #e8e8e8;
}

.audit-section:last-child {
    border-bottom: none;
}

.section-label {
    font-size: 8.5pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6pt;
    color: #7f8c8d;
    margin-bottom: 5pt;
}

.finding-list {
    margin: 0;
    padding-left: 16pt;
}

.finding-list li {
    font-size: 10pt;
    margin-bottom: 3pt;
    line-height: 1.45;
}

.rec-list {
    margin: 0;
    padding-left: 16pt;
}

.rec-list li {
    font-size: 10pt;
    margin-bottom: 3pt;
    line-height: 1.45;
    color: #2c3e50;
}

.warranted-text {
    font-size: 10pt;
    color: #2c3e50;
    line-height: 1.5;
}

.response-text {
    font-size: 10pt;
    line-height: 1.5;
}

.followup-text {
    font-size: 10pt;
    line-height: 1.5;
    color: #c0392b;
    font-style: italic;
}

.null-text {
    font-size: 10pt;
    color: #aaa;
    font-style: italic;
}

.scoring-note {
    font-size: 10pt;
    line-height: 1.5;
    background: #fdf9f0;
    padding: 8pt 10pt;
    border-left: 3px solid #e67e22;
    margin-top: 2pt;
}

.status-badge {
    display: inline-block;
    font-size: 8.5pt;
    font-weight: 700;
    padding: 2pt 7pt;
    border-radius: 3pt;
    color: #fff;
    margin-bottom: 6pt;
}

.toc-section {
    margin-bottom: 22pt;
}

.toc-title {
    font-size: 12pt;
    font-weight: 700;
    color: #2c3e50;
    border-bottom: 1px solid #ddd;
    padding-bottom: 4pt;
    margin-bottom: 8pt;
}

.toc-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 4pt 0;
    border-bottom: 1px dotted #eee;
    font-size: 10pt;
}

.toc-status {
    font-size: 9pt;
    font-weight: 700;
}
"""


def _null_or(val, fallback="—"):
    if val is None:
        return f'<span class="null-text">{fallback}</span>'
    return val


def build_html(data: dict) -> str:
    today = date.today().strftime("%B %d, %Y")
    audits = {k: v for k, v in data.items() if not k.startswith("_")}

    # Sort: response_documented first, then pending
    order = {"response_documented": 0, "received_filed": 1,
             "substantive_response": 2, "pending_council_action": 3}
    sorted_audits = sorted(audits.items(),
                           key=lambda x: order.get(x[1].get("status", ""), 9))

    # Table of contents
    toc_rows = ""
    for key, a in sorted_audits:
        status = a.get("status", "")
        label, color = STATUS_META.get(status, (status, "#888"))
        toc_rows += f"""
<div class="toc-row">
  <span>{a.get('title', key)}</span>
  <span class="toc-status" style="color:{color}">{label}</span>
</div>"""

    # Audit entries
    entries_html = ""
    for key, a in sorted_audits:
        status = a.get("status", "")
        status_label, status_color = STATUS_META.get(status, (status, "#888"))

        # Key findings
        findings = a.get("key_findings", [])
        findings_html = "<ul class='finding-list'>" + "".join(
            f"<li>{f}</li>" for f in findings
        ) + "</ul>" if findings else '<span class="null-text">Not documented</span>'

        # Recommendations
        recs = a.get("recommendations", [])
        recs_html = "<ul class='rec-list'>" + "".join(
            f"<li>{r}</li>" for r in recs
        ) + "</ul>" if recs else '<span class="null-text">Not documented</span>'

        # Warranted action
        warranted = a.get("warranted_action")
        warranted_html = (
            f'<div class="warranted-text">{warranted}</div>'
            if warranted
            else '<span class="null-text">Not assessed</span>'
        )

        # Council response
        agenda_date = a.get("council_agenda_date")
        response    = a.get("council_response")
        if agenda_date:
            response_html = f'<div class="response-text"><b>Agenda date:</b> {agenda_date}<br>'
            if response:
                response_html += f'<b>Action:</b> {response}</div>'
            else:
                response_html += '<b>Action:</b> <span class="null-text">Not yet recorded</span></div>'
        else:
            response_html = '<span class="null-text">Not yet presented to council</span>'

        # Followup pattern
        followup = a.get("followup_pattern")
        followup_html = (
            f'<div class="followup-text">{followup}</div>'
            if followup
            else '<span class="null-text">None documented yet</span>'
        )

        # Scoring note
        scoring_note = a.get("scoring_note", "")
        scoring_html = f'<div class="scoring-note">{scoring_note}</div>' if scoring_note else ""

        entries_html += f"""
<div class="audit-entry">
  <div class="audit-header">
    <div class="audit-title">{a.get('title', key)}</div>
    <div class="audit-meta-row">
      <span>Released: {a.get('date_released', '—')}</span>
      <span>Author: {a.get('author', 'City Auditor')}</span>
      <span>Registry key: {key}</span>
    </div>
  </div>
  <div class="audit-body">
    <div class="audit-section">
      <span class="status-badge" style="background:{status_color}">{status_label}</span>
    </div>
    <div class="audit-section">
      <div class="section-label">Key Findings</div>
      {findings_html}
    </div>
    <div class="audit-section">
      <div class="section-label">Auditor Recommendations</div>
      {recs_html}
    </div>
    <div class="audit-section">
      <div class="section-label">Warranted Council Action</div>
      {warranted_html}
    </div>
    <div class="audit-section">
      <div class="section-label">Council Response</div>
      {response_html}
    </div>
    <div class="audit-section">
      <div class="section-label">Follow-Up Pattern</div>
      {followup_html}
    </div>
    <div class="audit-section">
      <div class="section-label">Scoring Note — What This Reveals</div>
      {scoring_html}
    </div>
  </div>
</div>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Berkeley Council Scorecard — Audit Findings Registry</title></head>
<body>

<div class="doc-title">Berkeley City Council Scorecard<br>Audit Findings Registry</div>
<div class="doc-meta">Generated {today} &nbsp;·&nbsp; {len(audits)} City Auditor reports tracked</div>

<div class="intro-box">
  <strong>Purpose of this document</strong><br>
  City Auditor reports establish documented ground truth — independent findings that create an obligation for the council to act. Ordinary voters will not read these reports or connect them to subsequent council decisions. This registry does that work: it tracks what each audit found, what a taxpayer-aligned council should have done in response, and what the council actually did. The gap between warranted action and actual response is the scored event. Incidents in the incident catalogue that are linked to an audit cite the registry key from this document.
</div>

<div class="toc-section">
  <div class="toc-title">Audits Tracked</div>
  {toc_rows}
</div>

{entries_html}

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
    print(f"Audit findings PDF → {OUT_PDF}")


if __name__ == "__main__":
    main()
