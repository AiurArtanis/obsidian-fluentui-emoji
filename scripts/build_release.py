#!/usr/bin/env python3
"""Build and independently validate the existing fourteen release archives."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re

from package_emojis import (
    REPOSITORY_ROOT, STYLE_ORDER, Selection, build_obsidian_plugin_plan,
    build_plan, discover_assets, write_archive,
)
from validate_emoji_archive import validate_archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=REPOSITORY_ROOT / "dist/release")
    args = parser.parse_args()
    output = args.output_directory
    assets = discover_assets(REPOSITORY_ROOT / "assets", REPOSITORY_ROOT)
    groups = tuple(sorted({asset.group for asset in assets}, key=str.casefold))
    plans = [("fluent-emoji-for-obsidian-plugin.zip", build_obsidian_plugin_plan(assets), True)]
    for style in STYLE_ORDER:
        extension = "png" if style == "3d" else "svg"
        plans.append((f"fluent-emoji-all-{style}-{extension}.zip", build_plan(
            assets, Selection((style,), True), Selection(groups, False)), False))
    for group in groups:
        slug = re.sub(r"[^a-z0-9]+", "-", group.lower().replace("&", "and")).strip("-")
        plans.append((f"fluent-emoji-group-{slug}.zip", build_plan(
            assets, Selection(STYLE_ORDER, True), Selection((group,), False)), False))
    # Fail before writing anything if this directory contains a prior build.
    for name, _, _ in plans:
        if (output / name).exists():
            parser.error(f"Refusing to overwrite existing archive: {output / name}")
    reports = []
    for name, plan, plugin in plans:
        path = output / name
        write_archive(plan, path, obsidian_plugin=plugin)
        reports.append(validate_archive(path, REPOSITORY_ROOT))
        print(f"Validated {name}: {len(plan)} images, {path.stat().st_size} bytes", flush=True)
    report = {
        "source_metadata": len(list((REPOSITORY_ROOT / "assets").rglob("metadata.json"))),
        "source_images_by_style": dict(Counter(asset.style for asset in assets)),
        "corrected_names": sorted({(asset.source_path.relative_to(REPOSITORY_ROOT / "assets").parts[0],
                                    asset.emoji_name) for asset in assets
                                   if asset.source_path.relative_to(REPOSITORY_ROOT / "assets").parts[0]
                                   != asset.emoji_name}),
        "archives": reports,
    }
    (output / "validation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
