"""Adversarial ZIP/metadata regression tests, independent of the pack builder."""

import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

from validate_emoji_archive import ValidationError, validate_archive


class ArchiveValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "pack.zip"
        self.rows = [{"emojiName": "O button (blood type)", "unicode": "1f17e fe0f",
                      "emojiStyle": style} for style in ("3d", "flat", "high-contrast")]
        self.images = {
            "3d/o_button_(blood_type)_color.svg": "<svg/>",
            "flat/o_button_(blood_type)_flat.svg": "<svg/>",
            "high-contrast/o_button_(blood_type)_high_contrast.svg": "<svg/>",
        }

    def write(self, *, extra=None, metadata=None):
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("LICENSE", "MIT fixture license")
            archive.writestr("metadata.json", metadata if metadata is not None else
                             "\n".join(json.dumps(row) for row in self.rows) + "\n")
            for name, value in self.images.items():
                archive.writestr(name, value)
            for name, value in (extra or {}).items():
                archive.writestr(name, value)

    def test_all_three_styles_resolve_parentheses(self):
        self.write()
        result = validate_archive(self.path)
        self.assertEqual(3, result["images"])
        self.assertEqual(3, result["metadata_rows"])

    def test_old_directory_name_reproduces_missing_target(self):
        for row in self.rows:
            row["emojiName"] = "O button blood type"
        self.write()
        with self.assertRaisesRegex(ValidationError, "target missing"):
            validate_archive(self.path)

    def test_rejects_blank_rows_and_duplicate_json_keys(self):
        for raw in ('\n' + json.dumps(self.rows[0]),
                    '{"emojiName":"a","emojiName":"b","emojiStyle":"flat"}'):
            with self.subTest(raw=raw):
                self.write(metadata=raw)
                with self.assertRaises(ValidationError):
                    validate_archive(self.path)

    def test_rejects_missing_style_and_unreferenced_asset(self):
        for incomplete in (True, False):
            with self.subTest(incomplete=incomplete):
                if incomplete:
                    self.rows.pop()
                    self.images.pop("high-contrast/o_button_(blood_type)_high_contrast.svg")
                    self.write()
                else:
                    self.write(extra={"flat/unreferenced_flat.svg": "<svg/>"})
                with self.assertRaises(ValidationError):
                    validate_archive(self.path)

    def test_rejects_unsafe_and_case_ambiguous_paths(self):
        for name in ("../evil.svg", "/absolute.svg", "C:/drive.svg", "flat\\escape.svg",
                     "flat/./dot.svg", "flat/trailing. /a.svg", "flat/O_BUTTON_(BLOOD_TYPE)_FLAT.svg"):
            with self.subTest(name=name):
                self.write(extra={name: "<svg/>"})
                with self.assertRaises(ValidationError):
                    validate_archive(self.path)

    def test_rejects_duplicate_members(self):
        self.write()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.path, "a") as archive:
                archive.writestr("LICENSE", "duplicate")
        with self.assertRaisesRegex(ValidationError, "Duplicate ZIP"):
            validate_archive(self.path)

    def test_detects_crc_corruption(self):
        self.write()
        data = self.path.read_bytes()
        self.path.write_bytes(data.replace(b"<svg/>", b"<bad/>", 1))
        with self.assertRaisesRegex(ValidationError, "CRC failure"):
            validate_archive(self.path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
