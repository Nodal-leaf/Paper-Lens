import unittest

from research_parser import _block_record, _reading_order


class TestResearchParser(unittest.TestCase):
    def test_two_column_blocks_are_left_then_right(self):
        blocks = [
            {"kind": "text", "text": "Left top", "bbox": {"x0": 20, "x1": 250, "y0": 100}, "source_index": 1},
            {"kind": "text", "text": "Right top", "bbox": {"x0": 350, "x1": 580, "y0": 100}, "source_index": 2},
            {"kind": "text", "text": "Left bottom", "bbox": {"x0": 20, "x1": 250, "y0": 200}, "source_index": 3},
            {"kind": "text", "text": "Right bottom", "bbox": {"x0": 350, "x1": 580, "y0": 200}, "source_index": 4},
            {"kind": "text", "text": "Left last", "bbox": {"x0": 20, "x1": 250, "y0": 300}, "source_index": 5},
            {"kind": "text", "text": "Right last", "bbox": {"x0": 350, "x1": 580, "y0": 300}, "source_index": 6},
        ]
        self.assertEqual([b["text"] for b in _reading_order(blocks, 600)], ["Left top", "Left bottom", "Left last", "Right top", "Right bottom", "Right last"])

    def test_equation_and_cross_reference_are_preserved(self):
        source = {"kind": "text", "text": "x = y + z (3)", "page": 2, "bbox": {"x0": 1, "y0": 2, "x1": 3, "y1": 4}}
        block = _block_record(source, "block-1")
        self.assertEqual(block["type"], "equation")
        self.assertEqual(block["equation_number"], "3")

    def test_figure_table_and_cross_reference_blocks(self):
        figure = _block_record(
            {"kind": "text", "text": "Figure 2. Model overview", "page": 4,
             "bbox": {"x0": 1, "y0": 2, "x1": 3, "y1": 4}},
            "block-2",
        )
        table = _block_record(
            {"kind": "text", "text": "Table 1: Experimental results", "page": 5,
             "bbox": {"x0": 1, "y0": 2, "x1": 3, "y1": 4}},
            "block-3",
        )
        paragraph = _block_record(
            {"kind": "text", "text": "As shown in Figure 2 and Table 1, see Eq. (3).", "page": 5,
             "bbox": {"x0": 1, "y0": 2, "x1": 3, "y1": 4}},
            "block-4",
        )
        self.assertEqual(figure["type"], "figure_caption")
        self.assertEqual(table["type"], "table_caption")
        self.assertIn("Figure 2", paragraph["cross_references"])
        self.assertIn("Table 1", paragraph["cross_references"])


if __name__ == "__main__":
    unittest.main()
