# Codex GPT Image Skill

[![English](https://img.shields.io/badge/lang-English-blue)](README_en.md) [![Skill](https://img.shields.io/badge/skill-codex--gpt--image-cd3b35)](skills/codex-gpt-image)

一个可在 Codex、Claude Code、OpenClaw、Hermes Agent 等支持 `SKILL.md` 的 agent 中使用的 GPT Image 生图 skill。它不使用 `OPENAI_API_KEY`，而是读取本机 Codex OAuth 登录态，通过 Codex Responses 后端调用 `gpt-image-2` 的 `image_generation` 工具，从而复用 Codex / ChatGPT 订阅权限。

## 特点

- Codex OAuth：读取 `~/.codex/auth.json`，不要求 OpenAI API key
- 默认使用 `gpt-image-2`，支持 `low`、`medium`、`high`、`auto` 质量参数
- 支持文本生图和多参考图编辑
- 支持 2K/4K 合法尺寸，例如 `2048x1152`、`3840x2160`
- 支持透明背景请求自动使用 `gpt-image-1.5`
- 纯 Python 标准库脚本，便于在任意 agent 环境里调用

## 目录结构

```text
gpt-image-gen/
├── README.md
├── README_en.md
├── LICENSE
├── CHANGELOG.md
├── AGENTS.md
└── skills/
    └── codex-gpt-image/
        ├── SKILL.md
        ├── references/
        │   └── request-shape.md
        └── scripts/
            └── codex_gpt_image.py
```

## 安装

### Codex

推荐使用 `skills` CLI 安装到 Codex 的全局 skills 目录：

```bash
npx -y skills@latest add ningzimu/gpt-image-gen \
  --skill codex-gpt-image \
  --agent codex \
  --global
```

安装完成后，重启 Codex 让新 skill 生效。

本地开发时可以用软链接：

```bash
mkdir -p ~/.codex/skills
ln -s /path/to/gpt-image-gen/skills/codex-gpt-image ~/.codex/skills/codex-gpt-image
```

### Claude Code、Hermes Agent

这些 agent 都可以读取 `SKILL.md` 形式的 skill。推荐同样使用 `skills` CLI 安装：

```bash
# Claude Code
npx -y skills@latest add ningzimu/gpt-image-gen \
  --skill codex-gpt-image \
  --agent claude-code \
  --global

# Hermes Agent
npx -y skills@latest add ningzimu/gpt-image-gen \
  --skill codex-gpt-image \
  --agent hermes-agent \
  --global
```

常见目标目录是：Claude Code 使用 `~/.claude/skills/codex-gpt-image`，Hermes Agent 使用 `~/.hermes/skills/codex-gpt-image`。

### OpenClaw

暂不发布到 ClawHub。需要在 OpenClaw 中使用时，先用本仓库的 `skills/codex-gpt-image` 目录手动复制或软链接到 OpenClaw 可读取的 skills 目录；后续需要发布到 ClawHub 时再补发布流程。

## 前置条件

首选路径是本机已经登录 Codex，并存在可读的 Codex OAuth 文件：

```bash
codex login
test -f ~/.codex/auth.json
```

这个 skill 不读取也不需要 `OPENAI_API_KEY`。如果你想指定另一个 Codex auth 文件：

```bash
export CODEX_AUTH_FILE=/path/to/auth.json
```

如果机器上还没有 Codex 登录态，也可以直接用本 skill 的 device-code 登录流程。它参考 OpenClaw 的 `openai-codex` device-code 认证方式：先生成浏览器 URL 和短 code，用户在浏览器中确认后，脚本把 access/refresh token 写入 `~/.codex/auth.json`。

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py login --open-browser
```

在远程服务器或 Claude Code 终端里，可以不加 `--open-browser`，手动复制 URL 到本地浏览器：

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py login
```

## 使用方式

检查 Codex OAuth：

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py auth-status
```

如果缺少 auth，可以让检查命令自动进入 device-code 登录：

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py auth-status --login-if-missing
```

生成图片：

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py generate \
  --prompt "A polished launch poster for a terminal AI image tool" \
  --size 1536x1024 \
  --quality high \
  --out output/codex-gpt-image/poster.png
```

生成命令也支持 `--login-if-missing`，适合 agent 第一次使用时自动引导登录：

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py generate \
  --login-if-missing \
  --prompt "A polished launch poster for a terminal AI image tool" \
  --out output/codex-gpt-image/poster.png
```

使用参考图编辑：

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py generate \
  --image /path/to/reference.png \
  --prompt "Preserve the layout, turn it into a clean editorial illustration" \
  --size 1536x1024 \
  --out output/codex-gpt-image/edited.png
```

透明 PNG：

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py generate \
  --model gpt-image-1.5 \
  --output-format png \
  --background transparent \
  --prompt "A simple red circle sticker on transparent background" \
  --out output/codex-gpt-image/sticker.png
```

## 注意

- 这不是 OpenAI API key 方案，也不会把请求发到 `api.openai.com/v1/images/*`。
- 请求会发到 Codex Responses 后端：`https://chatgpt.com/backend-api/codex/responses`。
- Codex OAuth token 可能过期；遇到 401/403 时先重新登录 Codex。
- 不要把 `~/.codex/auth.json` 提交到任何仓库。

## 许可证

MIT
