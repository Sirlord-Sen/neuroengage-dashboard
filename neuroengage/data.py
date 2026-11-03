"""
Loading, merging and aggregating the NeuroEngage outreach exports.

Multiple Form exports are merged rather than replaced. Microsoft Forms lets
responses be edited after the fact, and later exports have been observed
*losing* data that an earlier one had (an event's duration, a batch of notes).
So each row is keyed by its Form response Id, and for every field the newest
export that actually has a value wins. Nothing that was ever recorded is lost.
"""

import csv
import os
import re
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime

from .parsing import (
    NameResolver,
    parse_activities,
    parse_attendees,
    parse_hours,
    resolve_columns,
    split_people,
)

DATE_FORMATS = ('%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d', '%d/%m/%Y')

#: Manual name corrections, applied on top of the automatic resolver.
#: Add an entry only when there is evidence for the correct spelling, and say
#: what that evidence is — the resolver reports every tie it had to break.
NAME_ALIASES = {
    # Both spellings appear once each, so frequency can't decide. The address
    # recorded for this volunteer is jennalyn.burnette@gmail.com.
    'Jennalyn Burnett': 'Jennalyn Burnette',
    # Confirmed the same person (Aug 2026): "Varshi" is a short form of
    # Amirthavarshani. Too dissimilar for the automatic resolver to merge.
    'Varshi Mahadevan': 'Amirthavarshani Mahadevan',
}


class Note:
    """One recorded interpretation, so every judgement call stays auditable."""

    def __init__(self, category, event, detail, public_detail=None):
        self.category = category
        self.event = event
        self.detail = detail
        # What the published page shows. The repo and site are public, so
        # free-text values (notes naming volunteers, emails) stay terminal-only.
        self.public_detail = detail if public_detail is None else public_detail

    def __repr__(self):
        return f'<{self.category}: {self.event} — {self.detail}>'


def parse_date(raw):
    text = (raw or '').strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def read_export(path):
    """Read one CSV into {response_id: {field: value}} using resolved columns."""
    with open(path, encoding='utf-8-sig', errors='replace', newline='') as handle:
        reader = csv.DictReader(handle)
        columns = resolve_columns(reader.fieldnames or [])
        rows = OrderedDict()
        for raw_row in reader:
            row = {
                field: (raw_row.get(header) or '').strip()
                for field, header in columns.items()
            }
            if not any(row.values()):
                continue  # trailing blank line
            key = row.get('id') or f"{row.get('date')}|{row.get('venue')}"
            rows[key] = row
    return rows


def merge_exports(paths):
    """Merge exports oldest-first; per field, the newest non-empty value wins."""
    merged, provenance, carried = OrderedDict(), {}, []

    for path in paths:
        label = os.path.basename(path)
        for key, row in read_export(path).items():
            target = merged.setdefault(key, {})
            source = provenance.setdefault(key, {})
            for field, value in row.items():
                if value:
                    target[field] = value
                    source[field] = label
                elif field in target and target[field]:
                    # Newer export dropped a value the older one had — keep it.
                    carried.append((key, field, target[field], source[field], label))
                else:
                    target.setdefault(field, '')

    return merged, provenance, carried


def build_events(paths):
    """Merge the exports and turn each row into a clean event record."""
    merged, provenance, carried = merge_exports(paths)
    notes, warnings = [], []

    for key, field, value, kept_from, dropped_by in carried:
        if field in ('id', 'zip'):
            continue
        row = merged[key]
        notes.append(Note(
            'carried',
            f"{row.get('date', '?')} {row.get('venue', '?')}",
            f'{field}: kept "{value}" from {kept_from} — {dropped_by} left it blank',
            f'{field}: kept the value from {kept_from} — {dropped_by} left it blank',
        ))

    # Roster is built from every name in the data so bare first names
    # ("Corey, Kyle, Maria, and David") can be expanded against real people.
    name_lists = []
    for row in merged.values():
        name_lists.append(split_people(row.get('lead', '')))
        name_lists.append(split_people(row.get('volunteers', '')))
    resolver = NameResolver(name_lists, NAME_ALIASES)

    events = []
    for key, row in merged.items():
        date = parse_date(row.get('date'))
        if date is None:
            if row.get('venue') or row.get('lead'):
                warnings.append(f"skipped response {key}: unreadable date {row.get('date')!r}")
            continue

        label = f"{date.strftime('%b')} {date.day}, {date.strftime('%Y')} · {row.get('venue', '')}"

        attendees, approx, att_note = parse_attendees(row.get('attendees'))
        if att_note:
            notes.append(Note('attendees', label, att_note))
        if attendees is None:
            warnings.append(f'{label}: no attendee count recorded')

        hours, hr_note = parse_hours(row.get('hours'))
        if hr_note:
            notes.append(Note('hours', label, hr_note))
        if hours is None:
            warnings.append(f'{label}: no duration recorded')

        activities, act_notes = parse_activities(row.get('activities'))
        for original, mapped in act_notes:
            notes.append(Note('activity', label, f'"{original}" counted as {" + ".join(mapped)}'))

        leads = resolver.resolve_all(split_people(row.get('lead', '')))
        helpers = resolver.resolve_all(split_people(row.get('volunteers', '')))
        if len(leads) > 1:
            notes.append(Note('leads', label, f'co-led by {len(leads)}: {", ".join(leads)}'))

        events.append({
            'id':         row.get('id', ''),
            'date':       f"{date.strftime('%b')} {date.day}, {date.strftime('%Y')}",
            'date_sort':  date.strftime('%Y-%m-%d'),
            'month':      f"{date.strftime('%b')} {date.strftime('%Y')}",
            'month_sort': date.strftime('%Y-%m'),
            'venue':      row.get('venue', ''),
            'zip':        row.get('zip', ''),
            'leads':      leads,
            'volunteers': helpers,
            'attendees':  attendees,
            'approx':     approx,
            'hours':      hours,
            'activities': activities,
            'notes':      row.get('notes', ''),
        })

    events.sort(key=lambda e: (e['date_sort'], e['venue']))

    for wrong, right in resolver.merges:
        notes.append(Note('name', '', f'"{wrong}" counted as {right}'))

    for variant, chosen in resolver.ties:
        if resolver.resolve(variant) == resolver.resolve(chosen):
            warnings.append(
                f'name spelling tie: "{variant}" and "{chosen}" are equally common; '
                f'using "{resolver.resolve(chosen)}" — pin it in NAME_ALIASES if that is wrong'
            )

    return events, notes, warnings, provenance


def month_range(first, last):
    """Every YYYY-MM from first to last inclusive, including empty ones."""
    year, month = int(first[:4]), int(first[5:7])
    end_year, end_month = int(last[:4]), int(last[5:7])
    out = []
    while (year, month) <= (end_year, end_month):
        out.append(f'{year:04d}-{month:02d}')
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def aggregate(events):
    """Roll events up by month, activity and lead volunteer.

    The monthly series spans every calendar month between the first and last
    event, including months with no activity, so the chart and the per-month
    averages describe the real period rather than only the months that happen
    to have data.
    """
    monthly = OrderedDict()
    if events:
        for key in month_range(events[0]['month_sort'], events[-1]['month_sort']):
            stamp = datetime.strptime(key, '%Y-%m')
            label = f"{stamp.strftime('%b')} {stamp.strftime('%Y')}"
            monthly[label] = {'events': 0, 'attendees': 0, 'hours': 0.0, 'empty': True}

    for event in events:
        bucket = monthly[event['month']]
        bucket['events'] += 1
        bucket['attendees'] += event['attendees'] or 0
        bucket['hours'] += event['hours'] or 0.0
        bucket['empty'] = False
    for bucket in monthly.values():
        bucket['hours'] = round(bucket['hours'], 2)

    activities = Counter()
    for event in events:
        activities.update(event['activities'])

    # Every lead of a co-led event gets credit, so counts describe people.
    leads = Counter()
    for event in events:
        leads.update(event['leads'])

    volunteers = set()
    for event in events:
        volunteers.update(event['leads'])
        volunteers.update(event['volunteers'])

    span = len(monthly) or 1
    total_attendees = sum(e['attendees'] or 0 for e in events)
    total_hours = round(sum(e['hours'] or 0.0 for e in events), 2)

    return {
        'monthly': monthly,
        'activities': dict(activities.most_common()),
        'leads': dict(leads.most_common()),
        'stats': {
            'total_events':      len(events),
            'total_attendees':   total_attendees,
            'total_hours':       total_hours,
            'unique_leads':      len(leads),
            'unique_volunteers': len(volunteers),
            'num_months':        span,
            'months_with_data':  sum(1 for m in monthly.values() if not m['empty']),
            'avg_attendees':     round(total_attendees / span),
            'avg_events':        round(len(events) / span, 1),
            'missing_hours':     sum(1 for e in events if e['hours'] is None),
            'missing_attendees': sum(1 for e in events if e['attendees'] is None),
            'estimated_counts':  sum(1 for e in events if e['approx']),
        },
    }
