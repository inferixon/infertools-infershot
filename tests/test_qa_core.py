import sys
from pathlib import Path
import unittest
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).parents[1]))
from qa_core import AnnotationHistory, repair_polygons, sheet_layout, write_capture_archive


class HistoryTests(unittest.TestCase):
    def test_eraser_undo_redo_and_new_branch(self):
        history = AnnotationHistory(2)
        marks = [{"kind": "line", "width": 3, "points": [[1, 2]]}]
        history.remember(marks)
        marks[0]["points"][0][0] = 99
        restored = history.undo([])
        self.assertEqual(restored[0]["points"], [[1, 2]])
        self.assertEqual(history.redo(restored), [])
        restored = history.undo([])
        history.remember(restored)
        self.assertIsNone(history.redo(restored))
        for index in range(5):
            history.remember([index])
        self.assertEqual(history.undo([]), [4])
        self.assertEqual(history.undo([]), [3])
        self.assertIsNone(history.undo([]))


class SheetTests(unittest.TestCase):
    def test_native_sizes_order_bounds_and_non_overlap(self):
        for count in range(1, 13):
            sizes = [(300 + index * 13, 450 - index * 7) for index in range(count)]
            (width, height), cells = sheet_layout(sizes)
            self.assertEqual([cell[2:] for cell in cells], sizes)
            for index, (x, y, w, h) in enumerate(cells):
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + w, width)
                self.assertLessEqual(y + h, height)
                for bx, by, bw, bh in cells[index + 1:]:
                    self.assertTrue(x + w <= bx or bx + bw <= x or y + h <= by or by + bh <= y)

    def test_empty_selection_rejected_and_stamp_scales_about_center(self):
        with self.assertRaises(ValueError):
            sheet_layout([])
        small, large = repair_polygons((100, 200), 24), repair_polygons((100, 200), 48)
        for polygon, scaled in zip(small, large):
            for (x, y), (sx, sy) in zip(polygon, scaled):
                self.assertAlmostEqual(sx - 100, (x - 100) * 2)
                self.assertAlmostEqual(sy - 200, (y - 200) * 2)


class ArchiveTests(unittest.TestCase):
    def test_snapshot_bytes_and_unique_flat_png_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captures.zip"
            items = [{"path": Path("first") / "capture.jpg", "data": b"first snapshot"},
                     {"path": Path("second") / "CAPTURE.jpg", "data": b"second snapshot"}]
            names = write_capture_archive(path, items)
            self.assertEqual(len({name.casefold() for name in names}), 2)
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(archive.namelist(), names)
                self.assertEqual([archive.read(name) for name in names], [item["data"] for item in items])
                self.assertTrue(all(name.endswith(".png") and "/" not in name and "\\" not in name for name in names))

    def test_empty_export_preserves_an_existing_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captures.zip"
            path.write_bytes(b"existing archive")
            with self.assertRaises(ValueError):
                write_capture_archive(path, [])
            self.assertEqual(path.read_bytes(), b"existing archive")
