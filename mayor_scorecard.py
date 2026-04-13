#!/usr/bin/env python3
"""
mayor_scorecard.py

Renders the Ishii mayoral accountability scorecard as HTML.
Uses the same SHARED_CSS as scorecard_pdf.py for visual consistency,
but with a distinct 4-dimension structure reflecting the mayor's
unique powers and responsibilities.

Called from generate_html.py; writes publish/scorecard_Ishii.html.
"""

import json
import os

# ---------------------------------------------------------------------------
# Mayor-specific data (from research across 51 meeting transcripts,
# 53 agenda items, newsletter analysis, and PAB institutional record)
# ---------------------------------------------------------------------------

# Agenda curation breakdown — 53 Ishii-authored or cosponsored items
AGENDA_CATEGORIES = [
    ("Budget relinquishments",       19, "36%",
     "Items where the mayor's discretion was ceded to City Manager or staff — "
     "budget acceptances, AAO amendments, appropriations she did not author."),
    ("Sanctuary / immigration",       5, "9%",
     "State-preempted and federal policy items: sanctuary resolutions, immigration "
     "communications, non-cooperation declarations. Zero operational effect on Berkeley budgets."),
    ("Procedural / organizational",   5, "9%",
     "Seating, appointments, committee assignments. Required administrative items."),
    ("Ceremonial / recognition",      4, "8%",
     "Proclamations, cultural month recognitions. Staff-drafted, no policy content."),
    ("Equity / targeted programs",    4, "8%",
     "Demographic-specific program creation or expansion with no alternatives analysis."),
    ("Charter / governance reform",   3, "6%",
     "Committee restructuring, vice-mayor term. Process items, not fiscal items."),
    ("Other / miscellaneous",        13, "24%",
     "Remaining items spanning housing, transit, public health, and resolutions."),
]

# P1 items in the same period — all from City Manager, none from Mayor
P1_ITEMS_REVIEWED = 7   # street paving, reserve policy, infrastructure bonds
P1_AUTHORED_BY_MAYOR = 0

# Meeting extension data (from transcript analysis, 51 meetings)
EXTENSION_MEETINGS = 19          # meetings requiring at least one extension vote
TOTAL_MEETINGS = 51
EXTENSIONS_PAST_11PM = 5
EXTENSIONS_PAST_MIDNIGHT = 2
EXTENSIONS_NOTE = (
    "April 28, 2025 (Gaza ceasefire resolution): 3 extensions required, meeting ended 11:51 PM — "
    "the most contentious non-budget night of the period. June 24, 2025 (budget adoption) "
    "and July 22, 2025 ran past midnight."
)

# Dimension scores (0.0–1.0)
D_AGENDA_CURATION    = 0.15   # F+ — zero P1 authored, heavy non-core, budget relinquishments
D_COMMUNICATIONS     = 0.22   # D  — Instagram style, no fiscal substance, ego markers
D_MEETING_MGMT       = 0.35   # D+ — shows up, but 37% of meetings extended, 2 past midnight
D_ACCOUNTABILITY_GAP = 0.10   # F  — PAB collapse on her watch, Aguilar gaslighting

# Weights
W_AGENDA       = 0.35
W_COMMS        = 0.25
W_MEETING      = 0.25
W_ACCOUNTABILITY = 0.15

MAYORAL_SCORE = (
    D_AGENDA_CURATION    * W_AGENDA
    + D_COMMUNICATIONS   * W_COMMS
    + D_MEETING_MGMT     * W_MEETING
    + D_ACCOUNTABILITY_GAP * W_ACCOUNTABILITY
)

# Fiscal vote data pulled from aggregate.json at last pipeline run
FISCAL_VOTES = {
    "total":      7,
    "yes":        7,
    "no":         0,
    "absent":     0,
    "dollars_yes": 3_290_337_518,
}

SESSIONS = {
    "total":         58,
    "fully_absent":   0,
    "late":           0,
    "attendance_rate": 1.0,
    "punctuality_rate": 1.0,
}


# ---------------------------------------------------------------------------
# Helpers (mirrors scorecard_pdf.py)
# ---------------------------------------------------------------------------

def _letter(score) -> tuple[str, str]:
    if score is None:        return "N/A", "grade-nc"
    if score >= 0.90:        return "A+",  "grade-a"
    if score >= 0.83:        return "A",   "grade-a"
    if score >= 0.77:        return "A\u2212", "grade-a"
    if score >= 0.70:        return "B+",  "grade-b"
    if score >= 0.63:        return "B",   "grade-b"
    if score >= 0.57:        return "B\u2212", "grade-b"
    if score >= 0.50:        return "C+",  "grade-c"
    if score >= 0.43:        return "C",   "grade-c"
    if score >= 0.37:        return "C\u2212", "grade-c"
    if score >= 0.30:        return "D+",  "grade-d"
    if score >= 0.23:        return "D",   "grade-d"
    if score >= 0.17:        return "D\u2212", "grade-d"
    return "F",  "grade-f"


def _pct_bar(value: float, width: int = 260) -> str:
    filled = max(0, min(1, value or 0))
    w_fill = int(filled * width)
    color = (
        "#2ecc71" if filled >= 0.70 else
        "#3498db" if filled >= 0.50 else
        "#e67e22" if filled >= 0.30 else
        "#e74c3c"
    )
    return (
        f'<svg width="{width}" height="18" style="vertical-align:middle">'
        f'<rect width="{width}" height="18" rx="4" fill="#ecf0f1"/>'
        f'<rect width="{w_fill}" height="18" rx="4" fill="{color}"/>'
        f'</svg>'
    )


def _fmt_m(v: int) -> str:
    if v >= 1_000_000_000: return f"${v/1_000_000_000:.2f}B"
    if v >= 1_000_000:     return f"${v/1_000_000:.1f}M"
    if v >= 1_000:         return f"${v/1_000:.0f}K"
    return f"${v:,}"


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_role_box(meta: dict) -> str:
    earliest = meta.get("earliest_meeting", "Dec 2024")
    latest   = meta.get("latest_meeting", "Mar 2026")
    n        = meta.get("transcripts", 51)
    return f"""
  <div class="section" style="background:#f8f9fa">
    <div class="section-title">The Office: Powers, Constraints, and What Accountability Requires</div>
    <div style="font-size:12.5px;line-height:1.7;color:#2c3e50;margin-bottom:12px">
      The Mayor of Berkeley holds powers unavailable to district council members:
      <strong>chairs all regular and special council sessions</strong>, helps shape and
      prioritize the meeting agenda through the Agenda Committee, makes key appointments
      to boards and commissions, and serves as the city&rsquo;s principal public voice
      through official communications and proclamations. Within the council&ndash;manager
      system defined by the Berkeley City Charter, these authorities do not include
      control of city operations or unilateral control of the agenda.
    </div>
    <div style="font-size:12.5px;line-height:1.7;color:#2c3e50;margin-bottom:12px">
      <strong>The mayor&rsquo;s effective power depends on coalition-building.</strong>
      With a reliable majority, agenda influence becomes actionable: items are scheduled
      promptly, framed in alignment with council priorities, and brought to a vote with
      predictable outcomes. Without that majority, the same tools are limited to
      sequencing and emphasis &mdash; able to delay or highlight issues, but not to
      decide them. In this structure, the mayor is not a gatekeeper but a
      <em>coordinator of votes</em>.
    </div>
    <div style="font-size:12.5px;line-height:1.7;color:#2c3e50;margin-bottom:12px">
      Because the structural deficit and infrastructure backlog are the city&rsquo;s
      documented fiscal constraints, a mayor who builds and maintains a coalition
      to force those tradeoffs onto the agenda and through to decisions is exercising
      the core function of the office. A mayor who does not assemble that majority,
      and instead fills the calendar with symbolic or ceremonial items while leaving
      fiscal choices to the default budget process, is not using the office&rsquo;s
      primary lever.
    </div>
    <div style="font-size:12px;line-height:1.65;color:#555;background:#fff;border-left:3px solid #7f8c8d;padding:10px 14px">
      This scorecard therefore asks two questions. First: did Ishii use her platform
      and agenda access to assemble a working majority around Berkeley&rsquo;s
      documented fiscal problems? Second: does the record of what she scheduled,
      communicated, and decided reflect that priority &mdash; or something else?
      Ishii&rsquo;s 91.7% block-vote rate is the highest on the council, confirming
      she votes with the majority consistently. But voting <em>with</em> a majority
      and <em>building</em> one around specific fiscal goals are different things.
      A coalition formed around low-friction consensus items is not evidence of
      governing effectiveness; it is evidence of conflict avoidance. The 58-session
      record evaluated here ({earliest}&ndash;{latest}) is the evidence.
    </div>
  </div>"""


def _render_dimensions() -> str:
    dims = [
        ("Agenda Leadership",  D_AGENDA_CURATION,    W_AGENDA,        "35%"),
        ("Communications",     D_COMMUNICATIONS,     W_COMMS,         "25%"),
        ("Meeting Management", D_MEETING_MGMT,       W_MEETING,       "25%"),
        ("Accountability Gap", D_ACCOUNTABILITY_GAP, W_ACCOUNTABILITY,"15%"),
    ]
    rows = ""
    for label, score, _w, wt in dims:
        g, cls = _letter(score)
        rows += f"""
        <div class="pillar-row">
          <div class="pillar-label">{label} <span style="font-size:10px;color:#aaa">({wt})</span></div>
          <div class="pillar-grade {cls}">{g}</div>
          <div class="pillar-bar">{_pct_bar(score)}</div>
          <div class="pillar-pct">{score*100:.0f}%</div>
        </div>"""
    return f"""
  <div class="section">
    <div class="section-title">Mayoral Accountability — Four Dimensions</div>
    {rows}
  </div>"""


def _render_agenda_section() -> str:
    # Category table
    cat_rows = ""
    for cat, n, pct, note in AGENDA_CATEGORIES:
        cat_rows += (
            f"<tr>"
            f"<td style='font-size:12px;font-weight:600;color:#2c3e50;padding:5px 8px 5px 0'>{cat}</td>"
            f"<td style='font-size:12px;text-align:center;padding:5px 8px'>{n}</td>"
            f"<td style='font-size:12px;text-align:center;padding:5px 8px'>{pct}</td>"
            f"<td style='font-size:11px;color:#7f8c8d;padding:5px 0 5px 8px'>{note}</td>"
            f"</tr>"
        )

    p1_color = "#e74c3c" if P1_AUTHORED_BY_MAYOR == 0 else "#27ae60"

    return f"""
  <div class="section">
    <div class="section-title">1 · Agenda Leadership &amp; Coalition Effectiveness &nbsp;<span style="font-size:10px;color:#aaa;font-weight:400">(35% of Mayoral Accountability score)</span></div>
    <div style="font-size:12.5px;line-height:1.6;color:#2c3e50;margin-bottom:14px">
      The core test for a Berkeley mayor is whether she used her coalition-building
      authority to force the city&rsquo;s documented fiscal tradeoffs onto the agenda
      and through to decisions. Of 53 items Ishii authored or cosponsored across the
      analysis period,
      <strong style="color:{p1_color}">{P1_AUTHORED_BY_MAYOR} address a documented P1 fiscal or infrastructure problem</strong>.
      All {P1_ITEMS_REVIEWED} P1-class items on Berkeley&rsquo;s agendas during this period
      were brought by the City Manager or staff &mdash; the default budget process the
      mayor&rsquo;s coalition authority exists to supplement and direct. Whether that
      reflects a judgment that the coalition wasn&rsquo;t available, or a preference
      not to make those fights, the effect is the same: the office&rsquo;s primary lever
      was not applied to its highest-priority purpose.
    </div>
    <div style="margin-bottom:16px">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#7f8c8d;margin-bottom:8px">Item Category Breakdown — 53 Authored Items</div>
      <table style="width:100%;border-collapse:collapse">
        <thead>
          <tr style="background:#f0f2f5">
            <th style="text-align:left;font-size:9.5px;color:#7f8c8d;font-weight:600;padding:4px 8px 4px 0;text-transform:uppercase;letter-spacing:.5px">Category</th>
            <th style="text-align:center;font-size:9.5px;color:#7f8c8d;font-weight:600;padding:4px 8px;text-transform:uppercase;letter-spacing:.5px">Items</th>
            <th style="text-align:center;font-size:9.5px;color:#7f8c8d;font-weight:600;padding:4px 8px;text-transform:uppercase;letter-spacing:.5px">Share</th>
            <th style="text-align:left;font-size:9.5px;color:#7f8c8d;font-weight:600;padding:4px 0 4px 8px;text-transform:uppercase;letter-spacing:.5px">Significance</th>
          </tr>
        </thead>
        <tbody>{cat_rows}</tbody>
      </table>
    </div>
    <div style="background:#fdf5f5;border-left:3px solid #e74c3c;padding:10px 14px;font-size:11.5px;line-height:1.6;color:#555">
      <strong>Vote intelligence signal:</strong> On January 21, 2025, Ishii authored the seating
      arrangement and vice mayor term revision item, which passed 4&ndash;3 — she cast a NO
      vote on her own item, suggesting the final version was amended away from her preference.
      A mayor who brings items to a vote without securing support is not reading her own council.
    </div>
  </div>"""


def _render_communications_section() -> str:
    return f"""
  <div class="section">
    <div class="section-title">2 · Communications Platform &nbsp;<span style="font-size:10px;color:#aaa;font-weight:400">(25% of Mayoral Accountability score)</span></div>
    <div style="font-size:12.5px;line-height:1.6;color:#2c3e50;margin-bottom:14px">
      A mayor&rsquo;s constituent communications are a policy document: they tell residents
      what the mayor thinks is important, what she takes credit for, and what she chooses
      not to discuss. Analysis of Ishii&rsquo;s newsletters across the analysis period
      reveals a pattern of <strong>celebrity branding over civic accountability</strong>.
    </div>
    <div style="margin-bottom:12px">
      <div style="font-size:11px;font-weight:700;color:#c0392b;margin-bottom:6px">EGO SIGNALS — FOUND</div>
      <div class="stat-grid">
        <div class="stat-box">
          <div style="font-size:13px;font-weight:700;color:#2c3e50">&ldquo;Team Ishii&rdquo;</div>
          <div class="stat-lbl">Personal branding applied to city staff. City employees are public servants, not team members of an elected official.</div>
        </div>
        <div class="stat-box">
          <div style="font-size:13px;font-weight:700;color:#2c3e50">Food &amp; social calendar</div>
          <div class="stat-lbl">Newsletter real estate dedicated to personal food preferences, cultural events attended, and social appearances — not city business.</div>
        </div>
        <div class="stat-box">
          <div style="font-size:13px;font-weight:700;color:#2c3e50">Intern bios</div>
          <div class="stat-lbl">Substantial newsletter content describing intern backgrounds. Civic communications function as staff social media.</div>
        </div>
        <div class="stat-box">
          <div style="font-size:13px;font-weight:700;color:#2c3e50">Inspirational copy</div>
          <div class="stat-lbl">Motivational poster language in place of fiscal content. Tonal mismatch with the severity of the city&rsquo;s documented problems.</div>
        </div>
      </div>
    </div>
    <div style="margin-bottom:12px">
      <div style="font-size:11px;font-weight:700;color:#c0392b;margin-bottom:6px">FISCAL SILENCE — DOCUMENTED</div>
      <div style="font-size:12px;line-height:1.6;color:#2c3e50">
        Newsletters actively promoted the African American Holistic Resource Center
        groundbreaking as a community achievement with <strong>zero mention of cost</strong>
        ($15.1M capital, $1.5&ndash;2M/year ongoing) or its relationship to the structural
        deficit. No newsletter across the analysis period contains structural deficit analysis,
        CalPERS/OPEB discussion, or P1 infrastructure content. The fiscal crisis that
        Berkeley&rsquo;s own City Manager called &ldquo;not sustainable&rdquo; does not appear
        in the Mayor&rsquo;s constituent communications.
      </div>
    </div>
    <div style="background:#fdf5f5;border-left:3px solid #e74c3c;padding:10px 14px;font-size:11.5px;line-height:1.6;color:#555">
      Contrast with District 4 newsletters (Tregub), which at minimum name the fiscal crisis
      in the opening paragraph before pivoting to glue traps. Ishii&rsquo;s newsletters do not
      acknowledge the crisis at all — they function as constituent social media, not governance communication.
    </div>
  </div>"""


def _render_meeting_section() -> str:
    ext_rate_pct = int(EXTENSION_MEETINGS / TOTAL_MEETINGS * 100)
    return f"""
  <div class="section">
    <div class="section-title">3 · Meeting Management &nbsp;<span style="font-size:10px;color:#aaa;font-weight:400">(25% of Mayoral Accountability score)</span></div>
    <div style="font-size:12.5px;line-height:1.6;color:#2c3e50;margin-bottom:14px">
      The mayor chairs council meetings and sets the pace. When meetings require
      extension votes — formal motions to continue past the scheduled end time — it
      is a ground-truth signal that the agenda exceeded what a governing body can
      reasonably process. Decisions made at midnight, under sustained public pressure,
      after hours of contentious comment, are not the same decisions that would be made
      with adequate deliberation. Extended meetings also close democratic participation:
      ordinary residents with jobs and families cannot wait until 1&nbsp;AM to speak.
    </div>
    <div class="stat-grid" style="margin-bottom:14px">
      <div class="stat-box">
        <div class="stat-val" style="color:#e67e22">{EXTENSION_MEETINGS}/{TOTAL_MEETINGS}</div>
        <div class="stat-lbl">Meetings requiring<br><b>at least one extension</b> ({ext_rate_pct}%)</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:#e74c3c">{EXTENSIONS_PAST_11PM}</div>
        <div class="stat-lbl">Meetings running<br><b>past 11&nbsp;PM</b></div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:#e74c3c">{EXTENSIONS_PAST_MIDNIGHT}</div>
        <div class="stat-lbl">Meetings running<br><b>past midnight</b></div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:#27ae60">{SESSIONS['attendance_rate']*100:.0f}%</div>
        <div class="stat-lbl">Mayor&rsquo;s personal<br>attendance rate (100%)</div>
      </div>
    </div>
    <div style="background:#fdf9f0;border-left:3px solid #e67e22;padding:10px 14px;font-size:11.5px;line-height:1.6;color:#555">
      <strong>Case study — April 28, 2025:</strong> {EXTENSIONS_NOTE}
      The Gaza ceasefire item required three extension votes and kept the chamber
      open past midnight for sustained public comment from organized advocacy groups.
      Items with this level of organized public pressure are foreseeable; a mayor
      who reads the room can sequence the agenda to limit decision fatigue on
      unrelated items or set tighter comment limits. Public comment was not limited.
    </div>
  </div>"""


def _render_accountability_section() -> str:
    return f"""
  <div class="section">
    <div class="section-title">4 · Accountability Gap &nbsp;<span style="font-size:10px;color:#aaa;font-weight:400">(15% of Mayoral Accountability score)</span></div>
    <div style="font-size:12.5px;line-height:1.6;color:#2c3e50;margin-bottom:14px">
      Ishii ran for mayor in a cycle when Measure II — creating the Police Accountability
      Board (PAB) and Office of the Director of Police Accountability (ODPA) — passed with
      <strong>85% of the vote</strong>. Under her mayoralty, the institution voters mandated
      did not survive in functional form.
    </div>
    <div style="margin-bottom:12px">
      <div style="font-size:11px;font-weight:700;color:#c0392b;margin-bottom:8px">TIMELINE OF INSTITUTIONAL COLLAPSE</div>
      <div style="font-size:12px;line-height:1.8;color:#2c3e50">
        <div style="margin-bottom:4px">
          <span style="color:#7f8c8d;font-size:10px;min-width:70px;display:inline-block">2020–2026</span>
          All original PAB commissioners departed. Board dropped to 4 of 9 seats.
        </div>
        <div style="margin-bottom:4px">
          <span style="color:#7f8c8d;font-size:10px;min-width:70px;display:inline-block">Jan 30, 2026</span>
          Last two original commissioners resigned, writing the PAB was
          &ldquo;even less empowered than its predecessor&rdquo; — the one the DOJ had cited as a national model.
        </div>
        <div style="margin-bottom:4px">
          <span style="color:#7f8c8d;font-size:10px;min-width:70px;display:inline-block">Dec 2025</span>
          ODPA Director Aguilar sued Police Chief Jen Louis to compel records release.
          BPD had refused records requests, requiring multiple subpoenas.
        </div>
        <div style="margin-bottom:4px">
          <span style="color:#7f8c8d;font-size:10px;min-width:70px;display:inline-block">Sep 2025</span>
          Aguilar placed items on council agenda using his charter authority — the authority
          voters designed him to have. Council members publicly criticized him for using it.
        </div>
        <div style="margin-bottom:4px">
          <span style="color:#7f8c8d;font-size:10px;min-width:70px;display:inline-block">Feb 9, 2026</span>
          Council voted <strong>8&ndash;0</strong> (Kesarwani absent) to fire Aguilar under
          &ldquo;without cause&rdquo; contract terms, triggering mandatory severance.
        </div>
      </div>
    </div>
    <div style="background:#fdf5f5;border-left:3px solid #e74c3c;padding:10px 14px;margin-bottom:12px;font-size:11.5px;line-height:1.6;color:#555">
      <strong>Post-vote statement — Ishii:</strong> &ldquo;The council remained committed to police
      accountability and was focused on filling the PAB vacancies, finding a new director and
      restoring credibility, trust and respect for both the accountability process and the
      people involved in this work.&rdquo; — issued immediately after the unanimous vote to
      eliminate the accountability office&rsquo;s leadership. A recommitment-to-accountability
      statement issued in the moment the accountability office&rsquo;s director was fired is
      the definitional form of performative governance.
      <em>(Source: Berkeleyside, Alex N. Gecan, Feb. 9, 2026)</em>
    </div>
  </div>"""


def _render_fiscal_section() -> str:
    fv = FISCAL_VOTES
    dollars_str = _fmt_m(fv["dollars_yes"])
    return f"""
  <div class="section">
    <div class="section-title">Fiscal Votes &amp; Attendance (Reference)</div>
    <div style="font-size:10px;color:#7f8c8d;margin-bottom:10px;font-style:italic">
      These metrics are comparable to district council members — included for reference
      but not the primary basis of the Mayoral Accountability score.
    </div>
    <div class="stat-grid" style="margin-bottom:10px">
      <div class="stat-box">
        <div class="stat-val" style="color:#27ae60">{SESSIONS['total']}/{SESSIONS['total']}</div>
        <div class="stat-lbl">Sessions attended<br>(100% — zero absences)</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:#27ae60">100%</div>
        <div class="stat-lbl">On-time rate<br>(zero late arrivals)</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:#e67e22">{fv['yes']}/{fv['total']}</div>
        <div class="stat-lbl">Major fiscal votes:<br>voted YES (status quo)</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:#e67e22">{dollars_str}</div>
        <div class="stat-lbl">Endorsed in tracked<br>fiscal authorizations</div>
      </div>
    </div>
    <div style="font-size:11px;color:#7f8c8d;font-style:italic;line-height:1.5">
      Ishii voted YES on all 7 tracked major fiscal items, including the FY2025&ndash;2026
      budget adoption — a budget whose cover memo her own City Manager described as
      following a trajectory that is &ldquo;not sustainable.&rdquo; Zero dissenting votes
      across any tracked fiscal item; zero motions to cut, redirect, or reprioritize.
    </div>
  </div>"""


# ---------------------------------------------------------------------------
# Master render function
# ---------------------------------------------------------------------------

def render_mayor_scorecard(meta: dict) -> str:
    """Render the complete Ishii mayoral accountability scorecard as HTML."""
    import scorecard_pdf as sc   # for SHARED_CSS

    g_str, g_cls = _letter(MAYORAL_SCORE)

    earliest = meta.get("earliest_meeting", "Dec 2024")
    latest   = meta.get("latest_meeting", "Mar 2026")
    n        = meta.get("transcripts", 51)
    gen_date = meta.get("generated", "")[:10]

    period = f"{earliest} \u2013 {latest} \u00b7 {n} meetings"

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
{sc.SHARED_CSS}

/* Mayor card accent */
.mayor-badge {{
  display: inline-block;
  background: #c0392b;
  color: #fff;
  font-size: 9px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  padding: 2px 7px;
  border-radius: 3px;
  margin-left: 8px;
  vertical-align: middle;
}}
.mayor-note {{
  font-size: 11px;
  color: #8899bb;
  margin-top: 6px;
  font-style: italic;
  line-height: 1.5;
}}
  </style>
</head>
<body>
<div class="card">

  <div class="header">
    <div class="hdr-left">
      <div class="name">ISHII <span class="mayor-badge">Mayor</span></div>
      <div class="subtitle">
        At-Large &nbsp;&middot;&nbsp; Berkeley City Council<br>
        {period}
      </div>
      <div class="mayor-note">
        This scorecard evaluates the mayor&rsquo;s unique powers separately from
        district council members. The grading dimension is <em>Mayoral Accountability</em>,
        not Voter Alignment.
      </div>
    </div>
    <div class="hdr-right">
      <div class="overall-label">Mayoral Accountability</div>
      <div class="overall-grade {g_cls}">{g_str}</div>
      {"<div style='font-size:10px;color:#8899bb;margin-top:4px'>as of " + latest + "</div>" if latest else ""}
    </div>
  </div>

  {_render_role_box(meta)}

  {_render_dimensions()}

  {_render_agenda_section()}

  {_render_communications_section()}

  {_render_meeting_section()}

  {_render_accountability_section()}

  {_render_fiscal_section()}

  <div class="footer">
    <span>Berkeley City Council Scorecard &nbsp;&middot;&nbsp; Mayor&rsquo;s accountability evaluated separately from district members</span>
    <span>Generated {gen_date}</span>
  </div>

</div>
</body>
</html>"""
