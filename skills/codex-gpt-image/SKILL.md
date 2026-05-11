---
name: codex-gpt-image
description: Generate images with the gpt-image-2 model using Codex/ChatGPT subscription authentication instead of OPENAI_API_KEY. Use when the user asks to create images, generate visual assets, or use gpt-image-2 while reusing local Codex auth instead of configuring an OpenAI API key.
---

# Codex GPT Image

Use this skill to generate or edit images through Codex OAuth instead of the OpenAI API-key path. The bundled CLI reads the local Codex auth file and calls the Codex Responses backend with the `image_generation` tool.

## When To Use

- The user asks to use `gpt-image-2`, `gpt-image-1.5`, or GPT Image through Codex auth/subscription.
- The current agent supports `SKILL.md` but does not have a native image tool.
- The user explicitly does not want to use `OPENAI_API_KEY`.
- The user wants the same local image workflow across Codex, Claude Code, OpenClaw, Hermes Agent, or similar agents.

Do not use this skill when the user wants the official OpenAI Images API, an OpenAI-compatible gateway, or API-key billing. This skill is deliberately Codex-OAuth-only.

## Core Workflow

1. Check local Codex auth:

   ```bash
   python3 /path/to/skills/codex-gpt-image/scripts/codex_gpt_image.py auth-status
   ```

2. If Codex auth is missing, run the device-code login flow:

   ```bash
   python3 /path/to/skills/codex-gpt-image/scripts/codex_gpt_image.py login --open-browser
   ```

   The CLI prints a browser URL and a short user code. The user must complete this step; never ask them to paste tokens.

3. Generate an image:

   ```bash
   python3 /path/to/skills/codex-gpt-image/scripts/codex_gpt_image.py generate \
     --prompt "A polished product poster for a terminal AI tool" \
     --size 1536x1024 \
     --quality high \
     --out output/codex-gpt-image/poster.png
   ```

4. Edit or use reference images by passing one or more `--image` inputs:

   ```bash
   python3 /path/to/skills/codex-gpt-image/scripts/codex_gpt_image.py generate \
     --image /absolute/path/reference.png \
     --prompt "Preserve the composition, convert it into a clean editorial illustration" \
     --size 1536x1024 \
     --out output/codex-gpt-image/edited.png
   ```

5. Report the saved path(s), model, size, and whether Codex OAuth was used.

## Defaults

- Auth file: `~/.codex/auth.json`
- Override auth file: `CODEX_AUTH_FILE=/path/to/auth.json`
- Login fallback: `login` uses OpenAI Codex device-code auth and writes the same auth file
- Responses base URL: `https://chatgpt.com/backend-api/codex`
- Image model: `gpt-image-2`
- Outer Responses model: `gpt-5.5`
- Size: `1024x1024`
- Quality: `high`
- Output format: `png`

## Transparent Images

`gpt-image-2` currently rejects `background=transparent`. If the user asks for true transparent output, call:

```bash
python3 /path/to/skills/codex-gpt-image/scripts/codex_gpt_image.py generate \
  --model gpt-image-1.5 \
  --output-format png \
  --background transparent \
  --prompt "A simple red circle sticker on transparent background" \
  --out output/codex-gpt-image/sticker.png
```

If the user did not explicitly ask for model-native transparency, a normal `gpt-image-2` image is usually preferred.

## Prompting

Keep prompts explicit and production-oriented:

- State the intended asset type.
- Quote any exact visible text.
- Specify composition, background, style, and constraints.
- For edits, repeat invariants: what must stay unchanged.
- Avoid adding logos, watermarks, or extra text unless requested.

## Failure Handling

- Missing auth file: run `codex_gpt_image.py login --open-browser`, or ask the user to run `codex login`, then retry.
- 401/403: the Codex OAuth token may be expired, the account may not have access, or the endpoint may reject the session. Ask the user to refresh Codex auth.
- Network failures: retry once if the request is idempotent and the user accepts possible duplicate image generation.
- Never print or paste tokens from `~/.codex/auth.json`.

## Implementation Notes

The CLI sends a Responses request with:

- outer model: `gpt-5.5`
- tool: `{ "type": "image_generation", "model": "gpt-image-2" }`
- stream: `true`
- store: `false`

It parses streamed SSE events and writes returned base64 image payloads to local files.
