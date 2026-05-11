# Codex GPT Image Skill

[![中文](https://img.shields.io/badge/docs-中文-blue)](README.md) [![Skill](https://img.shields.io/badge/skill-codex--gpt--image-cd3b35)](skills/codex-gpt-image)

A `SKILL.md` image-generation skill for Codex, Claude Code, OpenClaw, Hermes Agent, and other skill-capable agents. It does not use `OPENAI_API_KEY`. Instead, it reads the local Codex OAuth session and calls the Codex Responses backend with the `gpt-image-2` `image_generation` tool, allowing agents to reuse an existing Codex / ChatGPT subscription session.

## Features

- Codex OAuth auth from `~/.codex/auth.json`
- No OpenAI API key required
- Defaults to `gpt-image-2`
- Supports text-to-image and reference-image editing
- Supports legal GPT Image 2 sizes including 2K and 4K outputs
- Uses `gpt-image-1.5` for native transparent-background PNG/WebP requests
- Pure Python standard-library CLI

## Install

Install into the current agent's global skills directory with the `skills` CLI:

```bash
npx -y skills@latest add ningzimu/gpt-image-gen \
  --global
```

This repository currently contains one skill: `codex-gpt-image`. Restart the current agent after installation.

## Prerequisites

The preferred path is an existing Codex login on the same machine:

```bash
codex login
test -f ~/.codex/auth.json
```

Override the auth file when needed:

```bash
export CODEX_AUTH_FILE=/path/to/auth.json
```

If the machine does not have Codex auth yet, use the bundled device-code login flow. It follows the same OpenAI Codex device-code flow used by OpenClaw: the CLI prints a browser URL and a short code, the user confirms in the browser, and the CLI writes access/refresh tokens to `~/.codex/auth.json`.

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py login --open-browser
```

On remote servers or inside Claude Code, omit `--open-browser` and open the printed URL manually:

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py login
```

## Usage

Check auth:

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py auth-status
```

Start device-code login automatically when auth is missing:

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py auth-status --login-if-missing
```

Generate:

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py generate \
  --prompt "A polished launch poster for a terminal AI image tool" \
  --size 1536x1024 \
  --quality high \
  --out output/codex-gpt-image/poster.png
```

The generate command can also trigger login on first use:

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py generate \
  --login-if-missing \
  --prompt "A polished launch poster for a terminal AI image tool" \
  --out output/codex-gpt-image/poster.png
```

Edit with a reference image:

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py generate \
  --image /path/to/reference.png \
  --prompt "Preserve the layout, turn it into a clean editorial illustration" \
  --size 1536x1024 \
  --out output/codex-gpt-image/edited.png
```

Transparent PNG:

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py generate \
  --model gpt-image-1.5 \
  --output-format png \
  --background transparent \
  --prompt "A simple red circle sticker on transparent background" \
  --out output/codex-gpt-image/sticker.png
```

## Notes

- This skill does not call `api.openai.com/v1/images/*`.
- Requests go to `https://chatgpt.com/backend-api/codex/responses`.
- If you get 401/403, refresh Codex auth with `codex login`.
- Never commit `~/.codex/auth.json`.

## License

MIT
