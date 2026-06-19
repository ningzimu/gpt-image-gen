# Codex GPT Image Skill

[![中文](https://img.shields.io/badge/docs-中文-blue)](README.md) [![Skill](https://img.shields.io/badge/skill-codex--gpt--image-cd3b35)](skills/codex-gpt-image)

A `SKILL.md` image-generation skill for **OpenClaw, Claude Code, Codex, Hermes Agent**, and other skill-capable agents. It generates images with **`gpt-image-2` via Codex OAuth / ChatGPT login**, without requiring `OPENAI_API_KEY`.

The skill reads the local `~/.codex/auth.json` and calls the Codex Images backend at `https://chatgpt.com/backend-api/codex/images/generations` or `https://chatgpt.com/backend-api/codex/images/edits` so agents can reuse an existing Codex / ChatGPT subscription session.

## Who this is for

- You want `gpt-image-2` image generation inside OpenClaw, Claude Code, Codex, or Hermes Agent.
- You already have Codex / ChatGPT OAuth login and do not want to configure an OpenAI API key.
- You want one GPT Image skill that works across multiple `SKILL.md`-capable agents.
- You need text-to-image, reference-image editing, or explicit legal output dimensions when the user asks for them.

## Features

- OpenClaw skill / Claude Code skill / Codex skill / Hermes Agent skill
- Codex OAuth auth from `~/.codex/auth.json`
- No OpenAI API key required
- Defaults to `gpt-image-2`
- Supports text-to-image and reference-image editing
- Validates legal `gpt-image-2` output dimensions
- Supports common official Images API parameters: `background`, `moderation`, `output_format`, `output_compression`, and `mask`
- Pure Python standard-library CLI

## Install

Install into the current agent's global skills directory with the `skills` CLI:

```bash
npx -y skills@latest add ningzimu/codex-gpt-image \
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

The device-code login fallback uses the same public OAuth client id as official Codex login tooling by default. Override it when needed:

```bash
export CODEX_APP_SERVER_LOGIN_CLIENT_ID=your-client-id
```

If the machine does not have Codex auth yet, use the bundled device-code login flow. It follows the official Codex device-code login flow: the CLI prints a browser URL and a short code, the user confirms in the browser, and the CLI writes access/refresh tokens to `~/.codex/auth.json`.

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
  --out output/codex-gpt-image/edited.png
```

Edit with a mask:

```bash
python3 skills/codex-gpt-image/scripts/codex_gpt_image.py generate \
  --image /path/to/source.png \
  --mask /path/to/mask.png \
  --prompt "Replace the masked area with a flamingo float" \
  --out output/codex-gpt-image/masked-edit.png
```

## Notes

- This skill does not use `OPENAI_API_KEY` billing.
- This is not OpenAI's recommended API integration path; the Codex Images backend interface may change or stop working at any time and can be affected by account, product access, or usage rules.
- Requests go to `https://chatgpt.com/backend-api/codex/images/generations` or `https://chatgpt.com/backend-api/codex/images/edits`.
- `gpt-image-2` does not support transparent backgrounds; keep the default `background=auto`, or use `opaque` explicitly.
- If you get 401/403, refresh Codex auth with `codex login`.
- Never commit `~/.codex/auth.json`.

## License

MIT
