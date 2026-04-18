# Berkeley City Council Scorecard — Project Specification

## Purpose

This project produces a longitudinal performance scorecard for the Berkeley City Council, evaluated from the perspective of a taxpayer focused on structural fiscal repair. It measures whether elected officials engage with Berkeley's documented P1 crises: the structural deficit, infrastructure backlog (PCI 57 vs. goal of 70), CalPERS/OPEB obligations, and reserve policy.

The reference standard is the city's own professional documents — consecutive City Manager budget messages naming a "not sustainable" structural deficit, City Auditor findings naming a $32–33M structural gap, and infrastructure audits documenting a $1.8B capital backlog.

**Key philosophical stance:** This is not a promise-keeping scorecard. Members are evaluated on engagement with documented P1 problems regardless of their campaign platforms. A member who ignores the structural deficit is not serving taxpayers regardless of their position on housing affordability, police accountability, or other issues.

---

## Repository Structure

```
council/
├── generate.sh                        # Main entry point (bash orchestrator)
├── pipeline.py                        # Master scoring script (~2,500 lines)
├── council_scorecard.py               # Transcript scoring engine (~1,100 lines)
├── scorecard_pdf.py                   # Individual + summary PDF rendering (~1,600 lines)
├── methodology_pdf.py                 # METHODOLOGY.md → PDF
├── incidents_pdf.py                   # incidents.json → PDF
├── audit_findings_pdf.py              # audit_findings.json → PDF
├── agenda_scraper.py                  # berkeleyca.gov eAgenda HTML → JSON (~630 lines)
├── annotated_scraper.py               # Annotated agenda PDF extraction (~350 lines)
├── packet_scraper.py                  # Staff report PDF parsing (~620 lines)
├── add_newsletter.py                  # Newsletter ingestion → registry (~250 lines)
├── ingest_amendment_labels.py         # CSV labels → agenda items (~195 lines)
├── ingest_framework_labels.py         # Framework tags → agenda items (~125 lines)
├── generate_amendment_review.py       # Generate amendment CSV (~250 lines)
├── generate_framework_review.py       # Generate framework CSV (~300 lines)
├── lsi_analysis.py                    # LSI component breakdown (~475 lines)
├── waste_analysis.py                  # Off-mission vs. core analysis (~500 lines)
├── mayor_scorecard.py                 # Mayor-specific facilitator scoring (~545 lines)
├── generate_html.py                   # Alternative HTML reports (~400 lines)
│
├── minutes/                           # Meeting transcript PDFs (gitignored)
├── text/                              # Extracted transcript text (.txt)
│
├── agendas/                           # Agenda JSON + vote records
│   ├── *.json                         # Pre-meeting agendas
│   ├── annotated/                     # Post-meeting attendance + roll-call votes
│   ├── reports/                       # Staff report metadata
│   ├── classified/                    # P1/P2/P3 classification CSVs
│   ├── amendment_review.csv           # Amendment labels
│   └── .amendment_labels_ingested     # Sentinel file
│
├── sources/                           # Source document registries
│   ├── council_members.json
│   ├── governance_culture.json
│   ├── p1_agenda.json
│   ├── budgets/
│   ├── acfr/
│   ├── audits/
│   ├── contracts/
│   ├── policies/
│   ├── investments/
│   └── newsletters/
│
├── audit_findings.json                # City Auditor report registry + council responses
├── incidents.json                     # Out-of-meeting behavior catalog
├── member_commitments.json            # Campaign commitments per member
├── newsletter_index.json              # Newsletter P1 coverage scoring
├── fiscal_framework.json              # Cost/non-core service taxonomy
├── member_summaries.json              # Brief member profile summaries
│
├── METHODOLOGY.md                     # Scoring logic (auto-rendered to PDF)
├── WORKFLOW.md                        # Document intake procedures
│
└── scores/                            # All outputs
    ├── aggregate.json
    ├── per_meeting.json
    ├── linked_votes.json
    ├── snapshots/
    └── pdfs/
```

---

## Processing Pipeline

```
generate.sh [--all | --scrape | --scores-only | --methodology | --scrape-only]
│
├─ 1. Preflight: verify virtualenv, pdftotext availability
│
├─ 2. [--scrape] Scrape current data from berkeleyca.gov
│      ├── annotated_scraper.py → agendas/annotated/*.json
│      └── agenda_scraper.py   → agendas/*.json
│
├─ 3. Extract text from new transcript PDFs
│      └── pdftotext -layout minutes/*.pdf → text/*.txt
│
├─ 4. [if CSV changed] Re-ingest amendment labels
│      └── ingest_amendment_labels.py amendment_review.csv
│
├─ 5. pipeline.py — main scoring orchestrator
│      ├─ Load all transcripts via council_scorecard.load_all()
│      │    └─ Detect format (chevron / boardroom / vtt)
│      │       Parse attribution, extract speaker turns
│      ├─ Score transcripts: build_scoreboard(members)
│      │    ├─ LSI (5 components: domain, fiscal, inquiry, decisiveness, process)
│      │    ├─ Character (ego / collegiality / intellectual humility / warmth)
│      │    ├─ Voter alignment (fiscal concern, revenue-seeking, waste % vs. core %)
│      │    ├─ HSO (Homeless Services Orthodoxy, 0–100 scale)
│      │    ├─ Mayor facilitator scoring (call-ons, thanks, agenda pace)
│      │    └─ Per-meeting per-member scores
│      ├─ Extract votes from transcript text
│      │    ├─ Chevron format: >> NAME\n>> VOTE
│      │    ├─ Boardroom format: state-machine attribution + VOTE
│      │    └─ Clerk-call format: CLERK calls name, member responds
│      ├─ Link votes to agenda items by item number reference
│      ├─ Load agenda classifications (P1/P2/P3, fiscal framework tags)
│      ├─ Extract sponsorships and referrals
│      ├─ Compute efficiency metrics (turn length distribution, conciseness)
│      ├─ Load newsletter silence penalties
│      ├─ Load incident adjustments
│      ├─ Score procurement integrity (waived bids, no-bid signals)
│      ├─ Merge all streams → composite scores
│      └─ Save aggregate.json, per_meeting.json, linked_votes.json, snapshot
│
└─ 6. [--all] Generate PDFs
       ├── scorecard_pdf.py    → scores/pdfs/scorecard_*.pdf (9 members + SUMMARY)
       ├── methodology_pdf.py  → scores/pdfs/methodology.pdf
       ├── incidents_pdf.py    → scores/pdfs/incidents.pdf
       └── audit_findings_pdf.py → scores/pdfs/audit_findings.pdf
```

---

## Inputs

| Category | Format | Source | Frequency |
|---|---|---|---|
| Meeting transcripts | PDF | berkeleyca.gov meetings archive | Manual drop into `minutes/` |
| Extracted transcript text | TXT | `pdftotext -layout` | Auto on pipeline run |
| Pre-meeting agendas | JSON | berkeleyca.gov eAgenda HTML | `agenda_scraper.py` |
| Annotated agendas (votes + attendance) | JSON | berkeleyca.gov PDF repository | `annotated_scraper.py` |
| Staff reports | PDF/JSON signals | berkeleyca.gov agenda packets | `packet_scraper.py` |
| Budget documents | JSON extracts | berkeleyca.gov Finance pages | `sources/budgets/` |
| ACFRs | JSON extracts | City Auditor + external auditor | `sources/acfr/` |
| City Auditor reports | JSON (verbatim + key facts) | City Auditor office | `sources/audits/` |
| Member commitments | JSON | Ballotpedia, campaign sites | `member_commitments.json` |
| Incidents | JSON | Newsletters, transcripts, public records | `incidents.json` |
| Newsletters | Text + JSON metadata | Council members' email lists | `add_newsletter.py` |
| Fiscal framework | JSON | Author specification | `fiscal_framework.json` |
| Amendment labels | CSV → applied to agendas | Author annotation | `agendas/amendment_review.csv` |
| Framework labels | CSV → applied to agendas | Author annotation | `agendas/framework_labels.csv` |

**External APIs used:**
- `berkeleyca.gov` — public HTML scraping and PDF downloads; no authentication required
- Gmail API (optional) — newsletter ingestion via OAuth2

**No AI APIs are used.** All scoring is deterministic keyword matching and structural analysis.

---

## Outputs

| Path | Format | Content |
|---|---|---|
| `scores/aggregate.json` | JSON | Per-member composite scores across all dimensions |
| `scores/per_meeting.json` | JSON | Per-meeting per-member scores for trend tracking |
| `scores/linked_votes.json` | JSON | Roll-call votes matched to agenda items with dollar amounts and P1 flags |
| `scores/snapshots/<timestamp>.json` | JSON | Timestamped aggregate snapshot (auto-committed to git) |
| `scores/pdfs/scorecard_<Member>.pdf` | PDF | Individual 3–4 page member scorecard (9 members) |
| `scores/pdfs/scorecard_SUMMARY.pdf` | PDF | One-page comparison across all members (letter grades, key metrics) |
| `scores/pdfs/methodology.pdf` | PDF | Scoring methodology document (auto-regenerated from METHODOLOGY.md) |
| `scores/pdfs/incidents.pdf` | PDF | Catalog of out-of-meeting incidents with evidence tiers and scoring impact |
| `scores/pdfs/audit_findings.pdf` | PDF | Registry of City Auditor reports with council response patterns |

---

## Scoring Dimensions

### LSI — Legislative Sophistication Index

Five components, each 0–1, composited to a single LSI score:

1. **Domain knowledge** — rate of zoning, planning, and fiscal technical language
2. **Fiscal literacy** — rate of budget, revenue, deficit, reserve, and structural language
3. **Inquiry rate** — operational questions ("How will...?", "What's the cost?") per 1,000 words
4. **Decisiveness** — preference for clear yes/no positions vs. hedging on action items
5. **Process knowledge** — parliamentary procedure and meeting governance language

### Character Assessment

- **Ego** (negative) — self-reference frequency, "I did," "my initiative"
- **Collegiality** (positive) — direct peer address, credit-sharing language
- **Intellectual humility** (positive) — "I'm learning," "we should study," acknowledgment of complexity
- **Warmth** (positive) — appreciation language, collaborative framing

### Voter Alignment

- **Fiscal concern hits** — utterances naming budget deficit, shortfall, structural gap
- **Revenue-seeking hits** — proposing new taxes/bonds without cuts-first framing
- **Waste %** — fraction of speaking time on off-mission topics
- **Core %** — fraction on core fiscal/infrastructure/public safety topics
- **P1 speech %** — rate of language on the documented P1 crisis topics

### Homeless Services Orthodoxy (HSO)

Scale 0–100, where 0 = reform-oriented and 100 = status-quo aligned. Computed from sympathy vs. skeptic keyword ratios in transcript turns about homeless services, shelter, encampments, and related programs.

An HSO score ≥ 50 applies a quadratic penalty and blocks the A+ ceiling grade.

### Agenda Authorship and Sponsorship

Items are classified into tiers:
- **P1 (cls1)** — directly engages a documented crisis (structural deficit, infrastructure backlog, pension liability, reserves)
- **P2 (cls2)** — beneficial delivery within core city mandate
- **P3 (cls3)** — discretionary, low-priority, or non-core spending

Framework tags applied to items:
- `adds_non_core` — expands non-core service footprint
- `reduces_non_core` — reduces non-core service footprint
- `entrenches_cost_premium` — locks in above-market labor or procurement costs
- `revenue_seeking` — proposes new taxes or bonds without structural reprioritization

### Facilitator Scoring (Mayor only)

- Call-on rate (per 1,000 words) — how often the Mayor distributes speaking turns
- Thanks rate (per 1,000 words) — frequency of appreciative language toward colleagues
- Agenda management rate — pace and procedural efficiency signals
- Balance — distribution of call-ons across council members

### Newsletter Coverage

Each newsletter is classified:
- **p1_coverage** — substantive engagement with deficit, CalPERS, infrastructure, or reserves
- **rhetoric_no_substance** — names "challenging budget" without structural content → −0.025
- **p1_silence** — no acknowledgment of documented P1 crises → −0.05 per missed newsletter cycle

### Procurement Integrity

Signals extracted from staff report PDFs:
- Waived competitive bid processes
- Backdated contracts
- "No alternatives" clauses
- Sole-source justifications without documented necessity

### Incidents (Out-of-Meeting Behavior)

Evidence tiers:
- **Tier A** — primary public record (agenda items, votes, official emails, official statements) → weight 1.0
- **Tier B** — reputable reporting (Berkeleyside, Berkeley Scanner, member newsletters) → weight 0.75
- **Tier C** — direct observation or author knowledge → weight 0.50

Audit-linked incidents carry an additional 0.50× multiplier to prevent double-penalizing via both the audit registry and the incident catalog.

---

## Longitudinal Decay

Rhetoric and behavioral signals decay over time. Per-meeting contributions are weighted before aggregation:

```python
effective_weight = math.exp(-DECAY_LAMBDA * age_in_years)   # DECAY_LAMBDA = 0.7
```

| Age | Weight |
|-----|--------|
| 0 (current) | 1.00 |
| 1 year | ~0.50 |
| 2 years | ~0.25 |
| 3 years | ~0.12 |

**Applied in `compute_decay_rhetoric(meetings)`** (pipeline.py): iterates per-meeting scores with dates, accumulates decay-weighted totals for `fiscal_concern_hits`, `new_revenue_preference_hits`, `sra_raw` (stored as `ego_raw` in per-meeting data), `coll_raw`, `hum_raw`, `warm_raw`. Results override flat aggregates in the scoring pipeline.

**Applied in `load_incidents()`** (pipeline.py): each incident's `raw × tier_weight` is multiplied by `decay_weight(inc["date"])` before summing. Incidents with `"no_decay": true` are exempt.

**NOT decayed:** annotated agenda votes, major fiscal votes, fiscal referral authorship, HSA score (full-text aggregation — per-meeting HSA signals not yet tracked), audit silence penalty.

**`recompute_character_decay(aggregate)`** (pipeline.py): after decay-weighted raw values are merged, re-normalizes `sra_raw`, `coll_raw`, `hum_raw`, `warm_raw` across the cohort and recomputes `character` and `voter_disconnect` scores. Mirrors `build_scoreboard()` normalization logic using decay values.

---

## Composite Grade Formula

```
composite_raw = max(0.0,
    taxpayer_alignment × 0.70
    + focus × 0.30
    − attendance_deduction
    − low_engagement_adj
)
```

**Attendance deduction** — convex curve:
- 0 absences: 0.00
- 1–2 absences: −0.05 to −0.10
- 3 absences: −0.15
- 4 absences: −0.25
- 5+ absences: −0.30 (cap)

**Low engagement adjustment** — 0 to −0.10, triggered when member authors no P1 referrals AND shows low fiscal engagement.

**Letter grade thresholds:**

| Grade | Threshold |
|---|---|
| A+ | ≥ 0.90 |
| A  | ≥ 0.83 |
| A− | ≥ 0.77 |
| B+ | ≥ 0.70 |
| B  | ≥ 0.63 |
| B− | ≥ 0.57 |
| C+ | ≥ 0.50 |
| C  | ≥ 0.43 |
| C− | ≥ 0.37 |
| D+ | ≥ 0.30 |
| D  | ≥ 0.23 |
| D− | ≥ 0.17 |
| F  | < 0.17 |

**A+ ceiling conditions** (not all currently automated):
- HSO < 50 (required; quadratic curve penalizes neutrality — currently wired)
- Infrastructure outcomes accountability (not yet wired)
- Structural balance policy adoption (not yet wired)
- Reserve policy restoration (not yet wired; reserve target lowered 2025-07)
- Investment policy compliance (not yet wired; 9 consecutive quarters of underperformance)
- Section 115 Trust non-depletion (not yet wired; shifted from +$2M → −$3–6M/year)

---

## Keyword Matching Approach

All scoring uses regex pattern matching on lowercase, punctuation-normalized text:

- Case-insensitive
- Multi-word patterns with optional intervening text: `r"pattern1.{0,30}pattern2"`
- Negative lookahead for false positives: e.g., `r"(?!\s+comment)"` to exclude procedural "go to public comment"
- OCR override table for captioning artifacts (e.g., "kisserwine" → "Kesarwani")

Key keyword sets (defined in the top ~140 lines of `council_scorecard.py`):
`WASTE_KW`, `CORE_KW`, `FISCAL_CONCERN_KW`, `REVENUE_SEEKING_KW`, `HSO_SYMPATHY_KW`, `HSO_SKEPTIC_KW`, `P1_TOPIC_KW`, `DOMAIN_KW`, `FISCAL_KW`, `OP_QUESTION_KW`

---

## Transcript Format Detection

Three formats are supported with automatic detection:

**Chevron (`>>`)** — older captioner format
```
>> SPEAKER NAME:
>> Text of their turn.
```
Vote extraction: `>> NAME?\n>> VOTE.`

**Boardroom** — Zoom captioner with state-machine attribution
```
Board Room: Text attributed to current speaker.
```
Vote extraction: state machine detecting "Clerk calls NAME," member responds with vote

**VTT (WebVTT)** — Zoom transcripts with timestamps
```
00:01:23 Board Room: Text of turn.
```
Vote extraction: timestamp + state-machine + explicit name-call detection

---

## Key Data Structures

### `scores/aggregate.json`

One entry per council member. Key fields:

```jsonc
{
  "Ishii": {
    "words": 364123,
    "is_mayor": true,

    // LSI components (all 0–1)
    "domain_raw": 0.101,
    "fiscal_raw": 0.038,
    "inq_raw": 0.927,
    "dec_raw": 0.462,
    "proc_raw": 0.022,
    "lsi": 0.443,

    // Character (all 0–1)
    "n_ego": 0.339,        // inverted: lower is better
    "n_coll": 0.0,
    "n_hum": 0.226,

    // Voting
    "vote_yes_rate": null,
    "vote_abstain_rate": null,
    "block_vote_rate": 0.917,

    // Fiscal engagement
    "fiscal_concern_hits": 10,
    "revenue_seeking_hits": 7,
    "p1_speech_pct": 0.0106,
    "waste_pct": 0.319,
    "core_pct": 0.667,

    // Agenda authorship
    "cls1_authored": 0,
    "cls2_authored": 5,
    "cls3_authored": 6,
    "cls9_authored": 4,

    // Homeless Services Orthodoxy (0–100)
    "hso": 65,

    // Composite
    "taxpayer_alignment": 0.156,
    "focus": 0.143,
    "attendance_deduction": 0.0,
    "lightweight_penalty": 0.0,
    "composite_grade_raw": 0.144,
    "grade_letter": "F",

    // Mayor-specific
    "facilitator": {
      "callons_per1k": 0.162,
      "thanks_per1k": 0.585,
      "agenda_per1k": 0.610,
      "balance": 0.484,
      "member_mentions": { "Kesarwani": 130 }
    }
  }
}
```

### `scores/per_meeting.json`

Array of meeting objects, each containing per-member score snapshots with the same ~30 metrics as aggregate.

### `audit_findings.json`

Registry of City Auditor reports and council responses:

```jsonc
{
  "streets_rocky_road_2025": {
    "title": "Rocky Road: Berkeley Streets at Risk and Significantly Underfunded",
    "date_released": "2025-10",
    "key_findings": ["PCI 57 (at-risk; goal is 70)", "..."],
    "warranted_action": "Increase GF allocation before new bonds",
    "council_agenda_date": "2025-10-28",
    "council_response": "received_filed",
    "followup_pattern": "2026-03-17: Council unanimously directed staff to develop $300M bond...",
    "status": "response_documented",
    "scoring_note": "Council knew the root cause and chose the wrong response.",
    "source_extract": "sources/audits/streets_rocky_road_2025.json"
  }
}
```

### `incidents.json`

Per-member array of out-of-meeting behavior episodes:

```jsonc
{
  "Taplin": [
    {
      "date": "2025-11-18",
      "category": "atm_behavior",
      "evidence_tier": "A",
      "description": "Authored 'Advanced Fiscal Policies — Bond Schedule'...",
      "source": "Agenda record 2025-11-18 consent item 26",
      "audit_ref": null,
      "scoring_impact": -0.08
    }
  ]
}
```

### `newsletter_index.json`

Per-newsletter coverage classifications and penalties:

```jsonc
{
  "newsletters": [
    {
      "member": "Tregub",
      "date": "2026-01-16",
      "p1_keywords_found": [],
      "fiscal_rhetoric": true,
      "fiscal_rhetoric_quotes": ["navigating a challenging budgetary year"],
      "classification": "rhetoric_no_substance",
      "notes": "Opens with budget difficulty but covers only ADU policy and micromobility."
    }
  ]
}
```

### `fiscal_framework.json`

Taxonomy of core vs. non-core city services:

```jsonc
{
  "categories": [
    {
      "id": "1A",
      "label": "Public health — city-run layer",
      "type": "non_core_substitutable",
      "est_annual_gf": "12000000-15000000",
      "description": "City-run clinics duplicating county mandate",
      "alternative": "Transfer staff to county employment; negotiate ramp-down",
      "carry_cost_note": "City health employees carry CalPERS + OPEB.",
      "political_feasibility": "moderate"
    }
  ]
}
```

---

## P1 Crisis Reference Standard

The scoring reference is Berkeley's own professional documents. The documented P1 crises are:

1. **Structural deficit** — City Manager budget messages (consecutive years) describing "not sustainable" balancing measures; City Auditor finding a $32–33M structural gap
2. **Infrastructure backlog** — PCI 57 vs. goal of 70; $42M/year needed vs. $15M/year allocated; $1.8B capital backlog
3. **CalPERS/OPEB liability** — pension costs up 23% in FY2025 alone; unfunded actuarial liability growing
4. **Reserve depletion** — combined reserves ~14.5% vs. 20–30% policy target; reserve target quietly lowered July 2025
5. **Unaccountable program spending** — homeless services at $21M+/year across 33+ programs with no outcome metrics

A member who engages with these crises in floor speech, authorship, and voting scores higher regardless of their campaign platform. A member who names the problem in newsletters but proposes bonds-first solutions without structural reprioritization is penalized for rhetoric without substance.

---

## What Is Not Measured

- Whether members kept campaign promises on non-fiscal issues (housing affordability, police accountability, etc.)
- Overall quality of representation on issues outside P1 scope
- Floor speech volume or advocacy on P2/P3 issues, except where it crowds out P1 engagement
