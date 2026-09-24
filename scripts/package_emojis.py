#!/usr/bin/env python3
"""Build installable Fluent Emoji ZIP archives from this repository's assets.

The script intentionally has no third-party dependencies so maintainers can run
it from a clean checkout with Python 3.10 or newer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIRECTORY = REPOSITORY_ROOT / "assets"
LICENSE_PATH = REPOSITORY_ROOT / "LICENSE"
IMAGE_SUFFIXES = {".png", ".svg"}
SKIN_TONES = {
    "Default",
    "Light",
    "Medium-Light",
    "Medium",
    "Medium-Dark",
    "Dark",
}

# Keys are used in command-line input and output paths.  Values match the
# upstream directory names exactly.
STYLE_DIRECTORIES = {
    "3d": "3D",
    "color": "Color",
    "flat": "Flat",
    "high-contrast": "High Contrast",
}
STYLE_ALIASES = {
    "3d": "3d",
    "3 d": "3d",
    "color": "color",
    "flat": "flat",
    "high contrast": "high-contrast",
    "high-contrast": "high-contrast",
    "hc": "high-contrast",
    "高对比度": "high-contrast",
}
STYLE_ORDER = tuple(STYLE_DIRECTORIES)


class PackageError(RuntimeError):
    """An input or repository condition that makes packaging unsafe."""


@dataclass(frozen=True)
class Selection:
    """Selected values and whether they should become an archive directory."""

    values: tuple[str, ...]
    create_directory: bool


@dataclass(frozen=True)
class AssetFile:
    """One source SVG or PNG plus the upstream metadata that describes it."""

    source_path: Path
    source_relative_path: str
    emoji_name: str
    group: str
    style: str
    skin_tone: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class PlannedFile:
    """A source file and its final, collision-free ZIP member path."""

    asset: AssetFile
    archive_path: PurePosixPath


def _safe_path_component(value: str, *, label: str) -> str:
    """Reject values that could turn a ZIP member into a traversal path."""

    if not value or value in {".", ".."} or "\x00" in value or "/" in value or "\\" in value:
        raise PackageError(f"{label} 不能用作 ZIP 目录名：{value!r}")
    return value


def _style_from_path(relative_path: Path) -> tuple[str, str] | None:
    """Find the upstream style directory and optional skin-tone directory."""

    parts = relative_path.parts[:-1]
    for index, part in enumerate(parts):
        for style, directory in STYLE_DIRECTORIES.items():
            if part != directory:
                continue
            skin_tone = "Default"
            for preceding_part in reversed(parts[:index]):
                if preceding_part in SKIN_TONES:
                    skin_tone = preceding_part
                    break
            return style, skin_tone
    return None


def discover_assets(
    assets_directory: Path = ASSETS_DIRECTORY,
    repository_root: Path = REPOSITORY_ROOT,
) -> list[AssetFile]:
    """Read all upstream metadata files and return the SVG/PNG files they own."""

    if not assets_directory.is_dir():
        raise PackageError(f"找不到资源目录：{assets_directory}")

    records: list[AssetFile] = []
    for metadata_path in sorted(assets_directory.rglob("metadata.json")):
        try:
            with metadata_path.open("r", encoding="utf-8") as metadata_file:
                metadata = json.load(metadata_file)
        except (OSError, json.JSONDecodeError) as error:
            raise PackageError(f"无法读取 {metadata_path}：{error}") from error

        if not isinstance(metadata, dict):
            raise PackageError(f"{metadata_path} 的顶层必须是 JSON 对象")
        group = metadata.get("group")
        if not isinstance(group, str) or not group.strip():
            raise PackageError(f"{metadata_path} 缺少非空的 metadata.group")
        group = _safe_path_component(group.strip(), label="metadata.group")

        asset_directory = metadata_path.parent
        for source_path in sorted(asset_directory.rglob("*")):
            if not source_path.is_file() or source_path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            style_and_skin_tone = _style_from_path(source_path.relative_to(asset_directory))
            if style_and_skin_tone is None:
                # Do not accidentally package arbitrary preview files placed
                # beside metadata.json; only upstream style directories count.
                continue
            style, skin_tone = style_and_skin_tone
            try:
                source_relative_path = source_path.relative_to(repository_root).as_posix()
            except ValueError as error:
                raise PackageError(
                    f"资源文件不在仓库根目录内：{source_path}"
                ) from error
            records.append(
                AssetFile(
                    source_path=source_path,
                    source_relative_path=source_relative_path,
                    emoji_name=asset_directory.name,
                    group=group,
                    style=style,
                    skin_tone=skin_tone,
                    metadata=metadata,
                )
            )

    if not records:
        raise PackageError(f"在 {assets_directory} 中没有找到可打包的 SVG 或 PNG 资源")
    return records


def _split_selection(value: str) -> list[str]:
    return [part.strip() for part in value.replace("，", ",").split(",") if part.strip()]


def _parse_selection(
    raw_value: str,
    available_values: Sequence[str],
    *,
    label: str,
    aliases: dict[str, str] | None = None,
) -> Selection:
    """Parse ALL/NONE/a,b while preserving the available-values order."""

    value = raw_value.strip()
    if not value:
        return Selection(tuple(available_values), create_directory=False)

    tokens = _split_selection(value)
    normalised: list[str] = []
    available_by_casefold = {item.casefold(): item for item in available_values}
    for token in tokens:
        token_key = token.casefold()
        if aliases is not None:
            token_key = aliases.get(token_key, token_key)
        if token_key in {"all", "全部"}:
            normalised.append("ALL")
        elif token_key in {"none", "不选", "无", "不分组"}:
            normalised.append("NONE")
        else:
            resolved = available_by_casefold.get(token_key)
            if resolved is None:
                choices = ", ".join(available_values)
                raise PackageError(f"未知的 {label}：{token}。可选值：{choices}、ALL、NONE")
            normalised.append(resolved)

    if not normalised:
        return Selection(tuple(available_values), create_directory=False)
    if "ALL" in normalised and len(normalised) != 1:
        raise PackageError(f"{label} 的 ALL 不能和其他选项混用")
    if "NONE" in normalised and len(normalised) != 1:
        raise PackageError(f"{label} 的 NONE 不能和其他选项混用")
    if normalised == ["ALL"]:
        return Selection(tuple(available_values), create_directory=True)
    if normalised == ["NONE"]:
        return Selection(tuple(available_values), create_directory=False)

    chosen = set(normalised)
    return Selection(
        tuple(item for item in available_values if item in chosen),
        create_directory=True,
    )


def parse_style_selection(raw_value: str) -> Selection:
    return _parse_selection(
        raw_value,
        STYLE_ORDER,
        label="emoji-style",
        aliases=STYLE_ALIASES,
    )


def parse_group_selection(raw_value: str, groups: Sequence[str]) -> Selection:
    return _parse_selection(raw_value, groups, label="group")


def _sort_assets(records: Iterable[AssetFile]) -> list[AssetFile]:
    style_positions = {style: index for index, style in enumerate(STYLE_ORDER)}
    return sorted(
        records,
        key=lambda record: (
            style_positions[record.style],
            record.group.casefold(),
            record.source_relative_path.casefold(),
        ),
    )


def _path_with_collision_suffix(path: PurePosixPath, source_relative_path: str, attempt: int) -> PurePosixPath:
    digest = hashlib.sha256(source_relative_path.encode("utf-8")).hexdigest()
    suffix = digest[:10] if attempt == 0 else f"{digest[:10]}-{attempt}"
    return path.with_name(f"{path.stem}--{suffix}{path.suffix}")


def build_plan(
    records: Iterable[AssetFile],
    style_selection: Selection,
    group_selection: Selection,
) -> list[PlannedFile]:
    """Filter source records and give every selected file a safe ZIP path."""

    selected_styles = set(style_selection.values)
    selected_groups = set(group_selection.values)
    selected_records = [
        record
        for record in records
        if record.style in selected_styles and record.group in selected_groups
    ]
    if not selected_records:
        raise PackageError("当前选择没有匹配的图片资源")

    plan: list[PlannedFile] = []
    claimed_paths: set[PurePosixPath] = set()
    for record in _sort_assets(selected_records):
        parts: list[str] = []
        if style_selection.create_directory:
            parts.append(record.style)
        if group_selection.create_directory:
            parts.append(_safe_path_component(record.group, label="metadata.group"))
        candidate = PurePosixPath(*parts, record.source_path.name)
        attempt = 0
        while candidate in claimed_paths:
            candidate = _path_with_collision_suffix(
                PurePosixPath(*parts, record.source_path.name),
                record.source_relative_path,
                attempt,
            )
            attempt += 1
        claimed_paths.add(candidate)
        plan.append(PlannedFile(asset=record, archive_path=candidate))
    return plan


def build_obsidian_plugin_plan(records: Iterable[AssetFile]) -> list[PlannedFile]:
    """Build the three SVG-only style directories expected by the plugin."""

    selected_records = [
        record for record in records
        if record.style in {"color", "flat", "high-contrast"}
    ]
    groups = tuple(sorted({record.group for record in selected_records}, key=str.casefold))
    plan = build_plan(
        selected_records,
        Selection(("color", "flat", "high-contrast"), create_directory=True),
        Selection(groups, create_directory=False),
    )
    result: list[PlannedFile] = []
    for planned_file in plan:
        if planned_file.asset.source_path.suffix.lower() != ".svg":
            raise PackageError(
                f"Obsidian 插件资源包只接受 SVG：{planned_file.asset.source_relative_path}"
            )
        archive_path = planned_file.archive_path
        if planned_file.asset.style == "color":
            archive_path = PurePosixPath("3d", archive_path.name)
        result.append(PlannedFile(planned_file.asset, archive_path))
    return result


def _metadata_jsonl(
    files: Iterable[PlannedFile],
    *,
    style_aliases: dict[str, str] | None = None,
) -> str:
    """Merge original metadata once per Emoji/style as deterministically sorted JSONL."""

    unique_assets: dict[tuple[str, str], AssetFile] = {}
    for planned_file in files:
        asset = planned_file.asset
        key = (asset.emoji_name, asset.style)
        prior_asset = unique_assets.get(key)
        if prior_asset is not None and prior_asset.metadata != asset.metadata:
            raise PackageError(
                f"同一 Emoji/风格存在互相冲突的元数据：{asset.emoji_name} ({asset.style})"
            )
        unique_assets[key] = asset

    style_positions = {style: index for index, style in enumerate(STYLE_ORDER)}
    lines: list[str] = []
    for _, asset in sorted(
        unique_assets.items(),
        key=lambda item: (item[0][0].casefold(), style_positions[item[0][1]]),
    ):
        # Keep the upstream object intact and in its native field order.  The
        # two reserved fields are deliberately reconstructed so emojiName is
        # first and emojiStyle is last on every JSONL line.
        upstream_metadata = dict(asset.metadata)
        upstream_metadata.pop("emojiName", None)
        upstream_metadata.pop("emojiStyle", None)
        record = {
            "emojiName": asset.emoji_name,
            **upstream_metadata,
            "emojiStyle": (style_aliases or {}).get(asset.style, asset.style),
        }
        lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines) + "\n"


def _metadata_members(plan: Iterable[PlannedFile]) -> dict[PurePosixPath, list[PlannedFile]]:
    members: dict[PurePosixPath, list[PlannedFile]] = defaultdict(list)
    for planned_file in plan:
        members[planned_file.archive_path.parent].append(planned_file)
    return members


def write_archive(
    plan: Sequence[PlannedFile],
    output_path: Path,
    *,
    license_path: Path = LICENSE_PATH,
    force: bool = False,
    obsidian_plugin: bool = False,
) -> None:
    """Create and CRC-check an archive, then atomically publish it."""

    if not license_path.is_file():
        raise PackageError(f"找不到许可证文件：{license_path}")
    if output_path.exists() and not force:
        raise PackageError(f"输出文件已存在：{output_path}（如需覆盖，请添加 --force）")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=".tmp",
        prefix=f".{output_path.stem}-",
        dir=output_path.parent,
        delete=False,
    )
    temporary_path = Path(temporary_file.name)
    temporary_file.close()
    try:
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            archive.write(license_path, arcname="LICENSE")
            for planned_file in plan:
                archive.write(planned_file.asset.source_path, planned_file.archive_path.as_posix())
            if obsidian_plugin:
                archive.writestr(
                    "metadata.json",
                    _metadata_jsonl(plan, style_aliases={"color": "3d"}),
                )
            else:
                for directory, files in sorted(_metadata_members(plan).items(), key=lambda item: item[0].as_posix()):
                    metadata_member = directory / "metadata.jsonl"
                    archive.writestr(metadata_member.as_posix(), _metadata_jsonl(files))

        with zipfile.ZipFile(temporary_path, mode="r") as archive:
            damaged_member = archive.testzip()
        if damaged_member is not None:
            raise PackageError(f"CRC 校验失败：{damaged_member}")
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _default_output_path(repository_root: Path = REPOSITORY_ROOT) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return repository_root / "dist" / f"fluent-emoji-{timestamp}.zip"


def print_catalog(records: Sequence[AssetFile]) -> None:
    style_counts = Counter(record.style for record in records)
    group_counts = Counter(record.group for record in records)
    print("可选 emoji-style：")
    for style in STYLE_ORDER:
        print(f"  {style:<14} {STYLE_DIRECTORIES[style]:<14} {style_counts[style]} 个图片")
    print("  ALL              全部风格并保留风格目录")
    print("  NONE             全部风格但不创建风格目录")
    print("\n可选 group：")
    for group in sorted(group_counts, key=str.casefold):
        print(f"  {group:<22} {group_counts[group]} 个图片")
    print("  ALL              全部分组并保留分组目录")
    print("  NONE             全部分组但不创建分组目录")


def _prompt_for_selections(records: Sequence[AssetFile]) -> tuple[str, str]:
    print_catalog(records)
    style = input("\nemoji-style（例如 flat,color；直接回车表示 NONE）：").strip()
    group = input("group（例如 Activities；直接回车表示 NONE）：").strip()
    return style or "NONE", group or "NONE"


def _report_plan(
    plan: Sequence[PlannedFile],
    style_selection: Selection,
    group_selection: Selection,
    output_path: Path,
    *,
    dry_run: bool,
) -> None:
    styles = ", ".join(style_selection.values)
    groups = ", ".join(group_selection.values)
    print(f"已选择 {len(plan)} 个图片文件")
    print(f"emoji-style：{styles}（{'创建目录' if style_selection.create_directory else '不创建目录'}）")
    print(f"group：{groups}（{'创建目录' if group_selection.create_directory else '不创建目录'}）")
    if dry_run:
        print(f"预览完成，未生成 ZIP：{output_path}")
    else:
        print(f"已生成 ZIP：{output_path}")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="按 Fluent Emoji 风格和 metadata.group 打包 SVG/PNG 资源。"
    )
    parser.add_argument(
        "--emoji-style",
        metavar="SELECT",
        help="逗号分隔的风格（flat,color,3d,high-contrast）、ALL 或 NONE。",
    )
    parser.add_argument(
        "--group",
        metavar="SELECT",
        help="逗号分隔的 metadata.group、ALL 或 NONE。",
    )
    parser.add_argument(
        "--no-style-directory",
        action="store_true",
        help="保留 emoji-style 的筛选范围，但不创建风格目录。",
    )
    parser.add_argument(
        "--no-group-directory",
        action="store_true",
        help="保留 group 的筛选范围，但不创建分组目录。",
    )
    parser.add_argument("--output", type=Path, help="ZIP 输出路径。")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入 ZIP。")
    parser.add_argument("--force", action="store_true", help="允许覆盖已有 ZIP。")
    parser.add_argument("--list", action="store_true", help="列出可选风格和分组后退出。")
    parser.add_argument(
        "--obsidian-plugin",
        action="store_true",
        help="生成 SVG-only 插件包：3d(Color)、flat、high-contrast 和根目录 JSONL。",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> int:
    parser = build_argument_parser()
    arguments = parser.parse_args(argv)
    assets_directory = repository_root / "assets"
    license_path = repository_root / "LICENSE"
    try:
        records = discover_assets(assets_directory, repository_root)
        if arguments.obsidian_plugin:
            if (
                arguments.emoji_style is not None
                or arguments.group is not None
                or arguments.no_style_directory
                or arguments.no_group_directory
                or arguments.list
            ):
                raise PackageError("--obsidian-plugin 不能与风格/分组选择参数或 --list 混用")
            plan = build_obsidian_plugin_plan(records)
            output_path = arguments.output or repository_root / "dist" / "fluent-emoji-for-obsidian-plugin.zip"
            if not arguments.dry_run:
                write_archive(
                    plan,
                    output_path,
                    license_path=license_path,
                    force=arguments.force,
                    obsidian_plugin=True,
                )
            print(f"已选择 {len(plan)} 个 SVG 文件；目录：3d（Color）、flat、high-contrast")
            print(f"{'预览完成，未生成' if arguments.dry_run else '已生成'} ZIP：{output_path}")
            return 0
        if arguments.list:
            print_catalog(records)
            return 0

        if arguments.emoji_style is None and arguments.group is None:
            raw_style, raw_group = _prompt_for_selections(records)
        else:
            # When the command line supplies only one dimension, the other is
            # deliberately flattened rather than silently grouped by ALL.
            raw_style = arguments.emoji_style if arguments.emoji_style is not None else "NONE"
            raw_group = arguments.group if arguments.group is not None else "NONE"

        groups = tuple(sorted({record.group for record in records}, key=str.casefold))
        style_selection = parse_style_selection(raw_style)
        group_selection = parse_group_selection(raw_group, groups)
        if arguments.no_style_directory:
            style_selection = Selection(style_selection.values, create_directory=False)
        if arguments.no_group_directory:
            group_selection = Selection(group_selection.values, create_directory=False)
        plan = build_plan(records, style_selection, group_selection)
        output_path = arguments.output or _default_output_path(repository_root)
        if not arguments.dry_run:
            write_archive(plan, output_path, license_path=license_path, force=arguments.force)
        _report_plan(
            plan,
            style_selection,
            group_selection,
            output_path,
            dry_run=arguments.dry_run,
        )
        return 0
    except (OSError, PackageError) as error:
        print(f"打包失败：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
