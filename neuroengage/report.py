"""
Cumulative progress report for Dana Foundation reporting.

Builds docs/report.html from the same merged event stream as the dashboard, so
the two can never disagree. The report answers one question — how has outreach
accumulated since fall 2025? — with cumulative charts, per-term snapshots, and
a volunteer analysis (distinct and repeat volunteers, which the form already
captures via the additional-volunteers field).

Charts are server-rendered SVG: they need no JavaScript, so the page prints to
PDF exactly as it renders on screen. A light hover layer is added on screen.

Design notes (dashboard design system, validated with the dataviz palette
checker): one series per chart so identity is carried by each chart's title,
never by hue alone; every plotted value is also reachable through the monthly
data table and the term snapshot table; the repeat-volunteer ramp
#5FBFA0→#0A5C43 passes the ordinal checks (monotone lightness, ΔL ≥ .06,
light end ≥ 2:1 on white).
"""

import html
import json
import re
from collections import Counter, OrderedDict
from datetime import datetime
from difflib import SequenceMatcher

from .data import month_range

#: Start of the grant reporting window (advisor: "cumulative since fall 2025").
#: Events before this month are excluded from the report and noted; the grant
#: period itself runs through December 2027.
REPORT_START = '2025-08'
REPORT_HORIZON = 'December 2027'

#: Academic terms used for the snapshot table. Stated in the report footnotes.
TERMS = {
    (8, 9, 10, 11, 12): 'Fall',
    (1, 2, 3, 4): 'Spring',
    (5, 6, 7): 'Summer',
}

#: Entity colors, identical to the dashboard's (color follows the entity).
SERIES = {
    'attendees':  {'hue': '#1D9E75', 'label': 'People reached'},
    'events':     {'hue': '#534AB7', 'label': 'Events held'},
    'hours':      {'hue': '#BA7517', 'label': 'Event hours'},
    'volunteers': {'hue': '#E24B4A', 'label': 'Distinct volunteers'},
}

#: Reference paces from the NeuroEngage proposal (Dana NextGen), drawn as
#: gray target lines so each chart reads against what the grant committed to:
#: Goal 1b doubles outreach from one to two events per month; the program's
#: stated baseline is ≥1,000 K-12 students & public and ~100 volunteers a year.
#: Values are per-month rates. Hours has no stated target.
PROPOSAL_PACE = {
    'events':     {'rate': 2.0,        'label': 'proposal target (2/mo)'},
    'attendees':  {'rate': 1000 / 12,  'label': 'program baseline (1,000/yr)'},
    'volunteers': {'rate': 100 / 12,   'label': 'program baseline (~100/yr)'},
}

#: The proposal's named signature lesson plans (Goal 1a).
SIGNATURE_ACTIVITIES = ('Touch-a-Brain', 'Build-a-Brain', 'Build-a-Neuron')

#: Pre-grant program history: people reached per year, from Maria's annual
#: DMAP infographics. Fill this in and a "program history" panel appears on
#: the report and in the deck — past years in gray, the grant year (computed
#: live from the event data, never hand-entered) highlighted in teal. This is
#: how the report shows years of prior work without restarting the cumulative
#: charts anywhere but the true start of the reporting window.
#: e.g. PROGRAM_HISTORY = OrderedDict([('2023–24', 1150), ('2024–25', 1400)])
PROGRAM_HISTORY = OrderedDict()

#: Ordinal ramp for the repeat-volunteer buckets (validated, see module docstring).
RAMP = ['#5FBFA0', '#2FA981', '#158A64', '#0A5C43']


def normalize_venue(name):
    """Fold venue spellings for visit counting.

    Strips grade-level parentheticals ("(K-5)", "(8th Grade)") so one campus
    counts as one venue, and lets a fuzzy match absorb typos like
    "Gwinnet"/"Gwinnett". Distinct programs at one site (e.g. Beacon Hill
    Middle School vs Beacon Hill Gifted Connections) stay separate.
    """
    text = re.sub(r'\s*\([^)]*\)\s*', ' ', name or '')
    return re.sub(r'\s+', ' ', text).strip().lower()


def venue_stats(events):
    """Visits per venue with typo-folding; returns (list of (name, count), repeat_count)."""
    keys, surfaces = [], {}
    counts = Counter()
    for e in events:
        key = normalize_venue(e['venue'])
        if not key:
            continue
        match = next(
            (k for k in keys if SequenceMatcher(None, key, k).ratio() >= 0.92),
            None,
        )
        if match is None:
            keys.append(key)
            match = key
        counts[match] += 1
        surfaces.setdefault(match, Counter())[
            re.sub(r'\s*\([^)]*\)\s*', ' ', e['venue']).strip()] += 1
    ranked = [(surfaces[k].most_common(1)[0][0], n) for k, n in counts.most_common()]
    repeat = sum(1 for _, n in counts.items() if n >= 2)
    return ranked, repeat


def term_of(month_key):
    """'2025-09' -> ('Fall 2025', sort_key). Terms: Aug–Dec / Jan–Apr / May–Jul."""
    year, month = int(month_key[:4]), int(month_key[5:7])
    for months, name in TERMS.items():
        if month in months:
            return f'{name} {year}', (year, min(months))
    raise ValueError(month_key)


def month_label(month_key):
    stamp = datetime.strptime(month_key, '%Y-%m')
    return f"{stamp.strftime('%b')} {stamp.strftime('%Y')}"


# ── SERIES ───────────────────────────────────────────────────────────────────

def build_report_data(events, since=REPORT_START):
    """Split events at the window and build every series the report shows."""
    before = [e for e in events if e['month_sort'] < since]
    window = [e for e in events if e['month_sort'] >= since]

    excluded = {
        'events': len(before),
        'attendees': sum(e['attendees'] or 0 for e in before),
        'hours': round(sum(e['hours'] or 0.0 for e in before), 2),
    }

    months = month_range(since, window[-1]['month_sort']) if window else []
    by_month = {m: [] for m in months}
    for e in window:
        by_month[e['month_sort']].append(e)

    # People are credited at their first appearance, so the volunteer curve is
    # a cumulative count of distinct individuals, not of participations.
    first_seen, participations = {}, Counter()
    for e in window:
        for person in e['leads'] + e['volunteers']:
            first_seen.setdefault(person, e['month_sort'])
            participations[person] += 1

    monthly, cum = [], {'events': 0, 'attendees': 0, 'hours': 0.0, 'volunteers': 0}
    for m in months:
        evs = by_month[m]
        new_people = sum(1 for p, fm in first_seen.items() if fm == m)
        cum['events'] += len(evs)
        cum['attendees'] += sum(e['attendees'] or 0 for e in evs)
        cum['hours'] = round(cum['hours'] + sum(e['hours'] or 0.0 for e in evs), 2)
        cum['volunteers'] += new_people
        monthly.append({
            'month': m,
            'label': month_label(m),
            'events': len(evs),
            'attendees': sum(e['attendees'] or 0 for e in evs),
            'hours': round(sum(e['hours'] or 0.0 for e in evs), 2),
            'new_volunteers': new_people,
            'cum': dict(cum),
        })

    # Term snapshots: activity during each term plus the cumulative position
    # at term end — the advisor's "snapshots on a cumulative basis".
    terms = OrderedDict()
    for row in monthly:
        name, sort = term_of(row['month'])
        t = terms.setdefault(name, {
            'sort': sort, 'events': 0, 'attendees': 0, 'hours': 0.0,
            'active': set(), 'new_volunteers': 0, 'cum': None,
        })
        t['events'] += row['events']
        t['attendees'] += row['attendees']
        t['hours'] = round(t['hours'] + row['hours'], 2)
        t['new_volunteers'] += row['new_volunteers']
        t['cum'] = row['cum']
    for name, t in terms.items():
        for e in window:
            if term_of(e['month_sort'])[0] == name:
                t['active'].update(e['leads'] + e['volunteers'])
        t['active'] = len(t['active'])

    # Repeat volunteers, bucketed by events served.
    buckets = OrderedDict((('1 event', 0), ('2 events', 0), ('3–5 events', 0), ('6+ events', 0)))
    for count in participations.values():
        if count == 1:
            buckets['1 event'] += 1
        elif count == 2:
            buckets['2 events'] += 1
        elif count <= 5:
            buckets['3–5 events'] += 1
        else:
            buckets['6+ events'] += 1

    leads = set()
    for e in window:
        leads.update(e['leads'])

    roster = sorted(participations.items(), key=lambda kv: (-kv[1], kv[0]))
    estimated = sum(1 for e in window if e['approx'])

    # Proposal tie-ins: crew size per event (baseline "3–4 trainee volunteers")
    # and how often the signature lesson plans went into the field.
    crew_sizes = [len(e['leads']) + len(e['volunteers']) for e in window]
    avg_crew = round(sum(crew_sizes) / len(crew_sizes), 1) if crew_sizes else 0
    signature_events = sum(
        1 for e in window if any(a in SIGNATURE_ACTIVITIES for a in e['activities'])
    )
    activity_formats = len({a for e in window for a in e['activities']})

    # Community demand: who hosts us, and who asks us back.
    venues, repeat_venues = venue_stats(window)

    # Event scale: the biggest single events, plus the size distribution.
    sized = sorted(
        (e for e in window if e['attendees']),
        key=lambda e: -e['attendees'],
    )
    top_events = [
        {'venue': re.sub(r'\s*\([^)]*\)\s*', ' ', e['venue']).strip(),
         'when': datetime.strptime(e['month_sort'], '%Y-%m').strftime('%b %Y'),
         'attendees': e['attendees'], 'approx': e['approx']}
        for e in sized[:6]
    ]
    sizes = sorted(e['attendees'] for e in sized)
    median_size = sizes[len(sizes) // 2] if sizes else 0
    big_events = sum(1 for s in sizes if s >= 200)

    # Volunteer pipeline: distinct people active each month, split into
    # first-timers and returning (seen in an earlier window month).
    pipeline = []
    for m in months:
        people = set()
        for e in by_month[m]:
            people.update(e['leads'] + e['volunteers'])
        new = sum(1 for p in people if first_seen[p] == m)
        pipeline.append({
            'month': m, 'label': month_label(m),
            'new': new, 'returning': len(people) - new,
        })

    return {
        'since': since,
        'monthly': monthly,
        'terms': terms,
        'totals': dict(cum) if monthly else {'events': 0, 'attendees': 0, 'hours': 0, 'volunteers': 0},
        'excluded': excluded,
        'buckets': buckets,
        'repeat_count': sum(1 for c in participations.values() if c >= 2),
        'lead_count': len(leads),
        'roster': roster,
        'estimated': estimated,
        'avg_crew': avg_crew,
        'signature_events': signature_events,
        'activity_formats': activity_formats,
        'venues': venues,
        'repeat_venues': repeat_venues,
        'top_events': top_events,
        'median_size': median_size,
        'big_events': big_events,
        'pipeline': pipeline,
        'data_through': monthly[-1]['label'] if monthly else '—',
    }


# ── SVG PRIMITIVES ───────────────────────────────────────────────────────────

def nice_ticks(top):
    """0..top in 3–5 clean steps: 40 -> [0,10,20,30,40]."""
    if top <= 0:
        return [0, 1]
    raw = top / 4
    magnitude = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 1
    for mult in (1, 2, 2.5, 5, 10):
        step = mult * magnitude
        if step * 4 >= top:
            break
    ticks, v = [], 0
    while v < top:
        ticks.append(v)
        v += step
    ticks.append(v)
    return [int(t) if float(t).is_integer() else t for t in ticks]


def fmt_num(v):
    if isinstance(v, float) and not v.is_integer():
        return f'{v:,.2f}'.rstrip('0').rstrip('.')
    return f'{int(v):,}'


def cumulative_chart(rows, key, hue, title, pace=None):
    """One cumulative series as an area+line SVG small multiple.

    ``pace`` draws the proposal's committed pace as a gray reference line, so
    the chart reads as actual-versus-target rather than a bare count.
    """
    W, H = 336, 204
    L, R, T, B = 40, 14, 34, 24            # padding: y ticks / edge / term band / month band
    pw, ph = W - L - R, H - T - B
    values = [r['cum'][key] for r in rows]
    n = len(values)
    ref = [pace['rate'] * (i + 1) for i in range(n)] if pace else []
    top = max(values + ref[-1:]) or 1
    ticks = nice_ticks(top)
    top = ticks[-1]

    x = lambda i: L + (pw * i / (n - 1) if n > 1 else pw / 2)
    y = lambda v: T + ph - ph * v / top

    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Cumulative {html.escape(title.lower())}, {html.escape(rows[0]["label"])} to '
             f'{html.escape(rows[-1]["label"])}: ends at {fmt_num(values[-1])}">']

    # Gridlines + y ticks (solid hairlines, recessive).
    for t in ticks:
        yy = y(t)
        parts.append(f'<line class="grid" x1="{L}" y1="{yy:.1f}" x2="{W - R}" y2="{yy:.1f}"/>')
        parts.append(f'<text class="tick" x="{L - 5}" y="{yy + 3:.1f}" text-anchor="end">{fmt_num(t)}</text>')

    # Term boundaries and labels across the top band.
    spans, start = [], 0
    for i in range(1, n + 1):
        if i == n or term_of(rows[i]['month'])[0] != term_of(rows[start]['month'])[0]:
            spans.append((start, i - 1))
            start = i
    for s, e in spans:
        if s > 0:
            xx = (x(s) + x(s - 1)) / 2
            parts.append(f'<line class="term" x1="{xx:.1f}" y1="{T - 20}" x2="{xx:.1f}" y2="{H - B}"/>')
        label = term_of(rows[s]['month'])[0].upper()
        parts.append(f'<text class="termlab" x="{(x(s) + x(e)) / 2:.1f}" y="{T - 24}" '
                     f'text-anchor="middle">{html.escape(label)}</text>')

    # Month ticks: every other month plus the last — but never two adjacent
    # labels at the end (skip the regular tick that would touch the last one).
    for i, r in enumerate(rows):
        if (i % 2 == 0 and i < n - 1 - (1 if (n - 1) % 2 else 0)) or i == n - 1:
            stamp = datetime.strptime(r['month'], '%Y-%m')
            parts.append(f'<text class="tick" x="{x(i):.1f}" y="{H - B + 14}" '
                         f'text-anchor="middle">{stamp.strftime("%b")}</text>')

    pts = ' '.join(f'{x(i):.1f},{y(v):.1f}' for i, v in enumerate(values))
    area = f'{L},{y(0):.1f} {pts} {x(n - 1):.1f},{y(0):.1f}'
    parts.append(f'<polygon points="{area}" fill="{hue}" fill-opacity="0.1"/>')

    # Proposal pace behind the data: a recessive dashed gray reference line,
    # direct-labeled at its end so identity never rides on color.
    if ref:
        ref_pts = ' '.join(f'{x(i):.1f},{y(v):.1f}' for i, v in enumerate(ref))
        parts.append(f'<polyline points="{ref_pts}" fill="none" stroke="#B9B6AB" '
                     f'stroke-width="1.5" stroke-dasharray="4 3"/>')
        ry = y(ref[-1])
        if abs(y(values[-1]) - ry) >= 20:
            # Endpoints are far apart: label the target at its end.
            parts.append(f'<text class="reflab" x="{x(n - 1) - 4:.1f}" y="{ry + 13:.1f}" '
                         f'text-anchor="end">target {fmt_num(round(ref[-1]))}</text>')
        else:
            # Actual and target converge at the end — label mid-line instead,
            # where the two curves are furthest apart.
            mid = max(range(n), key=lambda i: abs(y(values[i]) - y(ref[i])))
            below = y(values[mid]) <= y(ref[mid])   # actual above → label under ref
            # The ref line slopes ~13px across the label's width, so clear it
            # by more than the slope on the label's near side.
            my = y(ref[mid]) + (22 if below else -16)
            parts.append(f'<text class="reflab" x="{x(mid):.1f}" y="{my:.1f}" '
                         f'text-anchor="middle">target {fmt_num(round(ref[-1]))}</text>')

    parts.append(f'<polyline points="{pts}" fill="none" stroke="{hue}" stroke-width="2" '
                 f'stroke-linejoin="round" stroke-linecap="round"/>')
    parts.append(f'<line class="axis" x1="{L}" y1="{y(0):.1f}" x2="{W - R}" y2="{y(0):.1f}"/>')

    # Endpoint: ≥8px marker with a surface ring, and the one direct label.
    ex, ey = x(n - 1), y(values[-1])
    parts.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4.5" fill="{hue}" stroke="#FFFFFF" stroke-width="2"/>')
    parts.append(f'<text class="endlab" x="{ex - 8:.1f}" y="{ey - 8:.1f}" text-anchor="end">{fmt_num(values[-1])}</text>')

    # Hover layer: one full-height hit slot per month (tooltip enhances; the
    # data table below carries every value without it).
    slot = pw / max(n - 1, 1)
    for i, r in enumerate(rows):
        x0 = max(L, x(i) - slot / 2)
        x1 = min(W - R, x(i) + slot / 2)
        parts.append(
            f'<rect class="hit" x="{x0:.1f}" y="{T - 20}" width="{x1 - x0:.1f}" height="{ph + 20}" '
            f'fill="transparent" tabindex="0" '
            f'data-tip="{html.escape(r["label"], quote=True)}: {fmt_num(r["cum"][key])} {html.escape(title.lower(), quote=True)}"'
            f'><title>{html.escape(r["label"])}: {fmt_num(r["cum"][key])}</title></rect>')

    parts.append('</svg>')
    return ''.join(parts)


def hbar_chart(items, hue, label_w=120, suffix=''):
    """Horizontal single-series bars: items = [(label, value, sublabel?)].

    ``suffix`` may contain a plural word (" visits"); it is singularized for
    a value of 1. The right margin is sized to the longest tip so value
    labels never clip.
    """
    def tip_text(item):
        value = item[1]
        word = suffix[:-1] if suffix.endswith('s') and value == 1 else suffix
        return f'{"~" if len(item) > 3 and item[3] else ""}{fmt_num(value)}{word}'

    W, bar, gap = 336, 16, 12
    L = label_w
    R = 12 + max(len(tip_text(it)) for it in items) * 6.2
    H = len(items) * (bar + gap) + 6
    top = max(v for _, v, *_ in items) or 1
    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Bar chart">']
    max_chars = int((label_w - 10) / 6.0)
    for i, item in enumerate(items):
        label, value = item[0], item[1]
        sub = item[2] if len(item) > 2 else ''
        yy = 3 + i * (bar + gap)
        w = max((W - L - R) * value / top, 2)
        r = min(4.0, w / 2)
        display = label if len(label) <= max_chars else label[:max_chars - 1].rstrip() + '…'
        label_y = yy + bar / 2 + (0.5 if sub else 3.5)
        parts.append(f'<text class="buck" x="{L - 8}" y="{label_y:.1f}" text-anchor="end">'
                     f'{html.escape(display)}</text>')
        if sub:
            parts.append(f'<text class="subval" x="{L - 8}" y="{label_y + 10:.1f}" '
                         f'text-anchor="end">{html.escape(sub)}</text>')
        parts.append(f'<path d="M{L},{yy} h{w - r:.1f} a{r:.1f},{r:.1f} 0 0 1 {r:.1f},{r:.1f} '
                     f'v{bar - 2 * r:.1f} a{r:.1f},{r:.1f} 0 0 1 -{r:.1f},{r:.1f} h-{w - r:.1f} z" '
                     f'fill="{hue}"><title>{html.escape(label)}{html.escape(" · " + sub if sub else "")}'
                     f': {fmt_num(value)}</title></path>')
        parts.append(f'<text class="buckval" x="{L + w + 7:.1f}" y="{yy + bar / 2 + 3.5}">'
                     f'{tip_text(item)}</text>')
    parts.append('</svg>')
    return ''.join(parts), H


def pipeline_chart(pipeline):
    """New vs returning volunteers per month as stacked columns.

    Two series (teal = first-time, purple = returning; the pair passes the
    palette validator) with a 2px surface gap between segments and totals
    direct-labeled on the column caps.
    """
    W, H = 336, 190
    L, R, T, B = 34, 10, 26, 24
    pw, ph = W - L - R, H - T - B
    n = len(pipeline)
    top_val = max((p['new'] + p['returning']) for p in pipeline) or 1
    ticks = nice_ticks(top_val)
    top = ticks[-1]
    slot = pw / n
    bar_w = min(slot * 0.62, 24)

    y = lambda v: T + ph - ph * v / top
    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="First-time and returning volunteers per month">']
    for t in ticks:
        parts.append(f'<line class="grid" x1="{L}" y1="{y(t):.1f}" x2="{W - R}" y2="{y(t):.1f}"/>')
        parts.append(f'<text class="tick" x="{L - 5}" y="{y(t) + 3:.1f}" text-anchor="end">{fmt_num(t)}</text>')

    for i, p in enumerate(pipeline):
        cx = L + slot * i + slot / 2
        x0 = cx - bar_w / 2
        total = p['new'] + p['returning']
        # Returning sits on the baseline; first-timers stack on top with a
        # 2px surface gap between the segments.
        ry0, ry1 = y(p['returning']), y(0)
        if p['returning']:
            parts.append(f'<rect x="{x0:.1f}" y="{ry0:.1f}" width="{bar_w:.1f}" '
                         f'height="{max(ry1 - ry0, 1):.1f}" fill="#534AB7">'
                         f'<title>{html.escape(p["label"])}: {p["returning"]} returning</title></rect>')
        if p['new']:
            ny0, ny1 = y(total), y(p['returning'])
            gap_off = 2 if p['returning'] else 0
            parts.append(f'<path d="M{x0:.1f},{ny0 + 4:.1f} a4,4 0 0 1 4,-4 h{bar_w - 8:.1f} '
                         f'a4,4 0 0 1 4,4 v{max(ny1 - ny0 - 4 - gap_off, 0):.1f} h-{bar_w:.1f} z" '
                         f'fill="#1D9E75"><title>{html.escape(p["label"])}: {p["new"]} first-time</title></path>')
        if total:
            parts.append(f'<text class="caplab" x="{cx:.1f}" y="{y(total) - 5:.1f}" '
                         f'text-anchor="middle">{total}</text>')
        stamp = datetime.strptime(p['month'], '%Y-%m')
        # Every other month plus the last, but never two adjacent labels at the end.
        if (i % 2 == 0 and i < n - 1 - (1 if (n - 1) % 2 else 0)) or i == n - 1:
            parts.append(f'<text class="tick" x="{cx:.1f}" y="{H - B + 14}" '
                         f'text-anchor="middle">{stamp.strftime("%b")}</text>')

    parts.append(f'<line class="axis" x1="{L}" y1="{y(0):.1f}" x2="{W - R}" y2="{y(0):.1f}"/>')
    parts.append('</svg>')
    return ''.join(parts), H


def history_chart(past, current_label, current_value):
    """People reached per year: past years in gray, the grant year in teal.

    The emphasis form — highlight one, gray the rest — so prior years give
    honest context without competing with the grant-window story.
    """
    years = list(past.items()) + [(current_label, current_value)]
    W, H = 336, 150
    L, R, T, B = 10, 10, 26, 22
    pw, ph = W - L - R, H - T - B
    top = max(v for _, v in years) or 1
    n = len(years)
    slot = pw / n
    bar_w = min(slot * 0.5, 44)

    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="People reached per year, {n} years">']
    for i, (label, value) in enumerate(years):
        current = i == n - 1
        cx = L + slot * i + slot / 2
        bh = max(ph * value / top, 2)
        y0 = T + ph - bh
        hue = '#1D9E75' if current else '#B9B6AB'
        r = min(4.0, bar_w / 2)
        parts.append(f'<path d="M{cx - bar_w / 2:.1f},{y0 + r:.1f} a{r},{r} 0 0 1 {r},-{r} '
                     f'h{bar_w - 2 * r:.1f} a{r},{r} 0 0 1 {r},{r} v{bh - r:.1f} h-{bar_w:.1f} z" '
                     f'fill="{hue}"><title>{html.escape(label)}: {fmt_num(value)}</title></path>')
        cap_cls = 'endlab' if current else 'caplab'
        parts.append(f'<text class="{cap_cls}" x="{cx:.1f}" y="{y0 - 6:.1f}" '
                     f'text-anchor="middle">{fmt_num(value)}</text>')
        parts.append(f'<text class="tick" x="{cx:.1f}" y="{H - B + 14}" '
                     f'text-anchor="middle">{html.escape(label)}</text>')
    parts.append(f'<line class="axis" x1="{L}" y1="{T + ph:.1f}" x2="{W - R}" y2="{T + ph:.1f}"/>')
    parts.append('</svg>')
    return ''.join(parts)


def bucket_chart(buckets):
    """Repeat-volunteer buckets as horizontal bars on the ordinal teal ramp."""
    W, bar, gap, L, R = 336, 18, 14, 96, 44
    H = len(buckets) * (bar + gap) + 8
    top = max(buckets.values()) or 1
    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Volunteers by number of events served">']
    for i, (label, value) in enumerate(buckets.items()):
        yy = 4 + i * (bar + gap)
        w = max((W - L - R) * value / top, 2)
        r = min(4.0, w / 2)
        parts.append(f'<text class="buck" x="{L - 8}" y="{yy + bar / 2 + 3.5}" text-anchor="end">{html.escape(label)}</text>')
        # Rounded at the data end only; square at the baseline.
        parts.append(f'<path d="M{L},{yy} h{w - r:.1f} a{r:.1f},{r:.1f} 0 0 1 {r:.1f},{r:.1f} v{bar - 2 * r:.1f} '
                     f'a{r:.1f},{r:.1f} 0 0 1 -{r:.1f},{r:.1f} h-{w - r:.1f} z" fill="{RAMP[i % len(RAMP)]}">'
                     f'<title>{html.escape(label)}: {value}</title></path>')
        parts.append(f'<text class="buckval" x="{L + w + 7:.1f}" y="{yy + bar / 2 + 3.5}">{value}</text>')
    parts.append('</svg>')
    return ''.join(parts)


# ── PAGE ─────────────────────────────────────────────────────────────────────

REPORT_CSS = """
  :root {
    --teal:#1D9E75; --teal-dark:#0d6e50; --purple:#534AB7; --amber:#BA7517; --red:#E24B4A;
    --ink:#1C1B18; --ink-mid:#4A4945; --ink-soft:#888780;
    --paper:#FAF8F3; --paper-2:#F1EFE8; --border:#E0DDD4; --white:#FFFFFF;
  }
  *{margin:0;padding:0;box-sizing:border-box;}
  html{-webkit-print-color-adjust:exact;print-color-adjust:exact;}
  body{font-family:'Outfit',sans-serif;background:var(--paper);color:var(--ink);font-size:13px;}
  .mono{font-family:'DM Mono',monospace;}

  .sheet{max-width:820px;margin:0 auto;background:var(--white);}
  @media screen{
    body{padding:2rem 1rem;}
    .sheet{border:1px solid var(--border);border-radius:2px;box-shadow:0 1px 8px rgba(28,27,24,.05);}
  }

  /* HEADER */
  .rp-header{background:var(--ink);padding:1.9rem 2.6rem 1.6rem;position:relative;overflow:hidden;}
  .rp-header::before{content:'';position:absolute;top:-70px;right:-50px;width:260px;height:260px;background:radial-gradient(circle,rgba(29,158,117,.25),transparent 70%);border-radius:50%;}
  .rp-header::after{content:'';position:absolute;bottom:-60px;left:180px;width:180px;height:180px;background:radial-gradient(circle,rgba(83,74,183,.2),transparent 70%);border-radius:50%;}
  .rp-header>*{position:relative;z-index:1;}
  .h-label{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.15em;color:var(--teal);text-transform:uppercase;margin-bottom:.45rem;}
  .h-title{font-family:'DM Serif Display',serif;font-size:1.9rem;color:#fff;line-height:1.12;}
  .h-sub{font-size:12.5px;color:#888780;font-weight:300;margin-top:.3rem;}
  .h-meta{font-family:'DM Mono',monospace;font-size:10px;color:#8a8a85;margin-top:.9rem;display:flex;gap:14px;flex-wrap:wrap;}
  .h-meta strong{color:#c9c9c2;font-weight:500;}

  /* KPI ROW */
  .kpis{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--border);}
  .kpi{padding:1.1rem 1.4rem 1rem;border-right:1px solid var(--border);position:relative;}
  .kpi:last-child{border-right:none;}
  .kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--accent,var(--teal));}
  .kpi-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-soft);margin-bottom:.45rem;}
  .kpi-value{font-family:'DM Serif Display',serif;font-size:2.1rem;line-height:1;}
  .kpi-sub{font-size:10.5px;color:var(--ink-soft);margin-top:.3rem;font-weight:300;}

  /* SECTIONS */
  .section{padding:1.5rem 2.6rem;}
  .section+.section{border-top:1px solid var(--border);}
  .sec-title{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-soft);margin-bottom:1rem;display:flex;align-items:center;gap:8px;}
  .sec-title .dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;}
  .sec-note{font-size:11px;color:var(--ink-soft);font-weight:300;margin:-0.6rem 0 1rem;}

  /* CHART GRID */
  .charts{display:grid;grid-template-columns:1fr 1fr;gap:1.2rem;}
  .chart-card{border:1px solid var(--border);border-radius:2px;padding:.9rem 1rem .6rem;}
  .chart-title{font-size:11.5px;font-weight:600;display:flex;align-items:center;gap:7px;margin-bottom:.5rem;flex-wrap:wrap;}
  .chart-title .key{width:14px;height:3px;border-radius:2px;flex-shrink:0;}
  .pace-key{margin-left:auto;font-family:'DM Mono',monospace;font-size:8px;font-weight:400;color:var(--ink-soft);letter-spacing:.02em;}
  .chart .reflab{font-family:'DM Mono',monospace;font-size:8.5px;fill:var(--ink-soft);}
  .chart{width:100%;height:auto;display:block;}
  .chart .grid{stroke:#EDEBE3;stroke-width:1;}
  .chart .axis{stroke:#C9C6BB;stroke-width:1;}
  .chart .term{stroke:var(--border);stroke-width:1;}
  .chart .tick{font-family:'DM Mono',monospace;font-size:8.5px;fill:var(--ink-soft);font-variant-numeric:tabular-nums;}
  .chart .termlab{font-family:'DM Mono',monospace;font-size:7px;letter-spacing:.09em;fill:var(--ink-soft);}
  .chart .endlab{font-family:'Outfit',sans-serif;font-size:11px;font-weight:600;fill:var(--ink);}
  .chart .buck{font-size:10.5px;fill:var(--ink-mid);}
  .chart .buckval{font-family:'DM Mono',monospace;font-size:10px;fill:var(--ink);}
  .chart .subval{font-family:'DM Mono',monospace;font-size:8.5px;fill:var(--ink-soft);}
  .chart .caplab{font-family:'DM Mono',monospace;font-size:8.5px;fill:var(--ink-mid);}
  .chart .hit{outline:none;}
  .chart .hit:focus-visible{stroke:var(--ink-soft);stroke-width:1;stroke-dasharray:none;}

  /* SPLIT (bars + facts) */
  .split{display:grid;grid-template-columns:1fr 1fr;gap:1.6rem;align-items:start;}
  .facts{display:flex;flex-direction:column;gap:.65rem;font-size:12px;color:var(--ink-mid);}
  .facts strong{color:var(--ink);font-weight:600;}
  .facts li{list-style:none;padding-left:14px;position:relative;line-height:1.5;}
  .facts li::before{content:'';position:absolute;left:0;top:8px;width:4px;height:4px;border-radius:50%;background:var(--teal);}

  /* TABLES */
  table{width:100%;border-collapse:collapse;}
  th{font-family:'DM Mono',monospace;font-size:8.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink-soft);text-align:right;padding:0 8px 7px;border-bottom:1px solid var(--border);font-weight:500;}
  th:first-child{text-align:left;padding-left:0;}
  td{font-size:12px;padding:7px 8px;border-bottom:1px solid var(--paper-2);text-align:right;font-variant-numeric:tabular-nums;color:var(--ink-mid);}
  td:first-child{text-align:left;font-weight:600;color:var(--ink);padding-left:0;}
  tr:last-child td{border-bottom:none;}
  .group-head th{border-bottom:none;padding-bottom:2px;text-align:center;color:var(--ink-mid);}
  .cum td{background:var(--paper);}
  td.cum-first{border-left:1px solid var(--border);}
  th.cum-first{border-left:1px solid var(--border);}
  .totals td{border-top:1px solid var(--border);font-weight:600;color:var(--ink);}

  /* ROSTER */
  .roster{columns:3;column-gap:1.6rem;font-size:10.5px;color:var(--ink-mid);}
  .roster div{break-inside:avoid;padding:2.5px 0;display:flex;justify-content:space-between;gap:8px;border-bottom:1px solid var(--paper-2);}
  .roster .n{font-family:'DM Mono',monospace;color:var(--ink-soft);flex-shrink:0;}
  .roster .repeat{color:var(--ink);font-weight:500;}
  .roster .repeat .n{color:var(--teal-dark);font-weight:500;}

  /* NOTES */
  .method{font-size:10.5px;color:var(--ink-soft);line-height:1.55;}
  .method li{margin-left:14px;margin-bottom:3px;}

  .rp-footer{padding:1.1rem 2.6rem;border-top:1px solid var(--border);display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap;font-family:'DM Mono',monospace;font-size:9.5px;color:var(--ink-soft);}
  .rp-footer a{color:var(--teal-dark);text-decoration:none;}

  details.datatable{margin-top:1rem;font-size:11px;}
  details.datatable summary{font-family:'DM Mono',monospace;font-size:9.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink-soft);cursor:pointer;}
  details.datatable table{margin-top:.7rem;}

  .tooltip{position:fixed;background:var(--ink);color:#fff;padding:6px 10px;border-radius:4px;font-size:11.5px;pointer-events:none;opacity:0;transition:opacity .12s;z-index:50;}
  .tooltip.show{opacity:1;}
  .tooltip strong{font-weight:600;}

  @media print{
    body{background:#fff;padding:0;}
    .sheet{max-width:none;border:none;box-shadow:none;}
    .section{padding:.55rem 0.2in;}
    .rp-header{padding:.85rem 0.2in .75rem;}
    .h-title{font-size:1.7rem;}
    .h-meta{margin-top:.5rem;}
    .kpis{border-top:1px solid var(--border);break-inside:avoid;}
    .kpi{padding:.6rem 1.2rem .5rem;}
    .kpi-value{font-size:1.8rem;}
    .chart-card,.split,.notes-group,tr,table,.rp-footer{break-inside:avoid;}
    .chart-card{padding:.45rem .7rem .2rem;}
    .chart-title{font-size:11px;margin-bottom:.3rem;}
    .charts{gap:.6rem;}
    .sec-title{break-after:avoid;margin-bottom:.5rem;}
    .sec-note{margin:-0.3rem 0 .5rem;font-size:10px;}
    td{padding:4.5px 8px;font-size:11px;}
    .facts{font-size:11px;gap:.45rem;}
    .roster{columns:4;font-size:9px;}
    .roster div{padding:1.5px 0;}
    .method{font-size:9px;}
    .method li{margin-bottom:1px;}
    .rp-footer{padding:.5rem 0.2in;}
    .no-print,.tooltip{display:none!important;}
    details.datatable{display:none;}
    a{color:inherit;text-decoration:none;}
  }
  @page{size:letter;margin:0.55in 0.45in;}

  @media (max-width:640px){
    .charts,.split,.kpis{grid-template-columns:1fr;}
    .kpi{border-right:none;border-bottom:1px solid var(--border);}
    .roster{columns:2;}
    .section,.rp-header{padding-left:1.2rem;padding-right:1.2rem;}
  }
"""

REPORT_JS = """
(function(){
  var tt=document.getElementById('tt');
  if(!tt)return;
  function show(el,ev){
    tt.innerHTML='';
    var parts=(el.getAttribute('data-tip')||'').split(': ');
    var s=document.createElement('strong');s.textContent=parts.shift();
    tt.appendChild(s);tt.appendChild(document.createElement('br'));
    tt.appendChild(document.createTextNode(parts.join(': ')));
    tt.classList.add('show');
    if(ev&&ev.clientX!==undefined){tt.style.left=(ev.clientX+14)+'px';tt.style.top=(ev.clientY-10)+'px';}
    else{var r=el.getBoundingClientRect();tt.style.left=(r.left+r.width/2)+'px';tt.style.top=(r.top-8)+'px';}
  }
  document.querySelectorAll('.hit').forEach(function(el){
    el.addEventListener('pointerenter',function(e){show(el,e);});
    el.addEventListener('pointermove',function(e){show(el,e);});
    el.addEventListener('pointerleave',function(){tt.classList.remove('show');});
    el.addEventListener('focus',function(){show(el);});
    el.addEventListener('blur',function(){tt.classList.remove('show');});
  });
})();
"""


def _kpi(label, value, sub, accent):
    return (f'<div class="kpi" style="--accent:{accent}">'
            f'<div class="kpi-label">{html.escape(label)}</div>'
            f'<div class="kpi-value">{value}</div>'
            f'<div class="kpi-sub">{html.escape(sub)}</div></div>')


def _term_table(data):
    head = ('<tr><th>Term</th><th>Events</th><th>People reached</th><th>Hours</th>'
            '<th>Volunteers active</th><th>New volunteers</th></tr>')
    rows = []
    for name, t in data['terms'].items():
        rows.append(
            f'<tr><td>{html.escape(name)}</td><td>{t["events"]}</td>'
            f'<td>{fmt_num(t["attendees"])}</td><td>{fmt_num(t["hours"])}</td>'
            f'<td>{t["active"]}</td><td>{t["new_volunteers"]}</td></tr>')
    totals = data['totals']
    rows.append(
        f'<tr class="totals"><td>Total since fall 2025</td><td>{totals["events"]}</td>'
        f'<td>{fmt_num(totals["attendees"])}</td><td>{fmt_num(totals["hours"])}</td>'
        f'<td>{totals["volunteers"]} distinct</td><td>{totals["volunteers"]}</td></tr>')
    return f'<table>{head}{"".join(rows)}</table>'


def _monthly_table(data):
    rows = ''.join(
        f'<tr><td>{html.escape(r["label"])}</td><td>{r["events"]}</td>'
        f'<td>{fmt_num(r["attendees"])}</td><td>{fmt_num(r["hours"])}</td>'
        f'<td>{r["new_volunteers"]}</td>'
        f'<td class="cum cum-first">{r["cum"]["events"]}</td><td class="cum">{fmt_num(r["cum"]["attendees"])}</td>'
        f'<td class="cum">{fmt_num(r["cum"]["hours"])}</td><td class="cum">{r["cum"]["volunteers"]}</td></tr>'
        for r in data['monthly'])
    return ('<details class="datatable"><summary>Monthly data table (every plotted value)</summary>'
            '<table><tr><th>Month</th><th>Events</th><th>People</th><th>Hours</th><th>New volunteers</th>'
            '<th class="cum-first">Σ Events</th><th>Σ People</th><th>Σ Hours</th><th>Σ Volunteers</th></tr>'
            f'{rows}</table></details>')


def _roster(data):
    entries = []
    for name, count in data['roster']:
        cls = ' class="repeat"' if count >= 2 else ''
        entries.append(f'<div{cls}><span>{html.escape(name)}</span>'
                       f'<span class="n">×{count}</span></div>')
    return f'<div class="roster">{"".join(entries)}</div>'


def _history_section(data, history):
    """Program-history panel; renders only when PROGRAM_HISTORY is filled in."""
    if not history:
        return ''
    since_year = int(data['since'][:4])
    grant_label = f'{since_year}–{str(since_year + 1)[-2:]}'
    chart = history_chart(history, grant_label, data['totals']['attendees'])
    return f'''
<div class="section">
  <div class="sec-title"><span class="dot" style="background:var(--teal-dark)"></span>Program history — people reached per year</div>
  <div class="sec-note">NeuroEngage outreach long predates this fellowship. Gray bars are pre-grant years from the program's annual DMAP infographics; the teal bar is the grant reporting year, computed from the event database. The cumulative charts above start where the teal bar starts.</div>
  <div style="max-width:520px">{chart}</div>
</div>'''


def render_report(data, sources, dashboard_href='index.html', history=None):
    generated = datetime.now()
    generated_date = f"{generated.strftime('%B')} {generated.day}, {generated.year}"
    totals = data['totals']
    since_label = month_label(data['since'])

    charts = []
    for key, spec in SERIES.items():
        pace = PROPOSAL_PACE.get(key)
        pace_key = (f'<span class="pace-key">--- {html.escape(pace["label"])}</span>' if pace else '')
        charts.append(
            f'<div class="chart-card"><div class="chart-title">'
            f'<span class="key" style="background:{spec["hue"]}"></span>'
            f'Cumulative {html.escape(spec["label"].lower())}{pace_key}</div>'
            f'{cumulative_chart(data["monthly"], key, spec["hue"], spec["label"], pace)}</div>')
    charts = ''.join(charts)

    if history is None:
        history = PROGRAM_HISTORY
    excl = data['excluded']
    excluded_note = ''
    if excl['events']:
        excluded_note = (
            f'{excl["events"]} earlier pilot events (before {html.escape(since_label)}: '
            f'{fmt_num(excl["attendees"])} attendees, {fmt_num(excl["hours"])} hours) precede the '
            f'reporting window and are not included here; they remain on the live dashboard.')

    repeat_pct = round(100 * data['repeat_count'] / totals['volunteers']) if totals['volunteers'] else 0

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NeuroEngage Progress Report</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Mono:wght@400;500&family=Outfit:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>{REPORT_CSS}</style>
</head>
<body>
<div class="tooltip" id="tt" aria-hidden="true"></div>
<div class="sheet">

<div class="rp-header">
  <div class="h-label">Georgia State University &bull; CBN / TReNDS &bull; Dana NextGen Fellowship</div>
  <div class="h-title">NeuroEngage Outreach — Cumulative Progress</div>
  <div class="h-sub">Prepared for Dana Foundation reporting</div>
  <div class="h-meta">
    <span>Reporting period <strong>Fall 2025 &ndash; {html.escape(REPORT_HORIZON)}</strong></span>
    <span>This snapshot <strong>{html.escape(since_label)} &ndash; {html.escape(data['data_through'])}</strong></span>
    <span>Generated <strong>{html.escape(generated_date)}</strong></span>
  </div>
</div>

<div class="kpis">
  {_kpi('Events held', fmt_num(totals['events']), 'outreach sessions since fall 2025', '#534AB7')}
  {_kpi('People reached', fmt_num(totals['attendees']), 'K-12 students & members of the public', '#1D9E75')}
  {_kpi('Event hours', fmt_num(totals['hours']), 'total duration of events run', '#BA7517')}
  {_kpi('Distinct volunteers', fmt_num(totals['volunteers']), f"{data['lead_count']} have led events", '#E24B4A')}
</div>

<div class="section">
  <div class="sec-title"><span class="dot" style="background:var(--teal)"></span>Growth over the grant reporting window</div>
  <div class="sec-note">Each panel accumulates month by month, so any point reads as “total to date.” Zero marks the start of the reporting window, not the program — outreach predates the fellowship, and the dashed lines carry that history as its pre-grant pace; the distance above them is this year’s growth.</div>
  <div class="charts">{charts}</div>
  {_monthly_table(data)}
</div>
{_history_section(data, history)}
<div class="section">
  <div class="sec-title"><span class="dot" style="background:var(--purple)"></span>Term snapshots</div>
  <div class="sec-note">What each academic term contributed; the bottom row is the total for the reporting window.</div>
  {_term_table(data)}
  <div class="sec-note" style="margin:.6rem 0 0">“Active” counts a person once per term; “new” = first event since fall 2025. In the total row, volunteers are counted once across the whole window — which is why the distinct total equals the sum of new volunteers, while active counts don’t add up (returning people appear in several terms).</div>
</div>

<div class="section">
  <div class="sec-title"><span class="dot" style="background:var(--amber)"></span>Volunteer engagement &amp; repeat service</div>
  <div class="split">
    <div>
      <div class="chart-title" style="margin-bottom:.7rem">Volunteers by number of events served</div>
      {bucket_chart(data['buckets'])}
    </div>
    <ul class="facts">
      <li>Outreach is running at <strong>{fmt_num(round(totals['events'] / max(len(data['monthly']), 1), 1))} events/month</strong> — ahead of the proposal's Goal 1b target of doubling from one to <strong>two events per month</strong>.</li>
      <li>Crews average <strong>{fmt_num(data['avg_crew'])} volunteers per event</strong> (proposal baseline: 3&ndash;4), and <strong>{data['repeat_count']} of {totals['volunteers']} volunteers ({repeat_pct}%)</strong> have served at two or more events — every name is captured on the intake form, so repeat service is trackable today.</li>
      <li><strong>{data['lead_count']}</strong> different people have led at least one event.</li>
      <li>The signature lesson plans named in the proposal (Touch-a-Brain, Build-a-Brain, Build-a-Neuron) ran at <strong>{data['signature_events']} of {totals['events']} events</strong>.</li>
    </ul>
  </div>
</div>

<div class="section">
  <div class="sec-title"><span class="dot" style="background:var(--red)"></span>Volunteer roster (events served)</div>
  {_roster(data)}
</div>

<div class="section">
  <div class="sec-title"><span class="dot" style="background:var(--ink-soft)"></span>Method notes</div>
  <ul class="method">
    <li>This report is the “breadth” arm of the NeuroEngage evaluation plan — the event database tracking trainees and learners engaged. Depth measures (self-efficacy surveys, focus groups) are collected separately.</li>
    <li>Charts measure the grant reporting window only. NeuroEngage outreach has run for years before this fellowship (see the program’s annual DMAP infographics); the dashed baseline paces summarize that prior performance level.</li>
    <li>Target paces on the charts come from the funded proposal: Goal 1b doubles outreach from one to two events/month; the program's stated baseline is at least 1,000 K-12 students &amp; members of the public and ~100 volunteers annually.</li>
    <li>Source: Microsoft Forms outreach reports ({html.escape(', '.join(sources))}), merged so a later export can correct but never erase an earlier value.</li>
    {f'<li>{excluded_note}</li>' if excluded_note else ''}
    <li>Academic terms: Fall = Aug&ndash;Dec, Spring = Jan&ndash;Apr, Summer = May&ndash;Jul.</li>
    <li>Attendance entered as a range is counted at its midpoint and flagged as an estimate; “event hours” is the duration of each event, not person-hours.</li>
    <li>Volunteer counts are floors: group entries (e.g. “lab members”) and unnamed helpers are not counted; spelling variants of the same person are merged.</li>
  </ul>
</div>

<div class="rp-footer">
  <span>NEUROENGAGE &bull; DANA NEXTGEN FELLOWSHIP &bull; GSU</span>
  <span class="no-print"><a href="{html.escape(dashboard_href)}">Live dashboard &rarr;</a></span>
  <span>Generated {html.escape(generated_date)}</span>
</div>

</div>
<script>{REPORT_JS}</script>
</body>
</html>"""
