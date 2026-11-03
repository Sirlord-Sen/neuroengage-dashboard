"""
PowerPoint deck for presenting the cumulative progress report.

Built from the same report data as docs/report.html, so the deck can never
drift from the page or the PDF. Charts are the report's own SVGs rendered to
high-resolution PNG (via headless Chrome) so the branding is pixel-identical;
titles, takeaways, KPIs and the term table are native PowerPoint shapes so
they stay editable.

Requires python-pptx (pip install python-pptx) and a Chromium-family browser;
both are needed only for the --pptx flag, never for the dashboard or report.
"""

import os
import subprocess
import tempfile

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

from .report import (
    PROGRAM_HISTORY,
    PROPOSAL_PACE,
    REPORT_CSS,
    REPORT_HORIZON,
    SERIES,
    bucket_chart,
    cumulative_chart,
    fmt_num,
    hbar_chart,
    history_chart,
    month_label,
    pipeline_chart,
)

INK = RGBColor(0x1C, 0x1B, 0x18)
INK_MID = RGBColor(0x4A, 0x49, 0x45)
INK_SOFT = RGBColor(0x88, 0x87, 0x80)
PAPER = RGBColor(0xFA, 0xF8, 0xF3)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BORDER = RGBColor(0xE0, 0xDD, 0xD4)
TEAL = RGBColor(0x1D, 0x9E, 0x75)
TEAL_DARK = RGBColor(0x0D, 0x6E, 0x50)
PURPLE = RGBColor(0x53, 0x4A, 0xB7)
AMBER = RGBColor(0xBA, 0x75, 0x17)
RED = RGBColor(0xE2, 0x4B, 0x4A)
ACCENTS = {'attendees': TEAL, 'events': PURPLE, 'hours': AMBER, 'volunteers': RED}

SANS = 'Outfit'
SERIF = 'DM Serif Display'
MONO = 'DM Mono'

SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)


# ── CHART RENDERING ──────────────────────────────────────────────────────────

def render_chart_pngs(data, chrome, workdir, scale=3):
    """Render each report chart SVG to a PNG at ``scale``× via headless Chrome."""
    jobs = {}
    for key, spec in SERIES.items():
        svg = cumulative_chart(data['monthly'], key, spec['hue'], spec['label'],
                               PROPOSAL_PACE.get(key))
        jobs[key] = (svg, 336, 204)
    bucket_h = len(data['buckets']) * 32 + 8
    jobs['buckets'] = (bucket_chart(data['buckets']), 336, bucket_h)

    venue_svg, venue_h = hbar_chart(
        [(name, count) for name, count in data['venues'][:8]],
        '#534AB7', label_w=150, suffix=' visits')
    jobs['venues'] = (venue_svg, 336, venue_h)

    scale_svg, scale_h = hbar_chart(
        [(e['venue'], e['attendees'], e['when'], e['approx']) for e in data['top_events']],
        '#1D9E75', label_w=150)
    jobs['scale'] = (scale_svg, 336, scale_h)

    pipe_svg, pipe_h = pipeline_chart(data['pipeline'])
    jobs['pipeline'] = (pipe_svg, 336, pipe_h)

    if PROGRAM_HISTORY:
        since_year = int(data['since'][:4])
        grant_label = f'{since_year}–{str(since_year + 1)[-2:]}'
        jobs['history'] = (
            history_chart(PROGRAM_HISTORY, grant_label, data['totals']['attendees']),
            336, 150)

    pngs = {}
    for name, (svg, w, h) in jobs.items():
        # The trailing body rule must reset margin AND padding: REPORT_CSS
        # styles body for the report page (2rem screen padding), and any
        # leftover offset here shifts the chart and crops its axis band.
        page = (f'<!DOCTYPE html><html><head>'
                f'<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500'
                f'&family=Outfit:wght@300;400;500;600&display=block" rel="stylesheet">'
                f'<style>{REPORT_CSS}'
                f'body{{margin:0!important;padding:0!important;background:#FFFFFF;}}'
                f'.chart{{width:{w * scale}px;height:{h * scale}px;}}'
                f'</style></head><body>{svg}</body></html>')
        html_path = os.path.join(workdir, f'{name}.html')
        png_path = os.path.join(workdir, f'{name}.png')
        with open(html_path, 'w', encoding='utf-8') as fh:
            fh.write(page)
        result = subprocess.run(
            [chrome, '--headless', '--disable-gpu', '--hide-scrollbars',
             f'--screenshot={png_path}', f'--window-size={w * scale},{h * scale}',
             '--virtual-time-budget=5000', f'file://{html_path}'],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0 or not os.path.exists(png_path):
            raise RuntimeError(f'chart render failed for {name}')
        _assert_not_cropped(png_path, name)
        pngs[name] = png_path
    return pngs


def _assert_not_cropped(png_path, name):
    """Fail loudly if chart ink reaches the image edge (an offset/crop bug).

    Every chart SVG keeps its marks and labels inside the viewBox with room
    to spare, so non-white pixels touching the bottom or right edge mean the
    page shifted and the axis band is being cut off.
    """
    from PIL import Image
    image = Image.open(png_path).convert('L')
    w, h = image.size
    pixels = image.load()
    bottom = any(pixels[x, h - 1] < 250 for x in range(0, w, 4))
    right = any(pixels[w - 1, y] < 250 for y in range(0, h, 4))
    if bottom or right:
        edge = 'bottom' if bottom else 'right'
    else:
        return
    raise RuntimeError(
        f'chart "{name}" renders to the {edge} edge of its PNG — '
        f'the page is offset and the chart is being cropped'
    )


# ── SHAPE HELPERS ────────────────────────────────────────────────────────────

def _fill(slide, x, y, w, h, color):
    from pptx.enum.shapes import MSO_SHAPE
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def _text(slide, x, y, w, h, runs, size, color, font=SANS, bold=False,
          align=PP_ALIGN.LEFT, spacing=None, line_spacing=None):
    """One text box; ``runs`` is a string or list of (text, overrides) tuples."""
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    para = tf.paragraphs[0]
    para.alignment = align
    if line_spacing:
        para.line_spacing = line_spacing
    if isinstance(runs, str):
        runs = [(runs, {})]
    for text, over in runs:
        run = para.add_run()
        run.text = text
        run.font.name = over.get('font', font)
        run.font.size = Pt(over.get('size', size))
        run.font.bold = over.get('bold', bold)
        run.font.color.rgb = over.get('color', color)
        if over.get('spacing', spacing):
            run.font._rPr.set('spc', str(int(over.get('spacing', spacing) * 100)))
    return box


def _bullets(slide, x, y, w, h, items, size=14, color=INK_MID, gap=8):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, item in enumerate(items):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.space_after = Pt(gap)
        para.line_spacing = 1.15
        if isinstance(item, str):
            item = [(item, {})]
        for text, over in item:
            run = para.add_run()
            run.text = text
            run.font.name = over.get('font', SANS)
            run.font.size = Pt(over.get('size', size))
            run.font.bold = over.get('bold', False)
            run.font.color.rgb = over.get('color', color)
    return box


def _footer(slide, page_no):
    _text(slide, Inches(0.55), Inches(7.08), Inches(8), Inches(0.3),
          'NEUROENGAGE  ·  DANA NEXTGEN FELLOWSHIP  ·  GSU',
          9, INK_SOFT, font=MONO, spacing=1.5)
    _text(slide, Inches(12.3), Inches(7.08), Inches(0.5), Inches(0.3),
          str(page_no), 9, INK_SOFT, font=MONO, align=PP_ALIGN.RIGHT)


def _slide(prs, background=PAPER):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _fill(slide, 0, 0, SLIDE_W, SLIDE_H, background)
    return slide


def _section_label(slide, text, accent):
    _fill(slide, Inches(0.55), Inches(0.62), Inches(0.28), Inches(0.055), accent)
    _text(slide, Inches(0.95), Inches(0.5), Inches(10), Inches(0.3),
          text.upper(), 11, INK_SOFT, font=MONO, spacing=2)


# ── SLIDES ───────────────────────────────────────────────────────────────────

def _title_slide(prs, data):
    slide = _slide(prs, background=INK)
    _fill(slide, 0, Inches(7.42), SLIDE_W / 4, Inches(0.08), TEAL)
    _fill(slide, SLIDE_W / 4, Inches(7.42), SLIDE_W / 4, Inches(0.08), PURPLE)
    _fill(slide, SLIDE_W / 2, Inches(7.42), SLIDE_W / 4, Inches(0.08), AMBER)
    _fill(slide, SLIDE_W * 3 / 4, Inches(7.42), SLIDE_W / 4, Inches(0.08), RED)

    _text(slide, Inches(0.9), Inches(2.15), Inches(11.5), Inches(0.4),
          'GEORGIA STATE UNIVERSITY  ·  CBN / TRENDS  ·  DANA NEXTGEN FELLOWSHIP',
          12, TEAL, font=MONO, spacing=2)
    _text(slide, Inches(0.9), Inches(2.6), Inches(11.5), Inches(1.6),
          'NeuroEngage Outreach', 48, WHITE, font=SERIF)
    _text(slide, Inches(0.9), Inches(3.5), Inches(11.5), Inches(1.0),
          'Cumulative Progress Report', 30, RGBColor(0xC9, 0xC9, 0xC2), font=SERIF)
    _text(slide, Inches(0.9), Inches(4.75), Inches(11.5), Inches(0.4),
          'Prepared for Dana Foundation reporting', 14,
          RGBColor(0x88, 0x87, 0x80))
    _text(slide, Inches(0.9), Inches(5.35), Inches(11.5), Inches(0.4), [
        ('Reporting period  ', {'color': RGBColor(0x88, 0x87, 0x80)}),
        (f'Fall 2025 – {REPORT_HORIZON}', {'color': RGBColor(0xC9, 0xC9, 0xC2), 'bold': True}),
        ('      This snapshot  ', {'color': RGBColor(0x88, 0x87, 0x80)}),
        (f"{month_label(data['since'])} – {data['data_through']}",
         {'color': RGBColor(0xC9, 0xC9, 0xC2), 'bold': True}),
    ], 12, RGBColor(0x88, 0x87, 0x80), font=MONO)


def _kpi_slide(prs, data):
    slide = _slide(prs)
    _section_label(slide, 'Headline numbers · since fall 2025', TEAL)
    totals = data['totals']
    months = len(data['monthly'])
    cards = [
        ('EVENTS HELD', fmt_num(totals['events']),
         f'{fmt_num(round(totals["events"] / months, 1))}/month — proposal target: 2/month', PURPLE),
        ('PEOPLE REACHED', fmt_num(totals['attendees']),
         'K-12 students & public — program baseline: 1,000/yr', TEAL),
        ('EVENT HOURS', fmt_num(totals['hours']),
         f'{fmt_num(round(totals["hours"] / totals["events"], 1))} hours per event on average', AMBER),
        ('DISTINCT VOLUNTEERS', fmt_num(totals['volunteers']),
         f'{data["lead_count"]} have led events — baseline: ~100/yr', RED),
    ]
    x, y = Inches(0.55), Inches(1.55)
    card_w, card_h, gap = Inches(2.97), Inches(3.4), Inches(0.11)
    for i, (label, value, sub, accent) in enumerate(cards):
        cx = x + i * (card_w + gap)
        _fill(slide, cx, y, card_w, card_h, WHITE)
        _fill(slide, cx, y, card_w, Inches(0.06), accent)
        _text(slide, cx + Inches(0.3), y + Inches(0.45), card_w - Inches(0.6), Inches(0.35),
              label, 11, INK_SOFT, font=MONO, spacing=1.5)
        _text(slide, cx + Inches(0.3), y + Inches(0.95), card_w - Inches(0.6), Inches(1.2),
              value, 54, INK, font=SERIF)
        _text(slide, cx + Inches(0.3), y + Inches(2.3), card_w - Inches(0.6), Inches(1.0),
              sub, 12, INK_SOFT)
    _text(slide, Inches(0.55), Inches(5.6), Inches(12.2), Inches(0.9),
          'Every breadth metric is ahead of, or on pace with, the commitments in the funded proposal.',
          17, INK_MID)
    _footer(slide, 2)


def _chart_slide(prs, data, key, png, page_no, takeaways):
    slide = _slide(prs)
    spec = SERIES[key]
    _section_label(slide, f'Growth since fall 2025 · {spec["label"]}', ACCENTS[key])
    _text(slide, Inches(0.55), Inches(1.0), Inches(9), Inches(0.7),
          f'Cumulative {spec["label"].lower()}', 26, INK, font=SERIF)

    img_w = Inches(7.6)
    img_h = Emu(int(img_w * 204 / 336))
    _fill(slide, Inches(0.55), Inches(1.95), img_w + Inches(0.3), img_h + Inches(0.3), WHITE)
    slide.shapes.add_picture(png, Inches(0.7), Inches(2.1), width=img_w)

    _bullets(slide, Inches(8.85), Inches(2.25), Inches(3.9), Inches(4.2),
             takeaways, size=14, gap=12)
    _footer(slide, page_no)


def _term_slide(prs, data, page_no):
    slide = _slide(prs)
    _section_label(slide, 'Term snapshots', PURPLE)
    _text(slide, Inches(0.55), Inches(1.0), Inches(11), Inches(0.7),
          'Activity by academic term, with the cumulative position at term end',
          24, INK, font=SERIF)

    headers = ['Term', 'Events', 'People reached', 'Hours', 'Volunteers active', 'New volunteers']
    rows = []
    for name, t in data['terms'].items():
        rows.append([name, t['events'], fmt_num(t['attendees']), fmt_num(t['hours']),
                     t['active'], t['new_volunteers']])
    totals = data['totals']
    rows.append(['Total since fall 2025', totals['events'], fmt_num(totals['attendees']),
                 fmt_num(totals['hours']), f'{totals["volunteers"]} distinct', totals['volunteers']])
    totals_row = len(rows)

    table_shape = slide.shapes.add_table(
        len(rows) + 1, len(headers),
        Inches(0.55), Inches(2.2), Inches(12.23), Inches(0.5) + Inches(0.55) * len(rows))
    table = table_shape.table
    table.columns[0].width = Inches(3.2)
    for col in list(table.columns)[1:]:
        col.width = Emu(int(Inches(12.23 - 3.2) / (len(headers) - 1)))
    for j, header in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = header
        cell.fill.solid()
        cell.fill.fore_color.rgb = INK
        for para in cell.text_frame.paragraphs:
            para.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.RIGHT
            for run in para.runs:
                run.font.name = MONO
                run.font.size = Pt(10)
                run.font.bold = False
                run.font.color.rgb = RGBColor(0xC9, 0xC9, 0xC2)
    for i, row in enumerate(rows, start=1):
        is_total = i == totals_row
        for j, val in enumerate(row):
            cell = table.cell(i, j)
            cell.text = str(val)
            cell.fill.solid()
            cell.fill.fore_color.rgb = PAPER if is_total else WHITE
            for para in cell.text_frame.paragraphs:
                para.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.RIGHT
                for run in para.runs:
                    run.font.name = SANS
                    run.font.size = Pt(13)
                    run.font.bold = is_total or (j == 0)
                    run.font.color.rgb = INK if (is_total or j == 0) else INK_MID
    _text(slide, Inches(0.55), Inches(5.95), Inches(12.2), Inches(0.9),
          '“Active” counts a person once per term; “new” = first event since fall 2025. The total row counts each volunteer once '
          'across the window, so it equals the sum of new volunteers.  Terms: Fall = Aug–Dec · Spring = Jan–Apr · Summer = May–Jul.',
          11.5, INK_SOFT)
    _footer(slide, page_no)


def _volunteer_slide(prs, data, png, page_no):
    slide = _slide(prs)
    _section_label(slide, 'Volunteer engagement & repeat service', AMBER)
    _text(slide, Inches(0.55), Inches(1.0), Inches(11), Inches(0.7),
          'Volunteers by number of events served', 26, INK, font=SERIF)

    totals = data['totals']
    repeat_pct = round(100 * data['repeat_count'] / totals['volunteers']) if totals['volunteers'] else 0
    bucket_h = len(data['buckets']) * 32 + 8
    img_w = Inches(6.6)
    img_h = Emu(int(img_w * bucket_h / 336))
    _fill(slide, Inches(0.55), Inches(2.0), img_w + Inches(0.4), img_h + Inches(0.4), WHITE)
    slide.shapes.add_picture(png, Inches(0.75), Inches(2.2), width=img_w)

    _bullets(slide, Inches(7.9), Inches(2.1), Inches(4.85), Inches(4.4), [
        [(f'{totals["volunteers"]} distinct volunteers', {'bold': True, 'color': INK}),
         (' since fall 2025 — every name is captured on the intake form, so repeat service is trackable today.', {})],
        [(f'{data["repeat_count"]} volunteers ({repeat_pct}%)', {'bold': True, 'color': INK}),
         (' have served at two or more events.', {})],
        [(f'Crews average {fmt_num(data["avg_crew"])} volunteers per event', {'bold': True, 'color': INK}),
         (' (proposal baseline: 3–4).', {})],
        [(f'{data["lead_count"]} different people', {'bold': True, 'color': INK}),
         (' have led at least one event.', {})],
        [('Signature lesson plans', {'bold': True, 'color': INK}),
         (f' (Touch-a-Brain, Build-a-Brain, Build-a-Neuron) ran at {data["signature_events"]} of {totals["events"]} events.', {})],
    ], size=15, gap=14)
    _footer(slide, page_no)


def _history_slide(prs, data, png, page_no):
    """Pre-grant years in gray, grant year in teal: growth without erasing history."""
    slide = _slide(prs)
    _section_label(slide, 'Program history', TEAL_DARK)
    _text(slide, Inches(0.55), Inches(1.0), Inches(11.5), Inches(0.7),
          'Years of outreach — and this year’s acceleration', 26, INK, font=SERIF)

    img_w = Inches(7.0)
    img_h = Emu(int(img_w * 150 / 336))
    _fill(slide, Inches(0.55), Inches(2.0), img_w + Inches(0.4), img_h + Inches(0.4), WHITE)
    slide.shapes.add_picture(png, Inches(0.75), Inches(2.2), width=img_w)

    _bullets(slide, Inches(8.3), Inches(2.15), Inches(4.45), Inches(4.2), [
        [('NeuroEngage outreach predates this fellowship', {'bold': True, 'color': INK}),
         (' — gray bars are pre-grant years from the annual DMAP infographics.', {})],
        [('The teal bar is the grant reporting year', {'bold': True, 'color': INK}),
         (', computed live from the event database.', {})],
        [('The cumulative charts that follow start where the teal bar starts', {'bold': True, 'color': INK}),
         (' — they measure the grant window, not the program’s lifetime.', {})],
    ], size=15, gap=14)
    _footer(slide, page_no)


def _demand_slide(prs, data, png, page_no):
    """Venues that host — and re-book — outreach: evidence of community demand."""
    slide = _slide(prs)
    _section_label(slide, 'Community demand', PURPLE)
    _text(slide, Inches(0.55), Inches(1.0), Inches(11.5), Inches(0.7),
          'Schools and partners keep asking us back', 26, INK, font=SERIF)

    venue_h = len(data['venues'][:8]) * 28 + 6
    img_w = Inches(7.0)
    img_h = Emu(int(img_w * venue_h / 336))
    _fill(slide, Inches(0.55), Inches(2.0), img_w + Inches(0.4), img_h + Inches(0.4), WHITE)
    slide.shapes.add_picture(png, Inches(0.75), Inches(2.2), width=img_w)

    n_venues = len(data['venues'])
    beacon = next((c for name, c in data['venues'] if 'Beacon Hill Middle' in name), 0)
    _bullets(slide, Inches(8.3), Inches(2.15), Inches(4.45), Inches(4.4), [
        [(f'{n_venues} distinct venues', {'bold': True, 'color': INK}),
         (' hosted NeuroEngage since fall 2025 — schools, festivals, community groups, and a national meeting.', {})],
        [(f'{data["repeat_venues"]} venues booked us more than once', {'bold': True, 'color': INK}),
         (' — repeat invitations are the clearest signal the work is valued.', {})],
        [(f'Beacon Hill Middle School alone hosted {beacon} events', {'bold': True, 'color': INK}),
         (', including a four-day December residency reaching 100 students a day.', {})],
        [('Requests now range from metro Atlanta to Washington, DC.', {})],
    ], size=15, gap=14)
    _footer(slide, page_no)


def _scale_slide(prs, data, png, page_no):
    """From 5-person classrooms to 600-person festivals."""
    slide = _slide(prs)
    _section_label(slide, 'Range of formats', TEAL)
    _text(slide, Inches(0.55), Inches(1.0), Inches(11.5), Inches(0.7),
          'From classrooms to festivals — the biggest single events', 26, INK, font=SERIF)

    scale_h = len(data['top_events']) * 28 + 6
    img_w = Inches(7.0)
    img_h = Emu(int(img_w * scale_h / 336))
    _fill(slide, Inches(0.55), Inches(2.0), img_w + Inches(0.4), img_h + Inches(0.4), WHITE)
    slide.shapes.add_picture(png, Inches(0.75), Inches(2.2), width=img_w)

    totals = data['totals']
    _bullets(slide, Inches(8.3), Inches(2.15), Inches(4.45), Inches(4.4), [
        [(f'{data["big_events"]} events reached 200+ people', {'bold': True, 'color': INK}),
         ('; the Atlanta Science Festival booth alone engaged '
          f'{fmt_num(data["top_events"][0]["attendees"]) if data["top_events"] else "—"}.', {})],
        [(f'Median event: {fmt_num(data["median_size"])} attendees', {'bold': True, 'color': INK}),
         (' — the same crews also run intensive small-group sessions like sheep-brain dissections for five homeschoolers.', {})],
        [(f'{data["activity_formats"]} distinct activity formats fielded', {'bold': True, 'color': INK}),
         (', from the signature lessons to newly piloted stress-physiology stations — the direction Goal 1c formalizes with mini-grant modules.', {})],
    ], size=15, gap=14)
    _footer(slide, page_no)


def _pipeline_slide(prs, data, png, page_no):
    """New vs returning volunteers per month."""
    slide = _slide(prs)
    _section_label(slide, 'Volunteer pipeline', TEAL_DARK)
    _text(slide, Inches(0.55), Inches(1.0), Inches(11.5), Inches(0.7),
          'Recruiting new volunteers while keeping the ones we have', 26, INK, font=SERIF)

    # Legend (two series share this chart, so identity never rides on color alone).
    _fill(slide, Inches(0.85), Inches(1.83), Inches(0.22), Inches(0.09), TEAL)
    _text(slide, Inches(1.17), Inches(1.72), Inches(1.6), Inches(0.3), 'first-time', 12, INK_MID)
    _fill(slide, Inches(2.45), Inches(1.83), Inches(0.22), Inches(0.09), PURPLE)
    _text(slide, Inches(2.77), Inches(1.72), Inches(1.6), Inches(0.3), 'returning', 12, INK_MID)

    img_w = Inches(7.0)
    img_h = Emu(int(img_w * 190 / 336))
    _fill(slide, Inches(0.55), Inches(2.15), img_w + Inches(0.4), img_h + Inches(0.4), WHITE)
    slide.shapes.add_picture(png, Inches(0.75), Inches(2.3), width=img_w)

    terms = list(data['terms'].items())
    new_by_term = ', '.join(f'{t["new_volunteers"]} in {name.split()[0]}' for name, t in terms)
    _bullets(slide, Inches(8.3), Inches(2.15), Inches(4.45), Inches(4.4), [
        [('Fresh intake every term', {'bold': True, 'color': INK}),
         (f' — {new_by_term} first-time volunteers.', {})],
        [('The purple share grows through the year', {'bold': True, 'color': INK}),
         (' — trained volunteers come back instead of churning, exactly what Goal 1a’s workshop pipeline needs.', {})],
        [(f'{data["repeat_count"]} of {data["totals"]["volunteers"]} volunteers', {'bold': True, 'color': INK}),
         (' have already served multiple events.', {})],
    ], size=15, gap=14)
    _footer(slide, page_no)


# ── ENTRY POINT ──────────────────────────────────────────────────────────────

def build_deck(data, sources, chrome, out_path):
    """Assemble the deck; returns the number of slides written."""
    totals = data['totals']
    months = len(data['monthly'])
    with tempfile.TemporaryDirectory() as workdir:
        pngs = render_chart_pngs(data, chrome, workdir)

        prs = Presentation()
        prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H

        _title_slide(prs, data)
        _kpi_slide(prs, data)
        next_page = 3
        if 'history' in pngs:
            _history_slide(prs, data, pngs['history'], next_page)
            next_page += 1

        takeaways = {
            'attendees': [
                [(f'{fmt_num(totals["attendees"])} people reached', {'bold': True, 'color': INK}),
                 (f' in the first {months} months.', {})],
                [('Nearly 4× the program baseline', {'bold': True, 'color': INK}),
                 (' of 1,000 people per year stated in the proposal.', {})],
                [(f'{data["estimated"]} attendance counts recorded as estimates (shown as ~ in the event log).', {})],
            ],
            'events': [
                [(f'{fmt_num(totals["events"])} events at '
                  f'{fmt_num(round(totals["events"] / months, 1))}/month', {'bold': True, 'color': INK}),
                 ('.', {})],
                [('Ahead of Goal 1b', {'bold': True, 'color': INK}),
                 (' — the proposal commits to doubling outreach from one to two events per month.', {})],
                [('Every academic term so far has beaten the target pace.', {})],
            ],
            'hours': [
                [(f'{fmt_num(totals["hours"])} hours', {'bold': True, 'color': INK}),
                 (' of hands-on outreach delivered.', {})],
                [(f'Averaging {fmt_num(round(totals["hours"] / totals["events"], 1))} hours per event.', {})],
                [('Hours are each event’s duration — person-hours across crews run higher still.', {})],
            ],
            'volunteers': [
                [(f'{totals["volunteers"]} distinct volunteers', {'bold': True, 'color': INK}),
                 (' engaged so far.', {})],
                [('On pace with the ~100 volunteers/year', {'bold': True, 'color': INK}),
                 (' the program historically recruits.', {})],
                [(f'{data["repeat_count"]} ({round(100 * data["repeat_count"] / totals["volunteers"])}%) have returned for two or more events.', {})],
            ],
        }
        page = next_page
        for key in SERIES:
            _chart_slide(prs, data, key, pngs[key], page, takeaways[key])
            page += 1

        _term_slide(prs, data, page); page += 1
        _demand_slide(prs, data, pngs['venues'], page); page += 1
        _scale_slide(prs, data, pngs['scale'], page); page += 1
        _pipeline_slide(prs, data, pngs['pipeline'], page); page += 1
        _volunteer_slide(prs, data, pngs['buckets'], page)

        prs.save(out_path)
        return len(prs.slides)
