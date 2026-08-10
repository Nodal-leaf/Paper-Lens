"""test_pdf_parser.py

Unit tests for pdf_parser module using standard unittest.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdf_parser import (
    identify_sections,
    build_hierarchy,
    save_to_json,
    parse_pdf_to_json,
    _clean_content_text,
    _is_author_or_affiliation_line
)


class TestPdfParser(unittest.TestCase):

    def test_author_line_detection(self):
        """Test that author names, affiliations, emails, and notes are recognized as author lines."""
        self.assertTrue(_is_author_or_affiliation_line("Peng Gao 1, Renrui Zhang 2, Rongyao Fang 2"))
        self.assertTrue(_is_author_or_affiliation_line("1Shanghai AI Laboratory, Shanghai, China."))
        self.assertTrue(_is_author_or_affiliation_line("Contributing authors: gaopeng@pjlab.org.cn;"))
        self.assertTrue(_is_author_or_affiliation_line("Hongyang He * 1 Xinyuan Song * 2 Yan Zhong3"))
        self.assertFalse(_is_author_or_affiliation_line("Mimic before Reconstruct: Enhancing Masked Autoencoders"))

    def test_clean_content_text_hyphenation(self):
        """Test that words split across line breaks with hyphens are re-joined properly."""
        raw_text = "pseudo-label gen-\neration with su-\npervision and frame-\nwork."
        cleaned = _clean_content_text(raw_text)
        self.assertEqual(cleaned, "pseudo-label generation with supervision and framework.")

    def test_identify_sections_basic(self):
        sample_text = """Abstract
This paper presents a new study.

Introduction
1.1 Background
Deep learning has advanced rapidly.

1.2 Motivation
We aim to solve current bottlenecks.

Related Work
2.1 Existing Methods
Previous work focused on rule-based systems.

Methodology
3.1 Proposed Architecture
Our system consists of three modules.
"""
        sections = identify_sections(sample_text)
        titles = [s['title'] for s in sections]
        self.assertIn('Abstract', titles)
        self.assertIn('Introduction', titles)
        self.assertIn('Background', titles)
        self.assertIn('Motivation', titles)
        self.assertIn('Related Work', titles)
        self.assertIn('Existing Methods', titles)
        self.assertIn('Methodology', titles)
        self.assertIn('Proposed Architecture', titles)

    def test_ignore_image_and_caption_lines(self):
        """Test that image labels and figure/table captions are not mistaken for section titles."""
        sample_text = """3. Proposed Framework
In this section we present our architecture.
0 1 40 1 1 0
Teacher Model B
Figure 2. Overview of the proposed TTN framework.
3.1 Dual-Teacher Knowledge Fusion
We fuse the outputs.
Table 1. Experimental configurations.
"""
        flat = identify_sections(sample_text)
        titles = [s['title'] for s in flat]

        self.assertIn('Proposed Framework', titles)
        self.assertIn('Dual-Teacher Knowledge Fusion', titles)
        self.assertNotIn('0 1 40 1 1 0', titles)
        self.assertNotIn('Figure 2. Overview of the proposed TTN framework.', titles)
        self.assertNotIn('Table 1. Experimental configurations.', titles)

        hierarchy = build_hierarchy(flat)
        sec3 = next(s for s in hierarchy if s['title'] == 'Proposed Framework')
        self.assertEqual(len(sec3['subsections']), 1)
        self.assertEqual(sec3['subsections'][0]['title'], 'Dual-Teacher Knowledge Fusion')

    def test_build_hierarchy(self):
        sample_text = """Abstract
Abstract text content.

Introduction
1.1 Background
Background text content.

1.2 Motivation
Motivation text content.

Related Work
2.1 Overview
Overview text content.

Methodology
"""
        flat = identify_sections(sample_text)
        hierarchy = build_hierarchy(flat)

        top_titles = [s['title'] for s in hierarchy]
        self.assertEqual(top_titles, ['Abstract', 'Introduction', 'Related Work', 'Methodology'])

        intro_node = next(s for s in hierarchy if s['title'] == 'Introduction')
        intro_sub_titles = [sub['title'] for sub in intro_node['subsections']]
        self.assertEqual(intro_sub_titles, ['Background', 'Motivation'])
        self.assertEqual(intro_node['subsections'][0]['number'], '1.1')
        self.assertEqual(intro_node['subsections'][1]['number'], '1.2')

        rw_node = next(s for s in hierarchy if s['title'] == 'Related Work')
        rw_sub_titles = [sub['title'] for sub in rw_node['subsections']]
        self.assertEqual(rw_sub_titles, ['Overview'])
        self.assertEqual(rw_node['subsections'][0]['number'], '2.1')

    def test_save_to_json(self):
        data = [
            {
                "title": "Abstract",
                "number": None,
                "content": "Sample content",
                "subsections": []
            }
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = Path(tmp_dir) / "output.json"
            save_to_json(data, json_file)

            self.assertTrue(json_file.exists())
            with open(json_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)

            self.assertEqual(loaded, data)

    @patch("pdf_parser.extract_text_from_pdf")
    def test_parse_pdf_to_json(self, mock_extract):
        mock_extract.return_value = """Abstract
This is abstract.

Introduction
1.1 Background
Background info.
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "test_paper.pdf"
            json_path = Path(tmp_dir) / "test_paper.json"
            pdf_path.touch()

            result = parse_pdf_to_json(pdf_path, json_path)

            self.assertTrue(json_path.exists())
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]['title'], 'Abstract')
            self.assertEqual(result[1]['title'], 'Introduction')
            self.assertEqual(len(result[1]['subsections']), 1)
            self.assertEqual(result[1]['subsections'][0]['title'], 'Background')


if __name__ == "__main__":
    unittest.main()
