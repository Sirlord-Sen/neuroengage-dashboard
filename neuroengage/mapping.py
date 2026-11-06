"""
Map of outreach visits: one dot per site, dot area proportional to people reached.

The form's zip-code field is almost always blank, so locations come from
``venues.csv`` at the repo root — one row per venue name as typed on the form,
with coordinates, a short map label, an optional ``site`` (venues that share a
campus are drawn as one dot) and an audience:

    k12     school visits and youth programs (the "children reached" view)
    public  community, family and professional events

Rows with blank coordinates are listed on the page as "not yet mapped" rather
than guessed. ``precision`` of ``zip`` or ``city`` draws a dashed outline so an
approximate position is never presented as exact.

map.html is an interactive Leaflet map on real street tiles (CARTO / OpenStreetMap,
with a satellite option). The standalone SVGs are still server-rendered from
county outlines so they drop straight into a poster at any size.
"""

import csv
import html
import json
import math
import os
import re
from difflib import SequenceMatcher

from .report import normalize_venue

HERE = os.path.dirname(os.path.abspath(__file__))
COUNTIES_PATH = os.path.join(HERE, 'ga_counties.json')

AUDIENCES = {
    'k12':    {'hue': '#1D9E75', 'label': 'K–12 school & youth visits'},
    'public': {'hue': '#534AB7', 'label': 'Community & public events'},
}
#: Sites farther than this from downtown Atlanta go in an inset, not the main map.
INSET_KM = 250
#: Area drawn again, enlarged, because its sites sit a few hundred metres apart.
ZOOM = {'lat': (33.700, 33.803), 'lon': (-84.420, -84.268)}
ATLANTA = (33.749, -84.388)
FONT = "'Outfit', 'Helvetica Neue', Arial, sans-serif"
MONO = "'DM Mono', Menlo, monospace"


# ── data ──────────────────────────────────────────────────────────────────

def load_venues(path):
    """Read venues.csv → list of dicts (lat/lon as float or None)."""
    rows = []
    with open(path, encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            row = {k: (v or '').strip() for k, v in row.items()}
            if not row.get('venue'):
                continue
            try:
                row['lat'], row['lon'] = float(row['lat']), float(row['lon'])
            except (TypeError, ValueError):
                row['lat'] = row['lon'] = None
            row['site'] = row.get('site') or row.get('label') or row['venue']
            row['label'] = row.get('label') or row['venue']
            row['audience'] = row.get('audience') if row.get('audience') in AUDIENCES else 'k12'
            row['key'] = normalize_venue(row['venue'])
            rows.append(row)
    return rows


def match_venue(name, venues):
    """Find the venues.csv row for a venue as typed on the form (typo-tolerant)."""
    key = normalize_venue(name)
    best, score = None, 0.0
    for row in venues:
        ratio = 1.0 if row['key'] == key else SequenceMatcher(None, key, row['key']).ratio()
        if ratio > score:
            best, score = row, ratio
    return best if score >= 0.88 else None


def _km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 12742 * math.asin(math.sqrt(h))


def _in_ring(lon, lat, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def load_counties(path=COUNTIES_PATH):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)['counties']


def county_of(lat, lon, counties):
    for county in counties:
        if any(_in_ring(lon, lat, ring) for ring in county['rings']):
            return f"{county['name']} Co."
    return None


def build_map_data(events, venues, counties=None):
    """Group events into map sites. Returns dict with sites, unmapped, unknown."""
    counties = counties if counties is not None else load_counties()
    sites, unmapped, unknown = {}, {}, {}
    for e in events:
        row = match_venue(e['venue'], venues)
        visit = {'date': e['date'], 'date_sort': e['date_sort'], 'venue': e['venue'].strip(),
                 'attendees': e['attendees'] or 0}
        if row is None:
            unknown.setdefault(e['venue'].strip(), []).append(visit)
            continue
        if row['lat'] is None:
            item = unmapped.setdefault(row['label'], {'label': row['label'], 'audience': row['audience'],
                                                       'note': row.get('source', ''), 'visits': []})
            item['visits'].append(visit)
            continue
        site = sites.setdefault(row['site'], {
            'site': row['site'], 'label': row['label'], 'audience': row['audience'],
            'lat': row['lat'], 'lon': row['lon'], 'precision': row.get('precision') or 'venue',
            'visits': [],
        })
        site['visits'].append(visit)

    out = []
    for site in sites.values():
        site['attendees'] = sum(v['attendees'] for v in site['visits'])
        site['visits'].sort(key=lambda v: v['date_sort'])
        site['inset'] = _km(ATLANTA, (site['lat'], site['lon'])) > INSET_KM
        site['county'] = ('Washington, DC' if site['inset'] and site['lon'] > -78
                          else county_of(site['lat'], site['lon'], counties) or '')
        out.append(site)
    out.sort(key=lambda s: -s['attendees'])
    for group in (unmapped, unknown):
        for item in (group.values() if group is unmapped else []):
            item['attendees'] = sum(v['attendees'] for v in item['visits'])
    unknown_list = [{'venue': k, 'visits': v, 'attendees': sum(x['attendees'] for x in v)}
                    for k, v in unknown.items()]
    return {
        'sites': out,
        'unmapped': sorted(unmapped.values(), key=lambda u: -u['attendees']),
        'unknown': sorted(unknown_list, key=lambda u: -u['attendees']),
    }


def summarize(data, audience=None):
    sites = [s for s in data['sites'] if audience in (None, s['audience'])]
    unmapped = [u for u in data['unmapped'] if audience in (None, u['audience'])]
    return {
        'sites': len(sites),
        'visits': sum(len(s['visits']) for s in sites),
        'attendees': sum(s['attendees'] for s in sites),
        'counties': len({s['county'] for s in sites if s['county'] and not s['inset']}),
        'outside_ga': sum(1 for s in sites if s['inset']),
        'unmapped_attendees': sum(u['attendees'] for u in unmapped),
        'unmapped_visits': sum(len(u['visits']) for u in unmapped),
    }


# ── drawing ───────────────────────────────────────────────────────────────

class _Projection:
    """Equirectangular, scaled by cos(latitude) — accurate enough at metro scale."""

    def __init__(self, sites, width, pad_deg=0.14):
        lats = [s['lat'] for s in sites] or [ATLANTA[0]]
        lons = [s['lon'] for s in sites] or [ATLANTA[1]]
        self.lat0, self.lat1 = min(lats) - pad_deg, max(lats) + pad_deg
        self.lon0, self.lon1 = min(lons) - pad_deg, max(lons) + pad_deg
        self.k = math.cos(math.radians((self.lat0 + self.lat1) / 2))
        span_x = (self.lon1 - self.lon0) * self.k
        span_y = self.lat1 - self.lat0
        self.scale = width / span_x
        self.width, self.height = width, span_y * self.scale

    def __call__(self, lat, lon):
        return ((lon - self.lon0) * self.k * self.scale, (self.lat1 - lat) * self.scale)


def _text_w(text, size):
    return len(text) * size * 0.56


def _box_hits_circle(box, cx, cy, r):
    x0, y0, x1, y1 = box
    nx, ny = min(max(cx, x0), x1), min(max(cy, y0), y1)
    return (nx - cx) ** 2 + (ny - cy) ** 2 < r * r


def _boxes_overlap(a, b, gap=2):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def _label_candidates(x, y, r, w, h):
    """Label positions around a dot: hugging it first, then farther out on a leader line."""
    for dist in (4, 18, 34, 52):
        for deg in (0, 180, -90, 90, -35, -145, 35, 145, -60, -120, 60, 120):
            a = math.radians(deg)
            ex, ey = x + math.cos(a) * r, y + math.sin(a) * r          # edge of the dot
            ax, ay = x + math.cos(a) * (r + dist), y + math.sin(a) * (r + dist)
            if abs(math.cos(a)) < 0.3:                                  # straight above/below
                anchor, x0 = 'middle', ax - w / 2
                y0 = ay - h if math.sin(a) < 0 else ay
            elif math.cos(a) > 0:
                anchor, x0, y0 = 'start', ax, ay - h / 2
            else:
                anchor, x0, y0 = 'end', ax - w, ay - h / 2
            box = (x0, y0, x0 + w, y0 + h)
            tx = {'start': x0, 'end': x0 + w, 'middle': x0 + w / 2}[anchor]
            leader = (ex, ey, ax, ay) if dist > 8 else None
            yield (tx, y0 + h * 0.78, anchor, box, leader)


def _segment_hits_circle(seg, cx, cy, r):
    x1, y1, x2, y2 = seg
    dx, dy = x2 - x1, y2 - y1
    t = max(0, min(1, ((cx - x1) * dx + (cy - y1) * dy) / (dx * dx + dy * dy or 1)))
    px, py = x1 + t * dx, y1 + t * dy
    return (px - cx) ** 2 + (py - cy) ** 2 < r * r


def _place_labels(marks, bounds, size, reserved=()):
    """Greedy placement, biggest dot first.

    Returns ({index: (x, y, anchor, leader)}, boxes). A label never overlaps
    another label, a reserved box, or leaves the bounds; it prefers not to sit
    on another dot, then moves out along a leader line before giving up.
    """
    placed, boxes = {}, list(reserved)
    bx0, by0, bx1, by1 = bounds
    for i in sorted(range(len(marks)), key=lambda i: -marks[i]['r']):
        m = marks[i]
        w, h = _text_w(m['text'], size), size * 1.2
        fallback = None
        for tx, ty, anchor, box, leader in _label_candidates(m['x'], m['y'], m['r'], w, h):
            if box[0] < bx0 or box[1] < by0 or box[2] > bx1 or box[3] > by1:
                continue
            if any(_boxes_overlap(box, b) for b in boxes):
                continue
            others = [o for j, o in enumerate(marks) if j != i]
            on_dot = any(_box_hits_circle(box, o['x'], o['y'], o['r'] + 1) for o in others)
            # A leader may leave through a dot that encloses this one (nested sites).
            crosses = leader and any(
                _segment_hits_circle(leader, o['x'], o['y'], o['r'] * .6) for o in others
                if (o['x'] - m['x']) ** 2 + (o['y'] - m['y']) ** 2 > o['r'] ** 2)
            if not on_dot and not crosses:
                fallback = (tx, ty, anchor, leader, box)
                break
            if fallback is None and leader is None:
                fallback = (tx, ty, anchor, leader, box)
        if fallback:
            placed[i] = fallback[:4]
            boxes.append(fallback[4])
    return placed, boxes


def _ring_path(ring, proj):
    pts = [proj(lat, lon) for lon, lat in ring]
    return 'M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in pts) + 'Z'


def _tip(site):
    lines = [f"{site['label']} — {site['attendees']:,} people, "
             f"{len(site['visits'])} visit{'s' if len(site['visits']) != 1 else ''}"]
    for v in site['visits']:
        lines.append(f"{v['date']} · {v['venue']} · {v['attendees']:,}")
    if site['precision'] != 'venue':
        lines.append(f"Approximate position ({site['precision']})")
    return '\n'.join(lines)


def _in_zoom(site):
    return (ZOOM['lat'][0] <= site['lat'] <= ZOOM['lat'][1]
            and ZOOM['lon'][0] <= site['lon'] <= ZOOM['lon'][1])


class _Zoom:
    """Projection for the enlarged central panel, fitted into a pixel box."""

    def __init__(self, box, k):
        self.box = box
        x0, y0, x1, y1 = box
        self.k = k
        self.scale = (x1 - x0) / ((ZOOM['lon'][1] - ZOOM['lon'][0]) * k)

    def __call__(self, lat, lon):
        x0, y0 = self.box[:2]
        return (x0 + (lon - ZOOM['lon'][0]) * self.k * self.scale,
                y0 + (ZOOM['lat'][1] - lat) * self.scale)


def _text(x, y, body, size, anchor='start', fill='#1C1B18', halo=True, mono=False, extra=''):
    fam = f' font-family="{html.escape(MONO, quote=True)}"' if mono else ''
    halo = ' paint-order="stroke" stroke="#FFFFFF" stroke-width="3" stroke-linejoin="round"' if halo else ''
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size:.1f}" '
            f'fill="{fill}"{fam}{halo}{extra}>{body}</text>')


def _site_label(site, x, y, anchor, size):
    return _text(x, y, f'{html.escape(site["label"])} <tspan fill="#4A4945" '
                 f'font-family="{html.escape(MONO, quote=True)}" font-size="{size * .9:.1f}">'
                 f'{site["attendees"]:,}</tspan>', size, anchor)


def _place_panel(w, h, W, H, marks, avoid, margin=12):
    """Find a spot for the enlarged panel that covers no dot and no other panel.

    Tries the right edge bottom-up, then the left edge, so it lands in the
    emptiest corner as sites are added; falls back to bottom-right.
    """
    def clear(box):
        if any(_boxes_overlap(box, b, gap=10) for b in avoid):
            return False
        return not any(_box_hits_circle(box, m['x'], m['y'], m['r'] + 16) for m in marks)

    # Full size anywhere first (right edge, then left, then interior); shrink only if nothing fits.
    for scale in (1.0, 0.9, 0.8, 0.72):
        sw, sh = w * scale, h * scale
        bottom = H - sh - 44
        xs = [W - sw - margin, margin] + [x for x in range(int(margin), int(W - sw - margin), 16)]
        for x0 in xs:
            y = bottom
            while y >= margin:
                box = (x0, y, x0 + sw, y + sh)
                if clear(box):
                    return box
                y -= 8
    return (W - w - margin, H - h - 44, W - margin, H - 44)


def render_map_svg(data, audience=None, width=960, standalone=False, label_size=11.5, max_r=None):
    """One SVG map. audience=None draws every site; 'k12' only school & youth visits.

    Layout: metro map; a 2-3x enlarged panel for central Atlanta & Decatur where
    sites sit within a few hundred metres of each other; a box for sites outside
    Georgia. Every view uses the same projection and dot scale so they compare.
    """
    counties = load_counties()
    all_sites = data['sites']
    sites = [s for s in all_sites if audience in (None, s['audience'])]
    main_all = [s for s in all_sites if not s['inset']]
    proj = _Projection(main_all, width)
    top = max((s['attendees'] for s in all_sites), default=1) or 1
    rmax = max_r or width * 0.042
    radius = lambda a: max(3.5, rmax * math.sqrt(a / top))
    W, H = width, proj.height
    mono = html.escape(MONO, quote=True)

    far = [s for s in sites if s['inset']]
    zoomed = [s for s in sites if not s['inset'] and _in_zoom(s)]
    metro = [s for s in sites if not s['inset'] and not _in_zoom(s)]

    # Fixed panels (pixel boxes).
    zw = W * 0.42
    zh = zw * (ZOOM['lat'][1] - ZOOM['lat'][0]) / ((ZOOM['lon'][1] - ZOOM['lon'][0]) * proj.k)
    far_box = (W - 230, 10, W - 10, 108) if far else None
    legend_box = (10, H - 162, 214, H - 10)

    # Main-map dots and labels.
    marks = []
    for s in metro:
        x, y = proj(s['lat'], s['lon'])
        marks.append({'x': x, 'y': y, 'r': radius(s['attendees']), 'site': s,
                      'text': f"{s['label']}  {s['attendees']:,}"})
    # Zoomed sites still get a dot on the main map (unlabelled) — they are obstacles too.
    ghost = []
    for s in zoomed:
        x, y = proj(s['lat'], s['lon'])
        ghost.append({'x': x, 'y': y, 'r': radius(s['attendees']), 'site': s, 'text': ''})
    frame = zoom_box = None
    if zoomed:
        fx0, fy0 = proj(ZOOM['lat'][1], ZOOM['lon'][0])
        fx1, fy1 = proj(ZOOM['lat'][0], ZOOM['lon'][1])
        frame = (fx0, fy0, fx1, fy1)
        zoom_box = _place_panel(zw, zh, W, H, marks, [b for b in (far_box, legend_box, frame) if b])
    reserved = [b for b in (zoom_box, far_box, legend_box, frame) if b]
    labels, label_boxes = _place_labels(marks + ghost, (6, 6, W - 6, H - 6), label_size, reserved)
    labels = {i: v for i, v in labels.items() if i < len(marks)}

    # Zoom-panel dots and labels.
    zmarks, zlabels, zproj = [], {}, None
    if zoom_box:
        zproj = _Zoom(zoom_box, proj.k)
        for s in zoomed:
            x, y = zproj(s['lat'], s['lon'])
            zmarks.append({'x': x, 'y': y, 'r': radius(s['attendees']), 'site': s,
                           'text': f"{s['label']}  {s['attendees']:,}"})
        zx0, zy0, zx1, zy1 = zoom_box
        title_box = (zx0, zy0, zx0 + 250, zy0 + 24)
        zlabels, _ = _place_labels(zmarks, (zx0 + 4, zy0 + 4, zx1 - 4, zy1 - 4), label_size, [title_box])

    out = []
    if standalone:
        out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" '
                   f'width="{W * 2:.0f}" height="{H * 2:.0f}" font-family="{html.escape(FONT, quote=True)}">')
        out.append(f'<rect width="{W:.0f}" height="{H:.0f}" fill="#FFFFFF"/>')
    else:
        out.append(f'<svg class="map-svg" viewBox="0 0 {W:.0f} {H:.0f}" role="img" '
                   f'aria-label="Map of outreach visit locations; dot size shows people reached">')
    tag = audience or 'all'
    out.append(f'<defs><clipPath id="clip-{tag}"><rect width="{W:.0f}" height="{H:.0f}"/></clipPath>')
    if zoom_box:
        zx0, zy0, zx1, zy1 = zoom_box
        out.append(f'<clipPath id="zclip-{tag}"><rect x="{zx0:.1f}" y="{zy0:.1f}" '
                   f'width="{zx1 - zx0:.1f}" height="{zy1 - zy0:.1f}"/></clipPath>')
    out.append('</defs>')

    # Counties: those with a visit get a faint tint so reach reads at a glance.
    reached = {s['county'] for s in sites}

    def county_fill(c):
        if f"{c['name']} Co." not in reached:
            return '#FAF8F3'
        return '#EEF6F2' if audience == 'k12' else '#F1F0EC'

    out.append(f'<g clip-path="url(#clip-{tag})">')
    for c in counties:
        d = ''.join(_ring_path(r, proj) for r in c['rings'])
        out.append(f'<path d="{d}" fill="{county_fill(c)}" stroke="#D9D5CA" stroke-width="0.8"/>')
    # County names only where they collide with nothing.
    taken = label_boxes + [(m['x'] - m['r'], m['y'] - m['r'], m['x'] + m['r'], m['y'] + m['r'])
                           for m in marks + ghost]
    csize = label_size * 0.78
    for c in counties:
        pts = [p for r in c['rings'] for p in r]
        x, y = proj(sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts))
        w = _text_w(c['name'], csize) * 1.25
        box = (x - w / 2, y - csize, x + w / 2, y + 2)
        if box[0] < 8 or box[2] > W - 8 or box[1] < 8 or box[3] > H - 8:
            continue
        if any(_boxes_overlap(box, b, gap=6) for b in taken):
            continue
        out.append(_text(x, y, html.escape(c['name'].upper()), csize, 'middle', '#B9B5AA',
                         halo=False, mono=True, extra=' letter-spacing="1.2"'))
    out.append('</g>')

    for m in sorted(marks + ghost, key=lambda m: -m['r']):
        out.append(_dot(m['x'], m['y'], m['r'], m['site'], standalone))
    for i, (x, y, anchor, leader) in labels.items():
        if leader:
            out.append(f'<path d="M{leader[0]:.1f},{leader[1]:.1f}L{leader[2]:.1f},{leader[3]:.1f}" '
                       f'stroke="#888780" stroke-width="0.8"/>')
        out.append(_site_label(marks[i]['site'], x, y, anchor, label_size))
    unlabeled = [m for i, m in enumerate(marks) if i not in labels]

    if zoom_box:
        zx0, zy0, zx1, zy1 = zoom_box
        fx0, fy0, fx1, fy1 = frame
        # Frame on the main map + connector to the panel.
        out.append(f'<rect x="{fx0:.1f}" y="{fy0:.1f}" width="{fx1 - fx0:.1f}" height="{fy1 - fy0:.1f}" '
                   f'fill="none" stroke="#4A4945" stroke-width="1" stroke-dasharray="4 3"/>')
        # Connector between the closest pair of corners, wherever the panel landed.
        a, b = min(((p, q) for p in ((fx0, fy0), (fx1, fy0), (fx0, fy1), (fx1, fy1))
                    for q in ((zx0, zy0), (zx1, zy0), (zx0, zy1), (zx1, zy1))),
                   key=lambda pq: (pq[0][0] - pq[1][0]) ** 2 + (pq[0][1] - pq[1][1]) ** 2)
        # Only when short — a long leader across the map reads as a route, not a pointer.
        if math.dist(a, b) < W * 0.2:
            out.append(f'<path d="M{a[0]:.1f},{a[1]:.1f}L{b[0]:.1f},{b[1]:.1f}" stroke="#B9B5AA" '
                       f'stroke-width="0.8" stroke-dasharray="4 3"/>')
        out.append(f'<rect x="{zx0:.1f}" y="{zy0:.1f}" width="{zx1 - zx0:.1f}" height="{zy1 - zy0:.1f}" '
                   f'fill="#FFFFFF" stroke="#4A4945" stroke-width="1"/>')
        out.append(f'<g clip-path="url(#zclip-{tag})">')
        for c in counties:
            d = ''.join(_ring_path(r, zproj) for r in c['rings'])
            out.append(f'<path d="{d}" fill="{county_fill(c)}" stroke="#D9D5CA" stroke-width="0.8"/>')
        for m in sorted(zmarks, key=lambda m: -m['r']):
            out.append(_dot(m['x'], m['y'], m['r'], m['site'], standalone))
        for i, (x, y, anchor, leader) in zlabels.items():
            if leader:
                out.append(f'<path d="M{leader[0]:.1f},{leader[1]:.1f}L{leader[2]:.1f},{leader[3]:.1f}" '
                           f'stroke="#888780" stroke-width="0.8"/>')
            out.append(_site_label(zmarks[i]['site'], x, y, anchor, label_size))
        out.append('</g>')
        out.append(_text(zx0 + 10, zy0 + 17, 'CENTRAL ATLANTA &amp; DECATUR · ENLARGED', label_size * .78,
                         fill='#888780', mono=True, extra=' letter-spacing="1.2"'))
        unlabeled += [m for i, m in enumerate(zmarks) if i not in zlabels]

    if far_box:
        x0, y0, x1, y1 = far_box
        out.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="3" fill="#FFFFFF" '
                   f'stroke="#D9D5CA"/>')
        step = (x1 - x0) / (len(far) + 1)
        for n, s in enumerate(far, 1):
            cx, cy = x0 + step * n, y0 + 50
            out.append(_dot(cx, cy, radius(s['attendees']), s, standalone))
            out.append(_site_label(s, cx, y1 - 14, 'middle', label_size * .9))
        out.append(_text(x0 + 10, y0 + 18, 'OUTSIDE GEORGIA', label_size * .78, fill='#888780',
                         halo=False, mono=True, extra=' letter-spacing="1.2"'))

    out.append(_legend(legend_box, radius, top, audience, sites, label_size))

    # 10 km scale bar, bottom right under the zoom panel.
    km10 = 10 * proj.scale / 111.32
    bx, by = W - 24 - km10, H - 14
    out.append(f'<path d="M{bx:.1f},{by - 4}V{by}H{bx + km10:.1f}V{by - 4}" fill="none" stroke="#888780" '
               f'stroke-width="1.2"/>')
    out.append(_text(bx - 6, by, '10 km', label_size * .8, 'end', '#888780', halo=False, mono=True))
    out.append('</svg>')
    return '\n'.join(out), unlabeled


def _dot(x, y, r, site, standalone):
    hue = AUDIENCES[site['audience']]['hue']
    dash = '' if site['precision'] == 'venue' else ' stroke-dasharray="3 2"'
    ring = '#FFFFFF' if site['precision'] == 'venue' else hue
    tip = html.escape(_tip(site), quote=True)
    attrs = '' if standalone else f' class="site" tabindex="0" data-tip="{tip}"'
    return (f'<g{attrs}><title>{tip}</title>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{hue}" fill-opacity="{0.78 if dash == "" else 0.35}" '
            f'stroke="{ring}" stroke-width="2"{dash}/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{max(r + 8, 12):.1f}" fill="transparent"/></g>')


def _legend(box, radius, top, audience, sites, size):
    x0, y0, x1, y1 = box
    out = [f'<g font-size="{size * .92:.1f}" fill="#4A4945">']
    out.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="3" fill="#FFFFFF" '
               f'fill-opacity="0.92" stroke="#E0DDD4"/>')
    out.append(f'<text x="{x0 + 12}" y="{y0 + 18}" font-family="{html.escape(MONO, quote=True)}" '
               f'font-size="{size * .78:.1f}" letter-spacing="1.2" fill="#888780">PEOPLE REACHED PER SITE</text>')
    # Nested size key, bottom-aligned.
    steps = [v for v in (50, 200, 500) if v <= top * 1.2] or [top]
    base = y0 + 104
    cx = x0 + 52
    for v in steps:
        r = radius(v)
        out.append(f'<circle cx="{cx}" cy="{base - r:.1f}" r="{r:.1f}" fill="none" stroke="#888780" stroke-width="1"/>')
        out.append(f'<path d="M{cx},{base - 2 * r:.1f}H{cx + 58}" stroke="#C9C5BA" stroke-width="0.8"/>')
        out.append(f'<text x="{cx + 62}" y="{base - 2 * r + 4:.1f}" font-family="{html.escape(MONO, quote=True)}">{v:,}</text>')
    yy = base + 18
    kinds = [audience] if audience else [k for k in AUDIENCES if any(s['audience'] == k for s in sites)]
    for k in kinds:
        out.append(f'<circle cx="{x0 + 18}" cy="{yy - 4}" r="5" fill="{AUDIENCES[k]["hue"]}" fill-opacity=".78"/>'
                   f'<text x="{x0 + 30}" y="{yy}">{html.escape(AUDIENCES[k]["label"])}</text>')
        yy += 16
    out.append('</g>')
    return ''.join(out)


# ── page ──────────────────────────────────────────────────────────────────

MAP_CSS = """
  :root{--teal:#1D9E75;--purple:#534AB7;--ink:#1C1B18;--ink-mid:#4A4945;--ink-soft:#888780;
        --paper:#FAF8F3;--paper-2:#F1EFE8;--border:#E0DDD4;--white:#FFFFFF;}
  *{margin:0;padding:0;box-sizing:border-box;}
  html{-webkit-print-color-adjust:exact;print-color-adjust:exact;}
  body{font-family:'Outfit',sans-serif;background:var(--paper);color:var(--ink);font-size:13px;}
  .mono{font-family:'DM Mono',monospace;}
  .sheet{max-width:1000px;margin:0 auto;background:var(--white);}
  @media screen{body{padding:2rem 16px;}.sheet{border:1px solid var(--border);border-radius:2px;}}
  header{background:var(--ink);padding:1.8rem 2.2rem 1.5rem;}
  .h-label{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.15em;color:var(--teal);text-transform:uppercase;margin-bottom:.45rem;}
  .h-title{font-family:'DM Serif Display',serif;font-size:1.9rem;color:#fff;line-height:1.12;}
  .h-sub{font-size:12.5px;color:#a9a8a2;font-weight:300;margin-top:.35rem;}
  .h-links{margin-top:.9rem;font-family:'DM Mono',monospace;font-size:10px;display:flex;gap:14px;flex-wrap:wrap;}
  .h-links a{color:#c9c9c2;}
  .kpis{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--border);}
  .kpi{padding:1rem 1.3rem;border-right:1px solid var(--border);border-top:3px solid var(--accent,var(--teal));}
  .kpi:last-child{border-right:none;}
  .kpi-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-soft);margin-bottom:.4rem;}
  .kpi-value{font-family:'DM Serif Display',serif;font-size:2rem;line-height:1;}
  .kpi-sub{font-size:10.5px;color:var(--ink-soft);margin-top:.3rem;font-weight:300;}
  .section{padding:1.4rem 2.2rem;}
  .section+.section{border-top:1px solid var(--border);}
  .sec-title{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-soft);margin-bottom:.9rem;}
  .toggle{display:flex;gap:6px;margin-bottom:.9rem;flex-wrap:wrap;}
  .toggle button{font:inherit;font-size:12px;padding:.35rem .8rem;border:1px solid var(--border);background:var(--white);border-radius:999px;cursor:pointer;color:var(--ink-mid);}
  .toggle button[aria-pressed=true]{background:var(--ink);color:#fff;border-color:var(--ink);}
  .view{display:none;}
  .view.on{display:block;}
  .map-svg{width:100%;height:auto;display:block;font-family:'Outfit',sans-serif;}
  #map{height:620px;border:1px solid var(--border);border-radius:4px;background:#eef0ee;}
  @media (max-width:700px){#map{height:460px;}}
  .leaflet-container{font-family:'Outfit',sans-serif;}
  .leaflet-container img.leaflet-tile{mix-blend-mode:plus-lighter;}
  .site-label{background:rgba(255,255,255,.92);border:none;box-shadow:0 1px 3px rgba(0,0,0,.18);border-radius:3px;
    padding:1px 6px;font-size:11.5px;font-weight:500;color:var(--ink);white-space:nowrap;}
  .site-label::before{display:none;}
  .site-label .n{font-family:'DM Mono',monospace;font-weight:400;color:var(--ink-mid);margin-left:4px;font-size:10.5px;}
  .leaflet-popup-content{margin:10px 14px;font-size:12px;line-height:1.45;}
  .pop-title{font-weight:500;font-size:13.5px;}
  .pop-sub{color:var(--ink-soft);font-size:11px;margin-bottom:6px;}
  .pop table td{padding:2px 6px 2px 0;border:none;font-size:11.5px;}
  .map-legend{background:rgba(255,255,255,.95);padding:10px 12px;border-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,.2);font-size:11.5px;line-height:1.5;color:var(--ink);}
  .map-legend .row{display:flex;align-items:center;gap:7px;}
  .map-legend .dot{display:inline-block;border-radius:50%;}
  .map-legend .sizes{display:flex;align-items:flex-end;gap:10px;margin-top:6px;}
  .map-legend .sizes div{text-align:center;font-family:'DM Mono',monospace;font-size:10px;color:var(--ink-mid);}
  .map-legend .sizes span{display:block;margin:0 auto 2px;border-radius:50%;border:1.5px solid var(--ink-mid);}
  .jump{margin-left:auto;}
  .site{cursor:pointer;outline:none;}
  .site:hover circle:first-of-type,.site:focus circle:first-of-type{fill-opacity:1;}
  .caption{font-size:11px;color:var(--ink-soft);font-weight:300;margin-top:.6rem;line-height:1.5;}
  #tip{position:fixed;pointer-events:none;background:var(--ink);color:#fff;font-size:11.5px;line-height:1.45;padding:.5rem .7rem;border-radius:4px;max-width:340px;white-space:pre-line;display:none;z-index:9;box-shadow:0 2px 10px rgba(0,0,0,.2);}
  #tip b{font-weight:500;}
  table{width:100%;border-collapse:collapse;font-size:12px;}
  th{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-soft);text-align:left;font-weight:400;padding:.4rem .5rem;border-bottom:1px solid var(--border);}
  td{padding:.4rem .5rem;border-bottom:1px solid var(--paper-2);vertical-align:top;}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;}
  .swatch{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle;}
  .notes li{margin:0 0 .45rem 1rem;font-size:12px;color:var(--ink-mid);line-height:1.5;}
  .approx{color:var(--ink-soft);font-size:10.5px;}
  .downloads a{color:var(--ink-mid);font-size:12px;margin-right:14px;}
  @media (max-width:700px){.kpis{grid-template-columns:repeat(2,1fr);}.section,header{padding-left:16px;padding-right:16px;}}
  @media print{body{padding:0;}.toggle,.downloads{display:none;}.view{display:block;break-inside:avoid;}}
"""

MAP_JS = r"""
(function(){
  var DATA=JSON.parse(document.getElementById('map-data').textContent);
  var HUE={k12:'#1D9E75',public:'#534AB7'};
  var MAXR=36,MINR=5;
  var maxAtt=Math.max.apply(null,DATA.sites.map(function(s){return s.attendees;}).concat([1]));
  function radius(n){return Math.max(MINR,MAXR*Math.sqrt(n/maxAtt));}
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function fmt(n){return n.toLocaleString('en-US');}

  var map=L.map('map',{scrollWheelZoom:true,zoomSnap:0.5,wheelPxPerZoomLevel:90});
  var ESRI='https://server.arcgisonline.com/ArcGIS/rest/services/';
  function esri(name,attr){return L.tileLayer(ESRI+name+'/MapServer/tile/{z}/{y}/{x}',{attribution:attr,maxZoom:18});}
  var bases={
    'Streets':esri('World_Street_Map','Tiles &copy; Esri — Esri, HERE, Garmin, USGS, OpenStreetMap contributors'),
    'Light':L.layerGroup([esri('Canvas/World_Light_Gray_Base','Tiles &copy; Esri — Esri, HERE, Garmin, OpenStreetMap contributors'),
                          esri('Canvas/World_Light_Gray_Reference','')]),
    'Satellite':L.layerGroup([esri('World_Imagery','Imagery &copy; Esri, Maxar, Earthstar Geographics'),
                              esri('Reference/World_Boundaries_and_Places','')]),
    'OpenStreetMap':L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      {attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',maxZoom:19})
  };
  bases['Streets'].addTo(map);
  L.control.layers(bases,null,{position:'topright'}).addTo(map);

  var layer=L.layerGroup().addTo(map), markers=[];
  function popup(s){
    var rows=s.visits.map(function(v){return '<tr><td>'+esc(v.date)+'</td><td>'+esc(v.venue)+'</td><td style="text-align:right">'+fmt(v.attendees)+'</td></tr>';}).join('');
    return '<div class="pop"><div class="pop-title">'+esc(s.label)+'</div>'+
      '<div class="pop-sub">'+fmt(s.attendees)+' people · '+s.visits.length+' visit'+(s.visits.length>1?'s':'')+
      (s.county?' · '+esc(s.county):'')+(s.precision!=='venue'?' · approximate location ('+esc(s.precision)+')':'')+'</div>'+
      '<table>'+rows+'</table></div>';
  }
  function draw(aud){
    layer.clearLayers(); markers=[];
    DATA.sites.filter(function(s){return !aud||s.audience===aud;})
      .sort(function(a,b){return b.attendees-a.attendees;})
      .forEach(function(s){
        var exact=s.precision==='venue';
        var m=L.circleMarker([s.lat,s.lon],{radius:radius(s.attendees),color:'#fff',weight:exact?1.5:2,
          dashArray:exact?null:'4 3',fillColor:HUE[s.audience],fillOpacity:.72});
        m.bindPopup(popup(s),{maxWidth:360});
        m.bindTooltip('<span>'+esc(s.label)+'</span><span class="n">'+fmt(s.attendees)+'</span>',
          {permanent:true,direction:'right',offset:[radius(s.attendees)+2,0],className:'site-label'});
        m.on('mouseover',function(){m.setStyle({fillOpacity:.95,weight:2.5});});
        m.on('mouseout',function(){m.setStyle({fillOpacity:.72,weight:exact?1.5:2});});
        m.addTo(layer); markers.push(m);
      });
    // smallest on top so big dots never hide small ones
    markers.slice().reverse().forEach(function(m){m.bringToFront();});
    declutter();
  }
  // hide labels that would overlap a bigger site's label
  function declutter(){
    var kept=[];
    markers.forEach(function(m){
      var el=m.getTooltip()&&m.getTooltip().getElement(); if(!el) return;
      el.style.visibility='visible';
      var b=el.getBoundingClientRect(), box=[b.left-2,b.top-2,b.right+2,b.bottom+2];
      var hit=kept.some(function(k){return !(box[2]<k[0]||box[0]>k[2]||box[3]<k[1]||box[1]>k[3]);});
      if(hit) el.style.visibility='hidden'; else kept.push(box);
    });
  }
  map.on('zoomend moveend',declutter);

  var GA=DATA.sites.filter(function(s){return !s.inset;}).map(function(s){return [s.lat,s.lon];});
  function home(){map.fitBounds(GA,{padding:[20,20],maxZoom:11});}
  home();

  // legend
  var legend=L.control({position:'bottomleft'});
  legend.onAdd=function(){
    var d=L.DomUtil.create('div','map-legend');
    var steps=[100,500,maxAtt>=1500?1500:Math.round(maxAtt)];
    d.innerHTML='<div class="row"><span class="dot" style="width:11px;height:11px;background:'+HUE.k12+'"></span>K–12 school &amp; youth</div>'+
      '<div class="row aud-public"><span class="dot" style="width:11px;height:11px;background:'+HUE.public+'"></span>Public &amp; community</div>'+
      '<div class="sizes">'+steps.map(function(n){var r=radius(n);return '<div><span style="width:'+2*r+'px;height:'+2*r+'px"></span>'+fmt(n)+'</div>';}).join('')+'</div>'+
      '<div style="font-size:10px;color:#888780;margin-top:3px">people reached · dashed = approximate</div>';
    return d;
  };
  legend.addTo(map);

  var current='k12';
  function setView(v){
    current=v; draw(v==='all'?null:'k12');
    document.querySelectorAll('.toggle button[data-view]').forEach(function(b){b.setAttribute('aria-pressed',b.dataset.view===v);});
    document.querySelectorAll('.kset').forEach(function(el){el.hidden=el.dataset.set!==v;});
    var pub=document.querySelector('.aud-public'); if(pub) pub.style.display=v==='all'?'flex':'none';
  }
  document.querySelectorAll('.toggle button[data-view]').forEach(function(btn){
    btn.addEventListener('click',function(){setView(btn.dataset.view);});
  });
  var dc=DATA.sites.filter(function(s){return s.inset;});
  document.querySelectorAll('.toggle button[data-jump]').forEach(function(btn){
    btn.addEventListener('click',function(){
      if(btn.dataset.jump==='home'||!dc.length) home();
      else map.setView([dc[0].lat,dc[0].lon],12);
    });
  });
  setView('k12');
})();
"""


def _kpi(label, value, sub, accent='var(--teal)'):
    return (f'<div class="kpi" style="--accent:{accent}"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{value}</div><div class="kpi-sub">{sub}</div></div>')


def render_map_page(data, sources, svgs, files):
    """svgs: {'k12': svg, 'all': svg}; files: {'k12': href, 'all': href} for poster downloads."""
    k12, everything = summarize(data, 'k12'), summarize(data)
    dates = sorted(v['date_sort'] for s in data['sites'] for v in s['visits'])
    span = ''
    if dates:
        from datetime import datetime
        fmt = lambda d: datetime.strptime(d, '%Y-%m-%d').strftime('%b %Y')
        span = f'{fmt(dates[0])} – {fmt(dates[-1])}'

    rows = []
    for s in data['sites']:
        hue = AUDIENCES[s['audience']]['hue']
        approx = '' if s['precision'] == 'venue' else f' <span class="approx">(approx., {s["precision"]})</span>'
        rows.append(f'<tr><td><span class="swatch" style="background:{hue}"></span>{html.escape(s["label"])}{approx}</td>'
                    f'<td>{html.escape(s["county"])}</td><td class="num">{len(s["visits"])}</td>'
                    f'<td class="num">{s["attendees"]:,}</td></tr>')

    notes = [
        'Dot <strong>area</strong> is proportional to the number of attendees recorded on the event form, '
        'summed over every visit to that site. The form records all attendees, not only children — '
        'school-night and festival counts include parents and families.',
        'Venues on one campus are drawn as one dot (e.g. Beacon Hill MS and its Gifted Connections program; '
        'Rockdale Magnet and its summer camp).',
    ]
    approx = [s for s in data['sites'] if s['precision'] != 'venue']
    if approx:
        notes.append('Dashed dots are approximate positions: ' + '; '.join(
            f'{html.escape(s["label"])} ({html.escape(s["precision"])})' for s in approx) + '.')
    if data['unmapped']:
        notes.append(
            f'<strong>Not yet mapped</strong> ({sum(u["attendees"] for u in data["unmapped"]):,} people, '
            f'{sum(len(u["visits"]) for u in data["unmapped"])} visits) — location unknown, add it to '
            '<code>venues.csv</code>: ' + '; '.join(
                f'{html.escape(u["label"])} ({u["attendees"]:,})' for u in data['unmapped']) + '.')
    if data['unknown']:
        notes.append('<strong>Venues missing from venues.csv</strong>: ' + '; '.join(
            html.escape(u['venue']) for u in data['unknown']) + '.')
    notes.append('Map tiles: Esri (streets, light gray, satellite) and OpenStreetMap contributors. Venue coordinates: OpenStreetMap '
                 'and web search, checked by hand. Poster SVG county outlines: US Census Bureau.')

    payload = {'sites': [{
        'label': s['label'], 'audience': s['audience'], 'lat': s['lat'], 'lon': s['lon'],
        'attendees': s['attendees'], 'precision': s['precision'], 'county': s['county'], 'inset': s['inset'],
        'visits': [{'date': v['date'], 'venue': v['venue'], 'attendees': v['attendees']} for v in s['visits']],
    } for s in data['sites']]}
    map_json = json.dumps(payload).replace('</', '<\\/')
    dc_button = ('<button data-jump="dc">Washington, DC</button>'
                 if any(s['inset'] for s in data['sites']) else '')

    k12_sub = (f'{k12["visits"]} visits · {k12["sites"]} sites'
               + (f' · +{k12["unmapped_attendees"]:,} not yet mapped' if k12['unmapped_attendees'] else ''))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NeuroEngage Outreach Map</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Serif+Display&family=Outfit:wght@300;400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>{MAP_CSS}</style></head>
<body><div class="sheet">
<header>
  <div class="h-label">NeuroEngage · Georgia State University</div>
  <div class="h-title">Where our outreach reaches</div>
  <div class="h-sub">Every school visit and public event, sized by the number of people reached · {span}</div>
  <div class="h-links"><a href="index.html">← Dashboard</a><a href="report.html">Progress report</a><a href="landscape.html">20-year landscape</a></div>
</header>
<div class="kpis">
  {_kpi('K–12 & youth reached', f'{k12["attendees"]:,}', k12_sub)}
  {_kpi('Schools & youth sites', k12['sites'], f'in {k12["counties"]} metro counties' + (' + Washington, DC' if k12['outside_ga'] else ''))}
  {_kpi('All people reached', f'{everything["attendees"]:,}', f'{everything["visits"]} events, mapped sites', 'var(--purple)')}
  {_kpi('Georgia counties reached', everything['counties'], 'all events', 'var(--purple)')}
</div>
<div class="section">
  <div class="toggle" role="group" aria-label="Which events to show">
    <button data-view="k12" aria-pressed="true">K–12 school &amp; youth visits</button>
    <button data-view="all" aria-pressed="false">All events</button>
    <button class="jump" data-jump="home">Metro Atlanta</button>
    {dc_button}
  </div>
  <div id="map" role="region" aria-label="Interactive map of outreach sites"></div>
  <p class="caption">Click a dot for the visits behind it. Scroll or pinch to zoom, drag to pan. Switch to Light or Satellite with the layers button (top right). Labels hide where they would overlap — zoom in to see them all.</p>
  <p class="caption downloads">Poster images (PNG, 3200×2300): <a href="map_poster_k12.png" download>K–12 map</a><a href="map_poster_all.png" download>All-events map</a> · Plain vector outlines (SVG): <a href="{files['k12']}" download>K–12</a><a href="{files['all']}" download>All events</a></p>
</div>
<div class="section">
  <div class="sec-title">Sites</div>
  <table><thead><tr><th>Site</th><th>County</th><th class="num">Visits</th><th class="num">People</th></tr></thead>
  <tbody>{''.join(rows)}</tbody></table>
</div>
<div class="section">
  <div class="sec-title">How to read this map</div>
  <ul class="notes">{''.join(f'<li>{n}</li>' for n in notes)}</ul>
  <p class="caption mono">Sources: {html.escape(', '.join(sources))} + venues.csv</p>
</div>
</div>
<script type="application/json" id="map-data">{map_json}</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>{MAP_JS}</script>
</body></html>"""


def build_map(events, venues_path, sources, out_dir, chrome=None):
    """Write map.html, poster SVGs and (with chrome) poster PNGs. Returns (paths, data, warnings)."""
    venues = load_venues(venues_path)
    data = build_map_data(events, venues)
    svgs, files, warnings, written = {}, {}, [], []
    for key, audience in (('k12', 'k12'), ('all', None)):
        inline, unlabeled = render_map_svg(data, audience)
        svgs[key] = inline
        poster, _ = render_map_svg(data, audience, standalone=True)
        name = f'map_{key}.svg'
        with open(os.path.join(out_dir, name), 'w', encoding='utf-8') as handle:
            handle.write('<?xml version="1.0" encoding="UTF-8"?>\n' + poster)
        files[key] = name
        written.append(os.path.join(out_dir, name))
        if unlabeled:
            warnings.append(f'map ({key}): no room to label ' + ', '.join(
                m['site']['label'] for m in unlabeled) + ' (still shown, with hover)')
    page = os.path.join(out_dir, 'map.html')
    with open(page, 'w', encoding='utf-8') as handle:
        handle.write(render_map_page(data, sources, svgs, files))
    written.insert(0, page)
    if chrome:
        for key, audience in (('k12', 'k12'), ('all', None)):
            png = os.path.join(out_dir, f'map_poster_{key}.png')
            ok, err = render_poster_png(render_poster_page(data, audience), chrome, png)
            if ok:
                written.append(png)
            else:
                warnings.append(f'map poster ({key}) not rendered: {err}')
    else:
        warnings.append('map poster PNGs skipped — Chrome not found')
    for u in data['unmapped']:
        warnings.append(f'map: no location for "{u["label"]}" ({u["attendees"]:,} people) — fill in venues.csv')
    for u in data['unknown']:
        warnings.append(f'map: venue "{u["venue"]}" is not in venues.csv — add a row')
    return written, data, warnings


# ── poster image (street map, rendered to PNG by headless Chrome) ──────────

POSTER_W, POSTER_H = 1600, 1150

POSTER_JS = r"""
(function(){
  var D=JSON.parse(document.getElementById('map-data').textContent);
  var HUE={k12:'#1D9E75',public:'#534AB7'}, MAXR=D.maxr, Z=D.zoom;
  var maxAtt=D.maxAtt;
  function radius(n,k){return Math.max(5*k,MAXR*k*Math.sqrt(n/maxAtt));}
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function fmt(n){return n.toLocaleString('en-US');}
  function tiles(m){
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',{maxZoom:18}).addTo(m);
  }
  var opts={zoomControl:false,attributionControl:false,zoomSnap:0.25,fadeAnimation:false,zoomAnimation:false};
  function inZoom(s){return s.lat>=Z.lat[0]&&s.lat<=Z.lat[1]&&s.lon>=Z.lon[0]&&s.lon<=Z.lon[1];}
  function bind(c,s,r,dir){
    c.unbindTooltip();
    c.bindTooltip('<span>'+esc(s.label)+'</span><span class="n">'+fmt(s.attendees)+'</span>',
      {permanent:true,direction:dir,offset:{left:[-(r+2),0],right:[r+2,0],top:[0,-(r+1)],bottom:[0,r+1]}[dir],className:'site-label'}).openTooltip();
  }
  function dots(m,sites,k,labelIf){
    var ms=[];
    sites.slice().sort(function(a,b){return b.attendees-a.attendees;}).forEach(function(s){
      var exact=s.precision==='venue', r=radius(s.attendees,k);
      var c=L.circleMarker([s.lat,s.lon],{radius:r,color:'#fff',weight:2,dashArray:exact?null:'5 4',
        fillColor:HUE[s.audience],fillOpacity:.78}).addTo(m);
      c._site=s; c._r=r; c._label=labelIf(s);
      ms.push(c);
    });
    ms.slice().reverse().forEach(function(c){c.bringToFront();});
    return ms;
  }
  function rect(el,pad){var b=el.getBoundingClientRect();return [b.left-pad,b.top-pad,b.right+pad,b.bottom+pad];}
  function hits(box,list){return list.some(function(k){return !(box[2]<k[0]||box[0]>k[2]||box[3]<k[1]||box[1]>k[3]);});}
  function inside(box,frame){return box[0]>=frame[0]&&box[1]>=frame[1]&&box[2]<=frame[2]&&box[3]<=frame[3];}
  function declutter(m,ms,avoid){
    var frame=rect(m.getContainer(),-4), kept=avoid.slice();
    // dots are obstacles too (except a label's own dot)
    var discs=ms.map(function(c){var p=c._path.getBoundingClientRect();return [p.left,p.top,p.right,p.bottom];});
    ms.forEach(function(c,i){
      if(!c._label) return;
      var others=discs.filter(function(_,j){return j!==i;});
      var dirs=['right','left','top','bottom'], placed=false;
      for(var d=0;d<dirs.length&&!placed;d++){
        bind(c,c._site,c._r,dirs[d]);
        var box=rect(c.getTooltip().getElement(),3);
        if(inside(box,frame)&&!hits(box,kept)&&!hits(box,others)){kept.push(box);placed=true;}
      }
      if(!placed){ // last resort: allow overlapping dots, never other labels or cards
        for(d=0;d<dirs.length&&!placed;d++){
          bind(c,c._site,c._r,dirs[d]);
          box=rect(c.getTooltip().getElement(),3);
          if(inside(box,frame)&&!hits(box,kept)){kept.push(box);placed=true;}
        }
      }
      if(!placed){c.unbindTooltip();window.HIDDEN.push(c._site.label);}
    });
  }
  window.HIDDEN=[];
  var GA=D.sites.filter(function(s){return !s.inset;});
  var main=L.map('main',opts); tiles(main);
  main.fitBounds(GA.map(function(s){return [s.lat,s.lon];}),{paddingTopLeft:[70,50],paddingBottomRight:[560,50]});
  L.rectangle([[Z.lat[0],Z.lon[0]],[Z.lat[1],Z.lon[1]]],{color:'#1C1B18',weight:1.5,dashArray:'6 4',fill:false}).addTo(main);
  var mainMarks=dots(main,GA,1,function(s){return !inZoom(s);});
  var inset=L.map('inset',opts); tiles(inset);
  inset.fitBounds([[Z.lat[0],Z.lon[0]],[Z.lat[1],Z.lon[1]]],{padding:[10,10]});
  var insetMarks=dots(inset,GA.filter(inZoom),1,function(){return true;});
  function box(id){var b=document.getElementById(id).getBoundingClientRect();return [b.left,b.top,b.right,b.bottom];}
  setTimeout(function(){
    declutter(main,mainMarks,[box('inset-wrap'),box('legend')]);
    declutter(inset,insetMarks,[]);
    document.body.setAttribute('data-ready','1');
  },400);
})();
"""


def render_poster_page(data, audience=None):
    """A fixed-size page meant to be screenshotted into a poster PNG."""
    sites = [s for s in data['sites'] if audience in (None, s['audience'])]
    summ = summarize(data, audience)
    max_att = max([s['attendees'] for s in data['sites']] + [1])
    payload = {
        'sites': [{'label': s['label'], 'audience': s['audience'], 'lat': s['lat'], 'lon': s['lon'],
                   'attendees': s['attendees'], 'precision': s['precision'], 'inset': s['inset']}
                  for s in sites],
        'zoom': ZOOM, 'maxAtt': max_att, 'maxr': 46,
    }
    map_json = json.dumps(payload).replace('</', '<\\/')
    dates = sorted(v['date_sort'] for s in sites for v in s['visits'])
    from datetime import datetime
    fmt = lambda d: datetime.strptime(d, '%Y-%m-%d').strftime('%b %Y')
    span = f'{fmt(dates[0])} – {fmt(dates[-1])}' if dates else ''
    if audience == 'k12':
        title, who = 'Where our school visits reach', 'students reached'
    else:
        title, who = 'Where our outreach reaches', 'people reached'
    extra = ' + Washington, DC' if summ['outside_ga'] else ''
    r = lambda n: max(5, 46 * math.sqrt(n / max_att))
    steps = [n for n in (50, 250, 750) if n <= max_att * 1.05] or [max_att]
    sizes = ''.join(f'<div><span style="width:{2*r(n):.0f}px;height:{2*r(n):.0f}px"></span>{n:,}</div>' for n in steps)
    aud_rows = ''.join(
        f'<div class="row"><span class="dot" style="background:{AUDIENCES[a]["hue"]}"></span>{lab}</div>'
        for a, lab in (('k12', 'K–12 school &amp; youth visits'), ('public', 'Public &amp; community events'))
        if audience in (None, a))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>NeuroEngage poster map</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Serif+Display&family=Outfit:wght@300;400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{width:{POSTER_W}px;height:{POSTER_H}px;font-family:'Outfit',sans-serif;color:#1C1B18;background:#fff;position:relative;overflow:hidden;}}
  header{{position:absolute;left:0;right:0;top:0;height:150px;padding:24px 40px;display:flex;align-items:center;gap:48px;border-bottom:3px solid #1D9E75;}}
  header .t{{flex:1;}}
  #main{{position:absolute;left:0;right:0;top:150px;bottom:0;}}
  .leaflet-container{{background:#eef0ee;font-family:'Outfit',sans-serif;}}
  .leaflet-tile-pane{{filter:saturate(.55) brightness(1.04);}}
  .card{{position:absolute;background:rgba(255,255,255,.95);border-radius:6px;box-shadow:0 2px 10px rgba(0,0,0,.18);z-index:1000;}}

  .eyebrow{{font-family:'DM Mono',monospace;font-size:13px;letter-spacing:.15em;text-transform:uppercase;color:#1D9E75;}}
  h1{{font-family:'DM Serif Display',serif;font-weight:400;font-size:46px;line-height:1.05;margin:6px 0 4px;}}
  .stats{{display:flex;gap:40px;}}
  .stat b{{display:block;font-family:'DM Serif Display',serif;font-weight:400;font-size:38px;line-height:1;}}
  .stat span{{font-size:14px;color:#4A4945;}}
  .sub{{font-size:15px;color:#4A4945;}}
  #inset-wrap{{right:32px;top:178px;width:500px;padding:10px;}}
  #inset{{width:480px;height:500px;border-radius:3px;}}
  .inset-title{{font-family:'DM Mono',monospace;font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#4A4945;margin:2px 2px 8px;}}
  #legend{{right:32px;bottom:32px;width:500px;padding:16px 20px;font-size:15px;}}
  #legend .row{{display:flex;align-items:center;gap:9px;margin-bottom:4px;}}
  #legend .dot{{width:15px;height:15px;border-radius:50%;}}
  .sizes{{display:flex;align-items:flex-end;gap:16px;margin-top:10px;}}
  .sizes div{{text-align:center;font-family:'DM Mono',monospace;font-size:13px;color:#4A4945;}}
  .sizes span{{display:block;margin:0 auto 4px;border-radius:50%;border:2px solid #4A4945;}}
  .lg-note{{font-size:13px;color:#888780;margin-top:6px;}}
  .credit{{position:absolute;left:16px;bottom:10px;font-size:11px;color:#4A4945;background:rgba(255,255,255,.8);padding:2px 6px;border-radius:3px;z-index:1000;}}
  .site-label{{background:rgba(255,255,255,.94);border:none;box-shadow:0 1px 3px rgba(0,0,0,.2);border-radius:3px;
    padding:2px 7px;font-size:15px;font-weight:500;color:#1C1B18;white-space:nowrap;}}
  .site-label::before{{display:none;}}
  .site-label .n{{font-family:'DM Mono',monospace;font-weight:400;color:#4A4945;margin-left:5px;font-size:13.5px;}}
</style></head>
<body>
<header>
  <div class="t">
    <div class="eyebrow">NeuroEngage · Georgia State University</div>
    <h1>{title}</h1>
    <div class="sub">{span} · {summ['counties']} Georgia counties{extra}</div>
  </div>
  <div class="stats">
    <div class="stat"><b>{summ['attendees']:,}</b><span>{who}</span></div>
    <div class="stat"><b>{summ['visits']}</b><span>visits</span></div>
    <div class="stat"><b>{summ['sites']}</b><span>sites</span></div>
  </div>
</header>
<div id="main"></div>
<div class="card" id="inset-wrap"><div class="inset-title">Close-up: downtown Atlanta &amp; Decatur</div><div id="inset"></div></div>
<div class="card" id="legend">
  {aud_rows}
  <div class="sizes">{sizes}</div>
  <div class="lg-note">Dot area = {who} · dashed = approximate location</div>
</div>
<div class="credit">Basemap © Esri, HERE, Garmin, USGS, OpenStreetMap contributors</div>
<script type="application/json" id="map-data">{map_json}</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>{POSTER_JS}</script>
</body></html>"""


def render_poster_png(page_html, chrome, png_path, scale=2):
    """Screenshot the poster page with headless Chrome (needs network for tiles)."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'poster.html')
        with open(src, 'w', encoding='utf-8') as handle:
            handle.write(page_html)
        cmd = [chrome, '--headless=new', '--disable-gpu', '--hide-scrollbars',
               f'--window-size={POSTER_W},{POSTER_H}', f'--force-device-scale-factor={scale}',
               '--virtual-time-budget=15000', f'--screenshot={png_path}', 'file://' + src]
        try:
            subprocess.run(cmd, capture_output=True, timeout=90)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)
    return os.path.exists(png_path), 'Chrome produced no file'
