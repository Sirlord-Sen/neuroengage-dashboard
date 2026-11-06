"""Outreach map: venue matching, site grouping, counties, and valid SVG output."""
import os
import sys
import tempfile
import unittest
import xml.dom.minidom

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from neuroengage.mapping import (  # noqa: E402
    build_map_data, county_of, load_counties, load_venues, match_venue,
    render_map_svg, summarize,
)

VENUES = """venue,label,site,audience,lat,lon,precision,source
Beacon Hill Middle School,Beacon Hill MS,Beacon Hill MS,k12,33.76754,-84.29922,venue,
Beacon Hill Gifted Connections,Beacon Hill MS,Beacon Hill MS,k12,33.76754,-84.29922,venue,
Gwinnett Online Campus,Gwinnett Online Campus,,k12,33.98413,-83.97171,venue,
Atlanta Science Festival Expo,ASF Expo,,public,33.76014,-84.39345,venue,
"National Cathedral School, Washington DC",NCS (DC),,k12,38.93221,-77.07171,venue,
Mystery School,Mystery School,,k12,,,,UNKNOWN
"""


def ev(venue, n, date='2026-01-10'):
    return {'venue': venue, 'attendees': n, 'date': date, 'date_sort': date}


class TestMap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False) as fh:
            fh.write(VENUES)
        cls.venues = load_venues(fh.name)
        os.unlink(fh.name)
        cls.events = [
            ev('Beacon Hill Middle School', 100), ev('Beacon Hill Gifted Connections', 50),
            ev('Gwinnet Online Campus', 40), ev('Gwinnett Online Campus (K-5)', 38),
            ev('Atlanta Science Festival Expo', 609),
            ev('National Cathedral School, Washington DC', 30),
            ev('Mystery School', 12), ev('Somewhere New', 7),
        ]
        cls.data = build_map_data(cls.events, cls.venues)

    def site(self, label):
        return next(s for s in self.data['sites'] if s['label'] == label)

    def test_typos_and_grade_suffixes_match(self):
        self.assertEqual(match_venue('Gwinnet Online Campus (8th Grade)', self.venues)['label'],
                         'Gwinnett Online Campus')
        self.assertIsNone(match_venue('Somewhere New', self.venues))

    def test_shared_campus_is_one_dot(self):
        beacon = self.site('Beacon Hill MS')
        self.assertEqual((beacon['attendees'], len(beacon['visits'])), (150, 2))

    def test_unmapped_and_unknown_are_reported_not_guessed(self):
        self.assertEqual([u['label'] for u in self.data['unmapped']], ['Mystery School'])
        self.assertEqual([u['venue'] for u in self.data['unknown']], ['Somewhere New'])

    def test_far_sites_go_to_inset_and_not_county_count(self):
        dc = self.site('NCS (DC)')
        self.assertTrue(dc['inset'])
        self.assertEqual(dc['county'], 'Washington, DC')
        k12 = summarize(self.data, 'k12')
        self.assertEqual(k12['counties'], 2)  # DeKalb, Gwinnett
        self.assertEqual(k12['outside_ga'], 1)
        self.assertEqual(k12['attendees'], 150 + 78 + 30)
        self.assertEqual(k12['unmapped_attendees'], 12)

    def test_counties(self):
        counties = load_counties()
        self.assertEqual(county_of(33.75358, -84.38542, counties), 'Fulton Co.')     # GSU
        self.assertEqual(county_of(33.7706, -84.29785, counties), 'DeKalb Co.')     # Decatur HS
        self.assertEqual(county_of(33.98413, -83.97171, counties), 'Gwinnett Co.')

    def test_svgs_are_valid_xml_and_filter_by_audience(self):
        for audience in (None, 'k12'):
            svg, _ = render_map_svg(self.data, audience, standalone=True)
            xml.dom.minidom.parseString(svg)
            self.assertIn('Beacon Hill MS', svg)
            self.assertEqual('ASF Expo' in svg, audience is None)


if __name__ == '__main__':
    unittest.main()
