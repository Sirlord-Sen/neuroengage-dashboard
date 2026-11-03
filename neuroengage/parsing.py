"""
Robust parsers for the free-text fields in the NeuroEngage outreach Form export.

Every parser in here returns a value *and* a note explaining how an ambiguous
entry was read. Nothing guesses silently: if a value can't be understood it
comes back as None and is reported, never quietly coerced to zero.
"""

import re
import unicodedata
from difflib import SequenceMatcher

# ── HEADER MATCHING ──────────────────────────────────────────────────────────
# Microsoft Forms rewords its questions between exports (that is what broke the
# previous version: "Length of Time (e.g., hours...)" became "Length of Time in
# hours (e.g., 2.5 hours...)" and every event silently scored 0 hours).
# So columns are matched on a normalised prefix, not an exact string.

#: field name -> prefixes that identify its column, in priority order
COLUMN_PREFIXES = {
    'id':         ['id'],
    'date':       ['event date'],
    'venue':      ['school organization or event name', 'school organization'],
    'zip':        ['zip code'],
    'lead':       ['lead volunteer'],
    'volunteers': ['additional volunteers'],
    'activities': ['activities'],
    'hours':      ['length of time', 'duration'],
    'attendees':  ['number of attendees', 'attendees'],
    'notes':      ['additional notes', 'notes'],
}

REQUIRED_FIELDS = ('id', 'date', 'venue', 'lead', 'activities', 'hours', 'attendees')


def normalize_header(raw):
    """Fold a Forms column header down to comparable words.

    Handles the junk Forms embeds in headers: embedded newlines, U+FFFD
    replacement chars, and non-breaking spaces.
    """
    text = unicodedata.normalize('NFKD', raw or '')
    text = text.replace('�', ' ').replace('\xa0', ' ')
    text = re.sub(r'[^0-9A-Za-z]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip().lower()


def resolve_columns(headers):
    """Map logical field names onto the actual header strings in this file.

    Raises ValueError listing what was found if a required column is missing,
    rather than letting the field silently read as empty.
    """
    normalized = {h: normalize_header(h) for h in headers if h and normalize_header(h)}
    resolved, used = {}, set()

    for field, prefixes in COLUMN_PREFIXES.items():
        for prefix in prefixes:
            match = next(
                (h for h, n in normalized.items() if n.startswith(prefix) and h not in used),
                None,
            )
            if match:
                resolved[field] = match
                used.add(match)
                break

    missing = [f for f in REQUIRED_FIELDS if f not in resolved]
    if missing:
        raise ValueError(
            "Could not find required column(s) {} in this export.\n"
            "Headers present:\n  {}\n"
            "If the Form question was reworded, add its new prefix to "
            "COLUMN_PREFIXES in neuroengage/parsing.py.".format(
                ', '.join(missing), '\n  '.join(repr(h) for h in headers)
            )
        )
    return resolved


# ── HOURS ────────────────────────────────────────────────────────────────────

_MERIDIEM_RANGE = re.compile(
    r'(?P<h1>\d{1,2})(?::(?P<m1>\d{2}))?\s*(?P<ap1>[ap])\.?m\.?'
    r'.*?(?:-|–|—|to|until|till|through)?\s*'
    r'(?P<h2>\d{1,2})(?::(?P<m2>\d{2}))?\s*(?P<ap2>[ap])\.?m\.?',
    re.I,
)
_PLAIN_RANGE = re.compile(
    r'(?P<h1>\d{1,2})(?::(?P<m1>\d{2}))?\s*(?:-|–|—|to|until)\s*'
    r'(?P<h2>\d{1,2})(?::(?P<m2>\d{2}))?',
    re.I,
)
_HRS_AND_MINS = re.compile(
    r'(?P<h>\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b[\s,]*'
    r'(?:(?P<m>\d+)\s*(?:m|min|mins|minutes?)\b)?',
    re.I,
)
_MINS_ONLY = re.compile(r'^(?P<m>\d+)\s*(?:m|min|mins|minutes?)\b', re.I)
_BARE_NUMBER = re.compile(r'^(?P<h>\d+(?:\.\d+)?)\s*$')


def _to_24h(hour, meridiem):
    hour = int(hour) % 12
    return hour + 12 if meridiem.lower() == 'p' else hour


def parse_hours(raw):
    """Read an event duration out of free text.

    Returns (hours, note). ``hours`` is None when nothing numeric is present.
    Understands:
        '2.5', '3 hours', '1 hr'      -> plain durations
        '4 hrs 45 min'                -> 4.75  (minutes are no longer dropped)
        '8am set up to 1pm clean up'  -> 5.0   (clock range, not "8 hours")
        '8:00 AM- 4:30 PM'            -> 8.5
    """
    text = (raw or '').strip()
    if not text:
        return None, None

    # A clock range with am/pm is checked first. The old parser matched a bare
    # leading digit before ever reaching this case, turning "8am ... to 1pm"
    # into 8 hours instead of 5.
    m = _MERIDIEM_RANGE.search(text)
    if m:
        start = _to_24h(m.group('h1'), m.group('ap1')) + int(m.group('m1') or 0) / 60
        end = _to_24h(m.group('h2'), m.group('ap2')) + int(m.group('m2') or 0) / 60
        if end <= start:
            end += 12
        return round(end - start, 2), f'read "{text}" as a {round(end - start, 2)}h clock range'

    m = _HRS_AND_MINS.search(text)
    if m and (m.group('m') or not _PLAIN_RANGE.match(text)):
        hours = float(m.group('h')) + int(m.group('m') or 0) / 60
        note = None
        if m.group('m'):
            note = f'read "{text}" as {round(hours, 2)}h (minutes included)'
        return round(hours, 2), note

    m = _PLAIN_RANGE.match(text)
    if m:
        start = int(m.group('h1')) + int(m.group('m1') or 0) / 60
        end = int(m.group('h2')) + int(m.group('m2') or 0) / 60
        if end <= start:
            end += 12
        return round(end - start, 2), f'read "{text}" as a {round(end - start, 2)}h range'

    m = _MINS_ONLY.match(text)
    if m:
        hours = round(int(m.group('m')) / 60, 2)
        return hours, f'read "{text}" as {hours}h'

    m = _BARE_NUMBER.match(text)
    if m:
        return float(m.group('h')), None

    m = re.match(r'^(\d+(?:\.\d+)?)', text)
    if m:
        return float(m.group(1)), f'read "{text}" as {m.group(1)}h — leading number only'

    return None, f'could not read a duration from "{text}"'


# ── ATTENDEES ────────────────────────────────────────────────────────────────

_APPROX_MARKERS = re.compile(r'~|\bapprox\w*\b|\babout\b|\best\w*\b|\+', re.I)
_RANGE_TOKEN = re.compile(r'(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)')
_FIRST_NUMBER = re.compile(r'\d+(?:\.\d+)?')


def parse_attendees(raw):
    """Read a headcount out of free text.

    Returns (count, is_approximate, note). ``count`` is None when no number is
    present at all.

    The old parser stripped every non-digit and concatenated what was left, so
    '50 7th graders' became 507 and '71 for TaB in expo hall; 22 for BaN in
    classrooms' became 7,122. This one takes the *first* number in each
    clause and sums the clauses:
        '50 7th graders'          -> 50
        '71 for TaB; 22 for BaN'  -> 93
        '~70-80'                  -> 75, approximate
    """
    text = (raw or '').strip()
    if not text:
        return None, False, None

    approx = bool(_APPROX_MARKERS.search(text))
    # Strip thousands separators so '1,200' stays one number before clause splitting.
    text_clean = re.sub(r'(?<=\d),(?=\d{3}\b)', '', text)
    clauses = [c for c in re.split(r';|\band\b|\bplus\b', text_clean, flags=re.I) if c.strip()]

    total, parts = 0, []
    for clause in clauses:
        rng = _RANGE_TOKEN.search(clause)
        if rng:
            low, high = float(rng.group(1)), float(rng.group(2))
            if high >= low:
                value = (low + high) / 2
                approx = True
                parts.append(f'{rng.group(0)} -> {value:g} (midpoint)')
                total += value
                continue
        num = _FIRST_NUMBER.search(clause)
        if num:
            value = float(num.group(0))
            parts.append(f'{value:g}')
            total += value

    if not parts:
        return None, False, f'could not read a headcount from "{text}"'

    count = int(round(total))
    note = None
    if len(parts) > 1:
        note = f'read "{text}" as {" + ".join(parts)} = {count}'
    elif parts[0] != str(count):
        note = f'read "{text}" as {count}'
    elif approx:
        note = f'"{text}" recorded as an estimate'
    return count, approx, note


# ── PEOPLE ───────────────────────────────────────────────────────────────────

_NON_NAMES = {'', 'n/a', 'na', 'none', 'nobody', 'no one', 'tbd', 'self', 'me'}
#: Entries that name a group or stand in for un-named people. Counting these as
#: individuals would inflate the volunteer roster with things that aren't people.
_NON_PERSON = re.compile(
    r'^(?:one|two|three|four|several|a few|some|many)?\s*(?:more|others?|etc\.?)$'
    r'|\blab members?\b|\bmembers?\b|\bstudents?\b|\bvolunteers?\b|\bteam\b|\bstaff\b'
    r'|\bothers\b|\bfamily\b|\bgroup\b',
    re.I,
)
_QUOTED_WITH_EMAIL = re.compile(r'"([^"]+)"\s*<[^>]*>')
_BARE_WITH_EMAIL = re.compile(r'([A-Za-z][A-Za-z.\'\-]*(?:\s+[A-Za-z][A-Za-z.\'\-]*){0,3})\s*<[^>]*>')
_PERSON_SPLIT = re.compile(r'\s*(?:;|,|&|\+|\band\b|\bwith\b)\s*', re.I)


def _looks_like_person(text):
    """Reject counts, addresses, group labels and placeholders."""
    if not text or text.lower() in _NON_NAMES:
        return False
    if re.search(r'\d|@|<|>|/', text):
        return False
    if not re.search(r'[A-Za-z]', text):
        return False
    if _NON_PERSON.search(text):
        return False
    return len(text) <= 60


def split_people(raw):
    """Split a volunteer cell into individual human names.

    'David Waxler & Meghan Vogt'        -> ['David Waxler', 'Meghan Vogt']
    'Corey, Kyle, Maria, and David'     -> ['Corey', 'Kyle', 'Maria', 'David']
    '"Lucy Kim" <NaKim0710@gmail.com>'  -> ['Lucy Kim']
    'N/A'                               -> []
    """
    text = (raw or '').strip()
    if not text or text.lower() in _NON_NAMES:
        return []

    names, remainder = [], text
    for pattern in (_QUOTED_WITH_EMAIL, _BARE_WITH_EMAIL):
        found = pattern.findall(remainder)
        if found:
            # The "quoted" part is sometimes just the address again
            # ("Jennalyn.burnette@gmail.com" <Jennalyn.burnette@gmail.com>),
            # so these go through the same sanity check as everything else.
            names.extend(n.strip() for n in found if _looks_like_person(n.strip()))
            remainder = pattern.sub(' ', remainder)

    for chunk in _PERSON_SPLIT.split(remainder):
        # Trim trailing parentheticals like "(no show)".
        chunk = re.sub(r'\s*\([^)]*\)\s*$', '', chunk.strip(' .')).strip()
        if _looks_like_person(chunk):
            names.append(chunk)

    seen, unique = set(), []
    for name in names:
        key = normalize_person(name)
        if key and key not in seen:
            seen.add(key)
            unique.append(name)
    return unique


def normalize_person(name):
    """Casefold a name for comparison: 'McKenzie  Whitaker' -> 'mckenzie whitaker'."""
    text = unicodedata.normalize('NFKD', name or '')
    text = re.sub(r"[^A-Za-z'\-\s]", ' ', text)
    return re.sub(r'\s+', ' ', text).strip().lower()


class NameResolver:
    """Collapses spelling variants of the same person onto one canonical name.

    Built from every name that appears anywhere in the data (leads and
    additional volunteers), so bare first names can be expanded against a real
    roster. Two variants merge only when they share a first or last name AND
    are highly similar, which merges 'Ethan Levine'/'Ethan Lavine' and
    'Kelli Grove'/'Kelly Grove' while keeping 'Aliyah Taylor' and
    'Aaliyah Murray' apart.
    """

    SIMILARITY = 0.88

    def __init__(self, name_lists, aliases=None):
        from collections import Counter

        counts = Counter()
        surfaces = {}
        for names in name_lists:
            for name in names:
                key = normalize_person(name)
                if not key:
                    continue
                counts[key] += 1
                surfaces.setdefault(key, Counter())[name.strip()] += 1

        self._counts = counts
        self._surfaces = surfaces
        #: variant pairs whose spellings were equally common — the winner was a
        #: tie-break, so a human may want to pin it in NAME_ALIASES.
        self.ties = []

        # Anchor on multi-word names, most frequent spelling first, so the
        # canonical form is deterministic and is the one people actually use.
        full = sorted(
            (k for k in counts if len(k.split()) > 1),
            key=lambda k: (-counts[k], k),
        )
        canonical, mapping = [], {}
        for key in full:
            match = self._closest(key, canonical)
            if match:
                mapping[key] = match
                if counts[key] == counts[match]:
                    self.ties.append((self._surface(key), self._surface(match)))
            else:
                canonical.append(key)
                mapping[key] = key

        # Expand single-word names against the roster when unambiguous.
        by_first = {}
        for key in canonical:
            by_first.setdefault(key.split()[0], []).append(key)
        for key in (k for k in counts if len(k.split()) == 1):
            options = by_first.get(key, [])
            if len(options) == 1:
                mapping[key] = options[0]
            else:
                mapping.setdefault(key, key)

        self._mapping = mapping
        self._canonical = canonical
        self._by_first = by_first
        # Manual overrides win over the automatic clustering, in either
        # direction: they redirect both the variant and whatever canonical form
        # the clustering happened to pick.
        self._forced = {
            normalize_person(wrong): normalize_person(right)
            for wrong, right in (aliases or {}).items()
        }

    @property
    def merges(self):
        """Every spelling that resolves to a different canonical name."""
        out = []
        for key in sorted(self._counts):
            surface = self._surface(key)
            canonical = self.resolve(surface)
            if canonical != surface:
                out.append((surface, canonical))
        return out

    def _closest(self, key, canonical):
        first, last = key.split()[0], key.split()[-1]
        best, best_score = None, 0.0
        for other in canonical:
            parts = other.split()
            if first != parts[0] and last != parts[-1]:
                continue
            score = SequenceMatcher(None, key, other).ratio()
            if score >= self.SIMILARITY and score > best_score:
                best, best_score = other, score
        return best

    def _surface(self, key):
        """The most common original spelling of a normalised name."""
        if key in self._surfaces:
            return self._surfaces[key].most_common(1)[0][0]
        return key.title()

    def resolve(self, name):
        key = normalize_person(name)
        key = self._forced.get(key, key)
        if key in self._mapping:
            key = self._mapping[key]
        else:
            key = self._match_unseen(key)
        return self._surface(self._forced.get(key, key))

    def _match_unseen(self, key):
        """Resolve a name that wasn't in the data the roster was built from."""
        if not key:
            return key
        parts = key.split()
        if len(parts) == 1:
            options = self._by_first.get(key, [])
            return options[0] if len(options) == 1 else key
        return self._closest(key, self._canonical) or key

    def resolve_all(self, names):
        out, seen = [], set()
        for name in names:
            canonical = self.resolve(name)
            if canonical not in seen:
                seen.add(canonical)
                out.append(canonical)
        return out


# ── ACTIVITIES ───────────────────────────────────────────────────────────────

def normalize_activity(raw):
    text = re.sub(r'[^0-9A-Za-z]+', ' ', raw or '')
    return re.sub(r'\s+', ' ', text).strip().lower()


#: normalised free text -> the activity/activities it actually represents.
#: One entry can expand to several when a volunteer typed multiple stations
#: into a single box.
ACTIVITY_ALIASES = {
    'cogntivie testing': ['Cognitive Testing'],
    'cognitive testing': ['Cognitive Testing'],
    'gsr': ['Galvanic Skin Response (GSR)'],
    'galvanic skin response gsr': ['Galvanic Skin Response (GSR)'],
    'stress in the brain 3 stations network maturation dendrite plasticity and stress reduction techniques':
        ['Stress in the Brain (3 stations)'],
    'stress in the brain 3 stations brain network maturation dendritic plasticity stress reduction techniques with biofeedback':
        ['Stress in the Brain (3 stations)'],
    'stress stations gsr dendritic spines brain networks':
        ['Stress in the Brain (3 stations)'],
    'blood pressure testing lead by nursing students gsr stress test lead by jennalyn':
        ['Blood Pressure Testing', 'Galvanic Skin Response (GSR)'],
    'two emotions stations': ['Emotions Stations'],
    'grad student panel discussion': ['Grad Student Panel'],
    'plasticized brain': ['Plasticized Brain'],
}


def parse_activities(raw):
    """Split the activities checkbox field and fold synonyms together.

    Returns (activities, notes). Unknown entries are kept verbatim rather than
    invented into something else.
    """
    out, notes, seen = [], [], set()
    for chunk in (raw or '').split(';'):
        chunk = chunk.strip().strip('.,')
        if not chunk:
            continue
        key = normalize_activity(chunk)
        mapped = ACTIVITY_ALIASES.get(key, [chunk])
        if key in ACTIVITY_ALIASES and mapped != [chunk]:
            notes.append((chunk, mapped))
        for activity in mapped:
            if activity not in seen:
                seen.add(activity)
                out.append(activity)
    return out, notes
