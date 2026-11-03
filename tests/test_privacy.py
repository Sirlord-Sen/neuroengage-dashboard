"""The published page must not echo free-text values carried between exports.

The repo and GitHub Pages site are public; carried notes have contained
volunteer emails and no-show remarks.
"""
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from neuroengage.data import Note  # noqa: E402
from neuroengage.render import render_notes  # noqa: E402

SECRET = 'jdoe1@student.gsu.edu was a no-show'


class TestCarriedNotesRedacted(unittest.TestCase):
    def test_public_detail_defaults_to_detail(self):
        note = Note('name', None, '"Levi" counted as Levi Shook')
        self.assertEqual(note.public_detail, note.detail)

    def test_render_uses_public_detail(self):
        note = Note('carried', '1/1/2026 X', f'notes: kept "{SECRET}"', 'notes: kept the value')
        html = render_notes([note])
        self.assertNotIn('jdoe1', html)
        self.assertIn('kept the value', html)

    def test_merge_keeps_value_out_of_page(self):
        import csv
        from neuroengage.data import build_events
        cols = ['Id', 'Event Date', 'School, organization, or event name',
                'Lead volunteer', 'Activities', 'Length of time',
                'Number of attendees', 'Additional notes']
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, note in (('a_2026-01-01.csv', SECRET), ('b_2026-02-01.csv', '')):
                path = os.path.join(tmp, name)
                with open(path, 'w', newline='', encoding='utf-8') as fh:
                    w = csv.writer(fh)
                    w.writerow(cols)
                    w.writerow(['1', '1/1/2026', 'Test School', 'Ann Lee',
                                'Brain Models', '2 hours', '20', note])
                paths.append(path)
            _, notes, _, _ = build_events(paths)
        carried = [n for n in notes if n.category == 'carried']
        self.assertTrue(carried, 'expected the dropped note to be carried')
        self.assertTrue(any(SECRET in n.detail for n in carried))  # terminal still sees it
        self.assertNotIn('jdoe1', render_notes(notes))

if __name__ == '__main__':
    unittest.main()
