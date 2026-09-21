"""Offline tests for package_emojis.py.

Run with: py scripts/test_package_emojis.py
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from package_emojis import (
    PackageError,
    build_plan,
    discover_assets,
    main,
    parse_group_selection,
    parse_style_selection,
    write_archive,
)


class PackageEmojiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.assets = self.root / "assets"
        (self.root / "LICENSE").write_text("fixture license\n", encoding="utf-8")

        self._add_asset(
            "Game",
            "Activities",
            {
                "Flat/game_flat.svg": b"<svg>game flat</svg>",
                "Color/game_color.svg": b"<svg>game color</svg>",
            },
        )
        self._add_asset(
            "Tool",
            "Objects",
            {
                "Flat/shared_flat.svg": b"<svg>tool flat</svg>",
                "3D/tool_3d.png": b"tool 3d png",
            },
        )
        self._add_asset(
            "Hand",
            "People & Body",
            {
                "Default/Flat/shared_flat.svg": b"<svg>hand default</svg>",
                "Light/Flat/hand_light_flat.svg": b"<svg>hand light</svg>",
                "Default/Color/hand_color.svg": b"<svg>hand color</svg>",
            },
        )
        self.records = discover_assets(self.assets, self.root)
        self.groups = tuple(sorted({record.group for record in self.records}, key=str.casefold))

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _add_asset(self, name: str, group: str, files: dict[str, bytes]) -> None:
        asset_directory = self.assets / name
        asset_directory.mkdir(parents=True, exist_ok=True)
        metadata = {
            "cldr": name.lower(),
            "glyph": "◇",
            "group": group,
            "unicode": name.casefold(),
        }
        (asset_directory / "metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
        for relative_path, content in files.items():
            output = asset_directory / relative_path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)

    def _plan(self, style: str, group: str):
        return build_plan(
            self.records,
            parse_style_selection(style),
            parse_group_selection(group, self.groups),
        )

    def _write(self, plan, *, force: bool = False) -> Path:
        output = self.root / "dist" / "fixture.zip"
        write_archive(plan, output, license_path=self.root / "LICENSE", force=force)
        return output

    def test_discovery_reads_only_style_images_and_skin_tones(self) -> None:
        self.assertEqual(7, len(self.records))
        self.assertEqual({"3d", "color", "flat"}, {record.style for record in self.records})
        hand_tones = {
            record.skin_tone
            for record in self.records
            if record.source_relative_path.startswith("assets/Hand/")
        }
        self.assertEqual({"Default", "Light"}, hand_tones)

    def test_style_selection_accepts_aliases_and_preserves_canonical_order(self) -> None:
        selection = parse_style_selection("flat, HC")
        self.assertTrue(selection.create_directory)
        self.assertEqual(("flat", "high-contrast"), selection.values)

    def test_style_selection_none_keeps_every_style_without_a_directory(self) -> None:
        selection = parse_style_selection("NONE")
        self.assertFalse(selection.create_directory)
        self.assertEqual(("3d", "color", "flat", "high-contrast"), selection.values)

    def test_selection_rejects_all_mixed_with_specific_value(self) -> None:
        with self.assertRaisesRegex(PackageError, "ALL"):
            parse_style_selection("ALL,flat")

    def test_selection_rejects_unknown_group(self) -> None:
        with self.assertRaisesRegex(PackageError, "未知的 group"):
            parse_group_selection("Unknown", self.groups)

    def test_selected_styles_and_all_groups_have_two_directory_levels(self) -> None:
        paths = {item.archive_path.as_posix() for item in self._plan("flat,color", "ALL")}
        self.assertIn("flat/Activities/game_flat.svg", paths)
        self.assertIn("color/Activities/game_color.svg", paths)
        self.assertIn("flat/People & Body/hand_light_flat.svg", paths)
        self.assertNotIn("3d/Objects/tool_3d.png", paths)

    def test_group_selection_filters_resources(self) -> None:
        plan = self._plan("3d", "Objects")
        self.assertEqual(["3d/Objects/tool_3d.png"], [item.archive_path.as_posix() for item in plan])

    def test_no_group_selection_flattens_only_the_group_level(self) -> None:
        paths = {item.archive_path.as_posix() for item in self._plan("flat", "NONE")}
        self.assertIn("flat/game_flat.svg", paths)
        self.assertIn("flat/shared_flat.svg", paths)
        self.assertTrue(any(path.startswith("flat/shared_flat--") for path in paths))
        self.assertFalse(any("/Activities/" in path for path in paths))

    def test_no_style_selection_flattens_only_the_style_level(self) -> None:
        paths = {item.archive_path.as_posix() for item in self._plan("NONE", "Activities")}
        self.assertEqual({"Activities/game_color.svg", "Activities/game_flat.svg"}, paths)

    def test_no_selection_flattens_both_levels(self) -> None:
        paths = {item.archive_path.as_posix() for item in self._plan("NONE", "NONE")}
        self.assertIn("game_flat.svg", paths)
        self.assertIn("game_color.svg", paths)
        self.assertFalse(any("/" in path for path in paths))

    def test_cli_can_flatten_a_selected_group_without_changing_its_scope(self) -> None:
        output = self.root / "dist" / "activities.zip"
        result = main(
            [
                "--emoji-style",
                "flat,color",
                "--group",
                "Activities",
                "--no-group-directory",
                "--output",
                str(output),
            ],
            repository_root=self.root,
        )
        self.assertEqual(0, result)
        with zipfile.ZipFile(output) as archive:
            self.assertIn("flat/game_flat.svg", archive.namelist())
            self.assertIn("color/game_color.svg", archive.namelist())
            self.assertNotIn("flat/Activities/game_flat.svg", archive.namelist())

    def test_archive_includes_license_resources_and_leaf_metadata(self) -> None:
        output = self._write(self._plan("flat,color", "ALL"))
        with zipfile.ZipFile(output) as archive:
            names = set(archive.namelist())
            self.assertIn("LICENSE", names)
            self.assertIn("flat/Activities/game_flat.svg", names)
            self.assertIn("flat/Activities/metadata.json", names)
            self.assertIn("color/People & Body/metadata.json", names)
            self.assertIsNone(archive.testzip())

    def test_leaf_metadata_matches_the_files_in_its_directory(self) -> None:
        output = self._write(self._plan("flat", "Activities"))
        with zipfile.ZipFile(output) as archive:
            metadata = json.loads(archive.read("flat/Activities/metadata.json"))
        self.assertEqual(1, metadata["schemaVersion"])
        self.assertEqual(1, metadata["count"])
        item = metadata["items"][0]
        self.assertEqual("game_flat.svg", item["file"])
        self.assertEqual("flat", item["style"])
        self.assertEqual("Activities", item["sourceMetadata"]["group"])
        self.assertEqual(
            hashlib.sha256(b"<svg>game flat</svg>").hexdigest(), item["sha256"]
        )

    def test_flattened_root_writes_one_root_metadata_file(self) -> None:
        output = self._write(self._plan("NONE", "NONE"))
        with zipfile.ZipFile(output) as archive:
            metadata = json.loads(archive.read("metadata.json"))
            self.assertNotIn("./metadata.json", archive.namelist())
        self.assertEqual(len(self.records), metadata["count"])

    def test_existing_output_requires_force(self) -> None:
        plan = self._plan("flat", "Activities")
        self._write(plan)
        with self.assertRaisesRegex(PackageError, "--force"):
            self._write(plan)
        self._write(plan, force=True)

    def test_missing_group_in_upstream_metadata_fails_closed(self) -> None:
        broken_asset = self.assets / "Broken"
        broken_asset.mkdir()
        (broken_asset / "metadata.json").write_text("{}", encoding="utf-8")
        (broken_asset / "Flat").mkdir()
        (broken_asset / "Flat" / "broken.svg").write_text("<svg/>", encoding="utf-8")
        with self.assertRaisesRegex(PackageError, "metadata.group"):
            discover_assets(self.assets, self.root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
