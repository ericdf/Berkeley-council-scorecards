# Berkeley City Council Scorecard — Methodology

**Version:** April 2026  
**Scope:** Years of city budgets, audited fiscal reports, and audit findings; 51 meeting transcripts (Dec 2024 – Mar 2026); 58 annotated agenda sessions; member campaign records and constituent communications  
**Audience:** Insiders briefing document — describes signals, sources, and weightings

---

## Philosophy

This scorecard is explicitly voter-aligned, not neutral. The evaluative framework assumes the voter cares about:

1. **Taxpayer alignment** — Does the member champion taxpayer interests, or treat property owners and residents as a funding source for their agenda? Do they demand alternatives to taxes and bonds, question efficiency, and push back on the status quo? Or do they reach for new revenue as a first resort?

2. **Focus** — Does the member spend the council's time on core city services (public safety, infrastructure, basic city operations), or on performative, ideological, and off-mission items that consume staff bandwidth and budget without delivering core value?

3. **Showing up** — Did the member actually do the job? Attendance at meetings — especially for binding fiscal votes — is the minimum bar.

**This is not a promise-keeping scorecard.** A member who campaigned on housing affordability and never mentioned the structural deficit is not evaluated on housing affordability. They are evaluated on whether they engage with Berkeley's documented P1 fiscal crises — because those crises exist regardless of what any member promised, and a representative who ignores them is not serving the taxpayer regardless of their campaign platform. A voter who wants to build a scorecard measuring housing production or homeless services expansion can do so; this one measures something different.

The scoring **does not** treat budget growth, new programs, or bond issuances as neutral acts. A YES vote on a budget adoption is a choice to endorse the status quo and forgo reprioritization. An absence during a major fiscal vote is a failure of the core duty of the office. A referral to study a new tax is the beginning of a political infrastructure campaign, not a neutral process step.

---

## Data Sources

| Source | What it provides |
|--------|-----------------|
| **Meeting transcripts** (51 PDFs, txt) | Attributed speech per member: rhetoric, debate style, fiscal language, special interest alignment signals |
| **Annotated agenda PDFs** (58 sessions) | Authoritative post-meeting record: exact attendance (roll call time, arrivals), per-item vote breakdown (Ayes/Noes/Abstain/Absent) |
| **Agenda JSONs** (58 sessions) | Pre-meeting agenda items: title, dollar amount, authors, cosponsors, off-mission flag, fiscal flags |
| **Staff report PDFs** (packet scraper) | Procurement signals: waived competitive bid, backdated contracts, no-alternatives clauses |
| **Budgets and CAFRs** (Finance Director) | Adopted annual budgets and Comprehensive Annual Financial Reports establish the city's own financial self-description: fund balances, appropriations, staffing levels, debt obligations, and the City Manager's budget message language. Distinct from City Auditor reports in origin and purpose: CAFRs are management-prepared financial statements with an external audit opinion on fair presentation; City Auditor reports are independent performance and operational audits initiated by the auditor, not management. Used to establish factual baseline — revenue trends, expenditure growth, reserve levels — against which council behavior is evaluated. |
| **City Auditor reports** (`audit_findings.json`) | Independent documented findings that establish ground truth: what the city's financial condition actually is, what structural problems exist, and what warranted action looks like. Audits are tracked in a separate registry; the council's response — or non-response — is the scored event. Three reports currently tracked: Rocky Road streets audit (Oct 2025), Homeless Response Team audit (Jul 2025), Financial Condition audit (Apr 2026). |
| **Incidents** (`incidents.json`) | Out-of-meeting behaviors: constituent interactions, public statements, newsletters, and patterns not captured in formal proceedings. Each incident is assigned one of three evidence tiers — A (primary public record), B (reputable reporting or member communications), C (direct observation) — which determine its effective scoring weight. Incidents with an `audit_ref` field are grounded in a specific City Auditor finding. |

Annotated agendas are the authoritative source for **what actually happened** (outcomes, votes, attendance). Transcripts fill the gap between plan and outcome — capturing the deliberation, rhetoric, and interpersonal style that votes alone don't reveal. City Auditor reports provide the independent factual baseline against which council action is evaluated.

**Why this reference standard matters:** The P1 problems scored here are grounded in the city's own professional documents — consecutive City Manager budget messages, City Auditor findings, infrastructure condition reports — not in the scorecard author's political preferences. A member who disagrees with the evaluation cannot simply claim it is ideological; they must dispute the City Manager's finding that the structural deficit is "not sustainable," or the Auditor's finding of a 66% pension funded ratio, or the MTC's finding of PCI 57. The city's own organization has documented what is broken. The scorecard asks whether elected officials are engaging with those findings.

---

## Scoring Tiers

### Tier 1 — Letter Grade

A single A–F composite representing overall alignment with taxpayer interests. Computed from weighted sub-scores (see below). Designed to be the one number a busy voter can reference.

**Composite formula:**

```
composite = max(0.0,
    taxpayer_alignment × 0.70 + focus × 0.30
    − attendance_deduction
    − lightweight_penalty
)
```

**Component weights and deductions:**

| Component | Role | Notes |
|-----------|------|-------|
| Taxpayer alignment | 70% weight | The core question: whose interests does this member champion? |
| Focus | 30% weight | What did they spend the council's time on? |
| Attendance deduction | Up to −0.30 | Convex curve: lenient for 1–2 absences, severe for 4–5 (see Fiscal Vote Record) |
| Lightweight penalty | Up to −0.10 | Triggered when member authors no P1 referrals AND shows low fiscal engagement (see P1/P2/P3 Framework) |

**Grade thresholds:** A+ ≥ 90 · A ≥ 83 · A− ≥ 77 · B+ ≥ 70 · B ≥ 63 · B− ≥ 57 · C+ ≥ 50 · C ≥ 43 · C− ≥ 37 · D+ ≥ 30 · D ≥ 23 · D− ≥ 17 · F < 17

---

## A+ Ceiling Conditions

A+ is not available to a member who is silent or miscalibrated on Berkeley's documented structural crises. The grade requires not just absence of bad behavior but **aspirations set at the level the city's own documents say the problems demand**. Setting sights too low on a documented crisis accepts a trajectory the city's own adopted reports describe as ruinous.

### The general principle: outcomes accountability

The core test applies to any domain where significant public money is spent:

> **A serious elected official demands measurable outcomes for significant public expenditures.** This applies equally to street maintenance, homeless services, public health, contracted social services, and staffing. The amount spent and the absence of measurement are what trigger the standard, not the political valence of the program. A member who approves or tolerates large recurring spending in any domain without requiring performance metrics, outcome data, or accountability mechanisms is not doing the job.

Silence is not neutrality. A member who does not demand accountability for a major spending program is implicitly endorsing it.

### Currently scored: Homeless Services Orthodoxy

HSO is one instance of the general principle — the one with the richest transcript signal and the best-documented evidence of unaccountable spending. Berkeley's homeless services apparatus ($21M+/yr, 33+ programs, Housing First mandate, decade of growth with no measurable reduction in visible homelessness) is where the scoring algorithm is best instrumented, not because homelessness is uniquely important but because the evidence record is clearest. A separate signal would be built for any other major program that shares the same profile: large recurring cost, clear measurable objective, council has not demanded outcome data.

HSO measures how invested a member is in the existing apparatus versus demanding accountability, outcome metrics, and reform. Scale: 0 (reform-oriented) → 100 (status-quo aligned). The scoring formula uses a quadratic curve: HSO 50 (neutral/silent) → taxpayer_alignment contribution capped at 0.25 of its maximum. A+ requires HSO well below 50 — not because demanding accountability for homeless services is uniquely virtuous, but because this is the largest unaccountable program in Berkeley's budget and neutrality on it signals a broader tolerance for unaccountable spending.

### Documented ceiling conditions not yet scored

The following are known gaps where the A+ ceiling should apply but the algorithm does not yet detect it. Each follows the same structure as HSO: significant recurring cost, measurable standard the city's own documents establish, council response that falls short.

**Infrastructure outcomes accountability.** The city's adopted goal is PCI 70. The Rocky Road audit (Oct 2025) found: current PCI ≈ 57; achieving PCI 70 requires $42M/year; the GF allocation is $2–8M/year; deferred maintenance costs $7 in repairs for every $1 spent early; delays will quadruple costs by 2050. PCI 70 is not an aspirational ceiling — it is the floor below which deterioration accelerates rapidly. A member who accepts PCI 70 as the goal without demanding the $42M/year to get there has accepted a 5× funding shortfall as normal. Same structure as HSO: large program, measurable objective, council has not demanded the outcome. *Gap: transcript signal cannot yet distinguish whether a member treats PCI 70 as a ceiling or a floor.*

**Structural balance policy gap.** The City Auditor explicitly recommended the council adopt a GFOA policy requiring assessment of whether recurring revenues match recurring expenditures. No member has moved to adopt it. Three consecutive budget cycles have included verbatim "not sustainable" findings. A council that receives that language repeatedly without adopting a structural balance requirement is not demanding accountability from its own budget process. *Gap: motion has not yet been made; absence of motion is the finding.*

**Reserve policy backslide.** The reserve target was lowered from 30% to 20–30% in July 2025, timed to avoid non-compliance rather than achieve the original goal. Combined reserves are ~14.5%, below even the revised floor. An A+ member voted against the revision or demanded a plan to reach the original target. *Gap: vote is on record; not yet wired into scoring.*

**Investment policy non-compliance.** City investments have underperformed LAIF for 9 consecutive quarters. The council receives quarterly evidence and has not acted. An A+ member has demanded corrective action on the record. *Gap: quarterly reports are on the action calendar; member response detectable in transcripts but not yet scored.*

**Section 115 Trust depletion.** The council shifted from contributing $2M/year to the pension pre-funding trust to withdrawing $3–6M/year to balance an operating budget the City Manager calls structurally unsustainable. An A+ member has objected to this trajectory on the record. *Gap: vote-based; not yet wired into scoring.*

### The common structure

Each condition follows the same pattern: significant recurring expenditure or structural obligation; measurable standard the city's own documents establish; council response that falls short; member who does not challenge the gap. Absence of objection is not neutrality — it is ratification.

The HSO condition is implemented because transcript signals are rich (sympathy/skeptic keyword matching across 51 meetings). The others await vote-record wiring (reserve policy, Section 115) or improved transcript pattern detection (infrastructure, structural balance). All are planned.
---

## P1/P2/P3 Priority Framework

Council work is tiered by urgency and alignment with Berkeley's documented structural problems.

| Tier | Label | Definition | Examples |
|------|-------|-----------|---------|
| **P1** | Crisis work | Directly addresses a documented structural problem (fiscal deficit, infrastructure backlog, pension liability, core services) | Budget reprioritization, fiscal referrals, no votes on spending, demand for efficiency data |
| **P2** | Beneficial delivery | Legitimate city function with a clear, measurable objective — not in crisis, but real | Housing project approvals, specific public art commissions, parks maintenance, public safety equipment |
| **P3** | Discretionary / ceremonial | Within Berkeley's general authority but low-priority, unaccountable, or purely performative | Cultural festivals, proclamations, arts grant programs, out-of-jurisdiction resolutions |

**The P1 engagement test:** A member who generates only P2 activity — approves contracts, shows up for votes, stays out of trouble — but never engages with the P1 crises documented in the city's own reports is not doing the full job. A member who generates P3 activity while P1 problems go unaddressed is actively substituting low-priority work for the high-priority work the city's own documents say is urgent.

**Scoring implication:** Members with zero P1 referrals authored and low fiscal engagement (fiscal vote presence + fiscal concern rate) receive a low P1 engagement penalty of up to −0.10 applied to the composite grade. The penalty scales with the engagement gap — a member with no P1 referrals but high fiscal concern rhetoric and consistent vote attendance receives no penalty; a member with no referrals, low rhetoric, and frequent absences receives the full penalty.

---

## Consent Calendar Classification

Consent calendar items — passed en bloc without floor debate — are classified into five tiers that feed into the agenda scoring and P1/P2/P3 analysis.

| Class | Label | What it means | Examples |
|-------|-------|--------------|---------|
| **1** | P1 core | Directly addresses a documented structural crisis | Police staffing, fire equipment, infrastructure contracts, budget amendments |
| **2** | P2 delivery | Legitimate city function, clear deliverable | Housing project approvals, specific public art commissions, park improvements, fleet maintenance |
| **3** | P3 discretionary | Within city authority but low priority or performative | Cultural festivals, arts grant programs, proclamations, council office budget relinquishments |
| **8** | Administrative necessity | Has to happen regardless; minimal policy content | Minutes approval, bid solicitations, routine contract renewals, CalPERS side letters, grant applications for ongoing programs |
| **9** | Questionable scope | City doing what another body should do, or shouldn't be doing at all | County health service duplication, out-of-jurisdiction resolutions, non-competitive personnel rules, vague consulting without deliverables |

**Art commissions:** Specific public artwork contracts for named artists at named locations are class 2 (city delivers public art). Arts consulting, strategic planning, and grant-award programs are class 3 (program overhead). Grant acceptance for ongoing programs is class 8 (administrative).

**Class 9 vs. class 3:** Class 3 items are low-priority but within Berkeley's appropriate scope. Class 9 items represent scope the city arguably should not carry — county service duplication, political advocacy outside city authority, and governance structures that insulate dysfunction from accountability.

Consent calendar classifications are stored in `agendas/classified/consent_items_classified.csv` (594 items, Dec 2024–Apr 2026). Distribution: 1=41, 2=268, 3=58, 8=174, 9=53.

Action calendar classifications are stored in `agendas/classified/action_items.csv` (175 items, Dec 2024–Apr 2026). Distribution: 1=40, 2=47, 3=17, 8=56, 9=15.

**Classification is topic-tier, not quality-of-response.** A P1 topic handled badly (e.g., a ballot-measures funding discussion that defaults to new taxes without contemplating cuts) is still class 1 — it addresses the right problem. The pipeline scores the quality of the response separately via fiscal concern rhetoric, revenue-seeking signals, and vote record. Classifying it as P3 would undercount the council's P1 engagement; the penalty for the wrong answer belongs in the scoring layer, not the classification layer.

---

### Tier 2 — Key Facts (visible on main scorecard)

Three plain-language facts that explain the grade. No jargon.

#### Showed Up
- **Source:** Annotated agenda PDFs (authoritative roll call records)
- **Components:** Sessions fully absent (never arrived) · Sessions late at roll call · Fiscal vote absences
- **Framing:** "Present for X of Y major budget votes" is the key line — budget votes are the council's most consequential act and absences on them are the primary attendance signal regardless of excuse

#### Stayed Focused
- **Source:** Transcripts + agenda item classification
- **Metric:** Focus % = (core-service words / total words) − (off-mission words / total words), normalized 0–100
- **Core services:** public safety, infrastructure (roads, sidewalks, utilities, facilities), permitting, basic city operations, bicycle transportation infrastructure
- **Off-mission:** foreign policy statements, ideological resolutions, performative oversight theater, fluff programs without measurable outcomes
- **Borderline / neutral:** Arts programming and cultural events are not scored as off-mission by default — they are a city function, albeit a lower-priority one. They are noted if a specific incident shows them being used to crowd out or distract from more consequential work.
- **Scope-creep within core items:** Even a core-service measure can be penalized if it is loaded with off-mission additions — e.g., bundling protected cycle tracks in new locations, environmental enhancements, or ideological carve-outs into a streets repair measure converts a straightforward repair obligation into a progressive amenity program. The focus signal captures this at the agenda item and transcript level.
- **Framing:** The council has limited time and staff bandwidth. Every off-mission item is a choice to not work on something that matters.

#### Taxpayer Alignment
- **Source:** Transcripts + annotated agenda votes + agenda item authorship
- **This is the most important dimension.** A member who talks fiscal restraint but authors bond referrals and votes yes on every budget is doing something specific: treating new revenue as the default rather than the last resort. A member who demands efficiency data, questions alternatives to new revenue, and actually votes no on bloated items is representing the payer.
- **Key sub-signals** (see Tier 4 for detail):
  - Fiscal concern rhetoric rate (mentions of cost, efficiency, alternatives per 10k words)
  - Off-mission items authored (active choice to consume budget on non-core items)
  - Revenue-seeking: authored/supported new tax or bond measures without accompanying cut analysis — scored *negative*, not neutral (see below)
  - Rhetoric-action gap: voiced fiscal concern AND voted yes on large spending items
  - Votes no on spending (rare and high-signal)
  - Special interest alignment score (inverse: deeper alignment with a spending constituency's status quo — e.g. homeless services apparatus, cycle track advocacy — without demanding accountability for outcomes = less taxpayer-aligned; HSO is the primary implemented instance)
- **Revenue-seeking vs. fiscal concern:** These are not the same signal. Asking "what can we cut?" is fiscal work. Asking "should we put a bond on the ballot?" is identifying a revenue path without doing the reprioritization work first. The two are tracked separately. Revenue-seeking without companion cut analysis scores negative (up to −0.10). Partial credit applies if the same member also uses fiscal probing language (cut_credit).

---

### Tier 3 — Informed Voter

Metrics that require some familiarity with how city government works, but are explainable in a sentence.

#### Character & Conduct
- **Source:** Transcripts and constituent communications
- **What it measures:** A measure of the member as a colleague and public servant. Combines four dimensions: collegiality (acknowledges and builds on others' contributions), humility (updates positions when presented with new information), warmth (treats staff, colleagues, and the public with genuine respect), and self-referential appeals (instances where a member relies on personal identity, credentials, history, or self-positioning as persuasive support in place of substantive argument or evidence — lower is better).
- **Formula:** `Character = 0.35×collegiality + 0.25×humility + 0.20×warmth + 0.20×(1 − self-referential appeals)`
- **Evidentiary basis:** Text analysis

#### Voter Disconnect
- **Source:** Transcripts + vote record
- **What it measures:** Composite signal for how out-of-step a member is with a constituent who expects fiscal accountability. High voter disconnect = high off-mission speech, high self-referential appeals, and low fiscal engagement.
- **Formula:** `Voter Disconnect = 0.40×waste% + 0.30×self-referential appeals + 0.30×(1 − fiscal engagement)`

#### Homeless Services Orthodoxy (HSO)
*The primary implemented example of special interest alignment scoring.*
- **Source:** Transcripts + agenda cosponsorship
- **Scale:** 0 (reform-oriented) → 100 (status-quo aligned)
- **What it measures:** How invested is the member in the existing homeless services apparatus — $21.7M+/yr across 33+ programs, Housing First mandate, low-barrier ideology — versus demanding accountability, outcomes data, and reform?
- **Why it matters:** HSO is the primary implemented instance of the general outcomes-accountability principle (see A+ Ceiling Conditions). Berkeley's homeless spending has grown for a decade with no measurable reduction in visible homelessness. The same standard — demand metrics, question the model, require accountability for results — applies to any major program, but this is where the evidence record and transcript signal are richest. A member who champions more spending and resists outcome metrics is not representing the taxpayers who fund the program.
- **Score distribution:** See current scorecard output. High scores indicate deep alignment with the existing homeless services apparatus and resistance to accountability reform; low scores indicate a reform or outcomes-focused orientation.

#### Block Vote Rate
- **Source:** Transcripts (roll-call extraction)
- **Council-wide rate:** ~92% of votes are unanimous
- **What it means:** The council almost never disagrees in public. This is a council-level finding, not a per-member score. Individual deviations (no votes, abstentions) are tracked separately and are high-signal precisely because they are rare.

---

### Tier 4 — Inside Baseball

Detailed signals for readers who want to understand the methodology or propose changes.

#### Rhetoric-Action Gap
- **Source:** Transcripts cross-referenced with agenda vote/authorship records
- **Logic:** A member who frequently invokes fiscal discipline language AND authors large spending items or off-mission agenda items is doing something specific. The score measures the gap between stated fiscal concern and revealed spending behavior. A gap of zero — rhetoric and action aligned — is available to any member who either stops the rhetoric or starts acting on it.
- **Threshold:** Triggered when fiscal concern rate ≥ 0.5 mentions/10k words AND spend authored ≥ $500k

#### Staff Referrals
- **Source:** Transcripts
- **What it measures:** How often a member directs staff to study, prepare, or report on something. Each referral consumes staff bandwidth. Classified by whether the referral topic is core-service or off-mission.
- **Why it's "inside baseball":** The mechanism (staff referrals as a budget and bandwidth tool) is familiar to city-government watchers but opaque to general voters.

#### Sponsorships
- **Source:** Transcripts (self-identification as author or co-author)
- **What it measures:** How often a member brings or co-sponsors agenda items. More sponsorships = more active agenda-setting. Combined with off-mission classification to distinguish productive from wasteful.

#### Procurement Signals
- **Source:** Staff report PDFs (packet scraper)
- **Signals tracked:** Waived competitive bid · Backdated/retroactive contracts · No alternatives considered
- **What it measures:** How often does a member vote yes on contracts or spending items with procurement red flags? This is a passive measure (most procurement is staff-driven) but patterns over time reveal whether members ask questions before approving.

#### Annotated Vote Statistics
- **Source:** Annotated agenda PDFs (all 58 sessions)
- **Fields:** annot_vote_total · annot_vote_yes · annot_vote_no · annot_vote_abstain · annot_vote_absent · annot_abstain_rate · annot_contested_abstain
- **Abstention semantics:** "I chose not to use my voting power on this matter." A pattern of abstaining signals disengagement, masked disagreement (fear of voting no), or failure to prepare. The council is elected to vote. Systematic abstention is a failure of the job function — constituents deserve a position, not a pass.
- **Contested abstentions** (abstaining when ≥1 other member voted no) are the highest-signal variant: the member knew there was a real choice to make and declined to make it. This is the strongest indicator of conflict avoidance over representation.
- **Current findings:** See current scorecard output for per-member abstention rates and contested abstention counts.

#### Fiscal Vote Record (Major Binding Votes)
- **Source:** Annotated agenda PDFs, cross-referenced with curated vote list
- **7 binding fiscal votes tracked** (Dec 2024–Apr 2026):
  1. 2025-01-21 · CMFA Bond – 2001 Ashby Ave · $44.9M
  2. 2025-05-20 · Lease Revenue Notes – Fire HQ · $11M
  3. 2025-05-20 · GO Bonds – Measure O Housing · $35M
  4. 2025-05-20 · FY2025 Budget Amendment (1st reading) · $85.7M
  5. 2025-06-03 · FY2025 Budget Amendment (2nd reading) · $144M
  6. 2025-06-24 · FY2026 Budget Adoption (1st reading) · $1.45B
  7. 2025-07-08 · FY2026 Budget Adoption (2nd reading) · $1.52B
- **Budget adoption framing:** A YES vote is not neutral. It is a choice not to cut, not to reprioritize, and not to address Berkeley's structural deficit. Every member present voted yes unanimously on the FY2026 budget at 1am.
- **Attendance deduction curve:** Uses a convex power curve: `(absences/total)^1.5 × 0.25`. This is lenient for 1–2 absences (−0.013 and −0.038) and severe for 4–5 absences (−0.120 and −0.151). The design reflects the judgment that one missed vote can have a real excuse; missing most major votes signals a different disposition. Maximum attendance deduction: −0.25.

---

## Audit Findings Stream

City Auditor reports are a separate evidentiary stream from incidents. They are not scored directly — the council's *response* to an audit is what gets scored.

**Why this distinction matters:** Incidents capture specific moments of individual behavior. Auditor reports establish independent, documented ground truth: facts the council is obligated to know, findings that create a duty to act, and a record that removes the ability to claim ignorance. When a council member subsequently acts in a way that contradicts a documented audit finding, that action is now interpretable as a choice — not a gap in knowledge.

**How audits feed into scoring:**
1. An audit is released and enters the registry (`audit_findings.json`) with key findings, auditor recommendations, and the action a taxpayer-aligned council should take.
2. When the audit goes on the council agenda, the council's first response is recorded. "Receive and file" without a companion motion is the baseline failure; a substantive motion by any member is the positive signal.
3. Subsequent council actions that contradict audit findings are scored harder because the ground truth is documented. A vote for a fifth bond cycle *after* receiving an audit that identified GF underfunding as the root cause of street decay is a different act than the same vote without that record.
4. Incidents that are grounded in an audit cite the registry key via the `audit_ref` field in `incidents.json`.

**Ordinary voters will not read City Auditor reports.** The audit findings registry (`scores/pdfs/audit_findings.pdf`) does that work — it translates what each audit found, what was warranted, and what the council actually did into a readable record. The pattern across audits — findings received, filed, and converted into bond campaigns — is the accountability story the scorecard is designed to tell.

**Audits currently tracked** (see `audit_findings.json`):
- `streets_rocky_road_2025` — Rocky Road streets audit (Oct 2025): response documented; council received and filed, then directed a $300M bond with no GF reprioritization motion
- `homeless_response_team_2025` — HRT audit (Jul 2025): pending council action; findings primarily staff-operational
- `financial_condition_2026` — Financial condition audit (Apr 2026): pending council action; $32–33M structural deficit, 66% pension funded ratio, $1.8B unfunded capital, GFOA policy gap

---

## Incident Tracking

Transcripts and agenda records capture what happens on the dais and in formal meetings. They do not capture everything that matters.

**Incidents** are documented behaviors or actions observed outside formal council proceedings that reveal something meaningful about a member's disposition toward taxpayers, constituents, or public resources. Examples:

- A constituent interaction that reveals a pattern of evasion or performative engagement
- A public statement expressing a preference for borrowing over cutting
- A pattern of scheduling "input meetings" after votes have already occurred
- An observable disposition (e.g., backing a new institution built on demographic grievance rather than service gaps) that is visible in their agenda record but not explicitly verbalized

### How incidents are documented

Incidents are stored in `incidents.json` with structured fields:

| Field | Contents |
|-------|----------|
| `category` | One of seven categories (see below) |
| `date` | Date or approximate period |
| `description` | Plain-language description of the behavior |
| `source` | How the behavior was observed or established |
| `scoring_impact` | Suggested adjustment to composite score (typically −0.10 to +0.10) |
| `evidence_tier` | A / B / C — see below |
| `audit_ref` | Optional. Key into the auditor registry when the incident is a response to a specific audit finding |

#### Evidence tiers

The strength of a claim should be proportional to the strength of the evidence behind it. Each incident is assigned a tier that determines its effective weight in scoring:

| Tier | Definition | Weight |
|------|-----------|--------|
| A | Primary public record: agenda items, vote records, official city emails, member official statements and farewell letters | 1.00 |
| B | Reputable reporting or personal newsletters: Berkeleyside, Berkeley Scanner, member personal-domain email | 0.75 |
| C | Direct observation or author knowledge: scorecard author's firsthand account without contemporaneous documentation | 0.50 |

Incidents with an `audit_ref` receive an additional **0.50× multiplier** on top of their tier weight. The audit mechanism already penalizes the council's failure to act on a finding; the incident captures the specific member's behavior within that context. Applying full incident weight on top of the audit penalty would double-charge the same underlying failure.

### Incident categories

| Category | Direction | What it captures |
|----------|-----------|-----------------|
| `revenue_without_cuts` | Negative | Sought new revenue without first asking what can be cut or done more efficiently |
| `performative_engagement` | Negative | Held meetings or sought input after decisions were made; performative not deliberative |
| `alternatives_dismissed` | Negative | Explicitly closed off alternatives without analysis or evidence |
| `claimed_ignorance` | Negative | Claimed not to know something they were obligated to know |
| `union_deference` | Negative | Sided with city unions without requesting productivity data or efficiency tradeoffs |
| `fiscal_integrity` | **Positive** | Pushed back on spending, demanded cost data, or advocated for cuts |
| `constituent_service` | **Positive** | Genuinely responsive constituent engagement with demonstrated follow-through |

### How incidents feed into scoring

The strength of a claim should be proportional to the strength of the evidence behind it. Each incident's raw `scoring_impact` is multiplied by its tier weight before being summed (see evidence tier table above). Incidents linked to a City Auditor finding via `audit_ref` receive an additional 0.50× multiplier: the audit mechanism already penalizes the council's failure to act on a finding; the incident captures the member's specific behavior within that context. Applying full incident weight on top of the audit penalty would double-charge the same underlying failure.

Weighted incident totals are capped at ±0.30 per member before being applied as an adjustment to the **Taxpayer Alignment** component of the composite grade. The cap prevents any single member's incident record from dominating the overall score.

Members with no incidents in the log are not assumed clean — it means nothing has been documented yet. A member with many incidents has a richer evidentiary record.

#### Audit silence

A separate penalty applies to members who were present at a formal audit presentation, voted to receive and file, and produced no follow-up motion within the response window. This is distinct from an incident: it is an automated signal for undifferentiated silence. Members who have a documented incident with an `audit_ref` matching the audit are exempt — their behavior post-audit is already individually characterized, whether positive or negative. Members in the `follow_up_authored_by` list in `audit_findings.json` are also exempt.

The silence penalty is −0.04 per audit event, applied to Taxpayer Alignment before the composite calculation.

The full incident catalogue is rendered as a separate PDF (`scores/pdfs/incidents.pdf`) for sharing with readers who want to see the underlying evidence behind scores.

---

## Structural Context

These facts are not per-member scores but inform what "taxpayer-aligned" means in Berkeley's specific context. Any member who does not publicly challenge these structural problems is implicitly endorsing them.

- **Staffing level:** Berkeley has more city employees per resident than any other city in California. This is not a measure of service quality — it is a measure of cost structure. The city duplicates services provided by Alameda County (e.g., maintains its own Health Department when every comparable city uses the county Health Department instead). The result is a fixed cost base that is among the highest in the state, with no corresponding premium in outcomes.
- **COVID precedent:** During COVID-19, the then-Mayor declared every city employee an "essential worker" — explicitly exempting all city staff from layoffs even as workloads (e.g., library pages with no books to shelve) collapsed. Other jurisdictions used the pandemic as a forcing function to reprioritize, eliminate redundant positions, and restructure. Berkeley did none of this. No current council member has proposed revisiting that precedent or conducting a post-COVID staffing review.
- **Duplication of county services:** Berkeley operates a standalone Health Department, mental health division, and homeless response infrastructure that parallel and sometimes conflict with Alameda County services. The City Auditor's 2025 review of the Homeless Response Team documented this fragmentation. No council member has proposed consolidating with county services as an efficiency measure.
- **Financial Condition Audit (April 2026):** The City Auditor's FY2016–FY2025 financial condition review documents a city in structural imbalance, with no corrective trajectory visible in council action:
  - **Structural deficit:** General Fund projected deficit of $32M (FY2027) and $33M (FY2028). Recent budgets were balanced using one-time measures: $4.7M from the workers' compensation reserve (FY2025) and a $3M withdrawal from the Section 115 pension pre-funding trust.
  - **Spending growth:** GF expenses grew 33% in real terms over the audit period; government-wide expenses grew 20% in real terms. Largest category growth: community development/housing +119%, health/welfare +107%. Salaries and benefits represent approximately two-thirds of the GF budget.
  - **Staffing growth:** FTE count grew 30%, from 1,336 to 1,747. The audit does not assess productivity per employee; no council member has publicly requested this analysis. Two related questions also go unasked: (1) **Technology-driven redundancy** — where technology has replaced manual work (e.g., license-plate-reader enforcement replacing manual permit sales), the positions that technology displaced remain on payroll with no council inquiry into whether those roles have been reassigned to genuine need or simply retained; (2) **Outsourcing assessment** — Berkeley employs its own refuse collectors, a practice no comparable city in the region maintains; no council member has requested an analysis of services that could be delivered more efficiently by contract. Both questions represent standard public-sector cost management that the council has not applied.
  - **Pension risk:** Net pension liability of $694.8M; funded ratio 66% (categorized as "high risk" and tied for 2nd-worst among comparable jurisdictions). Annual pension payments rising from $76M (FY2024) to projected $108M by FY2034. The Section 115 trust — a pension pre-funding reserve designed as a rainy-day buffer — has met its annual contribution goal in only 2 of 7 years and had $3M withdrawn in FY2025 to help balance the operating budget.
  - **Capital collapse:** Unfunded capital and deferred maintenance grew from $603.5M (FY2017) to $1.8B (FY2024). The required biennial unfunded capital liability report for FY2025 was not produced — city management cited "limited staff time." The council cannot deliberate on what it has not been shown.
  - **GFOA policy gap:** The council's adopted fiscal policies do not require assessing whether recurring revenues match recurring expenditures — a foundational GFOA best practice. The auditor explicitly recommends the council adopt this requirement. No member has moved to do so.
  - **Debt trajectory:** GO bonds of $205.4M represent 80% of outstanding debt ($1,524/resident). The proposed $300M infrastructure bond (2026 ballot) would increase debt service tax rates for approximately 20 years before declining — layered on top of a structural operating deficit that borrowing cannot solve.
  - **Council response to date:** The unanimous March 2026 vote to commission a $300M bond survey — taken with full knowledge of the structural deficit, the Section 115 withdrawal, and the pension trajectory — is the clearest available evidence of the council's revealed priority ordering: new debt over structural repair.

---

## Known Limitations and Open Questions

- **Transcript coverage:** Not all meetings have transcripts; some are garbled or poorly formatted. Rhetoric scores are only as good as the transcript quality.
- **Rhetoric-action gap:** A member who frequently invokes fiscal discipline language but authors large spending items and votes yes on every budget is doing something specific: using fiscal rhetoric as cover rather than as a guide to action. The `rhetoric_action_gap_score` pipeline variable partially captures this gap but could be refined.
- **Borrow-first language:** Members who express a preference for systematic bond issuance over general fund reprioritization — framing new debt as the natural response to infrastructure gaps rather than a last resort — are signaling a revenue-first disposition. This is currently captured weakly in transcript rhetoric — a dedicated signal is planned.
- **Tax/bond referral tracking:** Authoring or cosponsoring a referral to study a new tax or bond is the first step in a political infrastructure campaign. Now tracked as `FISCAL_REFERRAL_VOTES` (a curated list of upstream steps toward bond/tax ballot measures) and scored via `score_fiscal_referral_votes()`: −0.03 per item authored, −0.01 per item supported as cosponsor or aye vote, capped at −0.09. Weighted into taxpayer alignment as of April 2026.
- **Union and labor posture:** Members who consistently side with city unions in labor negotiations (without asking for productivity data or considering service-level tradeoffs) are imposing costs on taxpayers. Currently not scored directly.
- **Street paving misallocation:** Berkeley's streets are among the worst in Alameda County — and the council's response has been an unbroken cycle of bond measures with no corresponding general fund reprioritization. Key facts from audit and city reporting: the Pavement Condition Index (PCI) was ~57 as of 2024, rated "at risk" by the Metropolitan Transportation Commission — 10 points below the regional average and 3 below the threshold where "deterioration accelerates rapidly." Deferred maintenance backlog exceeds $250M. From 2018–2022 the city paved less than 3 miles/year; in 2018 zero streets were paved because staff failed to get bids out in time. General fund allocation to streets was $4.9–11.3M/year through 2020 — the council had to adopt a formal $15.3M/year commitment by policy in 2022 simply to commit to the minimum baseline. Achieving a PCI of 70 would require $42M/year. Regular maintenance is 5–10x cheaper than rehabilitation (MTC). The council's bond cycle: Measure M (2012) → T1 (2016) → L (failed at 59%, needed 2/3, 2022) → EE/FF (2024, best-case projected to merely hold PCI at 57) → new $300M bond + half-cent sales tax on 2026 ballot. No member has publicly called for the general fund reprioritization that would actually close the gap. Documented partially through incident tracking; not yet a dedicated pipeline signal.
- **Measure FF endorsement (2024 ballot):** The pre-2025 City Council endorsed Measure FF over Measure EE in the November 2024 election. Measure EE was the simpler parcel tax focused on street and sidewalk repair. Measure FF was the larger, more expensive version that bundled in protected cycle tracks where none existed, environmental enhancements, and green infrastructure alongside streets. Structurally, this endorsement reveals a standing disposition: even when addressing a core-service crisis (street decay), the council preferred the vehicle that includes progressive amenities. Council members seated at the time are attributable to this endorsement; members elected in November 2024 are not. This is a council-level contextual finding rather than a per-member scored incident. Bicycle transportation infrastructure (bike lanes, bike boulevards, maintenance of existing facilities) is considered core service; new cycle track construction in locations where none existed is scope expansion.
- **Constituent newsletter as advocacy:** Members occasionally use official constituent communications to mobilize support for county-level spending measures. This is outside a councilmember's jurisdiction and compounds taxpayer burden across city and county levels. County and city measures are additive obligations on the same tax base — members typically avoid cross-advertising to prevent voters from calculating cumulative burden. Documented through incident tracking; not yet a scoring signal.
- **Committee participation:** The Finance Committee and Budget & Finance Working Group are where substantive fiscal deliberation often occurs, but their minutes record only votes — not participation, debate, or the questions members asked. A member who does serious fiscal work in committee and is quieter in plenary sessions would be undercounted; a member who performs engagement in plenary while contributing nothing in committee would be overcounted. This gap is unresolvable with publicly available records.
- **Composite grade calibration:** The Tier 1 letter grade is implemented and producing results (as of Apr 2026). The formula (70% taxpayer, 30% focus, attendance/lightweight deductions) will continue to be refined as more data accumulates.
- **Fiscal referral author-matching:** The agenda JSON parser may not always identify the primary author of a referral item when authorship is attributed informally or through co-sponsorship structures. Members whose referral activity is undercounted via the automated parser should be cross-checked against the manual incident record. A more robust author-matching pass is planned.

---

## Proposing Changes

This document is the authoritative description of the scoring methodology. If you want to propose a new signal, adjusted weight, or different framing:

1. Identify which tier the signal belongs to
2. Describe the data source (transcript keyword, annotated agenda field, agenda item flag)
3. Describe the direction of scoring (higher = better or worse for taxpayers?)
4. Propose a weight relative to existing signals in that tier

Send proposals to the maintainer. The underlying pipeline (`pipeline.py`) is modular — adding a new scoring function is straightforward once the signal is well-defined.
