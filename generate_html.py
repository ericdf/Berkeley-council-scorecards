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

# Canonical incident list. Each entry is one incident with all implicated parties.
# members: list of canonical names implicated; "Full Council" = all current council members.
# scores: net score for each implicated party (member-specific composite of all dimensions).
# pillars: pillars implicated across all dimensions (for display; scoring by pillar TBD).
# pending: whether scores are subject to revision pending verification.
# Update this alongside incidents/YYYY-mm/ HTML files.
ALL_EDITORIAL_INCIDENTS: list[dict] = [
    {
        "title":   "American Renewal Plan — Federal Policy Framework on District Platform",
        "date":    "2026-04-12",
        "url":     "incidents/2026-04/incident_Bartlett_Renewal.html",
        "summary": "Bartlett published a five-pillar national economic reform framework on his "
                   "council office platform — addressed to federal policymakers — while Berkeley "
                   "faces an unresolved structural fiscal crisis and unaddressed local failures. "
                   "None of the plan's pillars touches any Berkeley P1 problem.",
        "members": ["Bartlett"],
        "scores":  {"Bartlett": -10},
        "pillars": ["Character & Conduct"],
        "pending": False,
    },
    {
        "title":   "Flock Safety Contract — Negotiated Protections Dismissed",
        "date":    "2026-03-24",
        "url":     "incidents/2026-03/incident_Flock_Rejection.html",
        "summary": "LunaParra and Ishii authored a supplemental to reject the Flock ALPR "
                   "contract; Tregub co-sponsored. Their sanctuary-city rationale ignored "
                   "that Berkeley's City Attorney had already negotiated full protections. "
                   "Officers identified Flock as 'the singular piece of technology' keeping "
                   "them engaged, amid a documented BPD attrition crisis.",
        "members": ["LunaParra", "Ishii", "Tregub"],
        "scores":  {"LunaParra": -9, "Ishii": -8, "Tregub": -6},
        "pillars": ["Fiscal Stewardship"],
        "pending": False,
    },
    {
        "title":   "Police Accountability Board Collapse — Aguilar Firing",
        "date":    "2026-02-09",
        "url":     "incidents/2026-02/incident_PAB_Aguilar.html",
        "summary": "Council voted 8–0 to fire ODPA Director Aguilar while the PAB was at "
                   "4 of 9 seats with all original commissioners gone. LunaParra voted yes "
                   "then issued a statement she was 'concerned the Council does not value "
                   "Police accountability.' Ishii declared the council 'remained committed' "
                   "immediately after eliminating the office's leadership.",
        "members": ["Full Council", "LunaParra", "Ishii"],
        "scores":  {"Full Council": -7, "LunaParra": -12, "Ishii": -10},
        "pillars": ["Character & Conduct"],
        "pending": False,
    },
    {
        "title":   "Household Entanglement with City Subcontractor",
        "date":    "2026-04-22",
        "url":     "incidents/2026-04/incident_Bartlett_Upline.html",
        "summary": "Bartlett's wife co-incorporated Upline Solutions, a city subcontractor "
                   "on a $607K cannabis education contract that failed to deliver. No public "
                   "disclosure or recusal from related votes was identified.",
        "members": ["Bartlett"],
        "scores":  {"Bartlett": -18},
        "pillars": ["Character & Conduct"],
        "pending": False,
    },
    {
        "title":   "BYA Cannabis Contract — Institutional Accountability Failure",
        "date":    "2026-04-22",
        "url":     "incidents/2026-04/incident_BYA_Institutional.html",
        "summary": "Despite a county evaluation documenting BYA contract failures, the council "
                   "reauthorized a $106K soda tax grant with no documented review. Bartlett "
                   "additionally deflected accountability in public remarks.",
        "members": ["Full Council", "Bartlett"],
        "scores":  {"Full Council": -3, "Bartlett": -7},
        "pillars": ["Character & Conduct", "Fiscal Stewardship"],
        "pending": True,
    },
    {
        "title":   "Sugar Tax Panel — Credential Misrepresentation and Duty of Care",
        "date":    "2026-04-22",
        "url":     "incidents/2026-04/incident_Ishii_Panel.html",
        "summary": "Ishii was appointed to the Sugar Tax Panel despite lacking required "
                   "credentials, then cited the appointment in her mayoral campaign. The "
                   "panel's performance verification record during her tenure is unconfirmed.",
        "members": ["Ishii"],
        "scores":  {"Ishii": -11},
        "pillars": ["Character & Conduct", "Fiscal Stewardship"],
        "pending": True,
    },
    {
        "title":   "Rocky Road Streets Audit — Findings Received, Lessons Ignored",
        "date":    "2025-10-28",
        "url":     "incidents/2025-10/incident_Rocky_Road_Bond.html",
        "summary": "Council filed the City Auditor's Rocky Road streets audit (PCI 57; $42M/year "
                   "gap; bond dependence as root cause), then five months later unanimously "
                   "directed a fifth bond cycle — the exact pattern the audit had documented "
                   "as the cause of failure. Taplin authored the bond schedule concurrent with "
                   "the audit filing; Tregub called the bond 'essential' with no mention of "
                   "the audit's structural findings.",
        "members": ["Full Council", "Taplin", "Tregub"],
        "scores":  {"Full Council": -5, "Taplin": -10, "Tregub": -9},
        "pillars": ["Fiscal Stewardship"],
        "pending": False,
    },
    {
        "title":   "Howard Johnson Motel — Community Meeting Three Weeks After Council Vote",
        "date":    "2024-12-11",
        "url":     "incidents/2024-12/incident_Tregub_Hotel.html",
        "summary": "Tregub held a community meeting on the Howard Johnson interim housing "
                   "project three weeks after the council had already voted to approve the "
                   "operating contract — framing a notification meeting as a community "
                   "conversation after the outcome was already determined.",
        "members": ["Tregub"],
        "scores":  {"Tregub": -8},
        "pillars": ["Character & Conduct"],
        "pending": False,
    },
    {
        "title":   "Council Office Staffing Doubled on Consent Calendar During Structural Deficit",
        "date":    "2023-11-16",
        "url":     "incidents/2023-11/incident_Taplin_Staffing.html",
        "summary": "Taplin authored and Bartlett co-authored a consent calendar item doubling "
                   "authorized council office staffing (1→2 FTEs per office; ~$442K/year "
                   "recurring) during an acknowledged structural deficit — no floor debate, "
                   "no alternatives analysis, justified by citing informal over-staffing that "
                   "already existed.",
        "members": ["Taplin", "Bartlett"],
        "scores":  {"Taplin": -8, "Bartlett": -4},
        "pillars": ["Fiscal Stewardship"],
        "pending": False,
    },
]

def _member_incidents(name: str) -> list[dict]:
    """Return incidents implicating a member, including Full Council incidents."""
    return [i for i in ALL_EDITORIAL_INCIDENTS
            if name in i["members"] or "Full Council" in i["members"]]

def _has_named_incidents(name: str) -> bool:
    """True if the member is specifically named (not just via Full Council) in any incident."""
    return any(name in i["members"] for i in ALL_EDITORIAL_INCIDENTS)


_INC_CSS = """
<style>
  .inc-record-section {
    margin: 0 24px 16px;
    border: 1px solid #e8ecef;
    border-radius: 6px;
    overflow: hidden;
    font-size: 12px;
  }
  .inc-record-header {
    background: #f0f2f5;
    padding: 7px 12px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .8px;
    color: #7f8c8d;
    border-bottom: 1px solid #e0e4e8;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .inc-record-all {
    font-size: 10px;
    font-weight: 600;
    color: #2980b9;
    text-decoration: none;
    text-transform: none;
    letter-spacing: 0;
  }
  .inc-record-all:hover { text-decoration: underline; }
  .inc-none {
    padding: 10px 14px;
    color: #aaa;
    font-size: 11.5px;
    font-style: italic;
  }
  .inc-pages { padding: 4px 0; }
  .inc-page-row {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 7px 14px;
    border-bottom: 1px solid #f0f2f5;
  }
  .inc-page-row:last-child { border-bottom: none; }
  .inc-alert { color: #e74c3c; font-size: 13px; flex-shrink: 0; }
  .inc-page-link {
    color: #2c3e50;
    text-decoration: none;
    font-size: 12px;
    line-height: 1.4;
    flex: 1;
  }
  .inc-page-link:hover { color: #2980b9; text-decoration: underline; }
  .inc-score-chip {
    font-size: 13px;
    font-weight: 900;
    color: #e74c3c;
    white-space: nowrap;
  }
  .inc-pillars { font-size: 9px; color: #7f8c8d; margin-top: 2px; }

  /* Recent incidents section (card top, replacing Rankings) */
  .recent-inc-section {
    margin: 0;
    border-bottom: 1px solid #ecf0f1;
  }
  .recent-inc-header {
    background: #fdf5f5;
    padding: 8px 24px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .8px;
    color: #c0392b;
    border-bottom: 1px solid #fde8e8;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .recent-inc-header a {
    font-size: 10px;
    font-weight: 600;
    color: #c0392b;
    text-decoration: none;
    text-transform: none;
    letter-spacing: 0;
  }
  .recent-inc-header a:hover { text-decoration: underline; }
  .recent-inc-none {
    padding: 10px 24px;
    color: #aaa;
    font-size: 12px;
    font-style: italic;
  }
  .recent-inc-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 24px;
    border-bottom: 1px solid #fde8e8;
    text-decoration: none;
    color: inherit;
  }
  .recent-inc-row:last-child { border-bottom: none; }
  .recent-inc-row:hover { background: #fdf5f5; }
  .rir-score {
    font-size: 20px;
    font-weight: 900;
    color: #e74c3c;
    min-width: 36px;
    text-align: right;
  }
  .rir-body { flex: 1; }
  .rir-title { font-size: 12px; font-weight: 700; color: #1a1a2e; line-height: 1.3; }
  .rir-pillars { font-size: 10px; color: #7f8c8d; margin-top: 2px; }
  .rir-arrow { font-size: 11px; color: #aaa; }
</style>"""


def _render_recent_incidents(name: str) -> str:
    """
    Recent Incidents section for top of scorecard, replacing Rankings.
    Shows up to 3 most recent incidents implicating the member.
    Always rendered — shows 'No incidents on record' if clean.
    Injected via RECENT_INCIDENTS_PLACEHOLDER sentinel.
    """
    incidents = _member_incidents(name)
    # Sort newest-first, take up to 3
    incidents = sorted(incidents, key=lambda i: i["date"], reverse=True)[:3]
    log_url = f"incidents/index.html#{name.lower()}"

    if not incidents:
        body = f'<div class="recent-inc-none">No incidents on record.</div>'
    else:
        rows = ""
        for inc in incidents:
            score = inc["scores"].get(name) or inc["scores"].get("Full Council", 0)
            score_str = f"{score:+d}" if score else "—"
            pillars = " · ".join(sorted(inc["pillars"]))
            rows += f"""
    <a class="recent-inc-row" href="{inc['url']}">
      <div class="rir-score">{score_str}</div>
      <div class="rir-body">
        <div class="rir-title">{inc['title']}</div>
        <div class="rir-pillars">{pillars}</div>
      </div>
      <div class="rir-arrow">→</div>
    </a>"""
        body = rows

    return f"""
  <div class="recent-inc-section">
    <div class="recent-inc-header">
      Incident Record
      <a href="{log_url}">Full incident log →</a>
    </div>
    {body}
  </div>
{_INC_CSS}"""


def _render_incident_record(name: str) -> str:
    """
    Incident Record section for bottom of scorecard card.
    Shows all incidents implicating the member with links.
    Always rendered. Injected via INCIDENTS_PLACEHOLDER sentinel.
    """
    incidents = _member_incidents(name)

    if incidents:
        rows = ""
        for inc in incidents:
            score = inc["scores"].get(name) or inc["scores"].get("Full Council", 0)
            score_str = f"{score:+d}" if score else "—"
            pillars = " · ".join(sorted(inc["pillars"]))
            rows += f"""
      <div class="inc-page-row">
        <span class="inc-alert">&#9888;</span>
        <a href="{inc['url']}" class="inc-page-link">
          {inc['title']}
          <div class="inc-pillars">{pillars}</div>
        </a>
        <span class="inc-score-chip">{score_str}</span>
      </div>"""
        body = f'<div class="inc-pages">{rows}\n    </div>'
    else:
        body = '<div class="inc-none">No incidents on record.</div>'

    log_url = f"incidents/index.html#{name.lower()}"
    return f"""
  <div class="inc-record-section">
    <div class="inc-record-header">
      Full Incident Record
      <a href="{log_url}" class="inc-record-all">Incident log →</a>
    </div>
    {body}
  </div>"""


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


_NAV_CSS = """<style>
body { flex-direction: column !important; align-items: center !important; }
.site-nav {
  width: 760px; max-width: 100%;
  background: #1a1a2e;
  padding: 9px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-radius: 8px 8px 0 0;
  margin-top: 20px;
}
.site-nav-home {
  font-size: 11px; font-weight: 700;
  color: #8899bb; text-decoration: none; letter-spacing: .3px;
}
.site-nav-home:hover { color: #fff; }
.site-nav-label {
  font-size: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 1.4px; color: #555e7a;
}
</style>"""

_NAV_HTML = (
    '<div class="site-nav">'
    '<a href="index.html" class="site-nav-home">&#8592; Scorecards</a>'
    '<span class="site-nav-label">Berkeley City Council</span>'
    '</div>\n'
)

def _add_index_link(html: str) -> str:
    """Inject nav bar above the card and fix body to column flex."""
    html = html.replace('</head>', _NAV_CSS + '\n</head>', 1)
    return html.replace('<body>\n', f'<body>\n{_NAV_HTML}', 1)


_TOOLTIP_CSS = """
<style>
/* Evidentiary basis tooltip enhancement (HTML only) */
.evid-basis {
  cursor: help;
  position: relative;
}
.evid-basis:hover::after {
  content: attr(data-tip);
  position: absolute;
  left: 0; top: 120%;
  background: #2c3e50; color: #fff;
  font-size: 10px; font-weight: 400; text-transform: none;
  letter-spacing: 0; line-height: 1.5;
  white-space: normal; width: 240px;
  padding: 6px 10px; border-radius: 4px;
  z-index: 999; pointer-events: none;
  box-shadow: 0 2px 8px rgba(0,0,0,.3);
}
</style>"""

_OFFICIAL_TIP  = ("Drawn from annotated agenda PDFs and official city records. "
                  "Not subject to interpretation — these are the facts as recorded.")
_TEXT_TIP      = ("Derived from keyword classification of attributed meeting transcripts, "
                  "constituent communications, and member public statements. "
                  "Full methodology at METHODOLOGY.md.")
_MIXED_TIP     = ("Combines official record data (votes, authorship) with text analysis "
                  "(rhetoric signals). See METHODOLOGY.md for component weights.")


def _add_tooltip_attrs(html: str) -> str:
    """Inject data-tip attributes on evid-basis badges for hover tooltips."""
    html = html.replace(
        'class="evid-basis evid-official"',
        f'class="evid-basis evid-official" data-tip="{_OFFICIAL_TIP}"',
    )
    html = html.replace(
        'class="evid-basis evid-text"',
        f'class="evid-basis evid-text" data-tip="{_TEXT_TIP}"',
    )
    html = html.replace(
        'class="evid-basis evid-text">Text analysis + official record',
        f'class="evid-basis evid-text" data-tip="{_MIXED_TIP}">Text analysis + official record',
    )
    # Inject tooltip CSS before </head>
    html = html.replace('</head>', _TOOLTIP_CSS + '\n</head>', 1)
    return html


def screen_html(html: str, add_back_link: bool = False) -> str:
    html = _strip_print_css(html)
    html = _add_viewport(html)
    html = _add_tooltip_attrs(html)
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
        has_incidents = _has_named_incidents(m['name'])
        alert = (f'<a href="incidents/index.html#{m["name"].lower()}" class="inc-badge" '
                 f'title="Active incident record — click for details">'
                 f'&#9888;&nbsp;Incident record</a> '
                 if has_incidents else "")
        rows += f"""
      <tr>
        <td class="name">
          {alert}<a href="{filename}">{m['display_name']}</a><br>
          <span class="sub">{m['district']}</span>
        </td>
        <td class="grade {m['grade_cls']}">{m['grade_str']}</td>
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
    .name  {{ font-size: 14px; font-weight: 600; }}
    .name a {{ color: #2c3e50; text-decoration: none; }}
    .name a:hover {{ color: #3498db; }}
    .sub   {{ font-size: 11px; color: #999; font-weight: 400; }}
    .grade {{ width: 52px; font-size: 22px; font-weight: 900; text-align: center; }}
    .inc-badge {{ display: inline-block; background: #e74c3c; color: #fff;
                  font-size: 9px; font-weight: 700; text-decoration: none;
                  padding: 2px 7px; border-radius: 10px; margin-bottom: 3px;
                  letter-spacing: .3px; }}
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
      {n_meetings} meetings analyzed &nbsp;·&nbsp; &#9888; = active incident record<br>
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
        <th>Member</th>
        <th>Grade</th>
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
        html = html.replace("<!-- RECENT_INCIDENTS_PLACEHOLDER -->",
                            _render_recent_incidents(name), 1)
        html = html.replace("<!-- INCIDENTS_PLACEHOLDER -->",
                            _render_incident_record(name), 1)
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
    mayor_html = mayor_html.replace("<!-- RECENT_INCIDENTS_PLACEHOLDER -->",
                                    _render_recent_incidents("Ishii"), 1)
    mayor_html = mayor_html.replace("<!-- INCIDENTS_PLACEHOLDER -->",
                                    _render_incident_record("Ishii"), 1)
    mayor_html = screen_html(mayor_html, add_back_link=True)
    mayor_out  = os.path.join(PUBLISH_DIR, "scorecard_Ishii.html")
    with open(mayor_out, "w", encoding="utf-8") as f:
        f.write(mayor_html)
    print(f"  → {mayor_out}", file=sys.stderr)

    # Summary page
    summary_html = sc.render_summary(aggregate, rankings, council_meta, meta)
    summary_html = screen_html(summary_html, add_back_link=True)
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
