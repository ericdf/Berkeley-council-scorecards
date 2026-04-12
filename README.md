# Berkeley City Council Scorecard Pipeline

## What This Is

A longitudinal performance scorecard for the Berkeley City Council, evaluated from the perspective of a taxpayer who wants Berkeley's documented structural fiscal problems addressed.

**The reference standard is the city's own documents** — consecutive City Manager budget messages using the phrase "not sustainable," City Auditor findings naming a $32–33M structural deficit, infrastructure audits documenting a $1.8B capital backlog and a streets PCI 13 points below the goal. These are not the scorecard author's opinions. They are the professional staff's documented findings. The question the scorecard answers is: *given what Berkeley's own organization has said is broken, are these elected officials engaging with those problems or not?*

**This is not a promise-keeping scorecard.** A member who campaigned on housing affordability and never mentioned the structural deficit is not evaluated on housing affordability. They are evaluated on whether they engage with the documented P1 fiscal crises — because those crises exist whether or not a member promised to address them, and a representative who ignores them is not serving the taxpayer regardless of their campaign platform.

The scorecard draws on seven independent signal streams, accumulated longitudinally:

| Stream | What it reveals |
|--------|----------------|
| **Member commitments** (`member_commitments.json`) | What each member told voters at election — the baseline for observing divergence between stated and actual priorities |
| **City budgets and audits** (`audit_findings.json`) | Ground truth: what the structural problems are, independently documented |
| **Incidents** (`incidents.json`) | Discrete behaviors outside formal meetings — constituent interactions, public statements, newsletters — at three evidence tiers (A/B/C) |
| **Constituent newsletters** (`newsletter_index.json`) | How members communicate Berkeley's fiscal situation to constituents — scored for engagement with P1 problems vs. silence or rhetoric-without-substance |
| **Meeting transcripts** (`text/`) | How members use their speaking time — fiscal language rate, P1 engagement share, rhetorical style, HSO alignment |
| **Agendas** (`agendas/`) | Where members focus legislative energy — P1/P2/P3 tier of items authored, consent vs. action calendar distribution |
| **Votes** (`agendas/annotated/`) | Outcomes — attendance on fiscal votes, amendment behavior, abstention patterns |

These streams are not equally reliable and are not treated as equally reliable. The scoring architecture weights each signal by evidence quality and applies caps to prevent any single stream from dominating.

See **`METHODOLOGY.md`** (or `scores/pdfs/methodology.pdf`) for a full description of signals, sources, scoring philosophy, and tier structure.

---

## Prerequisites

```bash
brew install poppler          # pdftotext for transcript extraction
mkvirtualenv council          # requires virtualenvwrapper
pip install -r requirements.txt
```

`.venv` is a symlink to `~/.virtualenvs/council` — both `workon council` and
`source .venv/bin/activate` work interchangeably.

---

## Common Tasks

### Build scorecards from existing data
No new transcripts, no network requests — just regenerate everything from cached data.

```bash
./generate.sh
```

### Add a new meeting transcript
Drop the transcript PDF into `minutes/`, then:

```bash
./generate.sh
```

`generate.sh` detects which PDFs haven't been extracted yet and processes only those
before rescoring and regenerating all PDFs.

### Refresh attendance and agenda data from berkeleyca.gov, then rebuild
Pulls updated annotated agenda PDFs and agenda JSONs before running the full pipeline.

```bash
./generate.sh --scrape
```

### Iterate on scoring logic without waiting for PDF generation
Edit `pipeline.py` or `council_scorecard.py`, then run quickly:

```bash
./generate.sh --scores-only
```

Skips scorecard PDFs. Still updates `aggregate.json` and regenerates `methodology.pdf`.

### Update the methodology document
Edit `METHODOLOGY.md`, then:

```bash
./generate.sh --methodology
```

`methodology.pdf` is also regenerated automatically at the end of every full
`./generate.sh` run.

---

## Artifacts Produced

```
scores/
  aggregate.json              — per-member composite scores (all dimensions)
  per_meeting.json            — per-meeting scores for trend tracking
  linked_votes.json           — roll-call votes matched to agenda items
  snapshots/                  — timestamped aggregate snapshots (delta tracking)
  pdfs/
    scorecard_<Member>.pdf    — individual member scorecard
    scorecard_SUMMARY.pdf     — one-page comparison across all members
    methodology.pdf           — insider methodology document
    incidents.pdf             — documented out-of-meeting incident catalogue
    audit_findings.pdf        — City Auditor report registry: findings, warranted action, council response
```

---

## Data Sources

| Directory | Contents | Updated by |
|-----------|----------|------------|
| `minutes/` | Meeting transcript PDFs | Add new PDFs manually |
| `text/` | Extracted transcript text | `generate.sh` (via pdftotext) |
| `agendas/*.json` | Pre-meeting agenda items (title, authors, dollar amounts, flags) | `agenda_scraper.py` |
| `agendas/annotated/*.json` | Post-meeting annotated agendas (authoritative attendance + per-item votes) | `annotated_scraper.py` |
| `agendas/reports/*.json` | Staff report procurement signals | `packet_scraper.py` |

Annotated agendas are the authoritative source for what actually happened —
attendance, vote outcomes, arrival times. Run `./generate.sh --scrape` after new
meetings to pull them.

---

## All `generate.sh` Options

| Flag | Effect |
|------|--------|
| *(none)* | Extract new transcripts → score → all PDFs + methodology |
| `--all` | Re-extract every transcript PDF, then full pipeline |
| `--scrape` | Refresh annotated agendas + agenda JSONs, then full pipeline |
| `--scrape-only` | Refresh data sources only, no scoring or PDFs |
| `--scores-only` | Re-score, skip scorecard PDFs, regenerate methodology PDF |
| `--methodology` | Regenerate `methodology.pdf` only |

---

## Key Scripts

| Script | Purpose |
|--------|---------|
| `pipeline.py` | Main scoring orchestrator — runs all dimensions, writes JSON |
| `council_scorecard.py` | Transcript scoring engine (LSI, rhetoric, beer score, etc.) |
| `scorecard_pdf.py` | WeasyPrint HTML→PDF scorecard renderer |
| `methodology_pdf.py` | Renders `METHODOLOGY.md` → `scores/pdfs/methodology.pdf` |
| `incidents_pdf.py` | Renders `incidents.json` → `scores/pdfs/incidents.pdf` |
| `audit_findings_pdf.py` | Renders `audit_findings.json` → `scores/pdfs/audit_findings.pdf` |
| `annotated_scraper.py` | Downloads annotated agenda PDFs → attendance + vote records |
| `agenda_scraper.py` | Scrapes eAgenda HTML → agenda item JSON |
| `packet_scraper.py` | Downloads staff report PDFs → procurement signals |
| `generate.sh` | Entry point for all artifact generation |
