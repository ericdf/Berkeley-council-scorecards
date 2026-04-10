# Berkeley City Council Scorecard Pipeline

Automated analysis of Berkeley City Council meeting transcripts and agenda records,
producing per-member scorecards evaluated from a taxpayer-aligned perspective.

See **`METHODOLOGY.md`** (or `scores/pdfs/methodology.pdf`) for a full description of
signals, sources, scoring philosophy, and tier structure.

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
| `annotated_scraper.py` | Downloads annotated agenda PDFs → attendance + vote records |
| `agenda_scraper.py` | Scrapes eAgenda HTML → agenda item JSON |
| `packet_scraper.py` | Downloads staff report PDFs → procurement signals |
| `generate.sh` | Entry point for all artifact generation |
