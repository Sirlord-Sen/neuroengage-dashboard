"""
Renders the dashboard HTML.

CSS and JS live in plain (non-f) strings so braces need no escaping, and every
value that comes from the spreadsheet is HTML-escaped or JSON-encoded on the
way in — a venue name containing < or " can no longer break the page.
"""

import html
import json
from datetime import datetime

CSS = """
  :root {
    --teal:#1D9E75; --teal-light:#E1F5EE; --teal-dark:#0d6e50;
    --purple:#534AB7; --purple-light:#EEEDFE;
    --amber:#BA7517; --amber-light:#FAEEDA;
    --red:#E24B4A;
    --ink:#1C1B18; --ink-mid:#4A4945; --ink-soft:#888780;
    --paper:#FAF8F3; --paper-2:#F1EFE8; --border:#E0DDD4; --white:#FFFFFF;
  }
  *{margin:0;padding:0;box-sizing:border-box;}
  body{font-family:'Outfit',sans-serif;background:var(--paper);color:var(--ink);}
  .mono{font-family:'DM Mono',monospace;}
  .soft{color:var(--ink-soft);}

  /* HEADER */
  .header{background:var(--ink);padding:2.5rem 3rem 2rem;position:relative;overflow:hidden;}
  .header::before{content:'';position:absolute;top:-60px;right:-60px;width:300px;height:300px;background:radial-gradient(circle,rgba(29,158,117,.25),transparent 70%);border-radius:50%;}
  .header::after{content:'';position:absolute;bottom:-40px;left:200px;width:200px;height:200px;background:radial-gradient(circle,rgba(83,74,183,.2),transparent 70%);border-radius:50%;}
  .header-inner{position:relative;z-index:1;}
  .h-label{font-family:'DM Mono',monospace;font-size:11px;letter-spacing:.15em;color:var(--teal);text-transform:uppercase;margin-bottom:.5rem;}
  .h-title{font-family:'DM Serif Display',serif;font-size:2.4rem;color:#fff;line-height:1.1;margin-bottom:.4rem;}
  .h-sub{font-size:14px;color:#888780;font-weight:300;}
  .h-date{font-family:'DM Mono',monospace;font-size:11px;color:#555;margin-top:1rem;}

  /* STAT BAR */
  .stats-bar{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--border);}
  .stat-card{padding:1.8rem 2rem;border-right:1px solid var(--border);background:var(--white);position:relative;overflow:hidden;transition:background .2s;cursor:default;}
  .stat-card:last-child{border-right:none;}
  .stat-card:hover{background:var(--paper);}
  .stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;}
  .stat-card:nth-child(1)::before{background:var(--teal);}
  .stat-card:nth-child(2)::before{background:var(--purple);}
  .stat-card:nth-child(3)::before{background:var(--amber);}
  .stat-card:nth-child(4)::before{background:var(--red);}
  .stat-label{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-soft);margin-bottom:.6rem;}
  .stat-value{font-family:'DM Serif Display',serif;font-size:2.8rem;color:var(--ink);line-height:1;margin-bottom:.3rem;}
  .stat-sub{font-size:12px;color:var(--ink-soft);font-weight:300;}

  /* GRID */
  .main{padding:2rem 3rem;display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;}
  .card{background:var(--white);border:1px solid var(--border);border-radius:2px;padding:1.5rem;animation:fadeUp .5s ease both;}
  .card.full{grid-column:1/-1;}
  .card-title{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-soft);margin-bottom:1.2rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;}
  .ct-left{display:flex;align-items:center;gap:8px;}
  .dot{width:8px;height:8px;border-radius:50%;display:inline-block;flex-shrink:0;}
  .avg-pill{font-family:'DM Mono',monospace;font-size:10px;padding:3px 8px;border-radius:10px;font-weight:400;white-space:nowrap;}
  .pill-teal{background:var(--teal-light);color:var(--teal-dark);}
  .pill-purple{background:var(--purple-light);color:var(--purple);}

  /* BARS */
  .bar-chart{display:flex;flex-direction:column;gap:10px;}
  .bar-row{display:flex;align-items:center;gap:10px;}
  .bar-row.empty{opacity:.45;}
  .bar-label{font-family:'DM Mono',monospace;font-size:10px;color:var(--ink-mid);width:64px;flex-shrink:0;text-align:right;}
  .bar-track{flex:1;height:22px;background:var(--paper-2);border-radius:2px;overflow:hidden;}
  .bar-fill{height:100%;border-radius:2px;transition:width 1s cubic-bezier(.4,0,.2,1);}
  .bar-val{font-family:'DM Mono',monospace;font-size:10px;color:var(--ink-mid);width:56px;flex-shrink:0;}

  /* ACTIVITIES */
  .activity-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;}
  .activity-item{display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--paper);border-radius:2px;border:1px solid var(--border);}
  .act-dot{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-family:'DM Mono',monospace;font-size:11px;font-weight:500;color:white;flex-shrink:0;}
  .act-name{font-size:12px;font-weight:500;color:var(--ink);line-height:1.2;}
  .act-count{font-family:'DM Mono',monospace;font-size:10px;color:var(--ink-soft);}

  /* VOLUNTEERS */
  .vol-list{display:flex;flex-direction:column;gap:8px;}
  .vol-row{display:flex;align-items:center;gap:10px;}
  .vol-name{font-size:12px;font-weight:500;color:var(--ink);width:140px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
  .vol-track{flex:1;height:16px;background:var(--paper-2);border-radius:2px;overflow:hidden;}
  .vol-fill{height:100%;background:var(--purple);border-radius:2px;transition:width 1s ease;}
  .vol-count{font-family:'DM Mono',monospace;font-size:11px;color:var(--ink-soft);width:24px;text-align:right;}

  /* TABLE */
  .event-table{width:100%;border-collapse:collapse;}
  .event-table th{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-soft);text-align:left;padding:0 10px 10px 0;border-bottom:1px solid var(--border);}
  .event-table td{font-size:12px;color:var(--ink-mid);padding:8px 10px 8px 0;border-bottom:1px solid var(--paper-2);vertical-align:top;}
  .event-table tr:last-child td{border-bottom:none;}
  .venue-cell{color:var(--ink);font-weight:500;max-width:200px;}
  .lead-cell{font-size:11px;}
  .attendee-pill{display:inline-flex;align-items:center;background:var(--teal-light);color:var(--teal-dark);font-family:'DM Mono',monospace;font-size:10px;padding:2px 7px;border-radius:10px;font-weight:500;}
  .attendee-pill.est{background:var(--paper-2);color:var(--ink-mid);}
  .tag{display:inline-block;background:var(--paper-2);color:var(--ink-mid);font-size:10px;padding:2px 6px;border-radius:2px;margin:1px;}
  .missing{color:var(--ink-soft);}

  /* DATA NOTES */
  .notes-card details{font-size:12px;}
  .notes-card summary{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-soft);cursor:pointer;margin-bottom:.8rem;}
  .notes-group{margin-bottom:1rem;}
  .notes-group h4{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-mid);margin-bottom:.4rem;font-weight:500;}
  .notes-group ul{list-style:none;display:flex;flex-direction:column;gap:4px;}
  .notes-group li{font-size:11px;color:var(--ink-mid);line-height:1.45;padding-left:14px;position:relative;}
  .notes-group li::before{content:'';position:absolute;left:0;top:7px;width:4px;height:4px;border-radius:50%;background:var(--border);}
  .notes-group li em{color:var(--ink-soft);font-style:normal;}

  /* TOOLTIP */
  .tooltip{position:fixed;background:var(--ink);color:white;padding:8px 12px;border-radius:4px;font-size:12px;pointer-events:none;opacity:0;transition:opacity .15s;z-index:1000;font-family:'Outfit',sans-serif;max-width:260px;}
  .tooltip.show{opacity:1;}

  /* FOOTER */
  .footer{padding:1.5rem 3rem;border-top:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap;}

  @keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
  .stat-card:nth-child(1){animation:fadeUp .4s ease .00s both;}
  .stat-card:nth-child(2){animation:fadeUp .4s ease .06s both;}
  .stat-card:nth-child(3){animation:fadeUp .4s ease .12s both;}
  .stat-card:nth-child(4){animation:fadeUp .4s ease .18s both;}
  .card:nth-child(1){animation-delay:.05s;}
  .card:nth-child(2){animation-delay:.10s;}
  .card:nth-child(3){animation-delay:.15s;}
  .card:nth-child(4){animation-delay:.20s;}
  .card:nth-child(5){animation-delay:.25s;}

  @media (max-width:900px){
    .header{padding:2rem 1.25rem 1.5rem;}
    .stats-bar{grid-template-columns:repeat(2,1fr);}
    .main{padding:1.25rem;grid-template-columns:1fr;}
    .footer{padding:1.25rem;}
  }
"""

JS = """
const DATA = __DATA__;
const COLORS=['#1D9E75','#534AB7','#BA7517','#E24B4A','#0d6e50','#8B80D4','#D4910F','#2E86AB','#E07A5F'];

const tt=document.getElementById('tt');
const tip=(e,h)=>{tt.innerHTML=h;tt.classList.add('show');move(e);};
const move=(e)=>{tt.style.left=(e.clientX+14)+'px';tt.style.top=(e.clientY-10)+'px';};
const hide=()=>tt.classList.remove('show');
const esc=(s)=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const el=(cls,text)=>{const d=document.createElement('div');d.className=cls;if(text!==undefined)d.textContent=text;return d;};

const STILL = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// The headline figures must end on the true total no matter what happens to the
// animation — an interrupted count-up would otherwise leave a partial number on
// screen looking like the real one.
function counter(node,target,dur=1200){
  const exact=Number(target).toLocaleString(undefined,{maximumFractionDigits:2});
  if(STILL||!window.requestAnimationFrame){node.textContent=exact;return;}
  const isF=!Number.isInteger(target);
  const t0=performance.now();
  let done=false;
  const finish=()=>{if(!done){done=true;node.textContent=exact;}};
  (function step(now){
    const p=Math.min((now-t0)/dur,1),e=1-Math.pow(1-p,3);
    if(p>=1){finish();return;}
    node.textContent=Number(isF?(target*e).toFixed(1):Math.round(target*e)).toLocaleString();
    requestAnimationFrame(step);
  })(t0);
  setTimeout(finish,dur+400);
}

counter(document.getElementById('s-events'),    DATA.stats.total_events);
counter(document.getElementById('s-attendees'), DATA.stats.total_attendees);
counter(document.getElementById('s-hours'),     DATA.stats.total_hours);
counter(document.getElementById('s-leads'),     DATA.stats.unique_leads);

// ── MONTHLY BARS ──
// The series covers every calendar month in the period, including months with
// no events, so the shape of the timeline is honest.
const months = Object.keys(DATA.monthly);
const nMonths = months.length;
const maxAtt = Math.max(1, ...months.map(m=>DATA.monthly[m].attendees));
const maxEvt = Math.max(1, ...months.map(m=>DATA.monthly[m].events));

months.forEach((m,i)=>{
  const bucket = DATA.monthly[m];
  const label  = m.replace(' 20'," '");
  const recent = i >= nMonths - 4;

  const makeRow=(value,width,color,opacity,valueText)=>{
    const row=el('bar-row'+(bucket.empty?' empty':''));
    row.appendChild(el('bar-label',label));
    const track=el('bar-track'), fill=el('bar-fill');
    fill.style.width='0%'; fill.style.background=color;
    if(opacity!==undefined) fill.style.opacity=opacity;
    fill.dataset.w=width;
    track.appendChild(fill); row.appendChild(track);
    row.appendChild(el('bar-val',valueText));
    return row;
  };

  const att=bucket.attendees, evt=bucket.events;
  const attRow=makeRow(att,(att/maxAtt*100).toFixed(1),recent?'#1D9E75':'#B0DDD1',undefined,att.toLocaleString());
  attRow.addEventListener('mouseenter',e=>tip(e,`<strong>${esc(m)}</strong><br>${att.toLocaleString()} attendees`));
  attRow.addEventListener('mousemove',move); attRow.addEventListener('mouseleave',hide);
  document.getElementById('att-bars').appendChild(attRow);

  const evtRow=makeRow(evt,(evt/maxEvt*100).toFixed(1),'#534AB7',recent?1:0.5,`${evt} evt${evt!==1?'s':''}`);
  evtRow.addEventListener('mouseenter',e=>tip(e,`<strong>${esc(m)}</strong><br>${evt} event${evt!==1?'s':''}`));
  evtRow.addEventListener('mousemove',move); evtRow.addEventListener('mouseleave',hide);
  document.getElementById('evt-bars').appendChild(evtRow);
});

const fillBars=(sel)=>document.querySelectorAll(sel).forEach(f=>f.style.width=f.dataset.w+'%');
if(STILL){fillBars('.bar-fill');}else{setTimeout(()=>fillBars('.bar-fill'),300);}

// ── ACTIVITIES ──
Object.entries(DATA.activities).forEach(([name,count],i)=>{
  const item=el('activity-item');
  const dot=el('act-dot',String(count));
  dot.style.background=COLORS[i%COLORS.length];
  const body=el('');
  body.appendChild(el('act-name',name));
  body.appendChild(el('act-count',`${count} event${count!==1?'s':''}`));
  item.appendChild(dot); item.appendChild(body);
  item.title=name;
  document.getElementById('act-grid').appendChild(item);
});

// ── LEAD VOLUNTEERS ──
// Co-led events credit each lead, so a bar is one person, never a joined string.
const leadEntries = Object.entries(DATA.leads);
const maxL = leadEntries.length ? leadEntries[0][1] : 1;
leadEntries.forEach(([name,count])=>{
  const row=el('vol-row');
  const label=el('vol-name',name); label.title=name;
  const track=el('vol-track'), fill=el('vol-fill');
  fill.style.width='0%'; fill.dataset.w=(count/maxL*100).toFixed(1);
  track.appendChild(fill);
  row.appendChild(label); row.appendChild(track); row.appendChild(el('vol-count',String(count)));
  row.addEventListener('mouseenter',e=>tip(e,`<strong>${esc(name)}</strong><br>${count} event${count!==1?'s':''} led`));
  row.addEventListener('mousemove',move); row.addEventListener('mouseleave',hide);
  document.getElementById('vol-list').appendChild(row);
});
if(STILL){fillBars('.vol-fill');}else{setTimeout(()=>fillBars('.vol-fill'),400);}
"""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NeuroEngage Outreach Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Mono:wght@400;500&family=Outfit:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>__CSS__</style>
</head>
<body>

<div class="tooltip" id="tt"></div>

<div class="header">
  <div class="header-inner">
    <div class="h-label">Georgia State University &bull; CBN / TReNDS</div>
    <div class="h-title">NeuroEngage Outreach Dashboard</div>
    <div class="h-sub">Dana NextGen Fellowship &mdash; Outreach Activity Record</div>
    <div class="h-date">Generated __GENERATED__ &bull; Data: __RANGE__ &bull; Source: __SOURCES__</div>
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
    <div class="stat-sub">__ATTENDEE_SUB__</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Event Hours</div>
    <div class="stat-value" id="s-hours">0</div>
    <div class="stat-sub">__HOURS_SUB__</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Lead Volunteers</div>
    <div class="stat-value" id="s-leads">0</div>
    <div class="stat-sub">__LEADS_SUB__</div>
  </div>
</div>

<div class="main">

  <div class="card">
    <div class="card-title">
      <span class="ct-left"><span class="dot" style="background:var(--teal)"></span>Attendees per month</span>
      <span class="avg-pill pill-teal">avg <strong>__AVG_ATT__</strong> / month over __SPAN__</span>
    </div>
    <div class="bar-chart" id="att-bars"></div>
  </div>

  <div class="card">
    <div class="card-title">
      <span class="ct-left"><span class="dot" style="background:var(--purple)"></span>Events per month</span>
      <span class="avg-pill pill-purple">avg <strong>__AVG_EVT__</strong> / month over __SPAN__</span>
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
    <div class="card-title"><span class="ct-left"><span class="dot" style="background:var(--teal)"></span>Full event log (__TOTAL_EVENTS__ events)</span></div>
    <table class="event-table">
      <thead><tr><th>Date</th><th>Venue / Organization</th><th>Lead(s)</th><th>Attendees</th><th>Activities</th><th>Hours</th></tr></thead>
      <tbody>__EVENT_ROWS__</tbody>
    </table>
  </div>

  <div class="card full notes-card">
    <details>
      <summary>How these numbers were read from the form responses (__NOTE_COUNT__ notes)</summary>
      __NOTES__
    </details>
  </div>

</div>

<div class="footer">
  <div class="mono soft" style="font-size:10px;letter-spacing:.08em">NEUROENGAGE &bull; DANA NEXTGEN FELLOWSHIP &bull; GSU</div>
  <div class="mono" style="font-size:10px"><a href="report.html" style="color:var(--teal-dark);text-decoration:none">Progress report &rarr;</a> &nbsp; <a href="map.html" style="color:var(--teal-dark);text-decoration:none">Outreach map &rarr;</a></div>
  <div class="mono soft" style="font-size:10px">__TOTAL_EVENTS__ events &bull; Generated __GENERATED__</div>
</div>

<script>__JS__</script>
</body>
</html>"""

NOTE_HEADINGS = {
    'carried':   'Values kept from an earlier export',
    'attendees': 'Attendance figures read from free text',
    'hours':     'Durations read from free text',
    'name':      'Name spellings treated as the same person',
    'leads':     'Events with more than one lead',
    'activity':  'Activity labels grouped together',
}
NOTE_ORDER = ['attendees', 'hours', 'name', 'leads', 'activity', 'carried']


def _fmt_hours(value):
    if value is None:
        return '<span class="missing">not recorded</span>'
    return f'{value:g}h'


def _fmt_attendees(event):
    if event['attendees'] is None:
        return '<span class="missing">&mdash;</span>'
    prefix = '~' if event['approx'] else ''
    cls = 'attendee-pill est' if event['approx'] else 'attendee-pill'
    return f'<span class="{cls}">{prefix}{event["attendees"]:,}</span>'


def render_notes(notes):
    grouped = {}
    for note in notes:
        grouped.setdefault(note.category, []).append(note)

    blocks = []
    for category in NOTE_ORDER:
        items = grouped.get(category)
        if not items:
            continue
        rows = []
        for note in items:
            event = f'<em>{html.escape(note.event)} &mdash; </em>' if note.event else ''
            rows.append(f'<li>{event}{html.escape(note.public_detail)}</li>')
        blocks.append(
            '<div class="notes-group"><h4>{}</h4><ul>{}</ul></div>'.format(
                html.escape(NOTE_HEADINGS.get(category, category)), ''.join(rows)
            )
        )
    return ''.join(blocks) or '<div class="notes-group"><p>No adjustments were needed.</p></div>'


def render_event_rows(events):
    rows = []
    for event in events:
        tags = ''.join(
            f'<span class="tag" title="{html.escape(a, quote=True)}">{html.escape(a)}</span>'
            for a in event['activities']
        )
        leads = html.escape(', '.join(event['leads'])) or '<span class="missing">&mdash;</span>'
        rows.append(
            '\n      <tr>'
            f'\n        <td class="mono soft" style="white-space:nowrap">{html.escape(event["date"])}</td>'
            f'\n        <td class="venue-cell">{html.escape(event["venue"])}</td>'
            f'\n        <td class="lead-cell">{leads}</td>'
            f'\n        <td>{_fmt_attendees(event)}</td>'
            f'\n        <td>{tags}</td>'
            f'\n        <td class="mono soft">{_fmt_hours(event["hours"])}</td>'
            '\n      </tr>'
        )
    return ''.join(rows)


def render(events, agg, notes, sources):
    stats = agg['stats']
    generated = datetime.now()
    generated_date = f"{generated.strftime('%B')} {generated.day}, {generated.year}"

    if events:
        first = datetime.strptime(events[0]['date_sort'], '%Y-%m-%d')
        last = datetime.strptime(events[-1]['date_sort'], '%Y-%m-%d')
        date_range = f"{first.strftime('%b %Y')} &ndash; {last.strftime('%b %Y')}"
    else:
        date_range = 'No data'

    payload = json.dumps({
        'monthly': agg['monthly'],
        'activities': agg['activities'],
        'leads': agg['leads'],
        'stats': stats,
    }, indent=2)
    # Never let spreadsheet text close the <script> element early.
    payload = payload.replace('</', '<\\/')

    span = f"{stats['num_months']} month{'s' if stats['num_months'] != 1 else ''}"

    attendee_sub = 'students &amp; community members'
    if stats['estimated_counts']:
        attendee_sub += f" &bull; {stats['estimated_counts']} estimated"
    if stats['missing_attendees']:
        attendee_sub += f" &bull; {stats['missing_attendees']} not recorded"

    hours_sub = 'total duration of events run'
    if stats['missing_hours']:
        hours_sub += f" &bull; {stats['missing_hours']} not recorded"

    leads_sub = f"people leading events &bull; {stats['unique_volunteers']} volunteers overall"

    substitutions = {
        '__CSS__': CSS,
        '__JS__': JS.replace('__DATA__', payload),
        '__GENERATED__': html.escape(generated_date),
        '__RANGE__': date_range,
        '__SOURCES__': html.escape(', '.join(sources)),
        '__TOTAL_EVENTS__': f"{stats['total_events']:,}",
        '__AVG_ATT__': f"{stats['avg_attendees']:,}",
        '__AVG_EVT__': f"{stats['avg_events']}",
        '__SPAN__': span,
        '__ATTENDEE_SUB__': attendee_sub,
        '__HOURS_SUB__': hours_sub,
        '__LEADS_SUB__': leads_sub,
        '__EVENT_ROWS__': render_event_rows(events),
        '__NOTES__': render_notes(notes),
        '__NOTE_COUNT__': str(len(notes)),
    }

    page = PAGE
    for placeholder, value in substitutions.items():
        page = page.replace(placeholder, value)
    return page
