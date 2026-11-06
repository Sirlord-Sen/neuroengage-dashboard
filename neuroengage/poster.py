"""
Poster charts: one standalone SVG (and a 2× PNG via headless Chrome) per panel,
sized for print with large type, in the same teal/purple system as the site.

Panels (all for the reporting window, Aug 2025 onward):

    stats         headline numbers
    lessons       lesson-plan usage: events per lesson plan, people reached as a label
    growth        cumulative people reached, month by month
    audience      K–12 students vs public, one split bar
    people        the same split as rows of people figures (1 figure = 50 people)
    timeline      every event as a dot on a month axis, sized by people reached
    volunteers    how many times each volunteer came out

``docs/poster.html`` previews them all with download links.
"""

import html
import math
import os
import subprocess
import tempfile
from collections import Counter
from datetime import datetime

from .mapping import load_venues, match_venue
from .report import nice_ticks

TEAL, PURPLE = '#1D9E75', '#534AB7'
INK, INK_MID, INK_SOFT, GRID, SURFACE = '#1C1B18', '#4A4945', '#888780', '#E6E3DA', '#FFFFFF'
SANS = "'Outfit','Helvetica Neue',Arial,sans-serif"
SERIF = "'DM Serif Display',Georgia,serif"
MONO = "'DM Mono',Menlo,monospace"
W = 1600

#: How each lesson plan is named on the poster (form wording -> display).
LESSON_NAMES = {
    'Stress in the Brain (3 stations)': 'Stress in the Brain',
    'Galvanic Skin Response (GSR)': 'Skin-response (GSR) stress test',
    'Swimcap': 'Brain-lobe swim caps',
}
MAX_LESSON_ROWS = 8  # the rest fold into "Other"

FONT_LINK = ('<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500'
             '&family=DM+Serif+Display&family=Outfit:wght@300;400;500;600&display=block" rel="stylesheet">')


def _e(s):
    return html.escape(str(s))


def _svg(h, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="{W}" height="{h}" '
            f'role="img" aria-label="{_e(title)}" font-family="{SANS}">'
            f'<rect width="{W}" height="{h}" fill="{SURFACE}"/>{body}</svg>')


def _header(title, sub, x=60):
    return (f'<text x="{x}" y="78" font-family="{SERIF}" font-size="52" fill="{INK}">{_e(title)}</text>'
            f'<text x="{x}" y="128" font-size="27" fill="{INK_MID}" font-weight="300">{_e(sub)}</text>')


def _bar_path(x, y, w, h, r=4):
    """Horizontal bar, square at the baseline (left), rounded at the data end."""
    r = min(r, w, h / 2)
    return (f'M{x:.1f},{y:.1f}H{x + w - r:.1f}Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f}'
            f'V{y + h - r:.1f}Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f}H{x:.1f}Z')


def _fmt(n):
    return f'{n:,.0f}' if isinstance(n, (int, float)) and float(n).is_integer() else f'{n:,}'


# ── data ────────────────────────────────────────────────────────────────────

def build_poster_data(report, events, venues_path):
    since = report['since']
    window = [e for e in events if e['month_sort'] >= since]

    uses, people = Counter(), Counter()
    for e in window:
        for a in e['activities']:
            uses[a] += 1
            people[a] += e['attendees'] or 0
    ranked = uses.most_common()
    lessons = [{'name': LESSON_NAMES.get(a, a), 'key': a, 'events': c, 'people': people[a]}
               for a, c in ranked[:MAX_LESSON_ROWS] if c > 1]
    rest = [(a, c) for a, c in ranked if LESSON_NAMES.get(a, a) not in {l['name'] for l in lessons}]
    if rest:
        lessons.append({'name': f'Other ({len(rest)} one-off activities)', 'key': 'Other', 'events': sum(c for _, c in rest),
                        'people': None, 'other': [a for a, _ in rest]})

    venues = load_venues(venues_path) if os.path.exists(venues_path) else {}
    aud = {'k12': {'people': 0, 'events': 0}, 'public': {'people': 0, 'events': 0}}
    timeline = []
    for e in window:
        row = match_venue(e['venue'], venues) if venues else None
        key = row['audience'] if row else 'public'
        aud[key]['people'] += e['attendees'] or 0
        aud[key]['events'] += 1
        timeline.append({'date': e['date_sort'], 'people': e['attendees'] or 0, 'audience': key,
                         'label': row['label'] if row else e['venue'].strip()})

    return {
        'since_label': datetime.strptime(since, '%Y-%m').strftime('%b %Y'),
        'through': report['data_through'],
        'totals': report['totals'],
        'repeat': report['repeat_count'],
        'monthly': report['monthly'],
        'buckets': report['buckets'],
        'lessons': lessons,
        'events_total': len(window),
        'audience': aud,
        'timeline': timeline,
    }


# ── panels ──────────────────────────────────────────────────────────────────

def stats_svg(d):
    t = d['totals']
    tiles = [
        (f"{t['attendees']:,}", 'people reached'),
        (f"{t['events']}", 'outreach events'),
        (f"{t['volunteers']}", 'GSU volunteers'),
        (f"{round(t['hours']):,}", 'volunteer hours'),
    ]
    h, cw = 300, (W - 120) / 4
    body = []
    for i, (v, lab) in enumerate(tiles):
        x = 60 + i * cw
        if i:
            body.append(f'<line x1="{x:.0f}" y1="70" x2="{x:.0f}" y2="250" stroke="{GRID}" stroke-width="2"/>')
        accent = TEAL if i == 0 else INK
        body.append(f'<text x="{x + 30:.0f}" y="170" font-family="{SERIF}" font-size="104" fill="{accent}">{v}</text>'
                    f'<text x="{x + 34:.0f}" y="222" font-size="30" fill="{INK_MID}">{lab}</text>')
    body.append(f'<text x="60" y="285" font-size="21" fill="{INK_SOFT}" font-weight="300">'
                f'{_e(d["since_label"])} – {_e(d["through"])} · {d["repeat"]} volunteers served at 2 or more events</text>')
    return _svg(h, ''.join(body), 'Headline numbers')


def lessons_svg(d):
    rows = d['lessons']
    top = rows[0]
    share = top['events'] / d['events_total']
    frac = {2: 'half', 3: 'a third'}.get(round(1 / share)) if share < .5 else None
    title = (f'{top["name"]} went to {top["events"]} of {d["events_total"]} events'
             if not frac else f'{top["name"]} went to {frac} of all events')
    label_w, x0, row_h, bar_h = 520, 60 + 520, 66, 24
    h = 190 + len(rows) * row_h + 40
    mx = max(r['events'] for r in rows)
    plot_w = W - x0 - 330
    body = [_header(title, f'Lesson plans used at outreach events, {d["since_label"]} – {d["through"]} · '
                           'an event can use more than one')]
    for i, r in enumerate(rows):
        y = 190 + i * row_h
        w = max(4, plot_w * r['events'] / mx)
        hue = TEAL if i == 0 else '#8FCDB8'
        if r.get('other'):
            hue = '#C9C6BC'
        people = f' · {r["people"]:,} people' if r['people'] else ''
        tip = f'{r["name"]}: {r["events"]} events' + (f', {r["people"]:,} people' if r['people'] else '')
        if r.get('other'):
            tip += ' — ' + '; '.join(r['other'])
        body.append(_icon(r['key'], 64, y + bar_h / 2 - 22, TEAL if i == 0 else INK_MID))
        body.append(f'<g><title>{_e(tip)}</title>'
                    f'<text x="128" y="{y + bar_h / 2 + 9:.0f}" font-size="28" '
                    f'fill="{INK if i == 0 else INK_MID}" font-weight="{500 if i == 0 else 400}">{_e(r["name"])}</text>'
                    f'<path d="{_bar_path(x0, y, w, bar_h)}" fill="{hue}"/>'
                    f'<text x="{x0 + w + 16:.0f}" y="{y + bar_h / 2 + 9:.0f}" font-size="27" fill="{INK}" font-weight="500">'
                    f'{r["events"]}<tspan font-weight="300" fill="{INK_SOFT}">'
                    f'{" events" if i == 0 else ""}{people}'
                    f'</tspan></text></g>')
    body.append(f'<line x1="{x0}" y1="176" x2="{x0}" y2="{190 + len(rows) * row_h - 30}" stroke="{INK_SOFT}" stroke-width="1"/>')
    return _svg(h, ''.join(body), 'Lesson plan usage')


def growth_svg(d):
    rows = d['monthly']
    vals = [r['cum']['attendees'] for r in rows]
    h, x0, x1, y0, y1 = 760, 150, W - 220, 650, 190
    ticks = nice_ticks(max(vals))
    ymax = ticks[-1]
    n = len(rows)
    X = lambda i: x0 + (x1 - x0) * i / max(1, n - 1)
    Y = lambda v: y0 - (y0 - y1) * v / ymax
    body = [_header(f'{vals[-1]:,} people reached, and still climbing',
                    f'Cumulative people reached at outreach events, {d["since_label"]} – {d["through"]}')]
    for t in ticks:
        body.append(f'<line x1="{x0}" y1="{Y(t):.1f}" x2="{x1}" y2="{Y(t):.1f}" stroke="{GRID}" stroke-width="1.5"/>'
                    f'<text x="{x0 - 18}" y="{Y(t) + 9:.1f}" text-anchor="end" font-size="24" fill="{INK_SOFT}" '
                    f'font-family="{MONO}">{t:,}</text>')
    pts = ' '.join(f'{X(i):.1f},{Y(v):.1f}' for i, v in enumerate(vals))
    body.append(f'<polygon points="{X(0):.1f},{y0} {pts} {X(n - 1):.1f},{y0}" fill="{TEAL}" fill-opacity=".12"/>'
                f'<polyline points="{pts}" fill="none" stroke="{TEAL}" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>')
    step = max(1, math.ceil(n / 9))
    for i, r in enumerate(rows):
        m = datetime.strptime(r['month'], '%Y-%m')
        if i % step == 0 or i == n - 1:
            lab = m.strftime('%b') + (f" ’{m.strftime('%y')}" if m.month in (1, 8) or i == 0 else '')
            body.append(f'<text x="{X(i):.1f}" y="{y0 + 44}" text-anchor="middle" font-size="24" fill="{INK_SOFT}">{lab}</text>')
        body.append(f'<g><title>{_e(r["label"])}: {r["attendees"]:,} this month, {vals[i]:,} total</title>'
                    f'<circle cx="{X(i):.1f}" cy="{Y(vals[i]):.1f}" r="16" fill="transparent"/></g>')
    # label the biggest monthly jump and the end
    jump = max(range(n), key=lambda i: rows[i]['attendees'])
    jm = rows[jump]
    body.append(f'<circle cx="{X(jump):.1f}" cy="{Y(vals[jump]):.1f}" r="8" fill="{TEAL}" stroke="{SURFACE}" stroke-width="3"/>'
                f'<text x="{X(jump) - 16:.1f}" y="{Y(vals[jump]) - 22:.1f}" text-anchor="end" font-size="24" fill="{INK_MID}">'
                f'+{jm["attendees"]:,} in {_e(jm["label"])}</text>')
    body.append(f'<circle cx="{X(n - 1):.1f}" cy="{Y(vals[-1]):.1f}" r="9" fill="{TEAL}" stroke="{SURFACE}" stroke-width="3"/>'
                f'<text x="{X(n - 1) + 20:.1f}" y="{Y(vals[-1]) + 10:.1f}" font-size="34" font-weight="600" fill="{INK}">{vals[-1]:,}</text>')
    body.append(f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="{INK_SOFT}" stroke-width="1.5"/>')
    return _svg(h, ''.join(body), 'People reached over time')


def audience_svg(d):
    k, p = d['audience']['k12'], d['audience']['public']
    total = k['people'] + p['people'] or 1
    h, x0, x1, y, bh = 400, 60, W - 60, 190, 64
    wk = (x1 - x0) * k['people'] / total
    gap = 4
    pct = lambda n: f'{round(100 * n / total)}%'
    body = [_header(f'{pct(k["people"])} of the people we reach are K–12 students',
                    f'People reached by audience, {d["since_label"]} – {d["through"]}')]
    body.append(f'<g><title>K–12 school &amp; youth: {k["people"]:,} people at {k["events"]} visits</title>'
                f'<rect x="{x0}" y="{y}" width="{wk - gap / 2:.1f}" height="{bh}" rx="4" fill="{TEAL}"/></g>'
                f'<g><title>Public &amp; community: {p["people"]:,} people at {p["events"]} events</title>'
                f'<rect x="{x0 + wk + gap / 2:.1f}" y="{y}" width="{x1 - x0 - wk - gap / 2:.1f}" height="{bh}" rx="4" fill="{PURPLE}"/></g>')
    body.append(f'<text x="{x0 + 28}" y="{y + bh / 2 + 12:.0f}" font-size="34" font-weight="600" fill="#fff">{pct(k["people"])}</text>'
                f'<text x="{x1 - 28}" y="{y + bh / 2 + 12:.0f}" text-anchor="end" font-size="34" font-weight="600" fill="#fff">{pct(p["people"])}</text>')
    ly = y + bh + 66
    body.append(f'<circle cx="{x0 + 12}" cy="{ly - 10}" r="12" fill="{TEAL}"/>'
                f'<text x="{x0 + 36}" y="{ly}" font-size="30" fill="{INK}"><tspan font-weight="600">{k["people"]:,}</tspan> '
                f'K–12 students</text>'
                f'<text x="{x0 + 36}" y="{ly + 40}" font-size="25" fill="{INK_MID}" font-weight="300">{k["events"]} school &amp; youth visits · '
                f'~{round(k["people"] / max(1, k["events"]))} per visit</text>')
    px = x0 + (x1 - x0) / 2 + 40
    body.append(f'<circle cx="{px + 12}" cy="{ly - 10}" r="12" fill="{PURPLE}"/>'
                f'<text x="{px + 36}" y="{ly}" font-size="30" fill="{INK}"><tspan font-weight="600">{p["people"]:,}</tspan> '
                f'members of the public</text>'
                f'<text x="{px + 36}" y="{ly + 40}" font-size="25" fill="{INK_MID}" font-weight="300">{p["events"]} festivals, '
                f'museum &amp; community events · ~{round(p["people"] / max(1, p["events"]))} per event</text>')
    return _svg(h, ''.join(body), 'Who we reach')


def volunteers_svg(d):
    items = list(d['buckets'].items())
    total = sum(v for _, v in items) or 1
    back = d['repeat']
    h, x0, y0, y1 = 640, 150, 540, 200
    plot_w = W - x0 - 120
    slot = plot_w / len(items)
    bw = min(150, slot * .5)
    mx = max(v for _, v in items)
    ticks = nice_ticks(mx)
    Y = lambda v: y0 - (y0 - y1) * v / ticks[-1]
    body = [_header(f'{back} of {total} volunteers came back for more',
                    f'GSU volunteers by number of events they served at, {d["since_label"]} – {d["through"]}')]
    for t in ticks:
        body.append(f'<line x1="{x0}" y1="{Y(t):.1f}" x2="{W - 120}" y2="{Y(t):.1f}" stroke="{GRID}" stroke-width="1.5"/>'
                    f'<text x="{x0 - 18}" y="{Y(t) + 9:.1f}" text-anchor="end" font-size="24" fill="{INK_SOFT}" font-family="{MONO}">{t}</text>')
    for i, (lab, v) in enumerate(items):
        cx = x0 + slot * (i + .5)
        hue = '#C9C6BC' if i == 0 else TEAL
        top = Y(v)
        r = min(4, (y0 - top) / 2)
        path = (f'M{cx - bw / 2:.1f},{y0}V{top + r:.1f}Q{cx - bw / 2:.1f},{top:.1f} {cx - bw / 2 + r:.1f},{top:.1f}'
                f'H{cx + bw / 2 - r:.1f}Q{cx + bw / 2:.1f},{top:.1f} {cx + bw / 2:.1f},{top + r:.1f}V{y0}Z')
        body.append(f'<g><title>{_e(lab)}: {v} volunteers</title><path d="{path}" fill="{hue}"/></g>'
                    f'<text x="{cx:.1f}" y="{top - 16:.1f}" text-anchor="middle" font-size="32" font-weight="600" fill="{INK}">{v}</text>'
                    f'<text x="{cx:.1f}" y="{y0 + 44}" text-anchor="middle" font-size="27" fill="{INK_MID}">{_e(lab)}</text>')
    body.append(f'<line x1="{x0}" y1="{y0}" x2="{W - 120}" y2="{y0}" stroke="{INK_SOFT}" stroke-width="1.5"/>')
    return _svg(h, ''.join(body), 'Volunteer return')


# ── icons (44×44 line glyphs, drawn in ink — identity comes from the label) ──

_BRAIN = ('M22 6c-3-3-9-2-10 3-5 0-8 5-6 9-3 3-2 9 2 10 0 5 5 8 9 6 2 3 5 3 5 3z'
          'M22 6c3-3 9-2 10 3 5 0 8 5 6 9 3 3 2 9-2 10 0 5-5 8-9 6-2 3-5 3-5 3'
          'M12 14c3 0 5 2 5 5M32 14c-3 0-5 2-5 5M10 26c3-1 6 0 7 3M34 26c-3-1-6 0-7 3')
ICONS = {
    'Touch-a-Brain': _BRAIN + 'M30 44v-6l-3-4c-1-2 1-3 2-2l3 3v-9c0-2 3-2 3 0v6c0-2 3-2 3 0v1c0-2 3-2 3 0v6l-2 5',
    'Build-a-Brain': _BRAIN + 'M33 33h10M38 28v10',
    'Build-a-Neuron': ('M22 22m-6 0a6 6 0 1 0 12 0a6 6 0 1 0-12 0M17 18l-7-8M10 10l-4 1M10 10l0-5'
                       'M16 25l-9 5M7 30l-3-3M27 18l6-9M33 9l4 1M28 22h12c3 0 3 4 6 4M40 22l2 6M36 22l1 5'),
    'Cognitive Testing': 'M11 6h22v34H11zM17 4h10v5H17zM15 17l3 3 5-6M15 29l3 3 5-6M26 18h4M26 30h4',
    'Presentation': 'M5 7h34v22H5zM22 29v8M14 42l8-5 8 5M11 22l7-7 5 4 9-9',
    'Stress in the Brain (3 stations)': 'M25 3L10 25h10l-4 17 18-24H23z',
    'Swimcap': 'M5 30c0-14 8-22 17-22s17 8 17 22zM5 30h34M22 8v22M13 13l4 17M31 13l-4 17M8 22h28',
    'Galvanic Skin Response (GSR)': 'M3 26h8l4-10 5 20 5-26 4 16h12M37 15a4 4 0 1 0 0.1 0',
    'Other': 'M10 22a3 3 0 1 0 0.1 0M22 22a3 3 0 1 0 0.1 0M34 22a3 3 0 1 0 0.1 0',
}


def _icon(key, x, y, color):
    d = ICONS.get(key, _BRAIN)
    return (f'<path d="{d}" transform="translate({x:.1f},{y:.1f})" fill="none" stroke="{color}" '
            f'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>')


# ── people-figure chart (isotype): one figure = PER_FIGURE people ──────────

PER_FIGURE = 50
_PERSON = 'M12 1a6.5 6.5 0 1 1-0.1 0zM2 44V25a10 10 0 0 1 20 0v19z'


def people_svg(d):
    k, p = d['audience']['k12'], d['audience']['public']
    per_row, fw, fh, x0 = 32, 44, 58, 60
    groups = [('K–12 students', k, TEAL, f'{k["events"]} school & youth visits'),
              ('Members of the public', p, PURPLE, f'{p["events"]} festivals, museum & community events')]
    total = k['people'] + p['people'] or 1
    y = 200
    body, defs = [], []
    for gi, (name, g, hue, sub) in enumerate(groups):
        n = g['people'] / PER_FIGURE
        body.append(f'<text x="{x0}" y="{y}" font-size="34" fill="{INK}"><tspan font-weight="600">{g["people"]:,}</tspan> {_e(name)}'
                    f'<tspan font-size="25" fill="{INK_MID}" font-weight="300">  ·  {round(100 * g["people"] / total)}% · {_e(sub)}</tspan></text>')
        y += 26
        count = max(1, round(n))  # whole figures only, same rule for every row
        for i in range(count):
            fx = x0 + (i % per_row) * fw
            fy = y + (i // per_row) * fh
            body.append(f'<path d="{_PERSON}" transform="translate({fx},{fy})" fill="{hue}"/>')
        y += math.ceil(count / per_row) * fh + 70
    h = y - 10
    body.insert(0, _header(f'Most of the people we reach are K–12 students',
                           f'People reached by audience, {d["since_label"]} – {d["through"]}'))
    body.append(f'<path d="{_PERSON}" transform="translate({x0},{h - 58}) scale(.6)" fill="{INK_MID}"/>'
                f'<text x="{x0 + 24}" y="{h - 34}" font-size="24" fill="{INK_MID}">= {PER_FIGURE} people (rounded to the nearest figure)</text>')
    return _svg(h, f'<defs>{"".join(defs)}</defs>' + ''.join(body), 'Who we reach, as people')


# ── event timeline: every event a dot, sized by people reached ─────────────

def timeline_svg(d):
    evs = sorted(d['timeline'], key=lambda e: e['date'])
    x0, x1, mid = 90, W - 90, 430
    first = datetime.strptime(d['monthly'][0]['month'] + '-01', '%Y-%m-%d')
    last_m = datetime.strptime(d['monthly'][-1]['month'] + '-01', '%Y-%m-%d')
    end = datetime(last_m.year + (last_m.month == 12), last_m.month % 12 + 1, 1)
    span = (end - first).days
    X = lambda dt: x0 + (x1 - x0) * (datetime.strptime(dt, '%Y-%m-%d') - first).days / span
    mx = max(e['people'] for e in evs) or 1
    R = lambda n: max(7, 52 * math.sqrt(n / mx))
    placed = []
    for e in sorted(evs, key=lambda e: -e['people']):
        x, r = X(e['date']), R(e['people'])
        for k in range(200):
            off = ((k + 1) // 2) * 3 * (1 if k % 2 else -1)
            y = mid + off
            if all(math.hypot(x - px, y - py) >= r + pr + 3 for px, py, pr, _ in placed):
                break
        placed.append((x, y, r, e))
    # labels for the biggest events sit in lanes above the swarm, with leaders
    lab_items = []
    for x, y, r, e in sorted(placed, key=lambda t: -t[3]['people'])[:6]:
        w = (len(e['label']) + len(f'{e["people"]:,}') + 1) * 12.2
        cx = min(max(x, x0 + w / 2), x1 - w / 2)
        lab_items.append([cx, w, x, y, r, e, 0])
    lanes = []
    for item in sorted(lab_items, key=lambda t: t[0]):
        lane = 0
        while any(abs(item[0] - o[0]) < (item[1] + o[1]) / 2 + 24 for o in lanes if o[6] == lane):
            lane += 1
        item[6] = lane
        lanes.append(item)
    n_lanes = max([i[6] for i in lab_items] + [0]) + 1
    top = min(py - pr for _, py, pr, _ in placed)
    bot = max(py + pr for _, py, pr, _ in placed)
    lane_y = lambda k: 210 + (n_lanes - 1 - k) * 40
    shift = lane_y(0) + 40 - top
    axis_y = bot + shift + 40
    h = int(axis_y + 110)
    body = [_header(f'{len(evs)} events in {round(span / 30.4)} months',
                    f'Every outreach event, {d["since_label"]} – {d["through"]} · dot area = people reached')]
    # month grid
    m = first
    while m < end:
        x = X(m.strftime('%Y-%m-%d'))
        body.append(f'<line x1="{x:.1f}" y1="{lane_y(0) + 20}" x2="{x:.1f}" y2="{axis_y}" stroke="{GRID}" stroke-width="1.5"/>')
        nm = datetime(m.year + (m.month == 12), m.month % 12 + 1, 1)
        cx = (x + X(nm.strftime('%Y-%m-%d'))) / 2
        lab = m.strftime('%b') + (f" ’{m.strftime('%y')}" if m.month in (1, 8) or m == first else '')
        body.append(f'<text x="{cx:.1f}" y="{axis_y + 36}" text-anchor="middle" font-size="22" fill="{INK_SOFT}">{lab}</text>')
        m = nm
    body.append(f'<line x1="{x0}" y1="{axis_y}" x2="{x1}" y2="{axis_y}" stroke="{INK_SOFT}" stroke-width="1.5"/>')
    for cx, w, x, y, r, e, lane in lab_items:
        ty = lane_y(lane)
        body.append(f'<line x1="{x:.1f}" y1="{ty + 8}" x2="{x:.1f}" y2="{y + shift - r:.1f}" stroke="{INK_SOFT}" stroke-width="1.5"/>'
                    f'<text x="{cx:.1f}" y="{ty:.1f}" text-anchor="middle" font-size="22" fill="{INK}">'
                    f'{_e(e["label"])} <tspan font-family="{MONO}" fill="{INK_MID}">{e["people"]:,}</tspan></text>')
    hue = {'k12': TEAL, 'public': PURPLE}
    for x, y, r, e in sorted(placed, key=lambda t: -t[2]):
        when = datetime.strptime(e['date'], '%Y-%m-%d').strftime('%b %-d, %Y')
        body.append(f'<g><title>{_e(e["label"])} — {when}: {e["people"]:,} people</title>'
                    f'<circle cx="{x:.1f}" cy="{y + shift:.1f}" r="{r:.1f}" fill="{hue[e["audience"]]}" fill-opacity=".85" '
                    f'stroke="{SURFACE}" stroke-width="3"/></g>')
    ly = h - 30
    body.append(f'<circle cx="{x0 + 10}" cy="{ly - 8}" r="10" fill="{TEAL}"/>'
                f'<text x="{x0 + 30}" y="{ly}" font-size="24" fill="{INK_MID}">K–12 school &amp; youth</text>'
                f'<circle cx="{x0 + 330}" cy="{ly - 8}" r="10" fill="{PURPLE}"/>'
                f'<text x="{x0 + 350}" y="{ly}" font-size="24" fill="{INK_MID}">Public &amp; community</text>')
    return _svg(h, ''.join(body), 'Event timeline')


def _untitled(svg, cut=150):
    """Drop the baked-in title block by moving the viewBox below it."""
    h = int(svg.split('height="', 1)[1].split('"', 1)[0])
    return (svg.replace(f'viewBox="0 0 {W} {h}"', f'viewBox="0 {cut} {W} {h - cut}"', 1)
               .replace(f'height="{h}"', f'height="{h - cut}"', 1))


PANELS = (
    ('stats', 'Headline numbers', stats_svg),
    ('lessons', 'Lesson plan usage', lessons_svg),
    ('growth', 'People reached over time', growth_svg),
    ('audience', 'Who we reach', audience_svg),
    ('people', 'Who we reach (people figures)', people_svg),
    ('timeline', 'Every event on a timeline', timeline_svg),
    ('volunteers', 'Volunteers coming back', volunteers_svg),
)


# ── output ──────────────────────────────────────────────────────────────────

def _png(svg, chrome, path, scale=2):
    h = int(svg.split('height="', 1)[1].split('"', 1)[0])
    page = (f'<!doctype html><html><head>{FONT_LINK}<style>html,body{{margin:0;padding:0;background:#fff;}}'
            f'svg{{display:block;}}</style></head><body>{svg}</body></html>')
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'p.html')
        with open(src, 'w', encoding='utf-8') as fh:
            fh.write(page)
        subprocess.run([chrome, '--headless=new', '--disable-gpu', '--hide-scrollbars',
                        f'--window-size={W},{h}', f'--force-device-scale-factor={scale}',
                        '--virtual-time-budget=6000', f'--screenshot={path}', 'file://' + src],
                       capture_output=True, timeout=60)
    return os.path.exists(path)


def build_poster(report, events, venues_path, out_dir, chrome=None):
    """Write docs/poster/<panel>.svg (+ .png with chrome) and docs/poster.html."""
    d = build_poster_data(report, events, venues_path)
    folder = os.path.join(out_dir, 'poster')
    os.makedirs(folder, exist_ok=True)
    written, cards = [], []
    for key, name, fn in PANELS:
        svg = fn(d)
        with open(os.path.join(folder, f'{key}.svg'), 'w', encoding='utf-8') as fh:
            fh.write('<?xml version="1.0" encoding="UTF-8"?>\n' + svg)
        written.append(os.path.join(folder, f'{key}.svg'))
        links = f'<a href="poster/{key}.svg" download>SVG</a>'
        if chrome and _png(svg, chrome, os.path.join(folder, f'{key}.png')):
            written.append(os.path.join(folder, f'{key}.png'))
            links = f'<a href="poster/{key}.png" download>PNG</a> ' + links
        if key != 'stats':
            bare = _untitled(svg)
            with open(os.path.join(folder, f'{key}_notitle.svg'), 'w', encoding='utf-8') as fh:
                fh.write('<?xml version="1.0" encoding="UTF-8"?>\n' + bare)
            written.append(os.path.join(folder, f'{key}_notitle.svg'))
            links += f' · no title: <a href="poster/{key}_notitle.svg" download>SVG</a>'
            if chrome and _png(bare, chrome, os.path.join(folder, f'{key}_notitle.png')):
                written.append(os.path.join(folder, f'{key}_notitle.png'))
                links += f' <a href="poster/{key}_notitle.png" download>PNG</a>'
        cards.append(f'<section><div class="cap"><span>{_e(name)}</span><span class="dl">{links}</span></div>{svg}</section>')
    cards.append('<section><div class="cap"><span>Outreach map</span><span class="dl">'
                 '<a href="map_poster_k12.png" download>K–12 PNG</a> <a href="map_poster_all.png" download>All events PNG</a>'
                 '</span></div><img src="map_poster_k12.png" alt="Map of K–12 school visits, dots sized by students reached"></section>')
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>NeuroEngage Poster Charts</title>{FONT_LINK}
<style>
  :root{{--ink:#1C1B18;--soft:#888780;--paper:#FAF8F3;--border:#E0DDD4;}}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:'Outfit',sans-serif;background:var(--paper);color:var(--ink);padding:2rem 16px;}}
  .wrap{{max-width:1100px;margin:0 auto;}}
  h1{{font-family:'DM Serif Display',serif;font-weight:400;font-size:2rem;}}
  .sub{{color:var(--soft);margin:.3rem 0 1.5rem;font-size:14px;}}
  .sub a{{color:var(--ink);}}
  section{{background:#fff;border:1px solid var(--border);border-radius:4px;margin-bottom:1.4rem;overflow:hidden;}}
  .cap{{display:flex;justify-content:space-between;padding:.6rem 1rem;border-bottom:1px solid var(--border);
        font-family:'DM Mono',monospace;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--soft);}}
  .dl a{{color:var(--ink);margin-left:10px;}}
  section svg,section img{{display:block;width:100%;height:auto;}}
</style></head><body><div class="wrap">
<h1>Poster charts</h1>
<p class="sub">{_e(d['since_label'])} – {_e(d['through'])} · each panel downloads as a 3200-px PNG or a vector SVG ·
<a href="index.html">Dashboard</a> · <a href="map.html">Map</a> · <a href="landscape.html">20-year landscape</a></p>
{''.join(cards)}
</div></body></html>"""
    with open(os.path.join(out_dir, 'poster.html'), 'w', encoding='utf-8') as fh:
        fh.write(page)
    written.insert(0, os.path.join(out_dir, 'poster.html'))
    return written
