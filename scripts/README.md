# Fluent Emoji 打包脚本

`package_emojis.py` 会扫描仓库的 `assets/`，根据上游每个 Emoji 的 `metadata.json` 读取 `group`，再把实际存在的 SVG 和 PNG 资源写入一个 ZIP。它不改动上游资源，也不需要安装第三方 Python 包。

打包结果适合被 Obsidian 插件作为离线图标包下载、校验和解压。每个包含图片的叶子目录都会有一份合并后的 `metadata.jsonl`；ZIP 根目录还会保留 Microsoft Fluent Emoji 的 `LICENSE`。

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
│   │   └── metadata.jsonl
│   └── People & Body/
│       ├── thumbs_up_flat.svg
│       └── metadata.jsonl
└── color/
    ├── Activities/
    │   ├── video_game_color.svg
    │   └── metadata.jsonl
    └── People & Body/
        ├── thumbs_up_color.svg
        └── metadata.jsonl
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
| `flat,color` | `ALL` | `风格/分组/图片 + metadata.jsonl` |
| `flat,color` | `NONE` | `风格/图片 + metadata.jsonl` |
| `NONE` | `ALL` | `分组/图片 + metadata.jsonl` |
| `NONE` | `NONE` | 根目录下的图片 + `metadata.jsonl` |

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

## Obsidian 插件专用包

以下命令生成 `fluent-emoji-for-obsidian-plugin.zip`：

```powershell
py scripts/package_emojis.py --obsidian-plugin
```

```text
fluent-emoji-for-obsidian-plugin.zip
├── LICENSE
├── metadata.json
├── 3d/                 # 上游 Color 风格 SVG；文件名保持上游原样
├── flat/               # 上游 Flat 风格 SVG
└── high-contrast/      # 上游 High Contrast 风格 SVG
```

三个风格目录只包含 SVG，不包含上游 3D PNG。`metadata.json` 是按要求命名的**全量 JSONL**，不是单个 JSON 对象：每行一条 Emoji／风格元数据，按 `emojiName` 升序；Color 的 `emojiStyle` 在此包中写为 `3d`，与目录名一致。每个 Emoji／风格只写一条元数据，肤色文件仍全部保留。

此模式不接受 `--emoji-style`、`--group` 或目录层级开关；可以使用 `--output`、`--dry-run` 和 `--force`。

## ZIP 内的 metadata.jsonl

每个包含图片的叶子目录只会生成一个 `metadata.jsonl`。这是 UTF-8 的 JSON Lines 文件：一行代表一个 Emoji／风格组合，按 `emojiName` 升序排列；肤色变体不会重复写同一条元数据。每行保留完整的上游 `metadata.json`，并额外遵守两个固定字段位置：首字段为 `emojiName`，末字段为 `emojiStyle`。

`icon-pack-v2` 的 JSONL 会保留全部 1,595 份源元数据中的 `alias`，以及将来新增的其他字段；插件包根目录的 `metadata.json` 也遵守同一保留规则。

```jsonl
{"emojiName":"Video game","cldr":"video game","fromVersion":"0.6","glyph":"🎮","group":"Activities","keywords":["controller","game","video game"],"tts":"video game","unicode":"1f3ae","emojiStyle":"flat"}
```

若取消目录层级后两个源文件的文件名相同，脚本会为后一个文件追加来源路径的短哈希；两个文件都不会被覆盖。JSONL 合并基于 Emoji 名称与风格，不受这类文件名改写影响。

写入时先创建临时 ZIP，完成 CRC 校验后才原子替换目标文件。已有目标 ZIP 默认不会被覆盖。

### 元数据名称与实际路径

自 `v2.0.1` 起，`emojiName` 优先保留与文件名匹配的原目录名称；若不匹配，仅当 `cldr` 或 `tts` 与该 Emoji 的所有真实风格、肤色文件名均一致时才采用该名称。例如目录 `O button blood type` 对应 `emojiName: "O button (blood type)"`。不会批量重命名图片或修改源元数据。插件模式会拒绝无法按名称解析的文件及发生冲突后改名的文件。

独立校验器不导入打包器，使用插件相同的名称转路径规则，检查全部 JSONL 行、肤色文件、空行、重复记录、大小写／Unicode 规范化歧义、ZIP 路径安全、根结构和 CRC。传入源仓库时，还逐条比较全部源元数据字段、许可内容及图片大小／CRC；不计算文件或 ZIP SHA。

```powershell
py scripts/validate_emoji_archive.py dist/fluent-emoji-for-obsidian-plugin.zip --source-root .
py scripts/test_validate_emoji_archive.py
py scripts/build_release.py
```

`build_release.py` 重建现有十四种正式资源包，并生成 `dist/release/validation-report.json`，拒绝覆盖同名产物。发布工作流只响应本 Fork 的新版本 tag，先创建草稿、下载并复核全部资产，再发布正式 Release；不会覆盖已有 Release。

## 测试

测试完全使用临时目录和合成资源，不会读取或修改真实 Emoji 素材：

```powershell
py scripts/test_package_emojis.py
```
