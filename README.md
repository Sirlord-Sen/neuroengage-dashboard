# NeuroEngage Outreach Dashboard

Dashboard and progress report for NeuroEngage outreach events, generated from
the Microsoft Forms export and published with GitHub Pages.

- **Dashboard** — `https://YOUR-USERNAME.github.io/neuroengage-dashboard`
- **Progress report** — `https://YOUR-USERNAME.github.io/neuroengage-dashboard/report.html`

---

## Updating the dashboard

1. Export the Microsoft Forms responses to CSV.
2. Save it into `data/` as `outreach_export_YYYY-MM-DD.csv` (today's date).
   **Keep the older exports** — see *Why exports are merged* below.
   The exports stay on your machine only (`data/*.csv` is git-ignored): they
   contain volunteer emails and free-text notes, and this repo is public.
   Back them up somewhere private (e.g. Dropbox).
3. Regenerate and commit:

```bash
python3 generate_dashboard.py
git add docs
git commit -m "Update dashboard"
git push
```

`generate_dashboard.py` with no arguments reads every CSV in `data/` in
filename order and writes `docs/index.html` **and** `docs/report.html`. No
dependencies beyond the Python 3 standard library.

Other options:

```bash
python3 generate_dashboard.py --pdf               # also write docs/NeuroEngage_Progress_Report.pdf
python3 generate_dashboard.py --pptx              # also build the 10-slide deck (needs python-pptx + Chrome)
python3 generate_dashboard.py -o preview.html     # write somewhere else first
python3 generate_dashboard.py old.csv new.csv     # specific files, oldest first
python3 generate_dashboard.py -q                  # only report problems
python3 generate_dashboard.py --no-map            # skip the outreach map
```

---

## The progress report (Dana Foundation)

`docs/report.html` is a cumulative view of the same data for grant reporting:
month-by-month cumulative charts (events, people reached, event hours,
distinct volunteers), per-term snapshot tables, repeat-volunteer analysis, and
the full volunteer roster with events served.

- **Reporting window**: fall 2025 onward (`REPORT_START` in
  `neuroengage/report.py`, override with `--report-since YYYY-MM`). The grant
  period runs through December 2027; the report grows into it as data arrives.
  Events before the window (the June 2025 pilots) are excluded from the
  figures and noted in the method notes.
- **PDF for submission**: the page is print-ready — run
  `python3 generate_dashboard.py --pdf` (uses Chrome/Chromium/Edge if
  installed) or open `report.html` in any browser and print to PDF.
- **Slide deck for presenting**: `python3 generate_dashboard.py --pptx`
  rebuilds `docs/NeuroEngage_Progress_Deck.pptx` (10 slides, 16:9) from the
  same data — title, KPI cards, one slide per cumulative chart with target
  paces, term snapshot table, repeat-volunteer analysis, volunteer roster, and
  method notes. Charts are images (pixel-identical to the report); all text
  and the table are native, editable PowerPoint shapes. Needs
  `pip install python-pptx` and a Chromium-family browser, both only for this
  flag. Regenerate the deck rather than editing numbers by hand — hand edits
  are overwritten on the next run.
- Academic terms are Fall = Aug–Dec, Spring = Jan–Apr, Summer = May–Jul.

Anything the generator had to interpret is printed to the terminal and repeated
on the page itself, under *How these numbers were read from the form responses*.
Read it after each update — it is how you catch a bad form response early.

---

## The outreach map

`docs/map.html` shows every visit site as a dot whose **area** is the number of
people reached there, with a toggle between *K–12 school & youth visits* and
*all events*. Central Atlanta & Decatur get an enlarged panel; sites outside
Georgia go in a box. `docs/map_k12.svg` and `docs/map_all.svg` are the same maps
as standalone vector files for the poster (drop into PowerPoint/Illustrator at
any size).

The form's zip-code field is almost always blank, so locations live in
**`venues.csv`** (committed — it holds only public venue names and coordinates):

| column | meaning |
|---|---|
| `venue` | name as typed on the form (typos and "(K-5)"-style suffixes still match) |
| `label` | short name drawn on the map |
| `site` | optional — venues sharing a campus get the same site and become one dot |
| `audience` | `k12` (school & youth) or `public` (community / family / professional) |
| `lat`, `lon` | leave blank if unknown — the venue is listed as *not yet mapped*, never guessed |
| `precision` | `venue`, or `zip` / `city` for an approximate spot (drawn dashed) |

After each export, the generator warns about any venue missing from
`venues.csv`; add a row (look the school up on openstreetmap.org — right-click →
*Show address* gives the coordinates) and rerun.

---

## The 20-year landscape

`docs/landscape.html` (and `docs/landscape.svg` for the poster) draws people
reached per **academic year** (Aug–Jul, labelled by the fall it starts) as a
horizon, with program milestones planted on it as flags.

- **`history.csv`** — `year,people,status,source`. `status` is `actual`,
  `estimate` (hollow dot) or `placeholder` (grey, and the whole figure is
  stamped DRAFT). Years not listed are filled live from the event form, and a
  listed year is never added to the form's count.
- **`milestones.csv`** — `date,label,status`, `date` as `YYYY` or `YYYY-MM`,
  `status` `confirmed` or `placeholder` (grey flag, "date TBC").

The values shipped in these files are **placeholders** until the real yearly
counts and milestone dates arrive.

---

## Why exports are merged rather than replaced

Form responses can be edited after submission, and a later export has been
observed **losing** data an earlier one had. In the August 2026 export, the
June 2 2025 Rockdale event lost its `3 hours` duration and ten events lost
their notes.

So exports are merged by response Id, and for each field the newest export that
actually has a value wins. A later export can correct a value but cannot blank
one out. That is why old exports stay in `data/`.

---

## How the messy fields are read

Volunteers type free text, so the parsers are deliberately forgiving — and they
report every judgement call rather than guessing quietly.

**Attendance** takes the first number in each clause and adds the clauses up:

| Entry | Counted as |
|---|---|
| `50 7th graders` | 50 |
| `71 for TaB in expo hall; 22 for BaN in classrooms` | 93 |
| `~70-80` | 75, flagged as an estimate (`~75` on the page) |
| `~40` | 40, flagged as an estimate |

**Duration** understands worded durations and clock ranges:

| Entry | Counted as |
|---|---|
| `2.5`, `3 hours`, `1 hr` | 2.5, 3, 1 |
| `4 hrs 45 min` | 4.75 |
| `8am set up to 1pm clean up` | 5 |
| `8:00 AM- 4:30 PM` | 8.5 |

A blank duration or headcount is reported as missing. It is never counted as
zero.

**Lead volunteers** are split into individual people, so a co-led event credits
each lead separately — `David Waxler & Meghan Vogt` is two people, and
`Corey, Kyle, Maria, and David` is four. Spelling variants of the same person
are merged (`Ethan Levine` → `Ethan Lavine`) and bare first names are expanded
against the roster of everyone named in the data.

Two variants only merge when they share a first or last name *and* are very
similar, which keeps genuinely different people apart. When both spellings are
equally common the generator prints a tie warning — pin the right one in
`NAME_ALIASES` in `neuroengage/data.py`.

**Activities** fold synonyms together, so `GSR` and
`Galvanic Skin Response (GSR)` are one activity, not two. Unrecognised entries
are kept exactly as typed rather than guessed at. Add new synonyms to
`ACTIVITY_ALIASES` in `neuroengage/parsing.py`.

**Monthly charts** cover every calendar month between the first and last event,
including months with no events, so the per-month averages describe the real
period rather than only the months that happen to have data.

---

## When the form changes

Columns are matched on a normalised prefix, so a reworded question keeps
working — `Length of Time (e.g., hours spent volunteering)` and
`Length of Time in hours (e.g., 2.5 hours spent volunteering)` both resolve. New
columns (like `Zip Code for Event Location`) are ignored safely.

If a question is renamed beyond recognition the generator **stops with an error
listing the headers it found**, instead of silently reading that field as empty.
Add the new wording to `COLUMN_PREFIXES` in `neuroengage/parsing.py`.

---

## Tests

```bash
python3 -m unittest discover tests
```

Every case in `tests/test_parsing.py` is a real entry someone typed into the
form, plus the failure modes of the earlier parser.

---

## File structure

```
neuroengage-dashboard/
├── data/                         ← local only, git-ignored
│   ├── outreach_export_2026-05-25.csv   ← keep old exports, they are merged
│   └── outreach_export_2026-08-12.csv
├── docs/
│   ├── index.html            ← the live dashboard (served by GitHub Pages)
│   ├── report.html           ← cumulative progress report (Dana Foundation)
│   └── NeuroEngage_Progress_Report.pdf   ← printable copy (regenerate with --pdf)
├── neuroengage/
│   ├── parsing.py            ← column matching + free-text parsers + name resolver
│   ├── data.py               ← merging exports, building events, aggregation
│   ├── render.py             ← dashboard HTML/CSS/JS
│   └── report.py             ← cumulative report: series, SVG charts, print CSS
├── tests/
│   ├── test_parsing.py
│   └── test_report.py
├── generate_dashboard.py     ← command-line entry point
└── README.md
```

---

## GitHub Pages setup (one time)

1. Repo **Settings** → **Pages**
2. **Source**: Deploy from a branch
3. Branch `main`, folder `/docs` → **Save**

The dashboard updates when you push a regenerated `docs/index.html`.

> The repo previously fetched the Excel file from OneDrive on a schedule via
> GitHub Actions. That workflow and `download_data.py` were removed, so updating
> is the manual export-and-regenerate flow above.
