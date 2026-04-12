# Source Document Workflow

How to add new source material to the pipeline. Each document type has a registry JSON file that inventories what exists and its scoring relevance. Only structured extracts (JSON) are committed — raw PDFs are excluded by `.gitignore`.

---

## General Principles

**URLs, not local copies.** Budget documents, ACFRs, and investment reports all have stable URLs on berkeleyca.gov. Store the URL in the registry; no local PDF needed. Policy documents (which are not directly linked from a stable URL) use dated subfolders.

**Extract, don't store.** Berkeley's PDFs are scanned images — they cannot be parsed programmatically. The workflow is: open the PDF at its URL, copy the key section (usually the first 1-3 pages), paste it in conversation, and the registry gets updated with structured data. The text extract is the permanent record.

**Registry first.** Every document gets an entry in its registry file before (or alongside) an extract. The registry entry explains why the document matters even when the extract is incomplete.

**Incidents are specific moments; audits are ground truth.** Don't create an incident for a finding that happened yesterday — wait until the council has had a reasonable opportunity to respond. An ignored audit is more damning than a fresh one.

---

## Adding an Annual Comprehensive Financial Report (ACFR)

The ACFR is the only city financial document subjected to independent external audit. It is categorically distinct from City Auditor performance reports: those are produced by a city employee; the ACFR is signed off by an independent CPA firm. The external auditor's opinion is the most authoritative financial signal available.

**Where files live:** `sources/acfr/` — PDFs are gitignored; move them here from wherever downloaded. Registry: `sources/acfr/acfr_reports.json`.

**The three FY2023–FY2025 ACFRs currently in `sources/budgets/` should be moved:**
```bash
mv sources/budgets/annual-comprehensive-financial-report-fy20*.pdf sources/acfr/
```

1. **Extract key figures** from the PDF — focus on four areas:
   - **Auditor's report** (first few pages): opinion type, any emphasis of matter paragraphs, going-concern language
   - **Management Discussion & Analysis (MD&A)**: the auditor-reviewed narrative; captures year-over-year trends in plain language
   - **Fund statements**: General Fund revenues, expenditures, ending balance
   - **Supplemental pension/OPEB schedules**: GASB 68 net pension liability, funded ratio; GASB 75 OPEB liability

2. **Update the registry entry** in `acfr_reports.json` with all extracted figures. Set `audit_opinion` — anything other than `"unmodified"` is a high-severity event requiring an immediate incident.

3. **Cross-reference against `audit_findings.json`**: The City Auditor's financial condition report cited specific figures (e.g., $694.8M net pension liability, 66% funded ratio). Verify these match the ACFR. Any divergence is itself a finding.

4. **Trend analysis** across the three-year set is the primary scoring value — a single year's ACFR has limited context; three years reveals trajectory.

5. **Create incidents** only if:
   - The external auditor issued a non-clean opinion or an emphasis paragraph that council has not acknowledged
   - A council member made a public statement that directly contradicts audited figures
   - The fund balance trend is deteriorating and the budget vote record shows no corrective action

---

## Adding a City Auditor Report

1. **Obtain the report.** Download the PDF. Do not commit it.

2. **Create a JSON extract** at `sources/audits/<audit_ref>.json`:
   ```json
   {
     "audit_ref": "unique_key_matching_registry",
     "title": "Official report title",
     "date_released": "YYYY-MM",
     "key_facts": [
       { "fact": "...", "page": 12 },
       ...
     ],
     "verbatim_quotes": [
       { "quote": "Exact language from the auditor.", "page": 5, "context": "..." },
       ...
     ],
     "recommendations": ["...", "..."]
   }
   ```

3. **Add a registry entry** in `audit_findings.json`:
   - Set `status: "pending_council_action"`
   - Fill in `key_findings`, `warranted_action`, `scoring_note`
   - Set `source_extract` to the path created in step 2
   - Leave `council_agenda_date` and `council_response` null

4. **When the audit goes before council**, update the registry entry:
   - Set `council_agenda_date` to the meeting date
   - Set `council_response` to `"received_filed"` or `"substantive_response"`
   - Document the `followup_pattern`
   - Advance `status` to `"response_documented"` once the pattern is clear

5. **Create incidents** in `incidents.json` if members acted (or failed to act) in a way that is now scoreable:
   - Use `"audit_ref": "<audit_ref>"` to link the incident to the registry entry
   - Wait until the council has had at least one meeting with the audit on the agenda
   - A receive-and-file with no companion motion is itself a scored event

---

## Adding a Budget Document

Berkeley budgets biennially (2-year cycles) with a mid-biennial adjustment, and publishes a separate 5-year Capital Improvement Program (CIP) each cycle. Operating budget and CIP are distinct documents with different extraction priorities.

**Operating budget — primary extraction target: the City Manager's transmittal letter.** This is the opening narrative where staff officially characterizes the financial picture. It is the most politically significant text in the document because it is what council members read and cite. Extract:
- Does staff acknowledge a structural deficit or imbalance, or present a balanced picture?
- What spending growth is described as necessary vs. discretionary?
- Compare language across cycles — frozen optimistic language while deficits grow is itself a signal

**CIP — primary extraction target: total unfunded capital needs.** This single number is the quantitative basis for every bond measure. If it does not decline across cycles, bonds are not solving the problem.

1. **Add a registry entry** in `sources/budgets/budget_documents.json`:
   - Set `component` to `"operating"` or `"cip"`
   - Set `cycle` to the biennial cycle it belongs to (e.g., `"FY2025-2026"`)
   - For CIPs, fill in `unfunded_capital_needs` from the document summary

2. **Create a JSON extract** at `sources/budgets/<document_ref>.json` with:
   - Verbatim City Manager transmittal language (operating budgets)
   - Unfunded needs figure with page reference (CIPs)
   - Any line items that changed significantly from the prior cycle

3. **Cross-reference** against `audit_findings.json` and other CIP entries — the static $1.65B unfunded needs figure across the FY2023-2027 and FY2025-2029 CIPs is already documented in the registry's `cross_document_finding` block.

---

## Adding a Labor Contract (MOU)

1. **Add a registry entry** in `sources/contracts/labor_contracts.json`.

2. **Create a JSON extract** at `sources/contracts/<document_ref>.json` with:
   - Contract period and ratification date
   - Per-year salary increase percentages
   - Any productivity or performance provisions (or their absence)
   - Vote record (each member's yes/no/absent)

3. **If no member requested efficiency provisions** before ratifying, that is a potential `union_deference` incident. Add it to `incidents.json` after confirming there was no off-agenda negotiation.

---

## Adding a Council Member Newsletter

Newsletters are obtained from email (subscribe directly to each district list). Plain-text copies are cached in the project so the scoring basis is preserved.

1. **Copy the newsletter body** as plain text to `sources/newsletters/text/<document_ref>.txt`. Strip HTML but keep structure. Commit the text file.

2. **Add a registry entry** in `sources/newsletters/newsletters.json`:
   - Set `text_cache` to the path from step 1
   - Fill in `scoring_signals` — specific statements or omissions that are scorecard-relevant
   - Add `incident_refs` back-links to any incidents sourced from this newsletter

3. **Common scoring patterns to watch for:**
   - Framing bond or tax measures as the only solution (without mentioning reprioritization)
   - Claiming credit for outcomes the member didn't vote for or advocate
   - Using official email lists to lobby for external spending measures

---

## Adding a Policy Statement

Policy documents from the City finance site are not reliably datestamped. Use the download date as the folder name so the version is traceable.

1. **Save the PDF** into `sources/policies/YYYY-MM-DD/` using today's date. The `.gitignore` excludes the PDF; the folder and any JSON extracts are committed.

2. **Add or update a registry entry** in `sources/policies/policy_statements.json`:
   - Set `downloaded_date` to the folder date
   - Fill in `scope` and any `documented_gaps` already known

3. **Create a JSON extract** at `sources/policies/<document_ref>.json` with:
   - Key provisions — what the policy actually commits the council to
   - Any explicit triggers, thresholds, or waiver procedures
   - Verbatim language for any provisions that are ambiguous or weak
   - Set `source_extract` in the registry entry to this path

4. **Document gaps** in the registry entry's `documented_gaps` field:
   - A gap between stated policy and council behavior is a higher-order accountability signal
   - A gap identified by the City Auditor is already documented ground truth — link it

5. **Advance `status`** from `"pending_review"` to `"extracted"` once key provisions are captured, and to `"gap_documented"` if a specific gap has been formally noted.

---

## Adding an Investment Performance Report

Quarterly reports from the City Treasurer showing pooled investment return vs. the LAIF benchmark. The scoring signal is persistent below-benchmark performance without any council inquiry.

1. **Copy the summary section** (usually the first 1-2 pages) to `sources/investments/text/<report_ref>.txt`. Commit the text file.

2. **Add a registry entry** in `sources/investments/investment_reports.json`:
   - Fill in `pooled_return_pct`, `benchmark_pct`, `basis_points_vs_benchmark`
   - Update `consecutive_quarters_below` — look at prior entries to get the running count
   - Set `source_file` to the text cache path

3. **The scoring threshold** for creating an incident is a pattern, not a single quarter:
   - 1 quarter below LAIF: note it; no incident
   - 2+ consecutive quarters below with no council inquiry: potential `alternatives_dismissed` incident
   - Council is asked and does nothing: incident warranted
   - Note total portfolio size when creating an incident — 117 bps below LAIF on $10M is noise; on $200M it is material

---

## Running the Pipeline After Updates

```bash
# Full pipeline: scrape + score + generate all PDFs
./generate.sh

# Score-only (no scraping):
source .venv/bin/activate
python pipeline.py

# Individual PDF targets:
python scorecard_pdf.py          # Member scorecards
python audit_findings_pdf.py     # Audit findings report
python council_scorecard.py      # Aggregate summary
```

Snapshots are saved to `scores/snapshots/` automatically by the pipeline and are committed to git as delta baselines.

---

## When to Create an Incident vs. Wait

| Situation | Action |
|-----------|--------|
| Auditor releases a new report | Add to `audit_findings.json`; no incident yet |
| Council receives and files the audit with no action | Create `incident` for each present member; type: `alternatives_dismissed` or `constituent_gaslight` depending on framing |
| Member makes a public statement contradicting audit findings | Create incident immediately; cite newsletter or transcript |
| Member advocates for a measure the audit identified as insufficient | Create incident; add `audit_ref` link |
| New contract ratified unanimously with no efficiency discussion | Create `union_deference` incident; note it covers all voting members |
| Policy gap identified but no council action yet | Document in `policy_statements.json`; hold incident until there's an opportunity for action |
| Single quarter below investment benchmark | Record in `investment_reports.json`; no incident yet |
| 2+ consecutive quarters below LAIF; no member has asked staff to explain | Create `alternatives_dismissed` incident; note portfolio size and cumulative opportunity cost |
| ACFR released with unmodified opinion | Extract figures; update `acfr_reports.json`; no incident unless figures contradict member statements |
| ACFR contains emphasis of matter or qualified opinion | High-severity event; create incident immediately; all members who received the report are accountable |
| New CIP shows same unfunded needs figure as prior CIP | Note in registry `cross_document_finding`; create incident when a member votes for a bond measure without acknowledging the static backlog |
