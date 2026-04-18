# Amendment Labeling Howto

## What this is

`agendas/amendment_review.csv` contains every amendment or substitute motion made
by a council member across all transcripts.  Most are procedural or planning-related
and will be labeled **neutral**.  A few may show genuine fiscal accountability
(positive) or budget gaming (negative).

Labeled rows feed directly into member scorecards via the Fiscal Stewardship Alignment score.

---

## Opening the file

Open `agendas/amendment_review.csv` in any spreadsheet (Numbers, Excel, Google Sheets).
The columns you fill in are the last three: **label**, **scoring_impact**, **notes**.

Leave all other columns untouched.

---

## Column reference

| Column | What it is |
|---|---|
| `date` | Meeting date (YYYY-MM-DD) |
| `meeting_type` | Regular or Special |
| `item_number` | Agenda item number (blank if not detected) |
| `item_title` | First 120 chars of item title from the agenda JSON |
| `member` | Council member who made the motion |
| `amendment_turn` | The full transcript turn — this is what they said |
| `before_context` | Up to 3 turns immediately before (format: `[Name] text`) |
| `after_context` | Up to 2 turns immediately after |
| `agenda_url` | Link to the full agenda for that meeting |
| `prelabel` | Auto-hint: `LIKELY_POS`, `LIKELY_NEG`, or blank — for triage only, not scored |
| **label** | **You fill this in** |
| **scoring_impact** | **You fill this in** (positive/negative rows only) |
| **notes** | **You fill this in** — quote the specific language |

---

## Label values

### `positive`
The amendment demonstrably improves fiscal accountability or taxpayer value, without
cutting P1 (fire, police, streets/maintenance) functions or adding new taxes:

- Introduces a **reporting or metrics requirement** ("require staff to submit quarterly
  performance data before further spending")
- Makes approval **conditional** on a future accountability gate
- Finds **cost-neutral funding** or explicitly offsets the cost within existing
  appropriations ("redirect from line X to fund this")
- **Reprioritizes within existing budget** rather than seeking new revenue
- Rejects or scales back a spending proposal without a P1 tradeoff

### `negative`
The amendment harms taxpayer interests or games the budget:

- **Cuts P1** (fire, police, paramedics, street maintenance, infrastructure upkeep)
  to fund non-P1 programs
- Uses **salary savings / unfilled positions / position lapse** as a funding source
  (treats a staffing gap as a piggy bank)
- Adds cost or debt without requiring any efficiency or cut analysis
- Moves a cost off-budget to avoid scrutiny

### `neutral`
Procedural change, language fix, technical clarification, organizational vote
(committee assignments, commission names), or zoning/planning amendment with no
direct fiscal or P1 consequence.  The vast majority of rows will be neutral.
**Neutral rows are discarded — do not assign a scoring_impact.**

### `skip`
Context is insufficient to judge and you chose not to open the agenda URL.
Skip rows are discarded.

---

## Scoring impact guidance

Fill `scoring_impact` only for **positive** and **negative** rows.
Use the sign that matches the label (+/−) and pick a magnitude:

| Situation | Suggested impact |
|---|---|
| Clear accountability clause, metrics requirement, or cost-neutral offset | +0.04 |
| Modest improvement (conditional language, partial offset) | +0.03 |
| Salary lapse / unfilled position used as funding | −0.03 |
| Modest P1 cut to fund non-P1 | −0.04 |
| Direct P1 cut with material dollar impact | −0.05 |

If you're unsure, use ±0.03 and note your uncertainty.

---

## Notes field

Quote the specific transcript language that justifies the label.  Brief is fine.

> "require staff to report outcomes within 90 days" → accountability condition

> "fund from vacant police positions" → salary lapse gaming

If you opened the agenda URL to confirm context, note what you found:
> "Agenda item 14: Homeless Response Team pilot — amendment added 6-month eval gate"

---

## Borderline cases

**"Friendly amendment to add a study / referral / commission review"**
→ Usually neutral.  Label positive only if the study is tied to a specific
accountability gate that delays or conditions spending.

**Substitute motion that adopts staff recommendation verbatim**
→ Neutral unless the staff recommendation itself was a fiscal improvement over
what was on the floor.  Check `before_context` to see what the original motion was.

**Amendment that reduces scope but doesn't offset cost**
→ Neutral unless the scope reduction demonstrably saves money and you can cite the
amount or mechanism.

**"I can amend my motion to just refer to committee"**
→ Neutral (procedural deferral).

---

## How to revise a label

Edit the row directly in the CSV and save.  The next time you run `./generate.sh`
(or `./generate.sh --scores-only`), the pipeline automatically detects that the CSV
has changed and re-ingests all labeled rows, replacing any previously written
amendment incidents.  You do not need to manually clean up `incidents.json`.

To un-label a row (revert to needs-review), clear the `label` cell.

---

## Running the ingestion manually

```bash
# Preview what would be written (no changes to incidents.json)
python3 ingest_amendment_labels.py agendas/amendment_review.csv --dry-run

# Write to incidents.json
python3 ingest_amendment_labels.py agendas/amendment_review.csv

# Recompute scores after ingestion
python3 pipeline.py --no-pdf
```

`./generate.sh --scores-only` does all three steps automatically when the CSV has
changed.
