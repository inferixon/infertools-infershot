import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("updater", Path(__file__).parents[1] / "update-installation.py")
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class UpdateTests(unittest.TestCase):
    def test_existing_values_lists_and_unknown_keys_survive(self):
        existing = {"save_path": "private", "colors": ["#123456"], "text": {"font_size": 20}, "custom": True}
        defaults = {"save_path": "default", "colors": ["#ff2020"],
                    "text": {"font_size": 24, "font_family": "Palatino Linotype"}, "question": {"size": 48}}
        merged = updater.append_defaults(existing, defaults)
        self.assertEqual(merged["save_path"], "private")
        self.assertEqual(merged["colors"], ["#123456"])
        self.assertEqual(merged["text"], {"font_size": 20, "font_family": "Palatino Linotype"})
        self.assertEqual(merged["question"], {"size": 48})
        self.assertTrue(merged["custom"])
        self.assertNotIn("question", existing)

    def test_install_preserves_config_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "source", Path(directory) / "installed"
            source.mkdir()
            target.mkdir()
            for name in updater.FILES:
                (source / name).write_text("new code", encoding="utf-8")
            (source / "config.json").write_text(json.dumps({"text": {"font_size": 24}, "question": {"size": 48}}))
            (target / "config.json").write_text('{"text":{"font_size":20},"custom":7}')
            (target / "infershot.py").write_text("old code")
            first = updater.install(source, target)
            self.assertEqual(json.loads((target / "config.json").read_text()),
                             {"text": {"font_size": 20}, "custom": 7, "question": {"size": 48}})
            self.assertEqual((Path(first["backup"]) / "infershot.py").read_text(), "old code")
            self.assertEqual(updater.install(source, target)["changed"], [])

    def test_invalid_config_aborts_before_code_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "source", Path(directory) / "installed"
            source.mkdir()
            target.mkdir()
            (source / "config.json").write_text("{}")
            (target / "config.json").write_text("invalid")
            (target / "infershot.py").write_text("original")
            with self.assertRaises(json.JSONDecodeError):
                updater.install(source, target)
            self.assertEqual((target / "infershot.py").read_text(), "original")


if __name__ == "__main__":
    unittest.main()
