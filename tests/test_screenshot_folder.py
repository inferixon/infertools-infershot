"""Directory ownership and recoverable clearing, without GUI dependencies."""

import json
import os
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from qa_core import clear_screenshot_folder, screenshot_files


class ScreenshotFolderTests(unittest.TestCase):
    def test_direct_images_sorted_newest_and_other_files_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "screens"
            folder.mkdir()
            old, new = folder / "old.JPG", folder / "new.png"
            old.write_bytes(b"old")
            new.write_bytes(b"new")
            os.utime(old, (100, 100))
            os.utime(new, (200, 200))
            (folder / "notes.txt").write_text("keep")
            nested = folder / "nested"
            nested.mkdir()
            (nested / "keep.png").write_bytes(b"keep")
            self.assertEqual(screenshot_files(folder), [new, old])
            batch = clear_screenshot_folder(folder, root / "recovery", [new, old])
            self.assertEqual(screenshot_files(folder), [])
            self.assertEqual((batch / new.name).read_bytes(), b"new")
            self.assertEqual((batch / old.name).read_bytes(), b"old")
            self.assertEqual(json.loads((batch / "restore.json").read_text())["source"], str(folder.resolve()))
            self.assertTrue((nested / "keep.png").exists())
            self.assertTrue((folder / "notes.txt").exists())

    def test_reject_outside_and_unconfirmed_new_images_stay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "screens"
            folder.mkdir()
            image, outside = folder / "one.png", root / "outside.png"
            image.write_bytes(b"one")
            outside.write_bytes(b"outside")
            with self.assertRaises(ValueError):
                clear_screenshot_folder(folder, root / "trash", [image, outside])
            self.assertTrue(image.exists())
            self.assertFalse((root / "trash").exists())
            confirmed = screenshot_files(folder)
            later = folder / "later.png"
            later.write_bytes(b"later")
            clear_screenshot_folder(folder, root / "trash", confirmed)
            self.assertEqual(screenshot_files(folder), [later])

    def test_missing_and_empty_folder_do_not_create_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(screenshot_files(root / "missing"), [])
            self.assertIsNone(clear_screenshot_folder(root, root / "trash", []))
            self.assertFalse((root / "trash").exists())

    def test_failed_batch_keeps_files_recoverable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "screens"
            folder.mkdir()
            first, second = folder / "first.png", folder / "second.png"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            import shutil
            real_move = shutil.move
            def fail_second(source, destination):
                if Path(source) == second.resolve():
                    raise PermissionError("File is busy")
                return real_move(source, destination)
            with patch("qa_core.shutil.move", side_effect=fail_second):
                with self.assertRaises(PermissionError):
                    clear_screenshot_folder(folder, root / "trash", [first, second])
            self.assertEqual(second.read_bytes(), b"second")
            batches = list((root / "trash").iterdir())
            self.assertEqual((batches[0] / first.name).read_bytes(), b"first")
            self.assertTrue((batches[0] / "restore.json").exists())

    def test_equivalent_relative_file_path_is_normalized(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            image = root / "one.png"
            image.write_bytes(b"one")
            relative = image.relative_to(Path.cwd())
            batch = clear_screenshot_folder(root, root / "trash", [relative])
            self.assertEqual((batch / image.name).read_bytes(), b"one")


if __name__ == "__main__":
    unittest.main()
