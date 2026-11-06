#!/usr/bin/env python3
"""
NeuroEngage Outreach Dashboard Generator
-----------------------------------------
Reads one or more Microsoft Forms CSV exports and writes the dashboard HTML
plus the cumulative progress report (for Dana Foundation reporting).

    python3 generate_dashboard.py                       # data/*.csv -> docs/index.html + report.html + map.html
    python3 generate_dashboard.py --pdf                 # also print the report to docs/NeuroEngage_Progress_Report.pdf
    python3 generate_dashboard.py -o preview.html
    python3 generate_dashboard.py old.csv new.csv -o out.html

Exports are merged oldest-first and for each field the newest export that has a
value wins, so a later export that drops a duration or a note does not erase it.
Pass files in chronological order; the default (sorted data/*.csv) already is,
given the outreach_export_YYYY-MM-DD.csv naming.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys

from neuroengage.data import aggregate, build_events
from neuroengage.landscape import build_landscape
from neuroengage.mapping import build_map
from neuroengage.poster import build_poster
from neuroengage.render import render
from neuroengage.report import REPORT_START, build_report_data, render_report

DEFAULT_DATA_GLOB = os.path.join('data', '*.csv')
DEFAULT_OUTPUT = os.path.join('docs', 'index.html')
DEFAULT_REPORT = os.path.join('docs', 'report.html')
DEFAULT_PDF = os.path.join('docs', 'NeuroEngage_Progress_Report.pdf')
DEFAULT_PPTX = os.path.join('docs', 'NeuroEngage_Progress_Deck.pptx')
DEFAULT_VENUES = 'venues.csv'
DEFAULT_HISTORY = 'history.csv'
DEFAULT_MILESTONES = 'milestones.csv'

CHROME_CANDIDATES = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    'google-chrome', 'chromium', 'chromium-browser',
]


def find_chrome():
    return next(
        (c for c in CHROME_CANDIDATES if os.path.exists(c) or shutil.which(c)),
        None,
    )


def print_to_pdf(report_path, pdf_path):
    """Print the report to PDF with a Chromium-family browser, if one exists."""
    chrome = find_chrome()
    if not chrome:
        return 'no Chromium-family browser found — skipped PDF (the report prints fine from any browser)'
    result = subprocess.run(
        [chrome, '--headless', '--disable-gpu', '--no-pdf-header-footer',
         f'--print-to-pdf={os.path.abspath(pdf_path)}',
         '--virtual-time-budget=8000',
         f'file://{os.path.abspath(report_path)}'],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 or not os.path.exists(pdf_path):
        return f'PDF export failed: {result.stderr.strip().splitlines()[-1] if result.stderr else "unknown error"}'
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Generate the NeuroEngage outreach dashboard.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('csv', nargs='*', help='CSV exports, oldest first (default: data/*.csv)')
    parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT, help=f'output HTML (default: {DEFAULT_OUTPUT})')
    parser.add_argument('--report-output', default=DEFAULT_REPORT, help=f'progress report HTML (default: {DEFAULT_REPORT})')
    parser.add_argument('--report-since', default=REPORT_START, metavar='YYYY-MM',
                        help=f'first month of the reporting window (default: {REPORT_START})')
    parser.add_argument('--no-report', action='store_true', help='skip the progress report')
    parser.add_argument('--pdf', action='store_true',
                        help=f'also print the report to {DEFAULT_PDF} (needs Chrome/Chromium/Edge)')
    parser.add_argument('--pptx', action='store_true',
                        help=f'also build the slide deck at {DEFAULT_PPTX} (needs python-pptx and Chrome)')
    parser.add_argument('--no-map', action='store_true', help='skip the outreach map (docs/map.html)')
    parser.add_argument('-q', '--quiet', action='store_true', help='only report problems')
    args = parser.parse_args(argv)

    paths = args.csv or sorted(glob.glob(DEFAULT_DATA_GLOB))
    if not paths:
        parser.error(f'no CSV exports found — looked for {DEFAULT_DATA_GLOB}')
    for path in paths:
        if not os.path.exists(path):
            parser.error(f'file not found: {path}')

    try:
        events, notes, warnings, _ = build_events(paths)
    except ValueError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1

    if not events:
        print('Error: no events with a readable date were found.', file=sys.stderr)
        return 1

    agg = aggregate(events)
    stats = agg['stats']

    if not args.quiet:
        print('Reading, oldest first:')
        for path in paths:
            print(f'  {path}')
        print(f'\n{stats["total_events"]} events  |  {stats["total_attendees"]:,} attendees  |  '
              f'{stats["total_hours"]:g} event hours  |  {stats["unique_leads"]} lead volunteers '
              f'({stats["unique_volunteers"]} volunteers overall)')
        print(f'{stats["num_months"]} month span ({stats["months_with_data"]} with events)  |  '
              f'avg {stats["avg_attendees"]:,} attendees/mo  |  avg {stats["avg_events"]} events/mo')
        if stats['estimated_counts']:
            print(f'{stats["estimated_counts"]} attendance figures are estimates (shown with ~)')

        by_category = {}
        for note in notes:
            by_category.setdefault(note.category, []).append(note)
        if by_category:
            print('\nHow ambiguous entries were read:')
            for category in ('attendees', 'hours', 'name', 'leads', 'activity', 'carried'):
                for note in by_category.get(category, []):
                    where = f'{note.event}: ' if note.event else ''
                    print(f'  [{category}] {where}{note.detail}')

    if warnings:
        print('\nMissing data:', file=sys.stderr)
        for warning in warnings:
            print(f'  ! {warning}', file=sys.stderr)

    sources = [os.path.basename(p) for p in paths]
    html = render(events, agg, notes, sources)
    output_dir = os.path.dirname(os.path.abspath(args.output))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as handle:
        handle.write(html)
    written = [args.output]

    if not args.no_report:
        report_data = build_report_data(events, since=args.report_since)
        if report_data['monthly']:
            report_html = render_report(report_data, sources)
            os.makedirs(os.path.dirname(os.path.abspath(args.report_output)) or '.', exist_ok=True)
            with open(args.report_output, 'w', encoding='utf-8') as handle:
                handle.write(report_html)
            written.append(args.report_output)
            if not args.quiet:
                totals = report_data['totals']
                print(f'\nProgress report ({args.report_since} onward): '
                      f'{totals["events"]} events | {totals["attendees"]:,} people | '
                      f'{totals["hours"]:g}h | {totals["volunteers"]} volunteers '
                      f'({report_data["repeat_count"]} repeat)')
            if args.pdf:
                problem = print_to_pdf(args.report_output, DEFAULT_PDF)
                if problem:
                    print(f'  ! {problem}', file=sys.stderr)
                else:
                    written.append(DEFAULT_PDF)
            if args.pptx:
                chrome = find_chrome()
                if not chrome:
                    print('  ! no Chromium-family browser found — skipped deck', file=sys.stderr)
                else:
                    try:
                        from neuroengage.slides import build_deck
                    except ImportError:
                        print('  ! python-pptx not installed (pip install python-pptx) — skipped deck',
                              file=sys.stderr)
                    else:
                        slide_count = build_deck(report_data, sources, chrome, DEFAULT_PPTX)
                        written.append(f'{DEFAULT_PPTX} ({slide_count} slides)')
        else:
            print(f'  ! no events on or after {args.report_since} — report skipped', file=sys.stderr)

    if not args.no_map:
        if os.path.exists(DEFAULT_VENUES):
            map_out = os.path.dirname(os.path.abspath(args.output)) or '.'
            map_files, _, map_warnings = build_map(events, DEFAULT_VENUES, sources, map_out, chrome=find_chrome())
            written.extend(os.path.relpath(p) for p in map_files)
            for warning in map_warnings:
                print(f'  ! {warning}', file=sys.stderr)
        else:
            print(f'  ! {DEFAULT_VENUES} not found — map skipped', file=sys.stderr)

    if os.path.exists(DEFAULT_HISTORY):
        out_dir = os.path.dirname(os.path.abspath(args.output)) or '.'
        land_files, _, land_warnings = build_landscape(events, DEFAULT_HISTORY, DEFAULT_MILESTONES, out_dir)
        written.extend(os.path.relpath(p) for p in land_files)
        for warning in land_warnings:
            print(f'  ! {warning}', file=sys.stderr)

    if not args.no_report and report_data['monthly']:
        out_dir = os.path.dirname(os.path.abspath(args.output)) or '.'
        poster_files = build_poster(report_data, events, DEFAULT_VENUES, out_dir, chrome=find_chrome())
        written.append(f'{os.path.relpath(poster_files[0])} (+{len(poster_files) - 1} poster chart files)')

    print(f'\nWrote {", ".join(written)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
