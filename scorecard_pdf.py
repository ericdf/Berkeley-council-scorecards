"""
PDF Scorecard Generator
=======================
Reads scores/aggregate.json and renders one PDF per member
plus a one-page summary comparison.

Requires: weasyprint (pip install weasyprint)
"""

import json
import os
import sys

from weasyprint import HTML, CSS

SCORES_DIR = os.path.join(os.path.dirname(__file__), "scores")
PDF_DIR    = os.path.join(SCORES_DIR, "pdfs")

DISTRICT = {
    "Kesarwani": "District 1",
    "Taplin":    "District 2",
    "Bartlett":  "District 3",
    "LunaParra": "District 5",
    "OKeefe":    "District 6 (fmr.)",
    "Tregub":    "District 7",
    "Blackaby":  "District 8",
    "Humbert":   "At-Large",
    "Ishii":     "Mayor",
}

# ---------------------------------------------------------------------------
# Letter grades
# ---------------------------------------------------------------------------

def letter(score) -> tuple[str, str]:
    """(grade_str, css_color_class)"""
    if score is None:
        return "N/A", "grade-nc"
    if score >= 0.90: return "A+",  "grade-a"
    if score >= 0.83: return "A",   "grade-a"
    if score >= 0.77: return "A\u2212", "grade-a"
    if score >= 0.70: return "B+",  "grade-b"
    if score >= 0.63: return "B",   "grade-b"
    if score >= 0.57: return "B\u2212", "grade-b"
    if score >= 0.50: return "C+",  "grade-c"
    if score >= 0.43: return "C",   "grade-c"
    if score >= 0.37: return "C\u2212", "grade-c"
    if score >= 0.30: return "D+",  "grade-d"
    if score >= 0.23: return "D",   "grade-d"
    if score >= 0.17: return "D\u2212", "grade-d"
    return "F", "grade-f"


def pct_bar(value: float, width: int = 260) -> str:
    """SVG horizontal bar, value 0-1."""
    filled = max(0, min(1, value or 0))
    w_fill = int(filled * width)
    color = "#2ecc71" if filled >= 0.70 else "#3498db" if filled >= 0.50 else "#e67e22" if filled >= 0.30 else "#e74c3c"
    return (
        f'<svg width="{width}" height="18" style="vertical-align:middle">'
        f'<rect width="{width}" height="18" rx="4" fill="#ecf0f1"/>'
        f'<rect width="{w_fill}" height="18" rx="4" fill="{color}"/>'
        f'</svg>'
    )


def focus_trend_arrow(core_trend_val) -> str:
    """Arrow for Focus % trend. Positive core_trend = more on-topic = improving = green ▲."""
    if core_trend_val is None: return ""
    if core_trend_val >  0.02: return '<span style="color:#27ae60">▲</span>'  # more focused — good
    if core_trend_val < -0.02: return '<span style="color:#e74c3c">▼</span>'  # less focused — bad
    return '<span style="color:#95a5a6">▬</span>'


def delta_badge(delta, key: str, threshold: float = 0.02) -> str:
    """
    Return a small colored badge like '▲ +4%' or '▼ −2%'.
    Green = improving, red = worsening.
    Keys where lower is better: waste_pct, recall.
    Returns '' if delta is None or below threshold.
    """
    if delta is None or abs(delta) < threshold:
        return ""
    lower_is_better = key in ("waste_pct", "recall")
    went_up = delta > 0
    improving = went_up != lower_is_better   # XOR: up is bad for lower-is-better keys
    color  = "#27ae60" if improving else "#e74c3c"
    arrow  = "▲" if went_up else "▼"
    sign   = "+" if went_up else "−"
    pct    = abs(delta) * 100
    return (
        f'<span style="font-size:10px;font-weight:700;color:{color};'
        f'margin-left:5px;white-space:nowrap">{arrow}{sign}{pct:.0f}%</span>'
    )


# ---------------------------------------------------------------------------
# CSS shared by all scorecards
# ---------------------------------------------------------------------------

SHARED_CSS = """
@page { size: letter; margin: 0; }
* { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }
body { background: #f0f2f5; display: flex; justify-content: center; }
.card { width: 760px; margin: 20px auto; background: #fff;
        border-radius: 8px; overflow: hidden;
        box-shadow: 0 4px 20px rgba(0,0,0,.15); }

/* Header */
.header { background: #1a1a2e; color: #fff; padding: 28px 32px 20px; display: flex; justify-content: space-between; align-items: flex-start; }
.hdr-left .name { font-size: 30px; font-weight: 800; letter-spacing: .5px; }
.hdr-left .subtitle { font-size: 12px; color: #8899bb; margin-top: 6px; line-height: 1.6; }
.hdr-right { text-align: right; }
.overall-label { font-size: 11px; color: #8899bb; text-transform: uppercase; letter-spacing: 1px; }
.overall-grade { font-size: 62px; font-weight: 900; line-height: 1; margin-top: 2px; }

/* Grade colours */
.grade-a  { color: #2ecc71; }
.grade-b  { color: #3498db; }
.grade-c  { color: #f39c12; }
.grade-d  { color: #e67e22; }
.grade-f  { color: #e74c3c; }
.grade-nc { color: #95a5a6; }

/* Sections */
.section { padding: 20px 32px; border-bottom: 1px solid #ecf0f1; }
.section:last-child { border-bottom: none; }
.section-title { font-size: 11px; font-weight: 700; text-transform: uppercase;
                 letter-spacing: 1.2px; color: #7f8c8d; margin-bottom: 14px; }

/* Executive summary */
.exec-archetype { font-size: 11px; font-weight: 700; text-transform: uppercase;
                  letter-spacing: 1.5px; color: #7f8c8d; margin-bottom: 6px; }
.exec-archetype span { color: #2c3e50; font-size: 14px; font-weight: 800;
                       text-transform: none; letter-spacing: 0; }
.exec-summary { font-size: 12.5px; line-height: 1.65; color: #2c3e50; }

/* Pillar rows */
.pillar-row { display: flex; align-items: center; margin-bottom: 10px; }
.pillar-label { width: 170px; font-size: 13px; font-weight: 600; color: #2c3e50; }
.pillar-grade { width: 36px; font-size: 16px; font-weight: 800; margin-right: 10px; }
.pillar-bar   { flex: 1; }
.pillar-pct   { width: 50px; text-align: right; font-size: 12px; color: #7f8c8d; }

/* Stat grid */
.stat-grid { display: flex; flex-wrap: wrap; gap: 12px; }
.stat-box { background: #f8f9fa; border-radius: 6px; padding: 12px 16px; flex: 1; min-width: 130px; }
.stat-val { font-size: 22px; font-weight: 800; color: #2c3e50; }
.stat-lbl { font-size: 11px; color: #7f8c8d; margin-top: 2px; line-height: 1.4; }

/* Rankings row */
.rank-row { display: flex; gap: 16px; }
.rank-item { background: #f8f9fa; border-radius: 6px; padding: 10px 14px; flex: 1; }
.rank-title { font-size: 10px; color: #7f8c8d; text-transform: uppercase; letter-spacing: 1px; }
.rank-val   { font-size: 18px; font-weight: 800; color: #2c3e50; margin-top: 2px; }

/* Insights */
.insight { display: flex; align-items: flex-start; margin-bottom: 8px; font-size: 13px; line-height: 1.5; color: #444; }
.insight .icon { width: 20px; flex-shrink: 0; font-weight: 700; }
.good  .icon { color: #27ae60; }
.warn  .icon { color: #f39c12; }
.bad   .icon { color: #e74c3c; }

/* Footer */
.footer { background: #f8f9fa; padding: 12px 32px; font-size: 10px; color: #aaa; display: flex; justify-content: space-between; }

/* Taxpayer alignment breakdown table */
.ta-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.ta-table td { padding: 5px 8px; vertical-align: top; }
.ta-table tr.group-header td { font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 1px; color: #7f8c8d; padding-top: 14px; padding-bottom: 4px;
    border-bottom: 1px solid #ecf0f1; }
.ta-table tr.data-row td:first-child { color: #2c3e50; font-weight: 600; width: 200px; }
.ta-table tr.data-row td.note { color: #7f8c8d; font-size: 11px; }
.ta-table tr.data-row td.contrib { text-align: right; font-weight: 700; width: 70px; }
.ta-table tr.data-row td.contrib.pos { color: #27ae60; }
.ta-table tr.data-row td.contrib.neg { color: #e74c3c; }
.ta-table tr.data-row td.contrib.zero { color: #95a5a6; }
.ta-table tr.subtotal td { border-top: 1px solid #ecf0f1; padding-top: 7px; font-weight: 700;
    color: #2c3e50; }
.ta-table tr.subtotal td.contrib { text-align: right; font-weight: 800; }
.ta-table tr.total-row td { border-top: 2px solid #2c3e50; padding-top: 8px; font-weight: 800;
    font-size: 13px; color: #1a1a2e; }
.ta-table tr.total-row td.contrib { text-align: right; }
"""


# ---------------------------------------------------------------------------
# Build key insights for a member
# ---------------------------------------------------------------------------

def build_insights(s: dict, rankings: dict, council_block_rate: float) -> list[tuple[str,str]]:
    """Return list of (type, text) where type is 'good'|'warn'|'bad'."""
    insights = []
    n = s["canonical"]

    # Composite grade rank
    vrank = rankings.get("composite_grade", {}).get(n)
    if vrank == 1:
        insights.append(("good", "Most taxpayer-aligned member on the council"))
    elif vrank and vrank <= 3:
        insights.append(("good", f"#{vrank} in overall rating — among the most taxpayer-aligned members"))

    # Waste
    wp = s.get("waste_pct", 0) or 0
    if wp >= 0.30:
        insights.append(("bad",  f"{wp*100:.0f}% of speech on off-mission topics (foreign policy, police theater, or tax increases)"))
    elif wp <= 0.10:
        insights.append(("good", f"Only {wp*100:.0f}% waste — among the most on-task members"))

    # Fiscal discipline
    fd = s.get("n_fiscal", 0.5) or 0.5
    if fd >= 0.80:
        insights.append(("good", "Consistently probes cost, funding sources, and trade-offs"))
    elif fd <= 0.25:
        insights.append(("bad",  "Rarely asks about cost or fiscal impact — items move without financial scrutiny"))

    # Staff referrals
    refs = s.get("staff_referrals", 0) or 0
    ref_waste = s.get("staff_ref_waste", 0) or 0
    if refs >= 3:
        tag = "bad" if ref_waste > refs//2 else "warn"
        insights.append((tag, f"{refs} staff referrals issued — each consumes 40–80 hours of staff time with no opportunity-cost analysis"))
    elif refs == 0:
        insights.append(("good", "No staff referrals issued — respects staff bandwidth"))

    # Position changes
    pc = s.get("hum_hits", 0) or 0
    if pc >= 3:
        insights.append(("good", f"Evidence of genuine intellectual flexibility — changes positions when presented with new information"))
    elif pc == 0:
        insights.append(("warn", "No detected position changes — votes appear predetermined regardless of debate or public input"))

    # Beer / recall
    brank = rankings.get("beer", {}).get(n)
    rrank = rankings.get("recall", {}).get(n)
    if brank == 1:
        insights.append(("good", "Highest Civic Temperament — genuine warmth, acknowledges colleagues, and demonstrates humility"))
    if rrank == 1:
        insights.append(("bad",  "Lowest Clarity score — ego signals, off-mission speech, staff overreach, and fiscal avoidance compound into the council's worst behavioral profile"))

    # Credential dropping
    cred = s.get("cred_hits", 0) or 0
    if cred >= 1:
        insights.append(("warn", f"Credential-dropping detected ({cred}×) — references personal expertise to close debate rather than open it"))

    # Spending vote record
    yes_voted = s.get("spending_yes_total", 0) or 0
    no_voted  = s.get("spending_no_total",  0) or 0
    sv_n      = s.get("spending_votes_n",   0) or 0
    conc_rate = s.get("fiscal_concern_rate", 0) or 0
    if yes_voted >= 10_000_000 and conc_rate >= 0.5:
        yes_m = yes_voted / 1_000_000
        insights.append(("bad",
            f"Roll-call record: voted YES on ${yes_m:.0f}M in spending items while invoking fiscal-concern language {s.get('fiscal_concern_hits',0)} times"))
    elif no_voted > 0:
        no_m = no_voted / 1_000_000
        insights.append(("good",
            f"Dissented on ${no_m:.1f}M in spending items — one of the few members to break from block spending votes"))
    elif sv_n >= 3 and yes_voted >= 1_000_000:
        yes_m = yes_voted / 1_000_000
        insights.append(("warn",
            f"Voted YES on ${yes_m:.0f}M in spending across {sv_n} tracked roll-calls (all block votes, no dissent)"))

    # Fiscal consistency (rhetoric-based — lower priority than vote record)
    hyp  = s.get("fiscal_hypocrisy_score", 0) or 0
    conc = s.get("fiscal_concern_hits", 0) or 0
    spend = s.get("action_budget_referral_total", 0) or 0
    if hyp >= 0.1 and yes_voted < 10_000_000:   # avoid double-flagging
        detail = s.get("fiscal_hypocrisy_detail", "")
        insights.append(("bad", f"Fiscal consistency flag: {detail}"))
    elif conc == 0 and spend >= 250_000:
        insights.append(("warn", f"Authored ${spend:,.0f} in budget referrals on the action calendar with no fiscal concern rhetoric in speeches"))
    elif conc >= 4 and spend == 0 and (s.get("action_off_mission_authored", 0) or 0) == 0:
        insights.append(("good", f"Fiscal concern rhetoric matches actions — {conc} deficit references, no large spending authored"))

    # Attendance
    fully_absent = s.get("sessions_fully_absent", 0) or 0
    sessions_total = s.get("sessions_total", 0) or 0
    if fully_absent >= 4:
        insights.append(("bad", f"Fully absent from {fully_absent} of {sessions_total} sessions — never arrived, no vote cast"))
    elif fully_absent >= 2:
        insights.append(("warn", f"Fully absent from {fully_absent} sessions (no arrival recorded)"))

    # Major fiscal vote absences
    fv_absent = s.get("fiscal_vote_absent", 0) or 0
    fv_total  = s.get("fiscal_vote_total",  0) or 0
    fv_miss   = s.get("fiscal_dollars_absent", 0) or 0
    if fv_absent >= 3:
        insights.append(("bad", f"Missed {fv_absent} of {fv_total} binding fiscal votes — {_fmt_m(fv_miss)} in authorizations voted on without them"))
    elif fv_absent >= 1:
        insights.append(("warn", f"Absent for {fv_absent} of {fv_total} binding fiscal votes ({_fmt_m(fv_miss)})"))

    # Annotated vote dissent / abstentions
    ann_no      = s.get("annot_vote_no",      0) or 0
    ann_abstain = s.get("annot_vote_abstain",  0) or 0
    ann_cont    = s.get("annot_contested_abstain", 0) or 0
    if ann_no >= 2:
        insights.append(("good", f"Voted NO {ann_no} times across all tracked items — among the most willing to dissent from bloc"))
    elif ann_no == 1:
        insights.append(("good", "Cast 1 dissenting NO vote — rare on this council"))
    if ann_cont >= 1:
        insights.append(("warn", f"Abstained {ann_cont}× on contested votes (another member voted no) — chose not to take a side when it mattered"))
    elif ann_abstain >= 3:
        insights.append(("warn", f"Abstained {ann_abstain} times — pattern suggests disengagement or unstated disagreement"))

    # Efficiency
    erank = rankings.get("efficiency", {}).get(n)
    atl   = s.get("avg_turn_len", 0) or 0
    if erank == 1:
        insights.append(("good", f"Most efficient speaker ({atl:.0f} words/turn avg) — says what needs saying and yields the floor"))
    elif erank and erank >= 7:
        insights.append(("warn", f"Least efficient speaker ({atl:.0f} words/turn avg) — long monologues consume meeting time"))

    return insights[:6]   # cap at 6


# ---------------------------------------------------------------------------
# Consent calendar section (embedded in member card)
# ---------------------------------------------------------------------------

def _render_agenda_section(s: dict) -> str:
    """
    Return HTML for Agenda Behavior section covering both consent and action calendars.
    Returns '' if no agenda data is present.
    """
    # Consent
    c_authored    = s.get("agenda_off_mission_authored",    0) or 0
    c_cosponsored = s.get("agenda_off_mission_cosponsored", 0) or 0
    false_fisc    = (s.get("agenda_false_fiscal_authored",   0) or 0) + \
                    (s.get("agenda_false_fiscal_cosponsored",0) or 0)
    disc_total    = s.get("agenda_discretionary_total",     0) or 0
    disc_items    = s.get("agenda_discretionary_items",     0) or 0

    # Action calendar
    a_authored    = s.get("action_off_mission_authored",    0) or 0
    a_cosponsored = s.get("action_off_mission_cosponsored", 0) or 0
    a_spend       = s.get("action_budget_referral_total",   0) or 0
    a_items       = s.get("action_budget_referral_items",   0) or 0

    # Fiscal hypocrisy
    hyp_score  = s.get("fiscal_hypocrisy_score", 0) or 0
    hyp_detail = s.get("fiscal_hypocrisy_detail", "") or ""
    concern    = s.get("fiscal_concern_hits", 0) or 0

    if c_authored + c_cosponsored + false_fisc + disc_total + a_authored + a_cosponsored + a_spend == 0:
        return ""

    def _clr(n, bad, warn=1):
        if n >= bad:  return "#e74c3c"
        if n >= warn: return "#f39c12"
        return "#2c3e50"

    def _stat(val, label, bad, warn=1, fmt=None):
        color = _clr(val, bad, warn)
        disp  = fmt(val) if fmt else str(val)
        return (
            f'<div class="stat-box">'
            f'<div class="stat-val" style="font-size:18px;color:{color}">{disp}</div>'
            f'<div class="stat-lbl" style="margin-top:4px">{label}</div>'
            f'</div>'
        )

    consent_row = (
        _stat(c_authored,    "Off-mission items<br>buried in consent (authored)", bad=2, warn=1) +
        _stat(c_cosponsored, "Off-mission consent<br>items co-sponsored",         bad=4, warn=2) +
        _stat(false_fisc,    'False &ldquo;None&rdquo; fiscal<br>claims (authored/cospon.)', bad=2, warn=1) +
        (f'<div class="stat-box">'
         f'<div class="stat-val" style="font-size:18px">${disc_total:,}</div>'
         f'<div class="stat-lbl" style="margin-top:4px">Discretionary relinquishments<br>'
         f'({disc_items} items from council budget)</div>'
         f'</div>' if disc_total or disc_items else '')
    )

    action_row = (
        _stat(a_authored,    "Off-mission items<br>brought to action calendar", bad=2, warn=1) +
        _stat(a_cosponsored, "Off-mission action<br>items co-sponsored",        bad=3, warn=1) +
        (f'<div class="stat-box">'
         f'<div class="stat-val" style="font-size:18px;color:{_clr(a_spend,1_000_000,250_000)}">'
         f'${a_spend:,.0f}</div>'
         f'<div class="stat-lbl" style="margin-top:4px">Budget referrals authored<br>'
         f'on action calendar ({a_items} items)</div>'
         f'</div>' if a_spend else '')
    )

    hyp_html = ""
    if hyp_score >= 0.05:
        hyp_html = (
            f'<div style="margin-top:12px;padding:10px 12px;background:#fff5f5;'
            f'border-left:3px solid #e74c3c;border-radius:4px;font-size:12px;line-height:1.6">'
            f'<b style="color:#e74c3c">Fiscal Consistency Flag</b> — '
            f'{concern} fiscal-concern speeches vs. '
            f'{"$" + f"{a_spend:,.0f}" + " authored in budget referrals" if a_spend else str(a_authored) + " off-mission items on action calendar"}'
            + (f'<br><span style="color:#95a5a6;font-size:10.5px">{hyp_detail}</span>' if hyp_detail else '')
            + '</div>'
        )

    return f"""
  <div class="section">
    <div class="section-title">Agenda Behavior — Consent &amp; Action Calendars</div>
    <div style="font-size:10px;color:#7f8c8d;margin-bottom:8px;font-style:italic">
      Consent = block votes on buried items &nbsp;·&nbsp; Action = explicitly debated (heavier signal)
    </div>
    <div style="font-size:11px;font-weight:600;color:#7f8c8d;text-transform:uppercase;
                letter-spacing:.8px;margin-bottom:6px">Consent Calendar</div>
    <div class="stat-grid">{consent_row}</div>
    <div style="font-size:11px;font-weight:600;color:#7f8c8d;text-transform:uppercase;
                letter-spacing:.8px;margin:12px 0 6px">Action Calendar</div>
    <div class="stat-grid">{action_row}</div>
    {hyp_html}
  </div>"""


# ---------------------------------------------------------------------------
# Spending vote record section
# ---------------------------------------------------------------------------

def _render_spending_votes(s: dict) -> str:
    """
    Section showing the member's roll-call voting record on items with dollar values.
    Returns '' if no spending votes are recorded.
    """
    yes_total   = s.get("spending_yes_total",     0) or 0
    no_total    = s.get("spending_no_total",      0) or 0
    abs_total   = s.get("spending_abstain_total", 0) or 0
    n_votes     = s.get("spending_votes_n",       0) or 0
    yes_pct     = s.get("spending_yes_pct")
    biggest     = s.get("largest_yes_item")

    if n_votes == 0:
        return ""

    def _fmt_m(v: int) -> str:
        if v >= 1_000_000:
            return f"${v/1_000_000:.1f}M"
        if v >= 1_000:
            return f"${v/1_000:.0f}K"
        return f"${v:,}"

    yes_color = "#2c3e50"   # neutral — unanimous councils make 100% unremarkable
    no_color  = "#27ae60" if no_total > 0 else "#95a5a6"

    yes_box = (
        f'<div class="stat-box">'
        f'<div class="stat-val" style="color:{yes_color}">{_fmt_m(yes_total)}</div>'
        f'<div class="stat-lbl">Voted <b>YES</b> on<br>({n_votes} spending votes)</div>'
        f'</div>'
    )
    no_box = (
        f'<div class="stat-box">'
        f'<div class="stat-val" style="color:{no_color}">{_fmt_m(no_total) if no_total else "—"}</div>'
        f'<div class="stat-lbl">Voted <b>NO</b> on<br>(dissent from block)</div>'
        f'</div>'
    )
    pct_box = ""
    if yes_pct is not None:
        pct_color = "#7f8c8d"   # 100% YES is normal; call it out only if below 90%
        if yes_pct < 0.90:
            pct_color = "#27ae60"
        pct_box = (
            f'<div class="stat-box">'
            f'<div class="stat-val" style="color:{pct_color}">{yes_pct*100:.0f}%</div>'
            f'<div class="stat-lbl">YES rate on<br>spending items</div>'
            f'</div>'
        )

    biggest_html = ""
    if biggest:
        bamt  = _fmt_m(biggest["dollar_total"])
        bdate = biggest.get("date", "")
        btitle = biggest.get("title", "")[:65]
        biggest_html = (
            f'<div style="margin-top:10px;padding:8px 12px;background:#f0f7ff;'
            f'border-left:3px solid #3498db;border-radius:4px;font-size:12px;line-height:1.6">'
            f'<b>Largest YES vote:</b> {bamt} &nbsp;·&nbsp; {bdate}<br>'
            f'<span style="color:#555">{btitle}</span>'
            f'</div>'
        )

    return f"""
  <div class="section">
    <div class="section-title">Spending Votes — Roll-Call Record</div>
    <div style="font-size:10px;color:#7f8c8d;margin-bottom:8px;font-style:italic">
      Dollar amounts from agenda items matched to extracted roll-calls.
      Coverage is partial: unanimous voice votes and some formats not captured.
    </div>
    <div class="stat-grid">{yes_box}{no_box}{pct_box}</div>
    {biggest_html}
  </div>"""


def _render_hso_section(s: dict) -> str:
    """
    Section showing the member's Homeless Services Orthodoxy (HSO) score.
    Measures investment in Berkeley's prevailing homeless services apparatus —
    $21.7M+/yr across 33 programs, Housing First mandate, low-barrier ideology —
    vs. demanding accountability, cost-per-client scrutiny, and enforcement.
    """
    score      = s.get("hso_score")
    sym_hits   = s.get("hso_sympathy_hits",  0) or 0
    ske_hits   = s.get("hso_skeptic_hits",   0) or 0
    net_rate   = s.get("hso_net_rate",       0.0) or 0.0
    sym_rate   = s.get("hso_sympathy_rate",  0.0) or 0.0
    ske_rate   = s.get("hso_skeptic_rate",   0.0) or 0.0
    cospon     = s.get("hso_items_cosponsored", 0) or 0

    if score is None:
        return ""

    # Color the score: high = status-quo aligned (red), low = reform-oriented (green)
    if score >= 70:
        score_color = "#c0392b"
        label = "High Orthodoxy"
    elif score >= 45:
        score_color = "#e67e22"
        label = "Moderate Orthodoxy"
    elif score >= 20:
        score_color = "#7f8c8d"
        label = "Mixed"
    else:
        score_color = "#27ae60"
        label = "Reform-Oriented"

    bar_w = int(min(100, max(0, score)) * 2.0)

    rhetoric_line = ""
    if sym_hits + ske_hits > 0:
        rhetoric_line = (
            f"<div style='margin-top:6px;font-size:11px;color:#555'>"
            f"Rhetoric: <b>{sym_hits}</b> orthodoxy-aligned signals "
            f"(<em>housing first, trauma-informed, unhoused neighbors&hellip;</em>) &nbsp;&nbsp;"
            f"<b>{ske_hits}</b> accountability signals "
            f"(<em>Grants Pass, cost-per-client, metrics&hellip;</em>)"
            f"</div>"
        )
    else:
        rhetoric_line = (
            "<div style='margin-top:6px;font-size:11px;color:#95a5a6;font-style:italic'>"
            "No orthodoxy-specific rhetoric detected in attributed speech.</div>"
        )

    cospon_line = ""
    if cospon > 0:
        cospon_line = (
            f"<div style='margin-top:4px;font-size:11px;color:#555'>"
            f"Cosponsored/authored <b>{cospon}</b> homeless-services agenda item(s).</div>"
        )

    return f"""
  <div class="section">
    <div class="section-title">Homeless Services Orthodoxy</div>
    <div style="font-size:10px;color:#7f8c8d;margin-bottom:8px;font-style:italic">
      Berkeley spends $21.7M+/yr across 33 programs; H&amp;W up 65% vs 25% revenue growth.
      Score measures investment in the prevailing homeless services apparatus vs.
      accountability and reform orientation. Lower is better.
      Based on attributed transcript speech; coverage partial.
    </div>
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:4px">
      <div style="font-size:28px;font-weight:bold;color:{score_color}">{score:.0f}</div>
      <div>
        <div style="font-size:13px;font-weight:bold;color:{score_color}">{label}</div>
        <svg width="200" height="12" style="display:block;margin-top:4px">
          <rect x="0" y="0" width="200" height="12" rx="4" fill="#ecf0f1"/>
          <rect x="0" y="0" width="{bar_w}" height="12" rx="4" fill="{score_color}"/>
        </svg>
        <div style="font-size:10px;color:#95a5a6;margin-top:2px">0 = reform-oriented &nbsp;·&nbsp; 100 = status-quo aligned</div>
      </div>
    </div>
    {rhetoric_line}
    {cospon_line}
  </div>"""


# ---------------------------------------------------------------------------
# Procurement integrity section (from packet_scraper staff report signals)
# ---------------------------------------------------------------------------

def _render_procurement_section(s: dict) -> str:
    score     = s.get("procurement_score")
    waived    = s.get("procurement_waived_bid_yes",  0) or 0
    backdated = s.get("procurement_backdated_yes",   0) or 0
    alt_none  = s.get("procurement_alt_none_yes",    0) or 0
    total     = s.get("procurement_flagged_yes",     0) or 0
    items     = s.get("procurement_flagged_items",  []) or []

    if score is None:
        return ""

    if score >= 70:
        score_color, label = "#c0392b", "High Risk"
    elif score >= 40:
        score_color, label = "#e67e22", "Elevated"
    elif score >= 15:
        score_color, label = "#7f8c8d", "Moderate"
    else:
        score_color, label = "#27ae60", "Low"

    bar_w = int(min(100, max(0, score)) * 2.0)

    signal_parts = []
    if waived:
        signal_parts.append(f"<b>{waived}</b> waived-bid item{'s' if waived != 1 else ''}")
    if backdated:
        signal_parts.append(f"<b>{backdated}</b> backdated contract{'s' if backdated != 1 else ''}")
    if alt_none:
        signal_parts.append(f"<b>{alt_none}</b> item{'s' if alt_none != 1 else ''} with "
                            f"&ldquo;alternatives: none&rdquo;")
    signals_html = (
        f"<div style='margin-top:6px;font-size:11px;color:#555'>"
        f"Voted YES on: {', '.join(signal_parts)}.</div>"
    ) if signal_parts else (
        "<div style='margin-top:6px;font-size:11px;color:#95a5a6;font-style:italic'>"
        "No red-flag procurement votes detected in covered items.</div>"
    )

    # Show up to 3 worst items
    items_html = ""
    if items:
        rows = ""
        for it in items[:3]:
            flags = it.get("flags", [])
            flag_str = " · ".join(
                {"waived_bid": "waived bid", "backdated": "backdated", "alt_none": "alt=none"}.get(f, f)
                for f in flags
            )
            dollar = it.get("dollar_total", 0)
            dollar_str = f"${dollar:,.0f}" if dollar else ""
            rows += (
                f"<tr><td style='padding:2px 8px 2px 0;font-size:10px;color:#555'>"
                f"{it['date']} #{it['item_number']}</td>"
                f"<td style='font-size:10px;color:#555'>{it['title'][:55]}</td>"
                f"<td style='font-size:10px;color:#e67e22;padding-left:6px'>{flag_str}</td>"
                f"<td style='font-size:10px;color:#c0392b;padding-left:6px'>{dollar_str}</td></tr>"
            )
        items_html = f"<table style='margin-top:6px;border-collapse:collapse'>{rows}</table>"

    return f"""
  <div class="section">
    <div class="section-title">Procurement Integrity</div>
    <div style="font-size:10px;color:#7f8c8d;margin-bottom:8px;font-style:italic">
      Votes on items where staff reports show waived competitive bids, retroactive contracts,
      or &ldquo;alternative actions considered: none.&rdquo; Score based on items with cached staff reports only.
    </div>
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:4px">
      <div style="font-size:28px;font-weight:bold;color:{score_color}">{score:.0f}</div>
      <div>
        <div style="font-size:13px;font-weight:bold;color:{score_color}">{label}</div>
        <svg width="200" height="12" style="display:block;margin-top:4px">
          <rect x="0" y="0" width="200" height="12" rx="4" fill="#ecf0f1"/>
          <rect x="0" y="0" width="{bar_w}" height="12" rx="4" fill="{score_color}"/>
        </svg>
        <div style="font-size:10px;color:#95a5a6;margin-top:2px">
          {total} flagged vote{'s' if total != 1 else ''} &nbsp;·&nbsp;
          0 = cleanest &nbsp;·&nbsp; 100 = most rubber-stamps
        </div>
      </div>
    </div>
    {signals_html}
    {items_html}
  </div>"""


# ---------------------------------------------------------------------------
# Attendance section (from annotated agenda PDFs)
# ---------------------------------------------------------------------------

def _render_attendance_section(s: dict) -> str:
    total        = s.get("sessions_total",         0) or 0
    fully_absent = s.get("sessions_fully_absent",   0) or 0
    late         = s.get("sessions_late",           0) or 0
    absent_roll  = s.get("sessions_absent_at_roll", 0) or 0
    att_rate     = s.get("attendance_rate",         1.0) or 1.0
    punct_rate   = s.get("punctuality_rate",        1.0) or 1.0

    if total == 0:
        return ""

    present = total - fully_absent

    def _clr(val, bad, warn):
        if val >= bad:  return "#e74c3c"
        if val >= warn: return "#f39c12"
        return "#27ae60"

    absent_color = _clr(fully_absent, 4, 2)
    late_color   = _clr(late,         8, 4)
    roll_color   = _clr(absent_roll, 15, 8)

    att_bar_w  = int(att_rate   * 240)
    att_color  = "#27ae60" if att_rate >= 0.95 else "#f39c12" if att_rate >= 0.85 else "#e74c3c"
    pct_bar_w  = int(punct_rate * 240)
    pct_color  = "#27ae60" if punct_rate >= 0.80 else "#f39c12" if punct_rate >= 0.60 else "#e74c3c"

    return f"""
  <div class="section">
    <div class="section-title">Attendance — {total} Sessions (Annotated Agenda Record)</div>
    <div style="font-size:10px;color:#7f8c8d;margin-bottom:10px;font-style:italic">
      Source: post-meeting annotated agenda PDFs — the authoritative attendance record.
      "Fully absent" = listed absent at roll call and never arrived.
    </div>
    <div class="stat-grid" style="margin-bottom:12px">
      <div class="stat-box">
        <div class="stat-val">{present}/{total}</div>
        <div class="stat-lbl">Sessions present<br>(attended at some point)</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:{absent_color}">{fully_absent}</div>
        <div class="stat-lbl">Sessions <b>fully absent</b><br>(never arrived)</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:{late_color}">{late}</div>
        <div class="stat-lbl">Sessions <b>late</b><br>(absent at roll, arrived later)</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:{roll_color}">{absent_roll}</div>
        <div class="stat-lbl">Sessions absent<br>at roll call</div>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:6px">
      <div style="display:flex;align-items:center;gap:10px">
        <div style="width:110px;font-size:11px;color:#555">Attendance rate</div>
        <svg width="240" height="12"><rect width="240" height="12" rx="4" fill="#ecf0f1"/>
          <rect width="{att_bar_w}" height="12" rx="4" fill="{att_color}"/></svg>
        <div style="font-size:11px;font-weight:700;color:{att_color}">{att_rate*100:.0f}%</div>
      </div>
      <div style="display:flex;align-items:center;gap:10px">
        <div style="width:110px;font-size:11px;color:#555">On-time rate</div>
        <svg width="240" height="12"><rect width="240" height="12" rx="4" fill="#ecf0f1"/>
          <rect width="{pct_bar_w}" height="12" rx="4" fill="{pct_color}"/></svg>
        <div style="font-size:11px;font-weight:700;color:{pct_color}">{punct_rate*100:.0f}%</div>
      </div>
    </div>
  </div>"""


# ---------------------------------------------------------------------------
# Major fiscal votes section
# ---------------------------------------------------------------------------

def _fmt_m(v: int) -> str:
    if v >= 1_000_000_000:
        return f"${v/1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:,}"

_CLASSIFICATION_LABEL = {
    "TEFRA_BOND":      "TEFRA Bond",
    "LEASE_BOND":      "Revenue Bond",
    "GO_BOND":         "GO Bond",
    "BUDGET_AMENDMENT":"Budget Amendment",
    "BUDGET_ADOPTION": "Budget Adoption",
}

_POSITION_STYLE = {
    "yes":     ("#e67e22", "YES",     "Endorsed status quo — voted to authorize"),
    "no":      ("#27ae60", "NO",      "Dissented — voted against authorization"),
    "absent":  ("#e74c3c", "ABSENT",  "Absent — missed binding fiscal vote"),
    "abstain": ("#f39c12", "ABSTAIN", "Chose not to use voting power"),
    "unknown": ("#95a5a6", "?",       "Position not determinable from record"),
}

def _render_fiscal_votes_section(s: dict) -> str:
    records      = s.get("fiscal_vote_records",      []) or []
    fv_total     = s.get("fiscal_vote_total",         0) or 0
    fv_absent    = s.get("fiscal_vote_absent",        0) or 0
    fv_yes       = s.get("fiscal_vote_yes",           0) or 0
    fv_no        = s.get("fiscal_vote_no",            0) or 0
    dollars_miss = s.get("fiscal_dollars_absent",     0) or 0
    dollars_yes  = s.get("fiscal_dollars_voted_yes",  0) or 0

    if not records:
        return ""

    absent_color = "#e74c3c" if fv_absent >= 3 else "#f39c12" if fv_absent >= 1 else "#27ae60"
    yes_color    = "#e67e22"   # all budget YES votes are status-quo endorsements

    summary_boxes = (
        f'<div class="stat-box">'
        f'<div class="stat-val" style="color:{absent_color}">{fv_absent}/{fv_total}</div>'
        f'<div class="stat-lbl">Binding fiscal votes<br><b>missed</b></div>'
        f'</div>'
        +
        (f'<div class="stat-box">'
         f'<div class="stat-val" style="color:{absent_color}">{_fmt_m(dollars_miss)}</div>'
         f'<div class="stat-lbl">In fiscal authorizations<br>absent for</div>'
         f'</div>' if dollars_miss else '')
        +
        f'<div class="stat-box">'
        f'<div class="stat-val" style="color:{yes_color}">{fv_yes}</div>'
        f'<div class="stat-lbl">Endorsed status quo<br>(voted YES)</div>'
        f'</div>'
        +
        (f'<div class="stat-box">'
         f'<div class="stat-val" style="color:#27ae60">{fv_no}</div>'
         f'<div class="stat-lbl">Dissented<br>(voted NO)</div>'
         f'</div>' if fv_no else '')
    )

    rows = ""
    for rec in records:
        pos   = rec.get("position", "unknown")
        color, badge, _ = _POSITION_STYLE.get(pos, _POSITION_STYLE["unknown"])
        amt   = rec.get("amount", 0)
        cls   = _CLASSIFICATION_LABEL.get(rec.get("classification",""), rec.get("classification",""))
        title = rec.get("title", "")
        date  = rec.get("date", "")
        rows += (
            f"<tr>"
            f"<td style='padding:4px 8px 4px 0;font-size:10px;color:#777;white-space:nowrap'>{date}</td>"
            f"<td style='font-size:10px;color:#888;white-space:nowrap'>{cls}</td>"
            f"<td style='font-size:10.5px;color:#2c3e50'>{title}</td>"
            f"<td style='font-size:10.5px;font-weight:700;text-align:right;white-space:nowrap'>{_fmt_m(amt)}</td>"
            f"<td style='text-align:center;padding-left:8px'>"
            f"<span style='font-size:10px;font-weight:800;color:{color};white-space:nowrap'>{badge}</span>"
            f"</td>"
            f"</tr>"
        )

    note = (
        '<div style="margin-top:8px;font-size:10px;color:#7f8c8d;font-style:italic">'
        'YES = endorsed the spending authorization (budget adoptions = chose not to cut or reprioritize). '
        'ABSENT = dereliction — items are only on the agenda because the Mayor expects passage.'
        '</div>'
    )

    return f"""
  <div class="section">
    <div class="section-title">Major Fiscal Votes — {fv_total} Binding Decisions</div>
    <div style="font-size:10px;color:#7f8c8d;margin-bottom:10px;font-style:italic">
      Curated list of binding fiscal votes Dec 2024–Jul 2025. Source: annotated agenda PDFs.
    </div>
    <div class="stat-grid" style="margin-bottom:12px">{summary_boxes}</div>
    <table style="width:100%;border-collapse:collapse">
      <thead>
        <tr style="background:#f0f2f5">
          <th style="text-align:left;font-size:9.5px;color:#7f8c8d;font-weight:600;padding:4px 8px 4px 0;text-transform:uppercase;letter-spacing:.5px">Date</th>
          <th style="text-align:left;font-size:9.5px;color:#7f8c8d;font-weight:600;padding:4px 8px;text-transform:uppercase;letter-spacing:.5px">Type</th>
          <th style="text-align:left;font-size:9.5px;color:#7f8c8d;font-weight:600;padding:4px 8px;text-transform:uppercase;letter-spacing:.5px">Item</th>
          <th style="text-align:right;font-size:9.5px;color:#7f8c8d;font-weight:600;padding:4px 8px;text-transform:uppercase;letter-spacing:.5px">Amount</th>
          <th style="text-align:center;font-size:9.5px;color:#7f8c8d;font-weight:600;padding:4px 8px;text-transform:uppercase;letter-spacing:.5px">Position</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    {note}
  </div>"""


# ---------------------------------------------------------------------------
# Taxpayer alignment score breakdown
# ---------------------------------------------------------------------------

def _render_taxpayer_breakdown(s: dict) -> str:
    """Detailed decomposition of the Taxpayer Alignment score."""

    def _fmt(v: float) -> tuple[str, str]:
        """Return (formatted string, CSS class) for a contribution value."""
        if abs(v) < 0.0005:
            return "—", "zero"
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.3f}", ("pos" if v > 0 else "neg")

    hso_raw      = s.get("hso_score") if s.get("hso_score") is not None else 50
    hso_part     = s.get("composite_hso_part",      0) or 0
    off_pen      = s.get("composite_off_penalty",   0) or 0
    raw          = s.get("composite_taxpayer_raw",  0) or 0

    # HSO contribution to raw: hso_part * 0.75 (inverted — high hso_part = low alignment)
    hso_contrib  =  (1.0 - hso_part) * 0.75    # "HSO alignment" fraction, weighted 75%
    scope_contrib = (1.0 - off_pen)  * 0.25    # scope discipline, weighted 25%

    inc_adj      = s.get("incident_score_adj",           0.0) or 0.0
    silence_pen  = -(s.get("composite_audit_silence_pen", 0.0) or 0.0)
    rhetoric_pen = -(s.get("composite_rhetoric_penalty",  0.0) or 0.0)
    rev_seek_pen = -(s.get("composite_revenue_seeking_pen", 0.0) or 0.0)
    fref_pen     = s.get("composite_fiscal_ref_penalty",  0.0) or 0.0
    final        = s.get("composite_taxpayer",            0.0) or 0.0

    # Labels for audit silence events
    silence_events = s.get("audit_silence_events") or []
    if silence_events:
        silence_label = "; ".join(e.replace("_", " ") for e in silence_events)
    elif s.get("audit_silence_events") is not None:
        silence_label = "audits presented — follow-up on record"
    else:
        silence_label = "none — behavior already characterized via incidents"

    inc_count  = s.get("incident_count", 0) or 0

    def _row(label: str, note: str, val: float) -> str:
        fstr, cls = _fmt(val)
        return (f'<tr class="data-row"><td>{label}</td>'
                f'<td class="note">{note}</td>'
                f'<td class="contrib {cls}">{fstr}</td></tr>')

    hso_str, hso_cls = _fmt(hso_contrib)
    sc_str,  sc_cls  = _fmt(scope_contrib)
    raw_str, raw_cls = _fmt(raw)
    fin_str, fin_cls = _fmt(final)

    return f"""
  <div class="section">
    <div class="section-title">Taxpayer Alignment — Score Breakdown</div>
    <div style="font-size:10px;color:#7f8c8d;margin-bottom:12px;font-style:italic">
      How the {final:.3f} Taxpayer Alignment score is constructed.
      Components sum to the raw figure; the final score is clamped to [0, 1].
    </div>
    <table class="ta-table">

      <tr class="group-header"><td colspan="3">Base — from voting record and agenda behavior</td></tr>
      <tr class="data-row">
        <td>HSO alignment</td>
        <td class="note">HSO score {hso_raw}/100 → inverse {(100-hso_raw):.0f}% → quadratic → {hso_part:.1%} &nbsp;(75% weight)</td>
        <td class="contrib {hso_cls}">{hso_str}</td>
      </tr>
      <tr class="data-row">
        <td>Scope discipline</td>
        <td class="note">Off-mission penalty {off_pen:.1%} → discipline {(1-off_pen):.1%} &nbsp;(25% weight)</td>
        <td class="contrib {sc_cls}">{sc_str}</td>
      </tr>
      <tr class="subtotal">
        <td colspan="2">Raw score</td>
        <td class="contrib">{raw_str}</td>
      </tr>

      <tr class="group-header"><td colspan="3">Adjustments — documented behaviors and penalties</td></tr>
      {_row("Incident record",
            f"{inc_count} incident{'s' if inc_count != 1 else ''}, tier-weighted, capped ±0.30",
            inc_adj)}
      {_row("Audit silence", silence_label, silence_pen)}
      {_row("Revenue-seeking penalty",
            "Revenue advocacy without companion cut analysis",
            rev_seek_pen)}
      {_row("Fiscal referral penalty",
            "Bond/tax campaign direction (capped −0.09)",
            fref_pen)}
      {_row("Rhetoric penalty",
            "Fiscal concern rhetoric with no dissent votes (high HSO or serial fiscal-vote absence)",
            rhetoric_pen)}

      <tr class="total-row">
        <td colspan="2">Final (clamped to [0, 1])</td>
        <td class="contrib">{fin_str}</td>
      </tr>
    </table>
  </div>"""


# ---------------------------------------------------------------------------
# Render one member scorecard
# ---------------------------------------------------------------------------

def render_member(s: dict, rankings: dict, council_block_rate: float, meta: dict,
                  summary: dict | None = None) -> str:
    name = s.get("display_name", s.get("canonical", "?"))
    dist = DISTRICT.get(s.get("canonical", ""), "")
    earliest = meta.get("earliest_meeting", "Dec 2024")
    latest   = meta.get("latest_meeting",   "")
    as_of    = f"through {latest}" if latest else ""
    period   = f"{earliest} – {latest} · {meta.get('transcripts', 51)} meetings"

    # Overall grade from composite (taxpayer alignment + focus + attendance + incidents)
    voter  = s.get("composite_grade", 0) or 0
    g_str, g_cls = letter(voter)

    # Pillar scores
    delta = s.get("_delta", {})
    pillars = [
        ("Civic Focus",         min(1.0, 1 - (s.get("waste_pct", 0) or 0) * 0.5 + (s.get("core_pct", 0) or 0) * 0.5), "waste_pct"),
        ("Legislative Skill",   s.get("lsi",      0) or 0,  "lsi"),
        ("Taxpayer Alignment",  max(0.0, s.get("composite_taxpayer", 0) or 0), "composite_taxpayer"),
        ("Character & Conduct", s.get("beer",      0) or 0, "beer"),
    ]
    pillar_html = ""
    for plabel, pval, dkey in pillars:
        pg, pc = letter(pval)
        badge = delta_badge(delta.get(dkey), dkey)
        pillar_html += f"""
        <div class="pillar-row">
          <div class="pillar-label">{plabel}</div>
          <div class="pillar-grade {pc}">{pg}</div>
          <div class="pillar-bar">{pct_bar(pval)}</div>
          <div class="pillar-pct">{pval*100:.0f}%{badge}</div>
        </div>"""

    # Vote stats — prefer annotated-agenda data; fall back to transcript extraction
    ann_total   = s.get("annot_vote_total",   0) or 0
    ann_no      = s.get("annot_vote_no",      0) or 0
    ann_abstain = s.get("annot_vote_abstain", 0) or 0
    ann_absent  = s.get("annot_vote_absent",  0) or 0
    ann_cont    = s.get("annot_contested_abstain", 0) or 0
    block_pct   = int(council_block_rate * 100)

    # Trend (focus = core_pct, positive = more on-topic = improving)
    ct = s.get("core_trend")
    trend_line = ""
    if ct is not None:
        direction = "improving" if ct > 0.02 else ("declining" if ct < -0.02 else "stable")
        trend_line = f"Recent focus trend: <b>{direction}</b> {focus_trend_arrow(ct)} (meeting focus {ct:+.1%} vs all-time avg)"

    # Rankings
    vrank = rankings.get("composite_grade", {}).get(s["canonical"], "—")
    brank = rankings.get("beer",  {}).get(s["canonical"], "—")
    rrank = rankings.get("recall",{}).get(s["canonical"], "—")
    erank = rankings.get("efficiency", {}).get(s["canonical"], "—")
    total = len([k for k in rankings.get("composite_grade",{})])
    v_badge = delta_badge(delta.get("composite_grade"), "composite_grade")
    b_badge = delta_badge(delta.get("beer"),      "beer")
    r_badge = delta_badge(delta.get("recall"),    "recall")
    e_badge = delta_badge(delta.get("efficiency"),"efficiency")

    # Insights
    insights_html = ""
    for itype, itext in build_insights(s, rankings, council_block_rate):
        icon = "✓" if itype == "good" else ("△" if itype == "warn" else "✗")
        insights_html += f'<div class="insight {itype}"><span class="icon">{icon}</span><span>{itext}</span></div>'

    refs = s.get("staff_referrals", 0) or 0
    spons = s.get("sponsorships", 0) or 0
    atl  = s.get("avg_turn_len", 0) or 0
    gen_date = meta.get("generated", "")[:10]

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>{SHARED_CSS}</style></head>
<body>
<div class="card">

  <div class="header">
    <div class="hdr-left">
      <div class="name">{name.upper()}</div>
      <div class="subtitle">
        {dist} &nbsp;·&nbsp; Berkeley City Council<br>
        {period}
      </div>
    </div>
    <div class="hdr-right">
      <div class="overall-label">Voter Alignment</div>
      <div class="overall-grade {g_cls}">{g_str}</div>
      {"<div style='font-size:10px;color:#8899bb;margin-top:4px'>as of " + latest + "</div>" if latest else ""}
    </div>
  </div>

  {f'''<div class="section">
    <div class="section-title">Executive Summary</div>
    <div class="exec-archetype">Character &nbsp;·&nbsp; <span>{summary.get("archetype", "")}</span></div>
    <div class="exec-summary">{summary.get("summary", "")}</div>
  </div>''' if summary and summary.get("summary") else ""}

  <div class="section">
    <div class="section-title">Performance Pillars</div>
    {pillar_html}
  </div>

  <div class="section">
    <div class="section-title">Rankings  (of {total} scored members)</div>
    <div class="rank-row">
      <div class="rank-item">
        <div class="rank-title">Voter Alignment</div>
        <div class="rank-val">#{vrank}{v_badge}</div>
      </div>
      <div class="rank-item">
        <div class="rank-title">Civic Temperament</div>
        <div class="rank-val">#{brank}{b_badge}</div>
      </div>
      <div class="rank-item">
        <div class="rank-title">Clarity</div>
        <div class="rank-val">#{rrank} <span style="font-size:12px;color:#7f8c8d">(#1=least)</span>{r_badge}</div>
      </div>
      <div class="rank-item">
        <div class="rank-title">Efficiency</div>
        <div class="rank-val">#{erank} <span style="font-size:12px;color:#7f8c8d">({atl:.0f} w/turn)</span>{e_badge}</div>
      </div>
    </div>
  </div>

  {_render_attendance_section(s)}

  {_render_fiscal_votes_section(s)}

  <div class="section">
    <div class="section-title">Voting Record — {ann_total} Items (Annotated Agenda)</div>
    <div style="font-size:10px;color:#7f8c8d;margin-bottom:8px;font-style:italic">
      Source: annotated agenda PDFs across all {ann_total} items with a parseable vote.
      Council block-vote rate: {block_pct}% — individual deviations are high-signal precisely because they are rare.
    </div>
    <div class="stat-grid">
      <div class="stat-box">
        <div class="stat-val" style="color:{'#27ae60' if ann_no >= 1 else '#7f8c8d'}">{ann_no}</div>
        <div class="stat-lbl">NO votes<br>(dissent from bloc)</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:{'#f39c12' if ann_abstain >= 3 else '#7f8c8d'}">{ann_abstain}</div>
        <div class="stat-lbl">Abstentions<br><em>(chose not to vote)</em></div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:{'#e74c3c' if ann_absent >= 10 else '#f39c12' if ann_absent >= 5 else '#7f8c8d'}">{ann_absent}</div>
        <div class="stat-lbl">Absent during vote<br>(item-level absences)</div>
      </div>
      <div class="stat-box">
        <div class="stat-val" style="color:{'#e74c3c' if ann_cont >= 1 else '#95a5a6'}">{ann_cont}</div>
        <div class="stat-lbl">Contested abstentions<br><em>(others voted no)</em></div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Agenda Impact &amp; Efficiency</div>
    <div class="stat-grid">
      <div class="stat-box">
        <div class="stat-val">{spons}</div>
        <div class="stat-lbl">Sponsorship signals<br>(authored or co-authored items)</div>
      </div>
      <div class="stat-box">
        <div class="stat-val">{refs}</div>
        <div class="stat-lbl">Staff referrals<br>(40–80 hrs each, no opp-cost review)</div>
      </div>
      <div class="stat-box">
        <div class="stat-val">{atl:.0f}w</div>
        <div class="stat-lbl">Avg words per turn<br>Rank #{erank} of {total}</div>
      </div>
      <div class="stat-box">
        <div class="stat-val">{s.get('pct_long',0):.0f}%</div>
        <div class="stat-lbl">Turns &gt;200 words<br>(monologue territory)</div>
      </div>
    </div>
  </div>

  {_render_spending_votes(s)}

  {_render_hso_section(s)}

  {_render_agenda_section(s)}

  {_render_taxpayer_breakdown(s)}

  <div class="section">
    <div class="section-title">Key Findings</div>
    {insights_html}
    {"<p style='font-size:12px;color:#7f8c8d;margin-top:10px'>" + trend_line + "</p>" if trend_line else ""}
  </div>

  <div class="footer">
    <span>Berkeley City Council Scorecard &nbsp;·&nbsp; Metrics explained in the <em>Berkeley City Council Scorecard Summary</em></span>
    <span>Generated {gen_date}</span>
  </div>

</div>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# Summary comparison page
# ---------------------------------------------------------------------------

def _render_procurement_watch() -> str:
    """
    Council-level procurement watch box: lists items from staff report cache
    with waived competitive bids or retroactive contracts.
    These pass on the consent calendar as a bloc — not individually attributable.
    """
    import glob as _glob
    reports_dir = os.path.join(os.path.dirname(__file__), "agendas", "reports")
    if not os.path.isdir(reports_dir):
        return ""

    flagged = []
    for path in sorted(_glob.glob(os.path.join(reports_dir, "*.json"))):
        try:
            r = json.load(open(path))
        except Exception:
            continue
        s = r.get("signals", {})
        flags = []
        if s.get("waived_competitive_bid"): flags.append("waived bid")
        if s.get("backdated"):              flags.append("retroactive")
        if not flags:
            continue
        dollars = s.get("dollar_amounts", [])
        flagged.append({
            "date":    r.get("date", ""),
            "item":    r.get("item_key", str(r.get("item_num", "?"))),
            "title":   r.get("title", "").lstrip("-").strip(),
            "flags":   flags,
            "dollars": dollars[:2],
            "grant":   s.get("grant_funded", False),
            "gf":      s.get("general_fund", False),
        })

    if not flagged:
        return ""

    rows = ""
    for it in flagged:
        flag_str  = " · ".join(f'<span style="color:#c0392b;font-weight:bold">{f}</span>' for f in it["flags"])
        dollar_str = " &nbsp; ".join(it["dollars"]) if it["dollars"] else ""
        src = "grant" if it["grant"] else ("gen. fund" if it["gf"] else "")
        rows += (
            f"<tr>"
            f"<td style='padding:3px 10px 3px 0;font-size:11px;color:#555;white-space:nowrap'>{it['date']} #{it['item']}</td>"
            f"<td style='font-size:11px;color:#333'>{it['title'][:70]}</td>"
            f"<td style='font-size:11px;padding-left:10px'>{flag_str}</td>"
            f"<td style='font-size:11px;color:#7f8c8d;padding-left:10px'>{dollar_str}</td>"
            f"<td style='font-size:11px;color:#7f8c8d;padding-left:6px'>{src}</td>"
            f"</tr>"
        )

    return f"""
<div style="margin:32px 0 0 0;padding:16px 20px;background:#fdf9f0;border-left:4px solid #e67e22;border-radius:4px">
  <div style="font-size:14px;font-weight:bold;color:#e67e22;margin-bottom:6px">
    Procurement Watch — {len(flagged)} item{'s' if len(flagged) != 1 else ''} flagged
  </div>
  <div style="font-size:10px;color:#7f8c8d;margin-bottom:10px;font-style:italic">
    Items passed on the consent calendar where staff reports show waived competitive bids
    or retroactive contracts. Consent calendar items are adopted as a bloc — individual
    member attribution requires transcript vote records (not available for these items).
  </div>
  <table style="border-collapse:collapse;width:100%">
    {rows}
  </table>
</div>"""


def render_summary(aggregate: dict, rankings: dict, council_meta: dict, meta: dict) -> str:
    members = sorted(
        [n for n in aggregate if not n.startswith("_") and n != "Ishii"
         and aggregate[n].get("words", 0) >= 1500],
        key=lambda x: -(aggregate[x].get("composite_grade", 0) or 0)
    )

    rows = ""
    for rank, n in enumerate(members, 1):
        s = aggregate[n]
        dn = s.get("display_name", n)
        dist = DISTRICT.get(n, "")
        vg, vc = letter(s.get("composite_grade"))
        bg, bc = letter(s.get("beer"))
        rg, rc = letter(1 - (s.get("recall", 0) or 0))   # invert: A = most clear
        cp  = s.get("core_pct", 0) or 0
        atl = s.get("avg_turn_len", 0) or 0
        refs = s.get("staff_referrals", 0) or 0
        erank = rankings.get("efficiency", {}).get(n, "—")
        ta = focus_trend_arrow(s.get("core_trend"))
        d  = s.get("_delta", {})
        vd = delta_badge(d.get("composite_grade"), "composite_grade", threshold=0.015) if d else ""

        # Spending vote column
        yes_total = s.get("spending_yes_total", 0) or 0
        sv_n      = s.get("spending_votes_n",   0) or 0
        if yes_total >= 1_000_000:
            yes_str = f"${yes_total/1_000_000:.0f}M"
        elif yes_total > 0:
            yes_str = f"${yes_total/1_000:.0f}K"
        else:
            yes_str = "—"
        spend_cell = (
            f'<b>{yes_str}</b>'
            + (f'<br><span class="subdist">{sv_n} votes</span>' if sv_n else "")
        )

        # Homeless Services Orthodoxy column
        hic_score = s.get("hso_score")
        if hic_score is not None:
            if hic_score >= 70:
                hic_color, hic_label = "#c0392b", "High"
            elif hic_score >= 45:
                hic_color, hic_label = "#e67e22", "Mod"
            elif hic_score >= 20:
                hic_color, hic_label = "#7f8c8d", "Mix"
            else:
                hic_color, hic_label = "#27ae60", "Low"
            hic_cell = f'<b style="color:{hic_color}">{hic_score:.0f}</b><br><span class="subdist" style="color:{hic_color}">{hic_label}</span>'
        else:
            hic_cell = "—"

        # Procurement integrity column
        proc_score = s.get("procurement_score")
        if proc_score is not None:
            if proc_score >= 70:
                proc_color = "#c0392b"
            elif proc_score >= 40:
                proc_color = "#e67e22"
            elif proc_score >= 15:
                proc_color = "#7f8c8d"
            else:
                proc_color = "#27ae60"
            proc_n = s.get("procurement_flagged_yes", 0) or 0
            proc_cell = (
                f'<b style="color:{proc_color}">{proc_score:.0f}</b>'
                + (f'<br><span class="subdist">{proc_n}v</span>' if proc_n else "")
            )
        else:
            proc_cell = "—"

        rows += f"""
        <tr>
          <td class="col-rank">#{rank}</td>
          <td class="col-name"><b>{dn}</b><br><span class="subdist">{dist}</span></td>
          <td class="col-grade {vc}">{vg}</td>
          <td class="col-bar">{pct_bar(s.get('composite_grade', 0), 110)}</td>
          <td class="col-num">{spend_cell}</td>
          <td class="col-num">{hic_cell}</td>
          <td class="col-num">{atl:.0f}w<br><span class="subdist">#{erank}</span></td>
          <td class="col-num">{refs}</td>
          <td class="col-grade {bc}">{bg}</td>
          <td class="col-grade {rc}">{rg}</td>
          <td class="col-delta">{vd if vd else '<span style="color:#ccc">—</span>'}</td>
          <td class="col-num">{cp*100:.0f}%</td>
          <td class="col-trend">{ta}</td>
        </tr>"""

    block_pct    = int((council_meta.get("block_vote_rate", 0) or 0) * 100)
    gen_date     = meta.get("generated", "")[:10]
    n_meetings   = meta.get("transcripts", 51)
    earliest     = meta.get("earliest_meeting", "")
    latest_mtg   = meta.get("latest_meeting", "")
    date_range   = f"{earliest} – {latest_mtg}" if earliest and latest_mtg else "Dec 2024–Mar 2026"
    as_of_label  = f"as of {latest_mtg}" if latest_mtg else ""

    about_page = f"""
<div class="about-page">
  <div class="about-header">
    <h1>About This Scorecard</h1>
    <p class="about-sub">Berkeley City Council &nbsp;·&nbsp; {date_range} &nbsp;·&nbsp; {n_meetings} meetings</p>
  </div>

  <div class="about-intro">
    <p>These scorecards evaluate council members from the perspective of a Berkeley voter who wants city government focused on Berkeley: lower costs, maintained infrastructure, a police department that is trusted and functional, and housing that ordinary people can afford. Foreign policy statements, police oversight theater, and programs that expand city spending without evidence of impact are treated as off-mission.</p>
    <p style="margin-top:8px">Scores are derived entirely from captioner transcripts using automated analysis — keyword classification, topic modeling, and state-machine speaker attribution. They measure what members <em>say and do in chambers</em>, not their policy positions or outside activities.</p>
  </div>

  <div class="about-metrics">

    <div class="metric-block">
      <div class="metric-name">Voter Alignment <span class="metric-weight">(Overall grade)</span></div>
      <div class="metric-desc">Composite taxpayer-alignment score: Taxpayer Alignment pillar (70%) + Civic Focus (30%) − attendance deduction. Taxpayer Alignment incorporates transcript rhetoric, voting record, HSO score, incidents, fiscal referral authorship, and fiscal hypocrisy signals. This is the correct summary grade — it captures behavior, not just speech.</div>
    </div>

    <div class="metric-block">
      <div class="metric-name">Legislative Skill <span class="metric-weight">(LSI)</span></div>
      <div class="metric-desc">Legislative Sophistication Index — five components: domain fluency (knowing the subject matter), fiscal discipline (probing costs and trade-offs), inquiry quality (the precision of questions asked), decisiveness (moving items forward without endless hedging), and procedural efficiency (using council process correctly). High LSI members add signal; low LSI members add noise.</div>
    </div>

    <div class="metric-block">
      <div class="metric-name">Civic Focus &amp; Focus % <span class="metric-weight">(pillar + summary column)</span></div>
      <div class="metric-desc">Are the topics this member engages with aligned with what the voter sent them to do? Focus % is the share of their meeting speech on core city business: budget, infrastructure, zoning, housing, public safety, and economic development. The inverse — time spent on foreign policy, police oversight theater, sanctuary city statements, and proposals that expand spending without evidence of impact — lowers the score. Focus Trend shows whether their recent meetings are more or less on-target than their historical average.</div>
    </div>

    <div class="metric-block">
      <div class="metric-name">Fiscal Discipline</div>
      <div class="metric-desc">How often the member asks about cost, funding sources, or fiscal trade-offs before voting. The council rarely considers the opportunity cost of staff referrals (~40–80 hours each) or unfunded mandates. Members who routinely probe finances before committing the city earn higher scores here.</div>
    </div>

    <div class="metric-block">
      <div class="metric-name">Civic Temperament</div>
      <div class="metric-desc">A measure of the member as a colleague and public servant: collegiality (acknowledges and builds on others' contributions), humility (updates positions when presented with new information), and warmth (treats staff, colleagues, and the public with genuine respect), minus ego signals (credential-dropping, self-referential flexes, and debate-closing appeals to personal authority). High Civic Temperament members make the council function better; low scores mean the member makes it worse.</div>
    </div>

    <div class="metric-block">
      <div class="metric-name">Clarity</div>
      <div class="metric-desc">Does this member make the council's work clearer and more tractable, or do they add friction and noise? Clarity combines ego signals (credential-dropping, debate-closing appeals to personal authority), off-mission speech, staff referral overreach, and fiscal avoidance into a single behavioral score. A high-Clarity member simplifies: they say what needs saying, probe what needs probing, and yield the floor. A low-Clarity member complicates. Graded so A = clearest, F = most obstructive.</div>
    </div>

  </div>

  <div class="about-notes">
    <b>What these scores don't measure:</b> constituent services, committee work, external advocacy, or policy outcomes. Transcripts capture chamber behavior only.
    &nbsp;·&nbsp; <b>Attribution:</b> Newer meetings use Zoom Boardroom format where speaker labels are assigned by state-machine inference — accuracy is estimated at ~80%.
    &nbsp;·&nbsp; <b>Vote data</b> is extracted from roll-call text in transcripts; events with fewer than 3 named members are excluded.
  </div>
</div>
"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
@page {{
  size: 11in 8.5in;   /* landscape letter */
  margin: 0.5in 0.55in 0.4in;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0;
     font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }}
body {{ background: white; color: #2c3e50; }}

.page-header {{ margin-bottom: 18px; border-bottom: 3px solid #1a1a2e; padding-bottom: 10px; }}
.page-header h1 {{ font-size: 20px; font-weight: 800; color: #1a1a2e; }}
.page-header h2 {{ font-size: 11px; color: #7f8c8d; font-weight: 400; margin-top: 4px; }}

table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
thead tr {{ background: #1a1a2e; }}
th {{
  color: white; padding: 9px 10px; text-align: left;
  font-size: 10px; text-transform: uppercase; letter-spacing: .7px;
  font-weight: 600;
}}
tbody tr {{ border-bottom: 1px solid #ecf0f1; }}
tbody tr:nth-child(even) {{ background: #f8f9fa; }}
td {{ padding: 10px 10px; vertical-align: middle; }}

.col-rank  {{ width: 30px; color: #aaa; font-size: 11px; text-align: center; }}
.col-name  {{ width: 110px; font-size: 13px; line-height: 1.4; }}
.col-grade {{ width: 44px; font-size: 18px; font-weight: 800; text-align: center; }}
.col-bar   {{ width: 130px; }}
.col-num   {{ width: 70px; text-align: center; font-size: 12px; line-height: 1.4; }}
.col-trend {{ width: 36px; text-align: center; font-size: 16px; }}
.col-delta {{ width: 52px; text-align: center; font-size: 11px; font-weight: 700; }}
.subdist   {{ font-size: 10px; color: #999; font-weight: 400; }}

/* Grade colours — same palette as member cards */
.grade-a  {{ color: #2ecc71; }}
.grade-b  {{ color: #3498db; }}
.grade-c  {{ color: #f39c12; }}
.grade-d  {{ color: #e67e22; }}
.grade-f  {{ color: #e74c3c; }}
.grade-nc {{ color: #95a5a6; }}

.footnote {{
  margin-top: 16px;
  font-size: 9.5px;
  color: #95a5a6;
  line-height: 1.6;
  border-top: 1px solid #ecf0f1;
  padding-top: 8px;
}}
.footnote b {{ color: #7f8c8d; }}

/* ---- About page (page 2) ---- */
.about-page {{
  page-break-before: always;
  color: #2c3e50;
}}
.about-header {{ margin-bottom: 14px; border-bottom: 3px solid #1a1a2e; padding-bottom: 10px; }}
.about-header h1 {{ font-size: 20px; font-weight: 800; color: #1a1a2e; }}
.about-sub {{ font-size: 11px; color: #7f8c8d; margin-top: 4px; }}
.about-intro {{ font-size: 11.5px; line-height: 1.6; color: #444; margin-bottom: 18px; }}
.about-metrics {{ column-count: 2; column-gap: 32px; }}
.metric-block {{ margin-bottom: 14px; break-inside: avoid; }}
.metric-name {{ font-size: 12px; font-weight: 700; color: #1a1a2e; margin-bottom: 3px; }}
.metric-weight {{ font-weight: 400; color: #7f8c8d; font-size: 11px; }}
.metric-desc {{ font-size: 11px; line-height: 1.6; color: #555; }}
.about-notes {{
  margin-top: 18px;
  font-size: 9.5px;
  color: #95a5a6;
  line-height: 1.6;
  border-top: 1px solid #ecf0f1;
  padding-top: 8px;
}}
.about-notes b {{ color: #7f8c8d; }}
</style>
</head>
<body>

<div class="page-header">
  <h1>Berkeley City Council — Member Scorecard Summary</h1>
  <h2>Ranked by Voter Alignment &nbsp;·&nbsp; {n_meetings} meetings analyzed &nbsp;·&nbsp;
      {date_range} &nbsp;·&nbsp; Council block-vote rate: {block_pct}%
      {f"&nbsp;·&nbsp; <b>{as_of_label}</b>" if as_of_label else ""}</h2>
</div>

<table>
  <thead>
    <tr>
      <th></th>
      <th>Member</th>
      <th>Overall</th>
      <th>Voter Alignment</th>
      <th>$ Voted YES</th>
      <th>HSO</th>
      <th>Words/Turn</th>
      <th>Staff Refs</th>
      <th>Civic Temp.</th>
      <th>Clarity</th>
      <th>Change</th>
      <th>Focus %</th>
      <th>Focus Trend</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>

<div class="footnote">
  <b>Voter Alignment</b> = Taxpayer Alignment 70% + Civic Focus 30% − attendance deduction (includes incidents, HSO, fiscal referrals, hypocrisy) &nbsp;·&nbsp;
  <b>$ Voted YES</b> = total dollars on agenda items where member's roll-call vote was YES (partial coverage) &nbsp;·&nbsp;
  <b>HSO</b> = Homeless Services Orthodoxy (0=reform-oriented, 100=status-quo aligned); measures investment in the prevailing $21.7M+/yr homeless services apparatus based on orthodoxy-aligned vs. accountability rhetoric in attributed speech &nbsp;·&nbsp;
  <b>Civic Temperament</b> = Collegiality + Humility + Warmth − Ego &nbsp;·&nbsp;
  <b>Clarity</b> = inverse of ego + off-mission + staff overreach + fiscal avoidance; A = clearest &nbsp;·&nbsp;
  <b>Focus %</b> = share of member's speech on core city topics (budget, infrastructure, housing, public safety) &nbsp;·&nbsp;
  <b>Focus Trend</b> ▲ improving &nbsp; ▼ declining (recent 90-day meeting focus vs. member's all-time avg) &nbsp;·&nbsp;
  <b>Change</b> = Voter Alignment vs. prior scorecard run &nbsp;·&nbsp;
  <b>Staff Refs</b> ≈ 40–80 hrs each, no opportunity-cost review &nbsp;·&nbsp;
  See page 2 for full methodology &nbsp;·&nbsp; Generated {gen_date}
</div>

{_render_procurement_watch()}

{about_page}

</body>
</html>"""


# ---------------------------------------------------------------------------
# Build ranking maps
# ---------------------------------------------------------------------------

def build_rankings(aggregate: dict) -> dict:
    members = [n for n in aggregate
               if not n.startswith("_") and n != "Ishii"
               and aggregate[n].get("words", 0) >= 1500]

    def rank_by(key, reverse=True):
        ordered = sorted(members, key=lambda x: (aggregate[x].get(key) or 0), reverse=reverse)
        return {n: i+1 for i, n in enumerate(ordered)}

    return {
        "voter":          rank_by("voter",          reverse=True),
        "composite_grade":rank_by("composite_grade",reverse=True),
        "beer":           rank_by("beer",           reverse=True),
        "recall":         rank_by("recall",         reverse=True),   # 1 = highest risk
        "efficiency":     rank_by("efficiency",     reverse=True),   # 1 = most efficient (high score)
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate_all(aggregate: dict = None, council_meta: dict = None):
    if aggregate is None:
        with open(os.path.join(SCORES_DIR, "aggregate.json")) as f:
            aggregate = json.load(f)

    meta = aggregate.get("_meta", {})
    if council_meta is None:
        council_meta = {
            "block_vote_rate":   meta.get("block_vote_rate", 0),
            "total_vote_events": meta.get("total_vote_events", 0),
            "block_vote_events": meta.get("block_vote_events", 0),
        }

    os.makedirs(PDF_DIR, exist_ok=True)
    rankings = build_rankings(aggregate)

    # Load hand-authored member summaries (archetype + prose description)
    summaries_path = os.path.join(os.path.dirname(__file__), "member_summaries.json")
    summaries: dict = {}
    if os.path.exists(summaries_path):
        with open(summaries_path, encoding="utf-8") as f:
            summaries = json.load(f)

    # Individual scorecards
    for name, s in aggregate.items():
        if name.startswith("_") or name == "Ishii":
            continue
        if (s.get("words") or 0) < 1500:
            continue
        html = render_member(s, rankings, council_meta.get("block_vote_rate", 0), meta,
                             summary=summaries.get(name, {}))
        out  = os.path.join(PDF_DIR, f"scorecard_{name}.pdf")
        HTML(string=html).write_pdf(out, stylesheets=[CSS(string="@page{margin:0}")])
        print(f"  → {out}", file=sys.stderr)

    # Summary page
    summary_html = render_summary(aggregate, rankings, council_meta, meta)
    summary_path = os.path.join(PDF_DIR, "scorecard_SUMMARY.pdf")
    HTML(string=summary_html).write_pdf(summary_path, stylesheets=[CSS(string="@page{margin:0}")])
    print(f"  → {summary_path}", file=sys.stderr)
    print(f"\nAll PDFs written to {PDF_DIR}/", file=sys.stderr)


if __name__ == "__main__":
    generate_all()
