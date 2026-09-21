# Fluent Emoji 打包脚本

`package_emojis.py` 会扫描仓库的 `assets/`，根据上游每个 Emoji 的 `metadata.json` 读取 `group`，再把实际存在的 SVG 和 PNG 资源写入一个 ZIP。它不改动上游资源，也不需要安装第三方 Python 包。

打包结果适合被 Obsidian 插件作为离线图标包下载、校验和解压。每个包含图片的叶子目录都会有一份汇总 `metadata.json`；ZIP 根目录还会保留 Microsoft Fluent Emoji 的 `LICENSE`。

## 快速开始

在仓库根目录执行：

```powershell
py scripts/package_emojis.py
```

脚本会列出可选风格及从 `metadata.group` 动态去重得到的分组。然后依次输入，例如：

```text
emoji-style（例如 flat,color；直接回车表示 NONE）：flat,color
group（例如 Activities；直接回车表示 NONE）：ALL
```

默认在 `dist/` 生成带时间戳的 ZIP，例如 `dist/fluent-emoji-20260921-120000.zip`。

也可以非交互运行：

```powershell
py scripts/package_emojis.py --emoji-style "flat,color" --group ALL --output "dist/flat-color.zip"
```

输出没有额外的顶层包目录：

```text
flat-color.zip
├── LICENSE
├── flat/
│   ├── Activities/
│   │   ├── video_game_flat.svg
│   │   └── metadata.json
│   └── People & Body/
│       ├── thumbs_up_flat.svg
│       └── metadata.json
└── color/
    ├── Activities/
    │   ├── video_game_color.svg
    │   └── metadata.json
    └── People & Body/
        ├── thumbs_up_color.svg
        └── metadata.json
```

## 选择规则

两层选择都是逗号分隔的多选，支持 `ALL` 和 `NONE`：

| 输入 | 包含的资源 | 是否创建这一层目录 |
| --- | --- | --- |
| `flat,color` 或具体分组名 | 仅所选值 | 是 |
| `ALL` | 该维度的全部值 | 是 |
| `NONE`、`不选`，或交互时直接回车 | 该维度的全部值 | 否 |

`NONE` 的含义是**取消目录层级，而不是排除资源**。例如：

| emoji-style | group | ZIP 布局 |
| --- | --- | --- |
| `flat,color` | `ALL` | `风格/分组/图片 + metadata.json` |
| `flat,color` | `NONE` | `风格/图片 + metadata.json` |
| `NONE` | `ALL` | `分组/图片 + metadata.json` |
| `NONE` | `NONE` | 根目录下的图片 + `metadata.json` |

若需要保留筛选范围、但让所选维度不再创建目录，可以追加 `--no-style-directory` 或 `--no-group-directory`。例如为 `Activities` 创建一个根目录直接包含四种风格的主题包：

```powershell
py scripts/package_emojis.py --emoji-style ALL --group Activities --no-group-directory --output "dist/activities.zip"
```

该 ZIP 的根目录会是 `3d/`、`color/`、`flat/`、`high-contrast/`，不会额外包一层 `Activities/`。

风格输入不区分大小写：`3d`、`color`、`flat`、`high-contrast` 均可用；`HC` 也可表示 `high-contrast`。每个选中的风格都会包含上游实际提供的全部肤色变体，不额外建立肤色目录。

如果只在命令行提供了一个维度，另一个维度按 `NONE` 处理：

```powershell
# 按风格建目录，不再按 group 建目录
py scripts/package_emojis.py --emoji-style flat

# 按 group 建目录，混合全部风格
py scripts/package_emojis.py --group "Activities,People & Body"
```

## 常用命令

```powershell
# 查看当前资源中可选的风格、分组和图片数量
py scripts/package_emojis.py --list

# 预览范围，不生成 ZIP
py scripts/package_emojis.py --emoji-style "flat,color" --group ALL --dry-run

# 只选择某个分组与 3D 风格
py scripts/package_emojis.py --emoji-style 3d --group Objects --output "dist/objects-3d.zip"

# 覆盖已有文件（默认拒绝覆盖）
py scripts/package_emojis.py --emoji-style flat --group ALL --output "dist/flat.zip" --force
```

## ZIP 内的 metadata

每个叶子目录的 `metadata.json` 结构如下：

```json
{
  "schemaVersion": 1,
  "count": 1,
  "items": [
    {
      "file": "video_game_flat.svg",
      "style": "flat",
      "skinTone": "Default",
      "sourcePath": "assets/Video game/Flat/video_game_flat.svg",
      "sizeBytes": 1234,
      "sha256": "…",
      "sourceMetadata": {
        "group": "Activities"
      }
    }
  ]
}
```

`sourceMetadata` 是上游 `metadata.json` 的完整对象，便于下游索引 Emoji 名称、Unicode、关键词和分组。若取消目录层级后两个源文件的文件名相同，脚本会为后一个文件追加来源路径的短哈希；两个文件都不会被覆盖，且汇总 metadata 会记录最终文件名。

写入时先创建临时 ZIP，完成 CRC 校验后才原子替换目标文件。已有目标 ZIP 默认不会被覆盖。

## 测试

测试完全使用临时目录和合成资源，不会读取或修改真实 Emoji 素材：

```powershell
py scripts/test_package_emojis.py
```
