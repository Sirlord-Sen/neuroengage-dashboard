#!/usr/bin/env python3
"""
NeuroEngage Outreach Dashboard Generator
-----------------------------------------
Usage:
    python3 generate_dashboard.py <path_to_csv> [output_html]

Example:
    python3 generate_dashboard.py outreach_data.csv dashboard.html

If no output file is specified, saves as: NeuroEngage_Dashboard.html
"""

import csv
import json
import sys
import os
import re
from datetime import datetime
from collections import defaultdict, OrderedDict


# ── HELPERS ──────────────────────────────────────────────────────────────────

def clean_key(k):
    """Strip newlines, replacement chars, and whitespace from CSV column names."""
    return re.sub(r'[\n\r\ufffd\x00-\x1f]', '', k).strip()


def parse_hours(raw):
    """Extract numeric hours from messy strings like '3 hours', '5', '8am set up to 1pm'."""
    raw = str(raw).strip().lower()
    if not raw:
        return 0.0
    # Plain number
    m = re.match(r'^(\d+\.?\d*)', raw)
    if m:
        return float(m.group(1))
    # "Xam ... Ypm"
    m = re.search(r'(\d+)\s*am.*?(\d+)\s*pm', raw)
    if m:
        return float(m.group(2)) - float(m.group(1))
    return 0.0


def parse_attendees(raw):
    cleaned = re.sub(r'[^\d]', '', str(raw).split('-')[0].split('~')[-1])
    try:
        return int(cleaned)
    except:
        return 0


# ── PARSE CSV ─────────────────────────────────────────────────────────────────

def parse_csv(filepath):
    events = []
    with open(filepath, encoding='utf-8-sig', errors='replace') as f:
        reader = csv.DictReader(f)
        for raw_row in reader:
            # Clean all keys
            row = {clean_key(k): v.strip() for k, v in raw_row.items() if k}

            # Date
            date_raw = row.get('Event Date', '')
            try:
                date = datetime.strptime(date_raw.strip(), '%m/%d/%Y')
            except:
                continue  # skip rows without valid date

            # Attendees
            attendees = parse_attendees(row.get('Number of Attendees', '0'))

            # Hours
            hours = parse_hours(row.get('Length of Time (e.g., hours spent volunteering)', '0'))

            # Activities — split on semicolon, strip blanks
            acts_raw = row.get('Activities (check all that apply)', '')
            activities = [a.strip() for a in acts_raw.split(';') if a.strip()]

            # Lead volunteer
            lead = row.get('Lead volunteer', '').strip()

            # Venue
            venue = row.get('School, organization, or event name', '').strip()

            events.append({
                'date':       date.strftime('%b %-d, %Y'),
                'date_sort':  date.strftime('%Y-%m-%d'),
                'month':      date.strftime('%b %Y'),
                'month_sort': date.strftime('%Y-%m'),
                'venue':      venue,
                'lead':       lead,
                'attendees':  attendees,
                'hours':      hours,
                'activities': activities,
            })

    events.sort(key=lambda x: x['date_sort'])
    return events


# ── AGGREGATE ─────────────────────────────────────────────────────────────────

def aggregate(events):
    # Build monthly dict in chronological order
    monthly = OrderedDict()
    for e in events:
        m = e['month']
        if m not in monthly:
            monthly[m] = {'events': 0, 'attendees': 0, 'hours': 0.0}
        monthly[m]['events']    += 1
        monthly[m]['attendees'] += e['attendees']
        monthly[m]['hours']     += round(e['hours'], 2)

    # Activity counts — loop through every event
    act_counts = defaultdict(int)
    for e in events:
        for a in e['activities']:
            if a:
                act_counts[a] += 1
    act_counts = dict(sorted(act_counts.items(), key=lambda x: -x[1]))

    # Lead counts
    lead_counts = defaultdict(int)
    for e in events:
        if e['lead']:
            lead_counts[e['lead']] += 1
    lead_counts = dict(sorted(lead_counts.items(), key=lambda x: -x[1]))

    # Summary stats
    total_events    = len(events)
    total_attendees = sum(e['attendees'] for e in events)
    total_hours     = round(sum(e['hours'] for e in events), 1)
    unique_leads    = len(lead_counts)
    num_months      = len(monthly)
    avg_attendees   = round(total_attendees / num_months) if num_months else 0
    avg_events      = round(total_events / num_months, 1) if num_months else 0

    return {
        'monthly':    monthly,
        'activities': act_counts,
        'leads':      lead_counts,
        'stats': {
            'total_events':    total_events,
            'total_attendees': total_attendees,
            'total_hours':     total_hours,
            'unique_leads':    unique_leads,
            'num_months':      num_months,
            'avg_attendees':   avg_attendees,
            'avg_events':      avg_events,
        }
    }


# ── GENERATE HTML ─────────────────────────────────────────────────────────────

def generate_html(events, agg, source_file):
    s = agg['stats']
    generated_date = datetime.now().strftime('%B %-d, %Y')

    if events:
        first = datetime.strptime(events[0]['date_sort'],  '%Y-%m-%d').strftime('%b %Y')
        last  = datetime.strptime(events[-1]['date_sort'], '%Y-%m-%d').strftime('%b %Y')
        date_range = f"{first} &ndash; {last}"
    else:
        date_range = "No data"

    # Serialize full data for JS — everything comes from the CSV
    data_json = json.dumps({
        'monthly':    dict(agg['monthly']),
        'activities': agg['activities'],
        'leads':      agg['leads'],
    }, indent=2)

    # Build event table rows dynamically from parsed events
    event_rows = ''
    for ev in events:
        acts_html = ''.join(f'<span class="tag">{a}</span>' for a in ev['activities'])
        hrs = f"{ev['hours']:.1f}".rstrip('0').rstrip('.') or '0'
        event_rows += f"""
      <tr>
        <td class="mono soft" style="white-space:nowrap">{ev['date']}</td>
        <td class="venue-cell">{ev['venue']}</td>
        <td style="font-size:11px">{ev['lead']}</td>
        <td><span class="attendee-pill">{ev['attendees']}</span></td>
        <td>{acts_html}</td>
        <td class="mono soft">{hrs}h</td>
      </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NeuroEngage Outreach Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Mono:wght@400;500&family=Outfit:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --teal:#1D9E75; --teal-light:#E1F5EE; --teal-dark:#0d6e50;
    --purple:#534AB7; --purple-light:#EEEDFE;
    --amber:#BA7517; --amber-light:#FAEEDA;
    --red:#E24B4A;
    --ink:#1C1B18; --ink-mid:#4A4945; --ink-soft:#888780;
    --paper:#FAF8F3; --paper-2:#F1EFE8; --border:#E0DDD4; --white:#FFFFFF;
  }}
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:'Outfit',sans-serif;background:var(--paper);color:var(--ink);}}
  .mono{{font-family:'DM Mono',monospace;}}
  .soft{{color:var(--ink-soft);}}

  /* HEADER */
  .header{{background:var(--ink);padding:2.5rem 3rem 2rem;position:relative;overflow:hidden;}}
  .header::before{{content:'';position:absolute;top:-60px;right:-60px;width:300px;height:300px;background:radial-gradient(circle,rgba(29,158,117,.25),transparent 70%);border-radius:50%;}}
  .header::after{{content:'';position:absolute;bottom:-40px;left:200px;width:200px;height:200px;background:radial-gradient(circle,rgba(83,74,183,.2),transparent 70%);border-radius:50%;}}
  .header-inner{{position:relative;z-index:1;}}
  .h-label{{font-family:'DM Mono',monospace;font-size:11px;letter-spacing:.15em;color:var(--teal);text-transform:uppercase;margin-bottom:.5rem;}}
  .h-title{{font-family:'DM Serif Display',serif;font-size:2.4rem;color:#fff;line-height:1.1;margin-bottom:.4rem;}}
  .h-sub{{font-size:14px;color:#888780;font-weight:300;}}
  .h-date{{font-family:'DM Mono',monospace;font-size:11px;color:#555;margin-top:1rem;}}

  /* STAT BAR */
  .stats-bar{{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--border);}}
  .stat-card{{padding:1.8rem 2rem;border-right:1px solid var(--border);background:var(--white);position:relative;overflow:hidden;transition:background .2s;cursor:default;}}
  .stat-card:last-child{{border-right:none;}}
  .stat-card:hover{{background:var(--paper);}}
  .stat-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;}}
  .stat-card:nth-child(1)::before{{background:var(--teal);}}
  .stat-card:nth-child(2)::before{{background:var(--purple);}}
  .stat-card:nth-child(3)::before{{background:var(--amber);}}
  .stat-card:nth-child(4)::before{{background:var(--red);}}
  .stat-label{{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-soft);margin-bottom:.6rem;}}
  .stat-value{{font-family:'DM Serif Display',serif;font-size:2.8rem;color:var(--ink);line-height:1;margin-bottom:.3rem;}}
  .stat-sub{{font-size:12px;color:var(--ink-soft);font-weight:300;}}

  /* GRID */
  .main{{padding:2rem 3rem;display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;}}
  .card{{background:var(--white);border:1px solid var(--border);border-radius:2px;padding:1.5rem;animation:fadeUp .5s ease both;}}
  .card.full{{grid-column:1/-1;}}
  .card-title{{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-soft);margin-bottom:1.2rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;}}
  .ct-left{{display:flex;align-items:center;gap:8px;}}
  .dot{{width:8px;height:8px;border-radius:50%;display:inline-block;flex-shrink:0;}}
  .avg-pill{{font-family:'DM Mono',monospace;font-size:10px;padding:3px 8px;border-radius:10px;font-weight:400;white-space:nowrap;}}
  .pill-teal{{background:var(--teal-light);color:var(--teal-dark);}}
  .pill-purple{{background:var(--purple-light);color:var(--purple);}}

  /* BARS */
  .bar-chart{{display:flex;flex-direction:column;gap:10px;}}
  .bar-row{{display:flex;align-items:center;gap:10px;}}
  .bar-label{{font-family:'DM Mono',monospace;font-size:10px;color:var(--ink-mid);width:64px;flex-shrink:0;text-align:right;}}
  .bar-track{{flex:1;height:22px;background:var(--paper-2);border-radius:2px;overflow:hidden;}}
  .bar-fill{{height:100%;border-radius:2px;transition:width 1s cubic-bezier(.4,0,.2,1);}}
  .bar-val{{font-family:'DM Mono',monospace;font-size:10px;color:var(--ink-mid);width:56px;flex-shrink:0;}}

  /* ACTIVITIES */
  .activity-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;}}
  .activity-item{{display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--paper);border-radius:2px;border:1px solid var(--border);}}
  .act-dot{{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-family:'DM Mono',monospace;font-size:11px;font-weight:500;color:white;flex-shrink:0;}}
  .act-name{{font-size:12px;font-weight:500;color:var(--ink);line-height:1.2;}}
  .act-count{{font-family:'DM Mono',monospace;font-size:10px;color:var(--ink-soft);}}

  /* VOLUNTEERS */
  .vol-list{{display:flex;flex-direction:column;gap:8px;}}
  .vol-row{{display:flex;align-items:center;gap:10px;}}
  .vol-name{{font-size:12px;font-weight:500;color:var(--ink);width:140px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .vol-track{{flex:1;height:16px;background:var(--paper-2);border-radius:2px;overflow:hidden;}}
  .vol-fill{{height:100%;background:var(--purple);border-radius:2px;transition:width 1s ease;}}
  .vol-count{{font-family:'DM Mono',monospace;font-size:11px;color:var(--ink-soft);width:24px;text-align:right;}}

  /* TABLE */
  .event-table{{width:100%;border-collapse:collapse;}}
  .event-table th{{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-soft);text-align:left;padding:0 10px 10px 0;border-bottom:1px solid var(--border);}}
  .event-table td{{font-size:12px;color:var(--ink-mid);padding:8px 10px 8px 0;border-bottom:1px solid var(--paper-2);vertical-align:top;}}
  .event-table tr:last-child td{{border-bottom:none;}}
  .venue-cell{{color:var(--ink);font-weight:500;max-width:200px;}}
  .attendee-pill{{display:inline-flex;align-items:center;background:var(--teal-light);color:var(--teal-dark);font-family:'DM Mono',monospace;font-size:10px;padding:2px 7px;border-radius:10px;font-weight:500;}}
  .tag{{display:inline-block;background:var(--paper-2);color:var(--ink-mid);font-size:10px;padding:2px 6px;border-radius:2px;margin:1px;}}

  /* TOOLTIP */
  .tooltip{{position:fixed;background:var(--ink);color:white;padding:8px 12px;border-radius:4px;font-size:12px;pointer-events:none;opacity:0;transition:opacity .15s;z-index:1000;font-family:'Outfit',sans-serif;}}
  .tooltip.show{{opacity:1;}}

  /* FOOTER */
  .footer{{padding:1.5rem 3rem;border-top:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;}}

  @keyframes fadeUp{{from{{opacity:0;transform:translateY(16px)}}to{{opacity:1;transform:translateY(0)}}}}
  .stat-card:nth-child(1){{animation:fadeUp .4s ease .00s both;}}
  .stat-card:nth-child(2){{animation:fadeUp .4s ease .06s both;}}
  .stat-card:nth-child(3){{animation:fadeUp .4s ease .12s both;}}
  .stat-card:nth-child(4){{animation:fadeUp .4s ease .18s both;}}
  .card:nth-child(1){{animation-delay:.05s;}}
  .card:nth-child(2){{animation-delay:.10s;}}
  .card:nth-child(3){{animation-delay:.15s;}}
  .card:nth-child(4){{animation-delay:.20s;}}
  .card:nth-child(5){{animation-delay:.25s;}}
</style>
</head>
<body>

<div class="tooltip" id="tt"></div>

<div class="header">
  <div class="header-inner">
    <div class="h-label">Georgia State University &bull; CBN / TReNDS</div>
    <div class="h-title">NeuroEngage Outreach Dashboard</div>
    <div class="h-sub">Dana NextGen Fellowship &mdash; Outreach Activity Record</div>
    <div class="h-date">Generated {generated_date} &bull; Data: {date_range} &bull; Source: {os.path.basename(source_file)}</div>
  </div>
</div>

<div class="stats-bar">
  <div class="stat-card">
    <div class="stat-label">Total Events</div>
    <div class="stat-value" id="s-events">0</div>
    <div class="stat-sub">outreach sessions logged</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">People Reached</div>
    <div class="stat-value" id="s-attendees">0</div>
    <div class="stat-sub">students &amp; community members</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Volunteer Hours</div>
    <div class="stat-value" id="s-hours">0</div>
    <div class="stat-sub">hours of outreach delivered</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Unique Lead Volunteers</div>
    <div class="stat-value" id="s-leads">0</div>
    <div class="stat-sub">different people leading events</div>
  </div>
</div>

<div class="main">

  <div class="card">
    <div class="card-title">
      <span class="ct-left"><span class="dot" style="background:var(--teal)"></span>Attendees per month</span>
      <span class="avg-pill pill-teal">avg <strong>{s['avg_attendees']:,}</strong> / month</span>
    </div>
    <div class="bar-chart" id="att-bars"></div>
  </div>

  <div class="card">
    <div class="card-title">
      <span class="ct-left"><span class="dot" style="background:var(--purple)"></span>Events per month</span>
      <span class="avg-pill pill-purple">avg <strong>{s['avg_events']}</strong> / month</span>
    </div>
    <div class="bar-chart" id="evt-bars"></div>
  </div>

  <div class="card">
    <div class="card-title"><span class="ct-left"><span class="dot" style="background:var(--amber)"></span>Activity usage</span></div>
    <div class="activity-grid" id="act-grid"></div>
  </div>

  <div class="card">
    <div class="card-title"><span class="ct-left"><span class="dot" style="background:var(--red)"></span>Events led per volunteer</span></div>
    <div class="vol-list" id="vol-list"></div>
  </div>

  <div class="card full">
    <div class="card-title"><span class="ct-left"><span class="dot" style="background:var(--teal)"></span>Full event log ({s['total_events']} events)</span></div>
    <table class="event-table">
      <thead><tr><th>Date</th><th>Venue / Organization</th><th>Lead</th><th>Attendees</th><th>Activities</th><th>Hours</th></tr></thead>
      <tbody>{event_rows}</tbody>
    </table>
  </div>

</div>

<div class="footer">
  <div class="mono soft" style="font-size:10px;letter-spacing:.08em">NEUROENGAGE &bull; DANA NEXTGEN FELLOWSHIP &bull; GSU</div>
  <div class="mono soft" style="font-size:10px">{s['total_events']} events &bull; Generated {generated_date}</div>
</div>

<script>
const DATA = {data_json};
const COLORS=['#1D9E75','#534AB7','#BA7517','#E24B4A','#0d6e50','#8B80D4','#D4910F','#2E86AB','#E07A5F'];

const tt=document.getElementById('tt');
const tip=(e,h)=>{{tt.innerHTML=h;tt.classList.add('show');move(e);}};
const move=(e)=>{{tt.style.left=(e.clientX+14)+'px';tt.style.top=(e.clientY-10)+'px';}};
const hide=()=>tt.classList.remove('show');

function counter(el,target,dur=1200){{
  const t0=performance.now();
  const isF=String(target).includes('.');
  (function step(now){{
    const p=Math.min((now-t0)/dur,1),e=1-Math.pow(1-p,3);
    el.textContent=Number(isF?(target*e).toFixed(1):Math.round(target*e)).toLocaleString();
    if(p<1)requestAnimationFrame(step);
  }})(t0);
}}

counter(document.getElementById('s-events'),   {s['total_events']});
counter(document.getElementById('s-attendees'), {s['total_attendees']});
counter(document.getElementById('s-hours'),     {s['total_hours']});
counter(document.getElementById('s-leads'),     {s['unique_leads']});

// ── BARS (fully dynamic from DATA) ──
const months = Object.keys(DATA.monthly);
const nMonths = months.length;
const maxAtt = Math.max(...months.map(m=>DATA.monthly[m].attendees));
const maxEvt = Math.max(...months.map(m=>DATA.monthly[m].events));

months.forEach((m,i)=>{{
  const attVal = DATA.monthly[m].attendees;
  const evtVal = DATA.monthly[m].events;
  const label  = m.replace(' 20'," '");
  const recent = i >= nMonths - 4;

  // Attendees bar
  const ar = document.createElement('div');
  ar.className='bar-row';
  ar.innerHTML=`<div class="bar-label">${{label}}</div>
    <div class="bar-track"><div class="bar-fill" style="width:0%;background:${{recent?'#1D9E75':'#B0DDD1'}}" data-w="${{(attVal/maxAtt*100).toFixed(1)}}"></div></div>
    <div class="bar-val">${{attVal.toLocaleString()}}</div>`;
  ar.addEventListener('mouseenter',e=>tip(e,`<strong>${{m}}</strong><br>${{attVal.toLocaleString()}} attendees`));
  ar.addEventListener('mousemove',move); ar.addEventListener('mouseleave',hide);
  document.getElementById('att-bars').appendChild(ar);

  // Events bar
  const er = document.createElement('div');
  er.className='bar-row';
  er.innerHTML=`<div class="bar-label">${{label}}</div>
    <div class="bar-track"><div class="bar-fill" style="width:0%;background:#534AB7;opacity:${{recent?1:0.5}}" data-w="${{(evtVal/maxEvt*100).toFixed(1)}}"></div></div>
    <div class="bar-val">${{evtVal}} evt${{evtVal!==1?'s':''}}</div>`;
  er.addEventListener('mouseenter',e=>tip(e,`<strong>${{m}}</strong><br>${{evtVal}} event${{evtVal!==1?'s':''}}`));
  er.addEventListener('mousemove',move); er.addEventListener('mouseleave',hide);
  document.getElementById('evt-bars').appendChild(er);
}});

setTimeout(()=>document.querySelectorAll('.bar-fill').forEach(el=>el.style.width=el.dataset.w+'%'),300);

// ── ACTIVITIES (fully dynamic from DATA) ──
Object.entries(DATA.activities).forEach(([name,count],i)=>{{
  const d=document.createElement('div');
  d.className='activity-item';
  d.innerHTML=`<div class="act-dot" style="background:${{COLORS[i%COLORS.length]}}">${{count}}</div>
    <div><div class="act-name">${{name}}</div><div class="act-count">${{count}} event${{count!==1?'s':''}}</div></div>`;
  document.getElementById('act-grid').appendChild(d);
}});

// ── VOLUNTEERS (fully dynamic from DATA) ──
const leadEntries = Object.entries(DATA.leads);
const maxL = leadEntries[0][1];
leadEntries.forEach(([name,count])=>{{
  const r=document.createElement('div');
  r.className='vol-row';
  r.innerHTML=`<div class="vol-name" title="${{name}}">${{name}}</div>
    <div class="vol-track"><div class="vol-fill" style="width:0%" data-w="${{(count/maxL*100).toFixed(1)}}"></div></div>
    <div class="vol-count">${{count}}</div>`;
  r.addEventListener('mouseenter',e=>tip(e,`<strong>${{name}}</strong><br>${{count}} events led`));
  r.addEventListener('mousemove',move); r.addEventListener('mouseleave',hide);
  document.getElementById('vol-list').appendChild(r);
}});
setTimeout(()=>document.querySelectorAll('.vol-fill').forEach(el=>{{el.style.transition='width 1s ease';el.style.width=el.dataset.w+'%';}}),400);
</script>
</body>
</html>"""


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    csv_path    = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else 'NeuroEngage_Dashboard.html'

    if not os.path.exists(csv_path):
        print(f"Error: file not found: {csv_path}")
        sys.exit(1)

    print(f"Reading: {csv_path}")
    events = parse_csv(csv_path)
    print(f"Parsed {len(events)} events")

    agg = aggregate(events)
    s   = agg['stats']
    print(f"  {s['total_events']} events | {s['total_attendees']:,} attendees | "
          f"{s['total_hours']}h | {s['unique_leads']} leads")
    print(f"  {s['num_months']} months | avg {s['avg_attendees']} att/mo | avg {s['avg_events']} evt/mo")
    print(f"  Activities found: {list(agg['activities'].keys())}")

    html = generate_html(events, agg, csv_path)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\nSaved: {output_path}")

if __name__ == '__main__':
    main()
