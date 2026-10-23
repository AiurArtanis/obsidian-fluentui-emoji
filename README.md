# Fluent Emoji icon packs for Obsidian

[English](#english) · [中文](#中文)

![Fluent Emoji](art/readme_banner.webp)

## English

Fluent Emoji are a collection of familiar, friendly, and modern emoji from Microsoft. This repository is a fork prepared for Obsidian plugin icon packs; it preserves the upstream asset layout while adding reproducible packaging and releases.

### What this fork adds

- `main` contains packaging tooling, bilingual documentation, and released installable ZIPs.
- `src` is an unmodified mirror of `microsoft/fluentui-emoji`'s `main` branch. A GitHub Actions workflow force-synchronizes it every six hours and can also be run manually. Do not add fork-specific changes there.
- `scripts/package_emojis.py` builds complete SVG/PNG archives by visual style and `metadata.group`, including a per-directory merged `metadata.jsonl` file and the upstream MIT license.

The first release, [`icon-pack-v1`](../../releases/tag/icon-pack-v1), contains one complete ZIP for each style, one ZIP per upstream group, and `fluent-emoji-for-obsidian-plugin.zip`. The plugin pack contains only SVGs in `3d/` (upstream Color), `flat/`, and `high-contrast/`, with one root `metadata.json` containing all metadata as JSONL.

[`icon-pack-v2`](../../releases/tag/v2) retains those archive layouts and adds reviewed English/Chinese `alias` lists to all 1,595 source metadata files. Every packaged JSONL record preserves `alias` and any other source metadata fields, with `emojiName` first and `emojiStyle` last.

[`v2.0.1`](../../releases/tag/v2.0.1) fixes generated metadata names that differ from actual filenames, including the parentheses in O button (blood type), and validates every metadata path and skin-tone variant before release. Source artwork and metadata fields are preserved.

### Build a pack locally

Python 3.10+ is sufficient; no third-party dependency is required.

```powershell
py scripts/package_emojis.py --emoji-style "flat,color" --group ALL --output "dist/flat-color.zip"
py scripts/package_emojis.py --obsidian-plugin
py scripts/test_package_emojis.py
```

See [scripts/README.md](scripts/README.md) for all selectors, output layouts, safety checks, and test coverage.

### Upstream contact

Please feel free to [open an upstream GitHub issue](https://github.com/microsoft/fluentui-emoji/issues/new) and assign to the following points of contact with questions or requests about the original artwork.

- Jason Custer ([@jasoncuster](https://github.com/jasoncuster)) / Spencer Nelson ([@spencer-nelson](https://github.com/spencer-nelson)) — Design

### Code of Conduct

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct). For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or contact opencode@microsoft.com with any additional questions or comments.

## 中文

Fluent Emoji 是 Microsoft 提供的一套熟悉、友好且现代的 Emoji。本仓库是面向 Obsidian 插件图标包的 Fork：保持上游素材目录不变，同时提供可复现的打包工具和可下载的发布产物。

### 本 Fork 增加的内容

- `main` 保存打包工具、双语文档和可安装的 ZIP Release。
- `src` 是 `microsoft/fluentui-emoji` 的 `main` 分支镜像，不包含本 Fork 改动。GitHub Actions 每六小时强制同步一次，也可手动运行；请不要直接向此分支添加改动。
- `scripts/package_emojis.py` 按视觉风格和 `metadata.group` 打包完整 SVG/PNG 资源，并在每个资源目录写入合并的 `metadata.jsonl`，同时保留上游 MIT 许可证。

首个发布版本 [`icon-pack-v1`](../../releases/tag/icon-pack-v1) 包含四个全量风格包、每个上游主题各一个 ZIP，以及 `fluent-emoji-for-obsidian-plugin.zip`。插件专用包仅收录 SVG，目录为 `3d/`（上游 Color）、`flat/`、`high-contrast/`；根目录的 `metadata.json` 保存全量 JSONL 元数据。

[`icon-pack-v2`](../../releases/tag/v2) 保持上述 ZIP 结构，为全部 1,595 份源元数据加入经审查的中英文 `alias`。包内每条 JSONL 元数据保留 `alias` 及源文件中的其他新增字段，且仍以 `emojiName` 为首字段、`emojiStyle` 为末字段。

[`v2.0.1`](../../releases/tag/v2.0.1) 修复生成的元数据名称与真实文件名不一致的问题（包括 O 型血按钮的括号），并在发布前逐条验证元数据路径和全部肤色变体。保留源图片及元数据字段。

### 本地打包

只需要 Python 3.10+，无需安装第三方依赖：

```powershell
py scripts/package_emojis.py --emoji-style "flat,color" --group ALL --output "dist/flat-color.zip"
py scripts/package_emojis.py --obsidian-plugin
py scripts/test_package_emojis.py
```

完整的选择器、输出结构、安全措施和测试说明见 [scripts/README.md](scripts/README.md)。
