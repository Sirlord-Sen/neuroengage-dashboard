"""
Tests for the cumulative progress report.

The synthetic cases pin the windowing, cumulative math and term logic; the
integration case pins the report against the real exports so the report can
never silently drift from the dashboard's numbers.

    python3 -m unittest discover tests
"""

import glob
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neuroengage.report import (  # noqa: E402
    build_report_data,
    fmt_num,
    nice_ticks,
    term_of,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def event(month, attendees=10, hours=2.0, leads=None, volunteers=None,
          approx=False, activities=None, venue='Test School'):
    return {
        'month_sort': month,
        'attendees': attendees,
        'hours': hours,
        'approx': approx,
        'leads': leads or ['Lead One'],
        'volunteers': volunteers or [],
        'activities': activities or [],
        'venue': venue,
    }


class TestTerms(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(term_of('2025-08')[0], 'Fall 2025')
        self.assertEqual(term_of('2025-12')[0], 'Fall 2025')
        self.assertEqual(term_of('2026-01')[0], 'Spring 2026')
        self.assertEqual(term_of('2026-04')[0], 'Spring 2026')
        self.assertEqual(term_of('2026-05')[0], 'Summer 2026')
        self.assertEqual(term_of('2026-07')[0], 'Summer 2026')
        self.assertEqual(term_of('2026-08')[0], 'Fall 2026')

    def test_terms_sort_chronologically(self):
        keys = [term_of(m)[1] for m in ('2025-08', '2026-01', '2026-05', '2026-08')]
        self.assertEqual(keys, sorted(keys))


class TestWindowing(unittest.TestCase):
    def test_events_before_the_window_are_excluded_and_reported(self):
        events = [event('2025-06', attendees=104, hours=9), event('2025-09')]
        data = build_report_data(events, since='2025-08')
        self.assertEqual(data['totals']['events'], 1)
        self.assertEqual(data['excluded'], {'events': 1, 'attendees': 104, 'hours': 9})

    def test_window_start_month_is_included(self):
        data = build_report_data([event('2025-08')], since='2025-08')
        self.assertEqual(data['totals']['events'], 1)


class TestCumulativeMath(unittest.TestCase):
    def test_series_accumulates_and_ends_at_the_totals(self):
        events = [
            event('2025-09', attendees=50, hours=2),
            event('2025-09', attendees=30, hours=1.5),
            event('2025-11', attendees=20, hours=3),
        ]
        data = build_report_data(events, since='2025-08')
        cums = [r['cum']['attendees'] for r in data['monthly']]
        self.assertEqual(cums, sorted(cums))          # never decreases
        self.assertEqual(data['monthly'][-1]['cum'], data['totals'])
        self.assertEqual(data['totals']['attendees'], 100)
        self.assertEqual(data['totals']['hours'], 6.5)

    def test_empty_months_hold_the_running_total(self):
        events = [event('2025-09', attendees=40), event('2025-12', attendees=10)]
        data = build_report_data(events, since='2025-09')
        by_month = {r['month']: r for r in data['monthly']}
        self.assertEqual(by_month['2025-10']['events'], 0)
        self.assertEqual(by_month['2025-10']['cum']['attendees'], 40)
        self.assertEqual(by_month['2025-12']['cum']['attendees'], 50)

    def test_missing_values_count_as_nothing_not_something(self):
        events = [event('2025-09', attendees=None, hours=None)]
        data = build_report_data(events, since='2025-08')
        self.assertEqual(data['totals']['attendees'], 0)
        self.assertEqual(data['totals']['hours'], 0)


class TestVolunteerAnalysis(unittest.TestCase):
    EVENTS = [
        event('2025-09', leads=['Ada'], volunteers=['Grace', 'Alan']),
        event('2025-10', leads=['Ada'], volunteers=['Grace']),
        event('2025-11', leads=['Grace'], volunteers=['Katherine']),
    ]

    def test_distinct_volunteers_count_people_once(self):
        data = build_report_data(self.EVENTS, since='2025-08')
        self.assertEqual(data['totals']['volunteers'], 4)   # Ada, Grace, Alan, Katherine

    def test_first_appearance_drives_the_curve(self):
        data = build_report_data(self.EVENTS, since='2025-08')
        by_month = {r['month']: r['new_volunteers'] for r in data['monthly']}
        self.assertEqual(by_month['2025-09'], 3)
        self.assertEqual(by_month['2025-10'], 0)            # both already known
        self.assertEqual(by_month['2025-11'], 1)            # only Katherine is new

    def test_repeat_buckets_partition_the_roster(self):
        data = build_report_data(self.EVENTS, since='2025-08')
        self.assertEqual(sum(data['buckets'].values()), data['totals']['volunteers'])
        self.assertEqual(data['buckets']['3–5 events'], 1)  # Grace served 3
        self.assertEqual(data['buckets']['2 events'], 1)    # Ada served 2
        self.assertEqual(data['buckets']['1 event'], 2)     # Alan, Katherine
        self.assertEqual(data['repeat_count'], 2)

    def test_leads_are_counted_as_people_who_led(self):
        data = build_report_data(self.EVENTS, since='2025-08')
        self.assertEqual(data['lead_count'], 2)             # Ada, Grace


class TestDemandAndPipeline(unittest.TestCase):
    def test_venue_typos_and_grade_parentheticals_fold_together(self):
        events = [
            event('2025-09', venue='Gwinnett Online Campus (8th Grade)'),
            event('2025-10', venue='Gwinnet Online Campus'),
            event('2025-11', venue='Gwinnett Online Campus (K-5)'),
            event('2025-12', venue='Decatur High School'),
        ]
        data = build_report_data(events, since='2025-08')
        self.assertEqual(data['venues'][0][1], 3)           # one campus, three visits
        self.assertEqual(len(data['venues']), 2)
        self.assertEqual(data['repeat_venues'], 1)

    def test_distinct_programs_at_similar_names_stay_separate(self):
        events = [
            event('2025-09', venue='Beacon Hill Middle School'),
            event('2025-10', venue='Beacon Hill Gifted Connections'),
        ]
        data = build_report_data(events, since='2025-08')
        self.assertEqual(len(data['venues']), 2)

    def test_pipeline_splits_new_from_returning(self):
        events = [
            event('2025-09', leads=['Ada'], volunteers=['Grace']),
            event('2025-10', leads=['Ada'], volunteers=['Katherine']),
        ]
        data = build_report_data(events, since='2025-09')
        by_month = {p['month']: p for p in data['pipeline']}
        self.assertEqual((by_month['2025-09']['new'], by_month['2025-09']['returning']), (2, 0))
        self.assertEqual((by_month['2025-10']['new'], by_month['2025-10']['returning']), (1, 1))

    def test_top_events_are_ranked_by_attendance(self):
        events = [
            event('2025-09', attendees=40, venue='Small School'),
            event('2025-10', attendees=600, venue='Big Festival'),
        ]
        data = build_report_data(events, since='2025-08')
        self.assertEqual(data['top_events'][0]['venue'], 'Big Festival')
        self.assertEqual(data['median_size'], 600)
        self.assertEqual(data['big_events'], 1)


class TestProgramHistory(unittest.TestCase):
    def test_history_panel_absent_until_years_are_filled_in(self):
        from neuroengage.report import render_report
        data = build_report_data([event('2025-09')], since='2025-08')
        page = render_report(data, ['x.csv'], history={})
        self.assertNotIn('Program history', page)

    def test_history_panel_appears_with_grant_year_computed_from_data(self):
        from collections import OrderedDict
        from neuroengage.report import render_report
        data = build_report_data([event('2025-09', attendees=500)], since='2025-08')
        page = render_report(
            data, ['x.csv'],
            history=OrderedDict([('2023–24', 900), ('2024–25', 1100)]))
        self.assertIn('Program history', page)
        self.assertIn('2025–26', page)      # grant-year label derived from window
        self.assertIn('>500<', page)        # grant-year value comes from the data

    def test_history_chart_grays_past_and_highlights_current(self):
        from collections import OrderedDict
        from neuroengage.report import history_chart
        svg = history_chart(OrderedDict([('2023–24', 900)]), '2025–26', 3900)
        self.assertEqual(svg.count('#B9B6AB'), 1)   # one gray past year
        self.assertEqual(svg.count('#1D9E75'), 1)   # one teal grant year


class TestChartHelpers(unittest.TestCase):
    def test_nice_ticks_are_clean_and_cover_the_max(self):
        for top in (7, 40, 99, 142.25, 3892):
            ticks = nice_ticks(top)
            self.assertEqual(ticks[0], 0)
            self.assertGreaterEqual(ticks[-1], top)
            self.assertLessEqual(len(ticks), 6)

    def test_fmt_num(self):
        self.assertEqual(fmt_num(3892), '3,892')
        self.assertEqual(fmt_num(142.25), '142.25')
        self.assertEqual(fmt_num(142.0), '142')


class TestAgainstRealExports(unittest.TestCase):
    """The report must equal the dashboard totals minus the pre-window events."""

    @classmethod
    def setUpClass(cls):
        from neuroengage.data import build_events
        paths = sorted(glob.glob(os.path.join(REPO, 'data', '*.csv')))
        if not paths:
            raise unittest.SkipTest('no data exports present')
        cls.events, _, _, _ = build_events(paths)
        cls.data = build_report_data(cls.events, since='2025-08')

    def test_window_plus_excluded_equals_everything(self):
        totals, excl = self.data['totals'], self.data['excluded']
        self.assertEqual(totals['events'] + excl['events'], len(self.events))
        self.assertEqual(
            totals['attendees'] + excl['attendees'],
            sum(e['attendees'] or 0 for e in self.events),
        )
        self.assertAlmostEqual(
            totals['hours'] + excl['hours'],
            sum(e['hours'] or 0 for e in self.events),
            places=2,
        )

    def test_roster_and_buckets_agree(self):
        self.assertEqual(len(self.data['roster']), self.data['totals']['volunteers'])
        self.assertEqual(sum(self.data['buckets'].values()), self.data['totals']['volunteers'])

    def test_term_table_sums_to_the_totals(self):
        terms = self.data['terms']
        self.assertEqual(sum(t['events'] for t in terms.values()), self.data['totals']['events'])
        self.assertEqual(sum(t['new_volunteers'] for t in terms.values()), self.data['totals']['volunteers'])
        last = list(terms.values())[-1]
        self.assertEqual(last['cum'], self.data['totals'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
