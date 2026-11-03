"""
Tests for the free-text parsers.

Every case here is a real entry that a volunteer actually typed into the
outreach form, plus the failure modes of the previous parser.

    python3 -m unittest discover tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neuroengage.parsing import (  # noqa: E402
    NameResolver,
    normalize_header,
    parse_activities,
    parse_attendees,
    parse_hours,
    resolve_columns,
    split_people,
)


class TestHours(unittest.TestCase):
    def check(self, raw, expected):
        self.assertEqual(parse_hours(raw)[0], expected, f'input {raw!r}')

    def test_plain_numbers(self):
        self.check('3', 3.0)
        self.check('2.5', 2.5)
        self.check('1.5', 1.5)

    def test_worded_durations(self):
        self.check('3 hours', 3.0)
        self.check('1 hour', 1.0)
        self.check('1 hr', 1.0)
        self.check('2 hrs', 2.0)
        self.check('4 hrs', 4.0)
        self.check('2.5 hours', 2.5)

    def test_hours_and_minutes_are_not_dropped(self):
        # The old parser returned 4.0 and silently lost the 45 minutes.
        self.check('4 hrs 45 min', 4.75)
        self.check('1 hour 30 minutes', 1.5)

    def test_clock_ranges(self):
        # The old parser matched the leading '8' and returned 8.0 for this.
        self.check('8am set up to 1pm clean up', 5.0)
        self.check('8:00 AM- 4:30 PM', 8.5)
        self.check('9am-12pm', 3.0)
        self.check('10:30am to 1:00pm', 2.5)

    def test_minutes_only(self):
        self.check('45 min', 0.75)

    def test_missing_is_none_not_zero(self):
        # Crucially not 0.0 — a blank must be reported, never counted as zero.
        self.assertEqual(parse_hours('')[0], None)
        self.assertEqual(parse_hours(None)[0], None)
        self.assertEqual(parse_hours('   ')[0], None)

    def test_unreadable_reports_a_note(self):
        value, note = parse_hours('all day')
        self.assertIsNone(value)
        self.assertIn('could not read', note)


class TestAttendees(unittest.TestCase):
    def check(self, raw, expected, approx=None):
        count, is_approx, _ = parse_attendees(raw)
        self.assertEqual(count, expected, f'input {raw!r}')
        if approx is not None:
            self.assertEqual(is_approx, approx, f'input {raw!r}')

    def test_plain(self):
        self.check('40', 40, approx=False)
        self.check('609', 609)
        self.check('1,200', 1200)

    def test_trailing_words_do_not_inflate(self):
        # The old parser stripped non-digits and concatenated: 507 and 256.
        self.check('50 7th graders', 50)
        self.check('25 6th graders', 25)

    def test_multiple_clauses_are_summed(self):
        # The old parser produced 7122 for this.
        self.check('71 for TaB in expo hall; 22 for BaN in classrooms', 93)

    def test_ranges_use_the_midpoint_and_are_flagged(self):
        self.check('~70-80', 75, approx=True)
        self.check('60-150', 105, approx=True)

    def test_approximations_are_flagged(self):
        self.check('~40', 40, approx=True)
        self.check('~80', 80, approx=True)
        self.check('about 30', 30, approx=True)

    def test_missing_is_none_not_zero(self):
        self.assertEqual(parse_attendees('')[0], None)
        self.assertEqual(parse_attendees(None)[0], None)

    def test_unreadable_reports_a_note(self):
        count, _, note = parse_attendees('lots of people')
        self.assertIsNone(count)
        self.assertIn('could not read', note)


class TestSplitPeople(unittest.TestCase):
    def test_single(self):
        self.assertEqual(split_people('David Waxler'), ['David Waxler'])

    def test_ampersand_and_word_and(self):
        self.assertEqual(split_people('David Waxler & Meghan Vogt'), ['David Waxler', 'Meghan Vogt'])
        self.assertEqual(split_people('David Waxler and Meghan Vogt'), ['David Waxler', 'Meghan Vogt'])
        self.assertEqual(split_people('Ethan Levine and Shaina McGrath'), ['Ethan Levine', 'Shaina McGrath'])

    def test_oxford_comma_list(self):
        self.assertEqual(
            split_people('Corey, Kyle, Maria, and David'),
            ['Corey', 'Kyle', 'Maria', 'David'],
        )

    def test_placeholders_are_not_people(self):
        for raw in ('', 'N/A', 'n/a', 'None', 'none'):
            self.assertEqual(split_people(raw), [], f'input {raw!r}')

    def test_group_labels_are_not_people(self):
        self.assertEqual(split_people('Bolton Lab Members'), [])
        self.assertEqual(split_people('One more'), [])
        self.assertEqual(split_people('approximately 70+'), [])

    def test_names_are_extracted_from_email_blobs(self):
        self.assertEqual(
            split_people('"Lucy Kim" <NaKim0710@gmail.com>; "Kiri Allen" <Kallen82@student.gsu.edu>'),
            ['Lucy Kim', 'Kiri Allen'],
        )

    def test_bare_addresses_are_not_names(self):
        self.assertEqual(
            split_people('"Jennalyn.burnette@gmail.com" <Jennalyn.burnette@gmail.com>'),
            [],
        )

    def test_parentheticals_are_trimmed(self):
        self.assertEqual(
            split_people('Corey Walker, Ezichi Emmanuel (no show)'),
            ['Corey Walker', 'Ezichi Emmanuel'],
        )


class TestNameResolver(unittest.TestCase):
    ROSTER = [
        ['Ethan Lavine'], ['Ethan Lavine'], ['Ethan Lavine'], ['Ethan Levine'],
        ['Nadja Brown'], ['Nadja Brown'], ['Nadia Brown'],
        ['Kyle Frantz'], ['Corey Walker'], ['Maria Misiura'], ['David Waxler'],
        ['Aaliyah Murray'], ['Aliyah Taylor'],
        ['Levi Shook'], ['Madison'],
    ]

    def setUp(self):
        self.resolver = NameResolver(self.ROSTER)

    def test_typos_merge_to_the_common_spelling(self):
        self.assertEqual(self.resolver.resolve('Ethan Levine'), 'Ethan Lavine')
        self.assertEqual(self.resolver.resolve('Nadia Brown'), 'Nadja Brown')

    def test_similar_but_distinct_people_stay_separate(self):
        self.assertEqual(self.resolver.resolve('Aaliyah Murray'), 'Aaliyah Murray')
        self.assertEqual(self.resolver.resolve('Aliyah Taylor'), 'Aliyah Taylor')

    def test_bare_first_names_expand_against_the_roster(self):
        self.assertEqual(self.resolver.resolve('Corey'), 'Corey Walker')
        self.assertEqual(self.resolver.resolve('Kyle'), 'Kyle Frantz')
        self.assertEqual(self.resolver.resolve('Maria'), 'Maria Misiura')
        self.assertEqual(self.resolver.resolve('David'), 'David Waxler')

    def test_unknown_single_names_are_left_alone(self):
        self.assertEqual(self.resolver.resolve('Madison'), 'Madison')

    def test_manual_aliases_override_the_automatic_choice(self):
        forced = NameResolver(self.ROSTER, {'Ethan Lavine': 'Ethan Levine'})
        self.assertEqual(forced.resolve('Ethan Lavine'), 'Ethan Levine')
        self.assertEqual(forced.resolve('Ethan Levine'), 'Ethan Levine')

    def test_co_leads_resolve_to_distinct_people(self):
        people = self.resolver.resolve_all(split_people('Corey, Kyle, Maria, and David'))
        self.assertEqual(people, ['Corey Walker', 'Kyle Frantz', 'Maria Misiura', 'David Waxler'])


class TestActivities(unittest.TestCase):
    def test_trailing_semicolons_are_ignored(self):
        self.assertEqual(parse_activities('Touch-a-Brain;')[0], ['Touch-a-Brain'])
        self.assertEqual(parse_activities('Touch-a-Brain')[0], ['Touch-a-Brain'])

    def test_typo_is_corrected(self):
        self.assertEqual(parse_activities('Cogntivie Testing;')[0], ['Cognitive Testing'])

    def test_synonyms_collapse(self):
        self.assertEqual(parse_activities('GSR')[0], ['Galvanic Skin Response (GSR)'])
        self.assertEqual(
            parse_activities('Galvanic Skin Response (GSR)')[0],
            ['Galvanic Skin Response (GSR)'],
        )

    def test_one_entry_can_hold_several_activities(self):
        result, _ = parse_activities(
            'blood pressure testing lead by Nursing students, GSR stress test lead by Jennalyn'
        )
        self.assertEqual(result, ['Blood Pressure Testing', 'Galvanic Skin Response (GSR)'])

    def test_stress_station_wordings_are_one_activity(self):
        a = parse_activities('Stress stations - GSR, dendritic spines, brain networks;')[0]
        b = parse_activities(
            'Stress in the brain - 3 stations - brain network maturation, '
            'dendritic plasticity, stress reduction techniques with biofeedback;'
        )[0]
        self.assertEqual(a, b)

    def test_unknown_activities_are_kept_verbatim(self):
        self.assertEqual(parse_activities('Sheep Brain Dissection;')[0], ['Sheep Brain Dissection'])

    def test_duplicates_within_a_row_collapse(self):
        self.assertEqual(parse_activities('GSR;Galvanic Skin Response (GSR);')[0],
                         ['Galvanic Skin Response (GSR)'])


class TestColumnResolution(unittest.TestCase):
    OLD = ['Id', 'Event Date', 'School, organization, or event name\n', 'Lead volunteer\n',
           'Additional Volunteers', 'Activities (check all that apply)',
           'Length of Time (e.g., hours spent volunteering)�',
           'Number of Attendees', 'Additional Notes', '']
    NEW = ['Id', 'Event Date', 'School, organization, or event name\n',
           'Zip Code for Event Location', 'Lead volunteer\n', 'Additional Volunteers',
           'Activities (check all that apply)',
           'Length of Time in hours (e.g., 2.5 hours spent volunteering)\xa0',
           'Number of Attendees', 'Additional Notes']

    def test_header_normalisation_strips_forms_junk(self):
        self.assertEqual(normalize_header('School, organization, or event name\n'),
                         'school organization or event name')
        self.assertEqual(normalize_header('Length of Time in hours (e.g., 2.5 hours)\xa0'),
                         'length of time in hours e g 2 5 hours')

    def test_both_export_generations_resolve(self):
        # The reworded duration question is why every event scored 0 hours before.
        for headers in (self.OLD, self.NEW):
            resolved = resolve_columns(headers)
            self.assertTrue(resolved['hours'].startswith('Length of Time'))
            self.assertEqual(resolved['attendees'], 'Number of Attendees')
            self.assertEqual(resolved['date'], 'Event Date')

    def test_new_zip_column_does_not_displace_the_lead(self):
        resolved = resolve_columns(self.NEW)
        self.assertEqual(resolved['lead'], 'Lead volunteer\n')
        self.assertEqual(resolved['zip'], 'Zip Code for Event Location')

    def test_a_missing_column_fails_loudly(self):
        headers = [h for h in self.NEW if not h.startswith('Length of Time')]
        with self.assertRaises(ValueError) as caught:
            resolve_columns(headers)
        self.assertIn('hours', str(caught.exception))


if __name__ == '__main__':
    unittest.main(verbosity=2)
