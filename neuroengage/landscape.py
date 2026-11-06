"""
Program "landscape": people reached per academic year as a horizon line, with
the program's milestones planted on it as flags.

Inputs (repo root):
    history.csv     year,people,status,source — one row per academic year,
                    labelled by its fall (2024 = Aug 2024 – Jul 2025).
                    status: actual | estimate | placeholder
    milestones.csv  date,label,status — date is YYYY or YYYY-MM;
                    status: confirmed | placeholder

Academic years that history.csv does not list are filled from the event form
(the grant years), so the newest peak is always live data. A year listed in
history.csv always wins — the form is never added on top of it, so nothing is
double-counted.

Honesty rules for a decorative form: the ridge is a monotone cubic through the
yearly values (it never overshoots a real value), the ground is zero, every
year has a marker whose style says how solid its number is, and any
placeholder value stamps the whole figure as a draft.
"""

import csv
import html
import math
from datetime import datetime

from .report import fmt_num, nice_ticks

FONT = "'Outfit', 'Helvetica Neue', Arial, sans-serif"
MONO = "'DM Mono', Menlo, monospace"
SERIF = "'DM Serif Display', Georgia, serif"
STATUS_STYLE = {
    'actual':      'records',
    'estimate':    'estimate',
    'placeholder': 'placeholder',
    'form':        'event form',
}


def academic_year(date_sort):
    d = datetime.strptime(date_sort, '%Y-%m-%d')
    return d.year if d.month >= 8 else d.year - 1


def ay_label(year):
    return f'{year}–{str(year + 1)[-2:]}'


def load_history(path):
    rows = {}
    with open(path, encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            try:
                year, people = int(row['year']), float(row['people'])
            except (TypeError, ValueError, KeyError):
                continue
            status = (row.get('status') or 'actual').strip().lower()
            rows[year] = {'year': year, 'people': people,
                          'status': status if status in STATUS_STYLE else 'actual',
                          'source': (row.get('source') or '').strip()}
    return rows


def load_milestones(path):
    out = []
    with open(path, encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            date = (row.get('date') or '').strip()
            label = (row.get('label') or '').strip()
            if not date or not label:
                continue
            parts = date.split('-')
            try:
                year = int(parts[0])
                month = int(parts[1]) if len(parts) > 1 else 8
            except ValueError:
                continue
            # Position on the academic-year axis: Aug = start of that year's slot.
            ay = year if month >= 8 else year - 1
            pos = ay + ((month - 8) % 12) / 12
            out.append({'date': date, 'label': label, 'pos': pos,
                        'placeholder': (row.get('status') or '').strip().lower() == 'placeholder'})
    return sorted(out, key=lambda m: m['pos'])


def build_landscape_data(events, history, data_through=None):
    """Merge history.csv with per-academic-year totals from the event form."""
    live, last_date = {}, None
    for e in events:
        ay = academic_year(e['date_sort'])
        live[ay] = live.get(ay, 0) + (e['attendees'] or 0)
        last_date = max(last_date or e['date_sort'], e['date_sort'])
    years = dict(history)
    for ay, people in live.items():
        if ay not in years:
            years[ay] = {'year': ay, 'people': people, 'status': 'form', 'source': 'NeuroEngage event form'}
    rows = [years[y] for y in sorted(years)]
    # The newest form year may still be in progress.
    if last_date and rows and rows[-1]['status'] == 'form':
        end = datetime.strptime(last_date, '%Y-%m-%d')
        if not (end.month == 7 and academic_year(last_date) == rows[-1]['year']):
            rows[-1]['partial'] = end.strftime('%b %Y')
    return rows


def _monotone(xs, ys):
    """Fritsch–Carlson monotone cubic → SVG path commands (no overshoot)."""
    n = len(xs)
    if n < 2:
        return f'L{xs[0]:.1f},{ys[0]:.1f}' if n else ''
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [d[0]] + [0.0] * (n - 2) + [d[-1]]
    for i in range(1, n - 1):
        m[i] = 0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2
    for i in range(n - 1):
        if d[i] == 0:
            m[i] = m[i + 1] = 0.0
            continue
        a, b = m[i] / d[i], m[i + 1] / d[i]
        s = a * a + b * b
        if s > 9:
            t = 3 / math.sqrt(s)
            m[i], m[i + 1] = t * a * d[i], t * b * d[i]
    out = []
    for i in range(n - 1):
        h = xs[i + 1] - xs[i]
        out.append(f'C{xs[i] + h / 3:.1f},{ys[i] + m[i] * h / 3:.1f} '
                   f'{xs[i + 1] - h / 3:.1f},{ys[i + 1] - m[i + 1] * h / 3:.1f} '
                   f'{xs[i + 1]:.1f},{ys[i + 1]:.1f}')
    return ''.join(out)


def _t(x, y, body, size, anchor='start', fill='#1C1B18', font=None, extra=''):
    fam = f' font-family="{html.escape(font, quote=True)}"' if font else ''
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" fill="{fill}"{fam}{extra}>'
            f'{body}</text>')


def render_landscape_svg(rows, milestones, standalone=False, W=1200, H=560):
    if not rows:
        return '<svg/>'
    L, R, T, B = 56, 70, 150, 64            # T leaves sky for the milestone flags
    ground = H - B
    years = [r['year'] for r in rows]
    y0, y1 = min(years), max(years)
    span = max(y1 - y0 + 1, 1)
    slot = (W - L - R) / span
    X = lambda pos: L + (pos - y0) * slot          # pos = academic-year position (Aug = .0)
    ticks = nice_ticks(max(r['people'] for r in rows))
    top = ticks[-1] or 1
    Y = lambda v: ground - (ground - T) * v / top
    draft = any(r['status'] == 'placeholder' for r in rows) or any(m['placeholder'] for m in milestones)
    mono = html.escape(MONO, quote=True)

    xs = [X(r['year'] + 0.5) for r in rows]
    ys = [Y(r['people']) for r in rows]
    ridge = f'M{xs[0]:.1f},{ys[0]:.1f}' + _monotone(xs, ys)
    area = (f'M{L:.1f},{ground}L{L:.1f},{ys[0]:.1f}L{xs[0]:.1f},{ys[0]:.1f}' + _monotone(xs, ys)
            + f'L{W - R:.1f},{ys[-1]:.1f}L{W - R:.1f},{ground}Z')
    ridge_full = f'M{L:.1f},{ys[0]:.1f}L' + ridge[1:] + f'L{W - R:.1f},{ys[-1]:.1f}'

    out = []
    if standalone:
        out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W * 2}" '
                   f'height="{H * 2}" font-family="{html.escape(FONT, quote=True)}">')
    else:
        out.append(f'<svg class="land-svg" viewBox="0 0 {W} {H}" role="img" aria-label="People reached per '
                   f'academic year, {ay_label(y0)} to {ay_label(y1)}, drawn as a landscape horizon with milestones">')
    out.append('<defs>'
               '<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
               '<stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#EAF4EF"/></linearGradient>'
               f'<linearGradient id="hill" x1="0" y1="{T}" x2="0" y2="{ground}" gradientUnits="userSpaceOnUse">'
               '<stop offset="0" stop-color="#2FA981"/><stop offset="1" stop-color="#0A5C43"/></linearGradient>'
               '</defs>')
    out.append(f'<rect width="{W}" height="{H}" fill="url(#sky)"/>')

    # Altitude lines — the y-axis, read like contour labels on the right.
    for v in ticks[1:]:
        y = Y(v)
        out.append(f'<path d="M{L},{y:.1f}H{W - R}" stroke="#1C1B18" stroke-opacity=".08" stroke-dasharray="2 4"/>')
        out.append(_t(W - R + 8, y + 4, fmt_num(v), 11, fill='#888780', font=MONO))
    out.append(_t(W - R + 8, T - 22, 'PEOPLE', 9.5, fill='#888780', font=MONO, extra=' letter-spacing="1.2"'))
    out.append(_t(W - R + 8, T - 10, 'PER YEAR', 9.5, fill='#888780', font=MONO, extra=' letter-spacing="1.2"'))

    # The hill (data) and its ridge line; placeholder years are drawn paler.
    out.append(f'<path d="{area}" fill="url(#hill)"/>')
    if any(r['status'] == 'placeholder' for r in rows):
        # Veil over placeholder spans so draft numbers never read as records.
        runs, start = [], None
        for r in rows + [None]:
            if r is not None and r['status'] == 'placeholder':
                start = r['year'] if start is None else start
                end = r['year']
            elif start is not None:
                runs.append((start, end))
                start = None
        for a, z in runs:
            x0 = L if a == y0 else X(a)
            out.append(f'<rect x="{x0:.1f}" y="{T - 10}" width="{X(z + 1) - x0:.1f}" '
                       f'height="{ground - T + 10}" fill="#FFFFFF" fill-opacity=".38"/>')
    out.append(f'<path d="{ridge_full}" fill="none" stroke="#FFFFFF" stroke-width="2"/>')
    out.append(f'<rect x="0" y="{ground}" width="{W}" height="{B}" fill="#1C1B18"/>')

    # Year markers on the ridge: filled = records/form, hollow = estimate, gray = placeholder.
    for r, x, y in zip(rows, xs, ys):
        st = r['status']
        fill = {'placeholder': '#B9B5AA', 'estimate': '#FFFFFF'}.get(st, '#1C1B18')
        stroke = '#FFFFFF' if st != 'estimate' else '#1C1B18'
        tip = f"{ay_label(r['year'])}: {fmt_num(r['people'])} people · {STATUS_STYLE[st]}"
        if r.get('partial'):
            tip += f" (so far, through {r['partial']})"
        if r['source']:
            tip += f" · {r['source']}"
        cls = '' if standalone else ' class="yr" tabindex="0"'
        out.append(f'<g{cls}><title>{html.escape(tip)}</title>'
                   f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
                   f'<rect x="{x - slot / 2:.1f}" y="{T - 20}" width="{slot:.1f}" height="{ground - T + 20}" '
                   f'fill="transparent"/></g>')

    # Direct labels: the peak and the newest year only.
    peak = max(range(len(rows)), key=lambda i: rows[i]['people'])
    for i in sorted({peak, len(rows) - 1}):
        r = rows[i]
        note = ' so far' if r.get('partial') else ''
        out.append(_t(xs[i], ys[i] - 12, f'{fmt_num(r["people"])}{note}', 13, 'middle', '#1C1B18',
                      extra=' font-weight="500" paint-order="stroke" stroke="#FFFFFF" stroke-width="4" '
                            'stroke-linejoin="round"'))

    # Ground: academic-year ticks every few years.
    every = 1 if span <= 10 else (2 if span <= 20 else 5)
    # Ticks at the start of each academic year (August), so a milestone's flag
    # stands exactly on its year; each year's dot sits mid-year.
    for yr in range(y0, y1 + 2):
        x = X(yr)
        major = (yr - y0) % every == 0 or yr == y1
        out.append(f'<path d="M{x:.1f},{ground}v{6 if major else 3}" stroke="#888780"/>')
        if major and yr <= y1:
            out.append(_t(x, ground + 20, str(yr), 11.5, 'middle', '#C9C9C2', MONO))
    out.append(_t(L, H - 14, 'Ticks mark the start of each academic year (August); each dot is that year’s total',
                  10.5, fill='#888780'))

    # Milestone flags: poles from the ridge up into the sky, labels in tiers.
    def ridge_y(pos):
        xp = X(pos)
        if xp <= xs[0]:
            return ys[0]
        if xp >= xs[-1]:
            return ys[-1]
        for i in range(len(xs) - 1):
            if xs[i] <= xp <= xs[i + 1]:
                t = (xp - xs[i]) / (xs[i + 1] - xs[i])
                return ys[i] + (ys[i + 1] - ys[i]) * t
        return ys[-1]

    tiers = [T - 108, T - 74, T - 40]
    placed = []
    for m in milestones:
        if not (y0 <= m['pos'] <= y1 + 1):
            continue
        x = X(m['pos'])
        label = m['label'] + (' (date TBC)' if m['placeholder'] else '')
        w = (len(label) + 5) * 7.0 + 24      # +5 for the year prefix
        anchor_left = x + w > W - R + 40
        box = (x - w, x) if anchor_left else (x, x + w)
        tier = next((t for t in tiers
                     if not any(bt == t and box[0] < b[1] + 8 and b[0] < box[1] + 8 for b, bt in placed)),
                    tiers[-1])
        placed.append((box, tier))
        top_y = ridge_y(m['pos'])
        hue = '#B9B5AA' if m['placeholder'] else '#534AB7'
        dash = ' stroke-dasharray="3 3"' if m['placeholder'] else ''
        out.append(f'<path d="M{x:.1f},{top_y:.1f}V{tier - 12}" stroke="#1C1B18" stroke-opacity=".55" '
                   f'stroke-width="1.2"{dash}/>')
        flag = (f'M{x:.1f},{tier - 12}h{-12 if anchor_left else 12}l{3 if anchor_left else -3},5'
                f'l{-3 if anchor_left else 3},5h{12 if anchor_left else -12}z')
        out.append(f'<path d="{flag}" fill="{hue}"/>')
        tx = x - 18 if anchor_left else x + 18
        year_txt = m['date'][:4]
        out.append(_t(tx, tier - 12 + 9, f'<tspan font-family="{mono}" fill="#888780">{year_txt}</tspan> '
                      f'{html.escape(label)}', 12.5, 'end' if anchor_left else 'start',
                      '#888780' if m['placeholder'] else '#1C1B18'))

    if draft:
        out.append(_t((L + W - R) / 2, T + 40, 'DRAFT · PLACEHOLDER NUMBERS — NOT REAL DATA', 15, 'middle',
                      '#B07A00', MONO, ' letter-spacing="3" fill-opacity=".75"'))
    out.append('</svg>')
    return '\n'.join(out)


LAND_CSS = """
  :root{--teal:#1D9E75;--ink:#1C1B18;--ink-mid:#4A4945;--ink-soft:#888780;--paper:#FAF8F3;--paper-2:#F1EFE8;--border:#E0DDD4;--white:#FFFFFF;}
  *{margin:0;padding:0;box-sizing:border-box;}
  html{-webkit-print-color-adjust:exact;print-color-adjust:exact;}
  body{font-family:'Outfit',sans-serif;background:var(--paper);color:var(--ink);font-size:13px;}
  .sheet{max-width:1200px;margin:0 auto;background:var(--white);}
  @media screen{body{padding:2rem 16px;}.sheet{border:1px solid var(--border);border-radius:2px;}}
  header{background:var(--ink);padding:1.8rem 2.2rem 1.5rem;}
  .h-label{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.15em;color:var(--teal);text-transform:uppercase;margin-bottom:.45rem;}
  .h-title{font-family:'DM Serif Display',serif;font-size:1.9rem;color:#fff;line-height:1.12;}
  .h-sub{font-size:12.5px;color:#a9a8a2;font-weight:300;margin-top:.35rem;}
  .h-links{margin-top:.9rem;font-family:'DM Mono',monospace;font-size:10px;display:flex;gap:14px;flex-wrap:wrap;}
  .h-links a{color:#c9c9c2;}
  .draft{background:#FFF6E0;border-bottom:1px solid #F0DDA8;padding:.7rem 2.2rem;font-size:12.5px;color:#6b4e00;}
  .section{padding:1.4rem 2.2rem;}
  .section+.section{border-top:1px solid var(--border);}
  .sec-title{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-soft);margin-bottom:.9rem;}
  .land-svg{width:100%;height:auto;display:block;font-family:'Outfit',sans-serif;}
  .yr{cursor:pointer;outline:none;}
  .yr:hover circle,.yr:focus circle{r:7;}
  #tip{position:fixed;pointer-events:none;background:var(--ink);color:#fff;font-size:11.5px;line-height:1.45;padding:.45rem .7rem;border-radius:4px;max-width:320px;display:none;z-index:9;}
  .key{display:flex;gap:18px;flex-wrap:wrap;font-size:11.5px;color:var(--ink-mid);margin-top:.8rem;}
  .key span{display:inline-flex;align-items:center;gap:6px;}
  .key i{display:inline-block;width:10px;height:10px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px #ccc;}
  table{width:100%;border-collapse:collapse;font-size:12px;}
  th{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-soft);text-align:left;font-weight:400;padding:.4rem .5rem;border-bottom:1px solid var(--border);}
  td{padding:.35rem .5rem;border-bottom:1px solid var(--paper-2);}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;}
  .ph{color:var(--ink-soft);font-style:italic;}
  .notes li{margin:0 0 .45rem 1rem;font-size:12px;color:var(--ink-mid);line-height:1.5;}
  .downloads a{color:var(--ink-mid);}
  .scroll{overflow-x:auto;}
  @media (max-width:700px){.section,header,.draft{padding-left:16px;padding-right:16px;}}
"""

LAND_JS = """
(function(){var tip=document.getElementById('tip');
document.querySelectorAll('.yr').forEach(function(g){var t=g.querySelector('title').textContent;g.querySelector('title').remove();
 function show(x,y){tip.textContent=t;tip.style.display='block';tip.style.left=Math.min(x+14,innerWidth-tip.offsetWidth-8)+'px';tip.style.top=(y+14)+'px';}
 g.addEventListener('mousemove',function(e){show(e.clientX,e.clientY);});
 g.addEventListener('mouseleave',function(){tip.style.display='none';});
 g.addEventListener('focus',function(){var b=g.getBoundingClientRect();show(b.left+b.width/2,b.top+40);});
 g.addEventListener('blur',function(){tip.style.display='none';});});})();
"""


def render_landscape_page(rows, milestones, svg, svg_file):
    draft = any(r['status'] == 'placeholder' for r in rows) or any(m['placeholder'] for m in milestones)
    trs = ''.join(
        f'<tr{" class=ph" if r["status"] == "placeholder" else ""}><td>{ay_label(r["year"])}</td>'
        f'<td class="num">{fmt_num(r["people"])}{" (so far)" if r.get("partial") else ""}</td>'
        f'<td>{STATUS_STYLE[r["status"]]}</td><td>{html.escape(r["source"])}</td></tr>' for r in rows)
    mrows = ''.join(
        f'<tr{" class=ph" if m["placeholder"] else ""}><td>{html.escape(m["date"])}</td>'
        f'<td>{html.escape(m["label"])}</td><td>{"date to confirm" if m["placeholder"] else "confirmed"}</td></tr>'
        for m in milestones)
    banner = ('<div class="draft"><strong>Draft.</strong> Grey years and grey flags are placeholder values that only '
              'show the design. Replace them in <code>history.csv</code> and <code>milestones.csv</code>; the banner and '
              'watermark disappear once nothing is a placeholder.</div>') if draft else ''
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NeuroEngage Outreach Landscape</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Serif+Display&family=Outfit:wght@300;400;500&display=swap" rel="stylesheet">
<style>{LAND_CSS}</style></head>
<body><div class="sheet">
<header>
  <div class="h-label">NeuroEngage · Georgia State University</div>
  <div class="h-title">Two decades of neuroscience outreach</div>
  <div class="h-sub">People reached per academic year, {ay_label(rows[0]['year'])} to {ay_label(rows[-1]['year'])}, with program milestones</div>
  <div class="h-links"><a href="index.html">← Dashboard</a><a href="map.html">Outreach map</a><a href="report.html">Progress report</a></div>
</header>
{banner}
<div class="section">
  <div class="scroll">{svg}</div>
  <div class="key">
    <span><i style="background:#1C1B18"></i>from records / event form</span>
    <span><i style="background:#fff;box-shadow:0 0 0 2px #1C1B18"></i>estimate</span>
    <span><i style="background:#B9B5AA"></i>placeholder</span>
  </div>
  <p class="key downloads">Poster file (vector SVG): <a href="{svg_file}" download>{svg_file}</a></p>
</div>
<div class="section"><div class="sec-title">Yearly figures</div>
<table><thead><tr><th>Academic year</th><th class="num">People</th><th>Basis</th><th>Source</th></tr></thead><tbody>{trs}</tbody></table></div>
<div class="section"><div class="sec-title">Milestones</div>
<table><thead><tr><th>Date</th><th>Milestone</th><th>Status</th></tr></thead><tbody>{mrows}</tbody></table></div>
<div class="section"><div class="sec-title">How to read this</div><ul class="notes">
<li>The height of the horizon is the number of people reached in that academic year (Aug–Jul); the ground line is zero. The ridge is a smooth curve through the yearly values that never rises above or dips below a real value.</li>
<li>Years from the NeuroEngage event form are computed live from the same data as the dashboard; earlier years come from <code>history.csv</code>. A year listed there is never added to the form's count.</li>
</ul></div>
</div><div id="tip" role="tooltip"></div><script>{LAND_JS}</script></body></html>"""


def build_landscape(events, history_path, milestones_path, out_dir):
    import os
    rows = build_landscape_data(events, load_history(history_path))
    milestones = load_milestones(milestones_path) if os.path.exists(milestones_path) else []
    svg_name = 'landscape.svg'
    with open(os.path.join(out_dir, svg_name), 'w', encoding='utf-8') as handle:
        handle.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                     + render_landscape_svg(rows, milestones, standalone=True))
    page = os.path.join(out_dir, 'landscape.html')
    with open(page, 'w', encoding='utf-8') as handle:
        handle.write(render_landscape_page(rows, milestones, render_landscape_svg(rows, milestones), svg_name))
    warnings = []
    n_ph = sum(r['status'] == 'placeholder' for r in rows)
    if n_ph:
        warnings.append(f'landscape: {n_ph} placeholder years in {os.path.basename(history_path)} — figure is marked DRAFT')
    n_mph = sum(m['placeholder'] for m in milestones)
    if n_mph:
        warnings.append(f'landscape: {n_mph} milestone dates still placeholders in {os.path.basename(milestones_path)}')
    return [page, os.path.join(out_dir, svg_name)], rows, warnings
