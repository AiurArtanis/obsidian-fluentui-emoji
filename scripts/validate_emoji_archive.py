#!/usr/bin/env python3
"""Independently audit release ZIPs using the consumer's metadata/path contract.

No pack-builder imports and no file digests: use ZIP CRC, sizes and source bytes.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
import unicodedata
import zipfile
import zlib


class ValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def validate_archive(path: Path, source_root: Path | None = None) -> dict:
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        _require(len(names) == len(set(names)), "Duplicate ZIP members")
        folded = set()
        for entry in entries:
            name = entry.filename
            parts = PurePosixPath(name).parts
            _require(bool(parts) and not name.startswith("/") and "\\" not in name
                     and not PureWindowsPath(name).drive and "\x00" not in name
                     and all(part not in {".", "..", ""} and ":" not in part
                             and part.rstrip(" .") == part for part in name.split("/")),
                     f"Unsafe ZIP path: {name}")
            _require(not entry.is_dir() and entry.file_size > 0, f"Empty/non-file member: {name}")
            _require(not stat.S_ISLNK(entry.external_attr >> 16), f"Symlink member: {name}")
            key = unicodedata.normalize("NFC", name).casefold()
            _require(key not in folded, f"Case/Unicode-normalized path collision: {name}")
            folded.add(key)
        _require(archive.testzip() is None, "ZIP CRC failure")
        _require("LICENSE" in names, "Missing root LICENSE")
        plugin = "metadata.json" in names
        members = set(names)
        metadata_names = [name for name in names if name.endswith("metadata.jsonl")]
        if plugin:
            _require(not metadata_names, "Plugin pack has unexpected JSONL members")
            metadata_names = ["metadata.json"]
            _require({name.split("/")[0] for name in names} ==
                     {"LICENSE", "metadata.json", "3d", "flat", "high-contrast"},
                     "Incorrect plugin root structure")
        _require(bool(metadata_names), "Missing metadata")
        source_metadata = {}
        source_images = {}
        if source_root is not None:
            _require(archive.read("LICENSE") == (source_root / "LICENSE").read_bytes(),
                     "Upstream LICENSE changed")
            for metadata_path in (source_root / "assets").rglob("metadata.json"):
                data = json.loads(metadata_path.read_text(encoding="utf-8"))
                key = data["unicode"]
                _require(key not in source_metadata, f"Ambiguous source unicode: {key}")
                source_metadata[key] = data
            for image in (source_root / "assets").rglob("*"):
                if image.suffix not in {".svg", ".png"} or not image.is_file():
                    continue
                _require(image.name not in source_images, f"Ambiguous source image: {image.name}")
                source_images[image.name] = image

        referenced = set()
        row_keys = set()
        normalized_names = {}
        rows_by_style = Counter()
        styles_by_name = {}
        rows_total = 0
        for metadata_name in sorted(metadata_names):
            raw = archive.read(metadata_name).decode("utf-8")
            lines = raw.splitlines()
            _require(bool(lines) and all(line.strip() for line in lines),
                     f"Empty metadata row: {metadata_name}")
            sorted_names = []
            for line in lines:
                row = json.loads(line, object_pairs_hook=_object)
                _require(isinstance(row, dict) and bool(row), "Metadata row must be a nonempty object")
                _require(next(iter(row)) == "emojiName" and next(reversed(row)) == "emojiStyle",
                         "Metadata field order/schema changed")
                name, style = row["emojiName"], row["emojiStyle"]
                _require(isinstance(name, str) and bool(name.strip()) and name == name.strip(),
                         "Empty/whitespace emojiName")
                _require(style in ({"3d", "flat", "high-contrast"} if plugin else
                                   {"3d", "color", "flat", "high-contrast"}), "Unknown style")
                _require((name, style) not in row_keys, f"Duplicate metadata: {name}/{style}")
                row_keys.add((name, style))
                styles_by_name.setdefault(name, set()).add(style)
                slug = name.lower().replace(" ", "_")
                normalized = unicodedata.normalize("NFC", slug).casefold()
                prior = normalized_names.setdefault(normalized, name)
                _require(prior == name, f"Ambiguous normalized emojiName: {name}/{prior}")
                tones = row.get("unicodeSkintones")
                _require(tones is None or isinstance(tones, list), "Invalid unicodeSkintones")
                variants = [""]
                if tones:
                    variants = ["default"] if style == "high-contrast" else [
                        "default", "light", "medium-light", "medium", "medium-dark", "dark"]
                suffix = "color" if plugin and style == "3d" else style.replace("-", "_")
                directory = PurePosixPath(style) if plugin else PurePosixPath(metadata_name).parent
                extension = ".png" if not plugin and style == "3d" else ".svg"
                for tone in variants:
                    filename = f"{slug}_{suffix}{'_' + tone if tone else ''}{extension}"
                    target = (directory / filename).as_posix()
                    _require(target in members, f"Metadata target missing: {target}")
                    _require(target not in referenced, f"Ambiguous metadata target: {target}")
                    referenced.add(target)
                if source_root is not None:
                    source = source_metadata.get(row.get("unicode"))
                    actual = {k: v for k, v in row.items() if k not in {"emojiName", "emojiStyle"}}
                    _require(source == actual, f"Source metadata fields changed: {name}/{style}")
                rows_by_style[style] += 1
                rows_total += 1
                sorted_names.append(name.casefold())
            _require(sorted_names == sorted(sorted_names), f"Unsorted metadata: {metadata_name}")
        images = members - set(metadata_names) - {"LICENSE"}
        _require(images == referenced, f"Unreferenced assets: {sorted(images - referenced)[:10]}")
        if plugin:
            for name, styles in styles_by_name.items():
                _require(styles ==
                         {"3d", "flat", "high-contrast"}, f"Incomplete style coverage: {name}")
            if source_root is not None:
                _require(len({name for name, _ in row_keys}) == len(source_metadata),
                         "Plugin pack does not cover all source metadata")
        if source_root is not None:
            for name in images:
                source = source_images.get(PurePosixPath(name).name)
                _require(source is not None, f"Asset renamed/not in source: {name}")
                data = source.read_bytes()
                info = archive.getinfo(name)
                _require(len(data) == info.file_size and zlib.crc32(data) == info.CRC,
                         f"Source size/CRC mismatch: {name}")
        details = path.stat()
        return {
            "path": str(path.resolve()), "size": details.st_size, "mtime_ns": details.st_mtime_ns,
            "crc": "passed", "path_safety": "passed", "metadata_targets": "passed",
            "source_fields_and_asset_crc": "passed" if source_root is not None else "not checked",
            "members": len(names), "images": len(images), "metadata_rows": rows_total,
            "rows_by_style": dict(sorted(rows_by_style.items())),
            "images_by_directory": dict(sorted(Counter(name.split('/')[0] for name in images).items())),
            "blank_metadata_rows": 0,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", type=Path, nargs="+")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        reports = [validate_archive(path, args.source_root) for path in args.archives]
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Archive validation failed: {error}\n")
    text = json.dumps(reports, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
