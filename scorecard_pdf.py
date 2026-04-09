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
"""


# ---------------------------------------------------------------------------
# Build key insights for a member
# ---------------------------------------------------------------------------

def build_insights(s: dict, rankings: dict, council_block_rate: float) -> list[tuple[str,str]]:
    """Return list of (type, text) where type is 'good'|'warn'|'bad'."""
    insights = []
    n = s["canonical"]

    # Voter alignment rank
    vrank = rankings.get("voter", {}).get(n)
    if vrank == 1:
        insights.append(("good", "Most voter-aligned member on the council"))
    elif vrank and vrank <= 3:
        insights.append(("good", f"#{vrank} in voter alignment — consistently focused on core city business"))

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

    # Fiscal consistency
    hyp  = s.get("fiscal_hypocrisy_score", 0) or 0
    conc = s.get("fiscal_concern_hits", 0) or 0
    spend = s.get("action_budget_referral_total", 0) or 0
    if hyp >= 0.1:
        detail = s.get("fiscal_hypocrisy_detail", "")
        insights.append(("bad", f"Fiscal consistency flag: {detail}"))
    elif conc == 0 and spend >= 250_000:
        insights.append(("warn", f"Authored ${spend:,.0f} in budget referrals on the action calendar with no fiscal concern rhetoric in speeches"))
    elif conc >= 4 and spend == 0 and (s.get("action_off_mission_authored", 0) or 0) == 0:
        insights.append(("good", f"Fiscal concern rhetoric matches actions — {conc} deficit references, no large spending authored"))

    # Abstentions
    abs_rate = s.get("vote_abstain_rate") or 0
    if abs_rate >= 0.05:
        insights.append(("warn", f"{abs_rate*100:.0f}% abstention rate — abstentions often function as unstated 'no' votes"))

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
# Render one member scorecard
# ---------------------------------------------------------------------------

def render_member(s: dict, rankings: dict, council_block_rate: float, meta: dict) -> str:
    name = s.get("display_name", s.get("canonical", "?"))
    dist = DISTRICT.get(s.get("canonical", ""), "")
    earliest = meta.get("earliest_meeting", "Dec 2024")
    latest   = meta.get("latest_meeting",   "")
    as_of    = f"through {latest}" if latest else ""
    period   = f"{earliest} – {latest} · {meta.get('transcripts', 51)} meetings"

    # Overall grade from voter score
    voter  = s.get("voter",  0) or 0
    g_str, g_cls = letter(voter)

    # Pillar scores
    delta = s.get("_delta", {})
    pillars = [
        ("Civic Focus",         1 - (s.get("waste_pct", 0) or 0) * 0.5 + (s.get("core_pct", 0) or 0) * 0.5, "waste_pct"),
        ("Legislative Skill",   s.get("lsi",      0) or 0,  "lsi"),
        ("Fiscal Discipline",   s.get("n_fiscal",  0) or 0, "n_fiscal"),
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

    # Vote stats
    vtot = s.get("vote_total") or 0
    vyes = s.get("vote_yes") or 0
    vno  = s.get("vote_no") or 0
    vabs = s.get("vote_abstain") or 0
    bind = s.get("vote_independent") or 0
    block_pct = int(council_block_rate * 100)

    # Trend (focus = core_pct, positive = more on-topic = improving)
    ct = s.get("core_trend")
    trend_line = ""
    if ct is not None:
        direction = "improving" if ct > 0.02 else ("declining" if ct < -0.02 else "stable")
        trend_line = f"Recent focus trend: <b>{direction}</b> {focus_trend_arrow(ct)} (meeting focus {ct:+.1%} vs all-time avg)"

    # Rankings
    vrank = rankings.get("voter", {}).get(s["canonical"], "—")
    brank = rankings.get("beer",  {}).get(s["canonical"], "—")
    rrank = rankings.get("recall",{}).get(s["canonical"], "—")
    erank = rankings.get("efficiency", {}).get(s["canonical"], "—")
    total = len([k for k in rankings.get("voter",{})])
    v_badge = delta_badge(delta.get("voter"),     "voter")
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

  <div class="section">
    <div class="section-title">Voting Record</div>
    <div class="stat-grid">
      <div class="stat-box">
        <div class="stat-val">{block_pct}%</div>
        <div class="stat-lbl">Council block-vote rate<br>(all members vote same)</div>
      </div>
      <div class="stat-box">
        <div class="stat-val">{bind}</div>
        <div class="stat-lbl">Independent votes<br>(broke from majority)</div>
      </div>
      <div class="stat-box">
        <div class="stat-val">{vabs}</div>
        <div class="stat-lbl">Abstentions<br><em>(often an unstated "no")</em></div>
      </div>
      <div class="stat-box">
        <div class="stat-val">{vtot}</div>
        <div class="stat-lbl">Total vote events<br>captured in transcripts</div>
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

  {_render_agenda_section(s)}

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

def render_summary(aggregate: dict, rankings: dict, council_meta: dict, meta: dict) -> str:
    members = sorted(
        [n for n in aggregate if not n.startswith("_") and n != "Ishii"
         and aggregate[n].get("words", 0) >= 1500],
        key=lambda x: -(aggregate[x].get("voter", 0) or 0)
    )

    rows = ""
    for rank, n in enumerate(members, 1):
        s = aggregate[n]
        dn = s.get("display_name", n)
        dist = DISTRICT.get(n, "")
        vg, vc = letter(s.get("voter"))
        bg, bc = letter(s.get("beer"))
        rg, rc = letter(1 - (s.get("recall", 0) or 0))   # invert: A = most clear
        cp  = s.get("core_pct", 0) or 0
        atl = s.get("avg_turn_len", 0) or 0
        refs = s.get("staff_referrals", 0) or 0
        erank = rankings.get("efficiency", {}).get(n, "—")
        ta = focus_trend_arrow(s.get("core_trend"))
        d  = s.get("_delta", {})
        vd = delta_badge(d.get("voter"), "voter", threshold=0.015) if d else ""
        rows += f"""
        <tr>
          <td class="col-rank">#{rank}</td>
          <td class="col-name"><b>{dn}</b><br><span class="subdist">{dist}</span></td>
          <td class="col-grade {vc}">{vg}</td>
          <td class="col-bar">{pct_bar(s.get('voter', 0), 110)}</td>
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
      <div class="metric-desc">The composite score: Legislative Skill (30%), Core-topic focus (35%), and inverse off-mission time (35%). A high score means the member spends meeting time on things Berkeley residents hired them to do.</div>
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
  <b>Voter Alignment</b> = LSI 30% + Focus % 35% + Inverse-off-mission % 35% &nbsp;·&nbsp;
  <b>Civic Temperament</b> = Collegiality + Humility + Warmth − Ego &nbsp;·&nbsp;
  <b>Clarity</b> = inverse of ego + off-mission + staff overreach + fiscal avoidance; A = clearest &nbsp;·&nbsp;
  <b>Focus %</b> = share of member's speech on core city topics (budget, infrastructure, housing, public safety) &nbsp;·&nbsp;
  <b>Focus Trend</b> ▲ improving &nbsp; ▼ declining (recent 90-day meeting focus vs. member's all-time avg) &nbsp;·&nbsp;
  <b>Change</b> = Voter Alignment vs. prior scorecard run &nbsp;·&nbsp;
  <b>Staff Refs</b> ≈ 40–80 hrs each, no opportunity-cost review &nbsp;·&nbsp;
  See page 2 for full methodology &nbsp;·&nbsp; Generated {gen_date}
</div>

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
        "voter":      rank_by("voter",      reverse=True),
        "beer":       rank_by("beer",       reverse=True),
        "recall":     rank_by("recall",     reverse=True),   # 1 = highest risk
        "efficiency": rank_by("efficiency", reverse=True),   # 1 = most efficient (high score)
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

    # Individual scorecards
    for name, s in aggregate.items():
        if name.startswith("_") or name == "Ishii":
            continue
        if (s.get("words") or 0) < 1500:
            continue
        html = render_member(s, rankings, council_meta.get("block_vote_rate", 0), meta)
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
