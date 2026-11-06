"""Landscape: history/form merge, academic years, no-overshoot curve, valid SVG."""
import os
import sys
import unittest
import xml.dom.minidom

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from neuroengage.landscape import (  # noqa: E402
    _monotone, academic_year, build_landscape_data, render_landscape_svg,
)


def ev(date, n):
    return {'date_sort': date, 'attendees': n}


class TestLandscape(unittest.TestCase):
    def test_academic_year_starts_in_august(self):
        self.assertEqual(academic_year('2025-07-31'), 2024)
        self.assertEqual(academic_year('2025-08-01'), 2025)

    def test_history_wins_and_form_fills_missing_years(self):
        history = {2024: {'year': 2024, 'people': 1000, 'status': 'actual', 'source': 'DMAP'}}
        events = [ev('2025-06-02', 40), ev('2025-09-01', 100), ev('2026-03-01', 50)]
        rows = build_landscape_data(events, history)
        self.assertEqual([(r['year'], r['people']) for r in rows], [(2024, 1000), (2025, 150)])
        self.assertEqual(rows[1]['status'], 'form')
        self.assertEqual(rows[1]['partial'], 'Mar 2026')  # year still in progress

    def test_curve_never_overshoots(self):
        xs, ys = [0, 10, 20, 30], [100, 100, 20, 20]
        nums = [float(v) for seg in _monotone(xs, ys).split('C')[1:]
                for pair in seg.split() for v in pair.split(',')[1:]]
        self.assertTrue(all(20 - 1e-6 <= y <= 100 + 1e-6 for y in nums))

    def test_svg_valid_and_draft_stamp(self):
        rows = [{'year': 2023, 'people': 500, 'status': 'placeholder', 'source': ''},
                {'year': 2024, 'people': 900, 'status': 'actual', 'source': 'x & y'}]
        ms = [{'date': '2024-01', 'label': 'A & B', 'pos': 2023 + 5 / 12, 'placeholder': False}]
        svg = render_landscape_svg(rows, ms, standalone=True)
        xml.dom.minidom.parseString(svg)
        self.assertIn('DRAFT', svg)
        rows[0]['status'] = 'actual'
        self.assertNotIn('DRAFT', render_landscape_svg(rows, ms, standalone=True))


if __name__ == '__main__':
    unittest.main()
