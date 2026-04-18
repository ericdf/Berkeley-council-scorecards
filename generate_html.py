#!/usr/bin/env python3
"""
generate_html.py

Generates screen-optimized HTML scorecards to publish/ directory.
Imports render functions from scorecard_pdf.py and strips print-specific CSS.

Usage:
    python3 generate_html.py
    python3 generate_html.py scores/aggregate.json   # explicit path
"""

import json
import os
import re
import sys
import types

# Stub weasyprint so scorecard_pdf can be imported without the library installed.
# generate_html.py never calls write_pdf(), so no real implementation needed.
if "weasyprint" not in sys.modules:
    _wp = types.ModuleType("weasyprint")
    class _Stub:
        def __init__(self, **kw): pass
        def write_pdf(self, *a, **kw): pass
    _wp.HTML = _wp.CSS = _Stub
    sys.modules["weasyprint"] = _wp

import scorecard_pdf as sc
import mayor_scorecard as ms

PUBLISH_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "publish")
INCIDENTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "incidents.json")

# Human-readable labels for incident categories
CATEGORY_LABELS = {
    "performative_engagement": "Performative engagement",
    "alternatives_dismissed":  "Alternatives dismissed",
    "claimed_ignorance":       "Claimed ignorance",
    "revenue_without_cuts":    "Seeks revenue without cuts",
    "union_deference":       "Union deference",
    "scope_indiscipline":    "Outside city scope",
    "fiscal_integrity":      "Fiscal discipline ✓",
    "constituent_service":   "Constituent service ✓",
}

def _load_incidents() -> dict:
    """Return per-member list of incident dicts from incidents.json."""
    try:
        with open(INCIDENTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, list)}


def _render_incidents_section(name: str) -> str:
    """
    Return an HTML string for the 'Recent behavior' section for a given member.
    Shows up to 5 most recent A/B-tier incidents with short_desc, sorted newest first.
    Returns empty string if no displayable incidents.
    """
    all_incidents = _load_incidents()
    incidents = all_incidents.get(name, [])

    # Filter to A/B tier with a short_desc, sort newest first
    displayable = [
        i for i in incidents
        if i.get("evidence_tier") in ("A", "B") and i.get("short_desc")
    ]
    # Sort: full dates first (YYYY-MM-DD), then partial (YYYY or YYYY-YYYY) at end
    def sort_key(i):
        d = i.get("date", "")
        if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            return d
        return "0000"  # partial dates sort to end
    displayable.sort(key=sort_key, reverse=True)
    displayable = displayable[:5]

    if not displayable:
        return ""

    rows = ""
    for inc in displayable:
        tier  = inc.get("evidence_tier", "")
        cat   = CATEGORY_LABELS.get(inc.get("category", ""), inc.get("category", ""))
        date  = inc.get("date", "")
        desc  = inc.get("short_desc", "")
        impact = inc.get("scoring_impact", 0) or 0
        positive = impact > 0

        # Impact dot: scale 0–10 mapped to 1–3 dots
        abs_impact = abs(impact)
        if abs_impact >= 0.09:
            dots = "●●●"
        elif abs_impact >= 0.06:
            dots = "●●○"
        else:
            dots = "●○○"

        dot_color  = "#2ecc71" if positive else "#e74c3c"
        tier_color = "#2ecc71" if tier == "A" else "#f39c12"

        rows += f"""
      <tr class="inc-row">
        <td class="inc-date">{date}</td>
        <td class="inc-body">
          <span class="inc-cat">{cat}</span>
          <span class="inc-desc">{desc}</span>
        </td>
        <td class="inc-meta">
          <span class="inc-tier" style="color:{tier_color}">Tier {tier}</span>
          <span class="inc-dots" style="color:{dot_color};letter-spacing:-1px" title="Impact: {impact:+.2f}">{dots}</span>
        </td>
      </tr>"""

    return f"""
<div class="incidents-section">
  <div class="incidents-header">Recent behavior</div>
  <table class="incidents-table">
    <tbody>{rows}
    </tbody>
  </table>
</div>
<style>
  .incidents-section {{
    margin: 16px 24px 8px;
    border: 1px solid #e8ecef;
    border-radius: 6px;
    overflow: hidden;
    font-size: 11.5px;
  }}
  .incidents-header {{
    background: #f0f2f5;
    padding: 7px 12px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .8px;
    color: #7f8c8d;
    border-bottom: 1px solid #e0e4e8;
  }}
  .incidents-table {{
    width: 100%;
    border-collapse: collapse;
  }}
  .inc-row {{
    border-bottom: 1px solid #f0f2f5;
  }}
  .inc-row:last-child {{
    border-bottom: none;
  }}
  .inc-date {{
    padding: 7px 8px 7px 12px;
    font-size: 10px;
    color: #aaa;
    white-space: nowrap;
    vertical-align: top;
    min-width: 72px;
  }}
  .inc-body {{
    padding: 7px 8px;
    vertical-align: top;
    line-height: 1.4;
  }}
  .inc-cat {{
    display: block;
    font-size: 9.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .5px;
    color: #95a5a6;
    margin-bottom: 2px;
  }}
  .inc-desc {{
    font-size: 11.5px;
    color: #34495e;
  }}
  .inc-meta {{
    padding: 7px 12px 7px 4px;
    vertical-align: top;
    text-align: right;
    white-space: nowrap;
  }}
  .inc-tier {{
    display: block;
    font-size: 9px;
    font-weight: 700;
    margin-bottom: 3px;
  }}
  .inc-dots {{
    font-size: 9px;
  }}
</style>"""


# ---------------------------------------------------------------------------
# CSS surgery — strip print rules, inject screen rules
# ---------------------------------------------------------------------------

def _strip_print_css(html: str) -> str:
    """Remove @page rules and page-break directives from inline <style> blocks."""
    # @page rules (single-line and multi-line)
    html = re.sub(r'@page\s*\{[^}]*\}', '', html)
    # page-break properties
    html = re.sub(r'page-break-before\s*:\s*\w+\s*;', '', html)
    html = re.sub(r'page-break-after\s*:\s*\w+\s*;', '', html)
    html = re.sub(r'page-break-inside\s*:\s*\w+\s*;', '', html)
    return html


def _add_viewport(html: str) -> str:
    """Add viewport meta tag for responsive rendering."""
    return html.replace(
        '<meta charset="utf-8">',
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
    )


def _add_index_link(html: str) -> str:
    """Inject a small nav link back to the index after <body>."""
    nav = (
        '<div style="text-align:center;padding:8px 0 0;font-size:11px;color:#7f8c8d">'
        '<a href="index.html" style="color:#3498db;text-decoration:none">← All scorecards</a>'
        '</div>\n'
    )
    return html.replace('<body>\n', f'<body>\n{nav}', 1)


def screen_html(html: str, add_back_link: bool = False) -> str:
    html = _strip_print_css(html)
    html = _add_viewport(html)
    if add_back_link:
        html = _add_index_link(html)
    return html


# ---------------------------------------------------------------------------
# Index page
# ---------------------------------------------------------------------------

def render_index(members_meta: list[dict], meta: dict) -> str:
    """
    members_meta: list of dicts with keys: name, display_name, district, grade_str, grade_cls, score
    """
    gen_date   = meta.get("generated", "")[:10]
    latest_mtg = meta.get("latest_meeting", "")
    n_meetings = meta.get("transcripts", 0)

    rows = ""
    for m in members_meta:
        filename = f"scorecard_{m['name']}.html"
        rows += f"""
      <tr>
        <td class="rank">{m['rank']}</td>
        <td class="name">
          <a href="{filename}">{m['display_name']}</a><br>
          <span class="sub">{m['district']}</span>
        </td>
        <td class="grade {m['grade_cls']}">{m['grade_str']}</td>
        <td class="score">{m['score']*100:.0f}%</td>
      </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Berkeley City Council Scorecards</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0;
         font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }}
    body {{ background: #f0f2f5; padding: 32px 16px; color: #2c3e50; }}
    .card {{ max-width: 540px; margin: 0 auto; background: #fff;
             border-radius: 8px; overflow: hidden;
             box-shadow: 0 4px 20px rgba(0,0,0,.12); }}
    .header {{ background: #1a1a2e; color: #fff; padding: 28px 32px 20px; }}
    .header h1 {{ font-size: 22px; font-weight: 800; }}
    .header p  {{ font-size: 12px; color: #8899bb; margin-top: 6px; line-height: 1.6; }}
    .intro {{ padding: 20px 24px; font-size: 12.5px; line-height: 1.7; color: #444;
              border-bottom: 1px solid #ecf0f1; }}
    .intro a {{ color: #3498db; text-decoration: none; }}
    .intro a:hover {{ text-decoration: underline; }}
    table {{ width: 100%; border-collapse: collapse; }}
    thead tr {{ background: #f0f2f5; }}
    th {{ font-size: 10px; text-transform: uppercase; letter-spacing: .8px;
          color: #7f8c8d; padding: 10px 16px; text-align: left; font-weight: 600; }}
    tbody tr {{ border-bottom: 1px solid #ecf0f1; }}
    tbody tr:hover {{ background: #f8f9fa; }}
    td {{ padding: 12px 16px; vertical-align: middle; }}
    .rank  {{ width: 32px; font-size: 11px; color: #aaa; text-align: center; }}
    .name  {{ font-size: 14px; font-weight: 600; }}
    .name a {{ color: #2c3e50; text-decoration: none; }}
    .name a:hover {{ color: #3498db; }}
    .sub   {{ font-size: 11px; color: #999; font-weight: 400; }}
    .grade {{ width: 52px; font-size: 22px; font-weight: 900; text-align: center; }}
    .score {{ width: 56px; text-align: right; font-size: 13px; color: #7f8c8d; }}
    .grade-a  {{ color: #2ecc71; }}
    .grade-b  {{ color: #3498db; }}
    .grade-c  {{ color: #f39c12; }}
    .grade-d  {{ color: #e67e22; }}
    .grade-f  {{ color: #e74c3c; }}
    .footer {{ padding: 12px 20px; font-size: 10px; color: #aaa; text-align: center; }}
    .summary-link {{ display: block; text-align: center; padding: 14px;
                     background: #f8f9fa; border-top: 1px solid #ecf0f1;
                     font-size: 12px; color: #3498db; text-decoration: none; }}
    .summary-link:hover {{ background: #ecf0f1; }}
  </style>
</head>
<body>
<div class="card">
  <div class="header">
    <h1>Berkeley City Council Scorecards</h1>
    <p>
      Ranked by Voter Alignment &nbsp;·&nbsp; {n_meetings} meetings analyzed<br>
      {"As of " + latest_mtg + " &nbsp;·&nbsp; " if latest_mtg else ""}Generated {gen_date}
    </p>
  </div>
  <div class="intro">
    Berkeley&rsquo;s nine-member City Council governs ~125,000 residents, directs ~$292M in General
    Fund spending and ~$630M across all city funds, and oversees an organization of ~1,600 budgeted
    positions and ~2,700 employees. The city&rsquo;s own documents describe the fiscal trajectory as
    &ldquo;not sustainable&rdquo;: a ~$32M annual structural deficit and ~$1.8B in deferred
    infrastructure investment. These scorecards ask how each member is performing against that
    backdrop &mdash; drawn from years of city budgets, audited fiscal reports, and audit findings,
    alongside meeting transcripts, voting records, and member communications.
    <a href="methodology.html">Methodology &rarr;</a>
  </div>
  <table>
    <thead>
      <tr>
        <th></th>
        <th>Member</th>
        <th>Grade</th>
        <th>Score</th>
      </tr>
    </thead>
    <tbody>{rows}
    </tbody>
  </table>
  <a class="summary-link" href="scorecard_SUMMARY.html">View full comparison table →</a>
  <div style="border-top: 3px solid #c0392b; margin: 0; padding: 16px 24px 8px;
              background: #fdf5f5;">
    <div style="font-size: 10px; font-weight: 700; text-transform: uppercase;
                letter-spacing: 1.2px; color: #c0392b; margin-bottom: 10px;">
      Mayor — Evaluated Separately
    </div>
    <div style="font-size: 12px; color: #555; line-height: 1.6; margin-bottom: 12px;">
      The mayor sets the agenda, chairs meetings, and holds unique powers unavailable to
      district council members. She is graded on <em>Mayoral Accountability</em> —
      agenda curation, constituent communications, meeting management, and accountability
      gap — not the same Voter Alignment metric used for district members.
    </div>
    <table style="width:100%;border-collapse:collapse">
      <tbody>
        <tr style="border-bottom: none;">
          <td style="width:32px;font-size:11px;color:#aaa;text-align:center">★</td>
          <td style="font-size:14px;font-weight:600;padding:10px 16px">
            <a href="scorecard_Ishii.html" style="color:#2c3e50;text-decoration:none">Ishii</a><br>
            <span style="font-size:11px;color:#999;font-weight:400">Mayor · At-Large</span>
          </td>
          <td style="width:52px;font-size:22px;font-weight:900;text-align:center;color:#e67e22">{ms._letter(ms.MAYORAL_SCORE)[0]}</td>
          <td style="width:56px;text-align:right;font-size:13px;color:#7f8c8d">{ms.MAYORAL_SCORE*100:.0f}%</td>
        </tr>
      </tbody>
    </table>
  </div>
  <div class="footer">Berkeley City Council Analysis &nbsp;·&nbsp; Generated {gen_date}</div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

METHODOLOGY_SCREEN_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 15px;
    line-height: 1.65;
    color: #2c3e50;
    background: #f0f2f5;
    padding: 32px 16px;
}
.wrap {
    max-width: 740px;
    margin: 0 auto;
    background: #fff;
    border-radius: 8px;
    padding: 40px 48px;
    box-shadow: 0 4px 20px rgba(0,0,0,.12);
}
.back { font-size: 12px; margin-bottom: 24px; }
.back a { color: #3498db; text-decoration: none; }
h1 { font-size: 26px; font-weight: 800; color: #1a1a2e;
     border-bottom: 3px solid #c0392b; padding-bottom: 10px; margin-bottom: 6px; }
h2 { font-size: 17px; font-weight: 700; color: #c0392b;
     margin-top: 36px; margin-bottom: 8px;
     border-bottom: 1px solid #ecf0f1; padding-bottom: 4px; }
h3 { font-size: 14px; font-weight: 700; color: #2c3e50;
     margin-top: 24px; margin-bottom: 6px; }
h4 { font-size: 13px; font-weight: 700; color: #555;
     margin-top: 16px; margin-bottom: 4px; }
p  { margin: 0 0 12px 0; }
ul, ol { margin: 6px 0 12px 0; padding-left: 22px; }
li { margin-bottom: 5px; }
table { width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 13px; }
th { background: #2c3e50; color: #fff; font-weight: 600;
     padding: 7px 10px; text-align: left; border: 1px solid #2c3e50; }
td { padding: 6px 10px; border: 1px solid #ddd; vertical-align: top; }
tr:nth-child(even) td { background: #f8f9fa; }
code { font-family: 'Courier New', monospace; font-size: 12px;
       background: #f0f0f0; padding: 1px 4px; border-radius: 3px; }
pre  { background: #f0f0f0; padding: 14px 16px; border-radius: 4px;
       overflow-x: auto; font-size: 12px; margin: 0 0 12px 0; }
pre code { background: none; padding: 0; }
hr { border: none; border-top: 1px solid #ecf0f1; margin: 28px 0; }
blockquote { border-left: 3px solid #c0392b; margin: 10px 0;
             padding: 6px 16px; background: #fdf5f5;
             color: #555; font-style: italic; }
strong { color: #1a1a2e; }
"""


def _render_methodology_html() -> str:
    """Convert METHODOLOGY.md to a screen-optimized HTML page."""
    try:
        import markdown as _md
    except ImportError:
        return ""
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "METHODOLOGY.md")
    if not os.path.exists(src):
        return ""
    with open(src, encoding="utf-8") as f:
        md_text = f.read()
    body = _md.markdown(md_text, extensions=["tables", "fenced_code", "nl2br"])
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Berkeley Council Scorecards — Methodology</title>
  <style>{METHODOLOGY_SCREEN_CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="back"><a href="index.html">← All scorecards</a></div>
  {body}
</div>
</body>
</html>"""


def generate_html(aggregate: dict = None, council_meta: dict = None):
    if aggregate is None:
        agg_path = os.path.join(sc.SCORES_DIR, "aggregate.json")
        if len(sys.argv) > 1:
            agg_path = sys.argv[1]
        with open(agg_path) as f:
            aggregate = json.load(f)

    meta = aggregate.get("_meta", {})
    if council_meta is None:
        council_meta = {
            "block_vote_rate":   meta.get("block_vote_rate", 0),
            "total_vote_events": meta.get("total_vote_events", 0),
            "block_vote_events": meta.get("block_vote_events", 0),
        }

    os.makedirs(PUBLISH_DIR, exist_ok=True)
    rankings  = sc.build_rankings(aggregate)

    summaries_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "member_summaries.json")
    summaries: dict = {}
    if os.path.exists(summaries_path):
        with open(summaries_path, encoding="utf-8") as f:
            summaries = json.load(f)

    # Individual member scorecards
    index_members = []
    for name, s in sorted(aggregate.items(),
                          key=lambda kv: -(kv[1].get("composite_grade", 0) or 0)):
        if name.startswith("_") or name == "Ishii":
            continue
        if (s.get("words") or 0) < 1500:
            continue

        html = sc.render_member(
            s, rankings, council_meta.get("block_vote_rate", 0), meta,
            summary=summaries.get(name, {})
        )
        incidents_html = _render_incidents_section(name)
        if incidents_html:
            html = html.replace("</body>", f"{incidents_html}\n</body>", 1)
        html = screen_html(html, add_back_link=True)

        out = os.path.join(PUBLISH_DIR, f"scorecard_{name}.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  → {out}", file=sys.stderr)

        grade_str, grade_cls = sc.letter(s.get("composite_grade"))
        rank = rankings.get("composite_grade", {}).get(name, "?")
        index_members.append({
            "name":         name,
            "display_name": s.get("display_name", name),
            "district":     sc.DISTRICT.get(name, ""),
            "rank":         rank,
            "grade_str":    grade_str,
            "grade_cls":    grade_cls,
            "score":        s.get("composite_grade", 0) or 0,
        })

    # Mayor scorecard (Ishii — separate accountability framework)
    mayor_html = ms.render_mayor_scorecard(meta)
    ishii_incidents = _render_incidents_section("Ishii")
    if ishii_incidents:
        mayor_html = mayor_html.replace("</body>", f"{ishii_incidents}\n</body>", 1)
    mayor_html = screen_html(mayor_html, add_back_link=True)
    mayor_out  = os.path.join(PUBLISH_DIR, "scorecard_Ishii.html")
    with open(mayor_out, "w", encoding="utf-8") as f:
        f.write(mayor_html)
    print(f"  → {mayor_out}", file=sys.stderr)

    # Summary page
    summary_html = sc.render_summary(aggregate, rankings, council_meta, meta)
    summary_html = screen_html(summary_html, add_back_link=False)
    # Make the summary scrollable horizontally on small screens
    summary_html = summary_html.replace(
        '<body>',
        '<body>\n<div style="text-align:center;padding:8px 0 0;font-size:11px;color:#7f8c8d">'
        '<a href="index.html" style="color:#3498db;text-decoration:none">← All scorecards</a>'
        '</div>'
    )
    summary_out = os.path.join(PUBLISH_DIR, "scorecard_SUMMARY.html")
    with open(summary_out, "w", encoding="utf-8") as f:
        f.write(summary_html)
    print(f"  → {summary_out}", file=sys.stderr)

    # Index page
    index_members_sorted = sorted(index_members, key=lambda m: m["rank"]
                                  if isinstance(m["rank"], int) else 99)
    index_html = render_index(index_members_sorted, meta)
    index_out  = os.path.join(PUBLISH_DIR, "index.html")
    with open(index_out, "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"  → {index_out}", file=sys.stderr)

    # Methodology page
    meth_html = _render_methodology_html()
    if meth_html:
        meth_out = os.path.join(PUBLISH_DIR, "methodology.html")
        with open(meth_out, "w", encoding="utf-8") as f:
            f.write(meth_html)
        print(f"  → {meth_out}", file=sys.stderr)
    else:
        print("  → methodology.html  (skipped — install: pip install markdown)", file=sys.stderr)

    print(f"\nAll HTML written to {PUBLISH_DIR}/", file=sys.stderr)
    print("Run publish.sh to push to GitHub Pages.", file=sys.stderr)


if __name__ == "__main__":
    generate_html()
