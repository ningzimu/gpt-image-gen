# OpenAI Images API And Codex Request Reference

This reference summarizes the official OpenAI Images API fields used by this skill and the Codex OAuth request shape used to reach the Codex Images backend.
Treat the linked OpenAI documentation as the source of truth when behavior changes:

- Create image: https://developers.openai.com/api/reference/resources/images/methods/generate
- Create image edit: https://developers.openai.com/api/reference/resources/images/methods/edit
- Image generation guide: https://developers.openai.com/api/docs/guides/image-generation
- GPT Image 2 model page: https://developers.openai.com/api/docs/models/gpt-image-2

## Codex Request Shape

This skill uses Codex OAuth with Codex backend equivalents of the public Images API.

Codex backend endpoints:

```text
POST https://chatgpt.com/backend-api/codex/images/generations
POST https://chatgpt.com/backend-api/codex/images/edits
```

Public OpenAI API equivalents:

```text
POST https://api.openai.com/v1/images/generations
POST https://api.openai.com/v1/images/edits
```

Request headers:

| Header | Source / rule |
| --- | --- |
| `Authorization` | `Bearer <access token from ~/.codex/auth.json>` |
| `Accept` | `application/json` |
| `Content-Type` | `application/json` |
| `originator` | Skill originator string |
| `User-Agent` | Skill user-agent string |
| `ChatGPT-Account-ID` | Included only when an account id is available from Codex auth |

Generation requests contain the user's prompt plus the shared image parameters below.
Edit requests also contain one or more local reference images encoded as base64 data URLs, and may include a mask when the user requests a masked edit.

## Parameter Selection

Prefer official API defaults unless the user request requires a specific option.
Do not choose a concrete `size`, `quality`, `background`, `moderation`, or `output_format` only because it appears in documentation or prior examples.

For `size`, use an explicit value only when the user asks for a specific dimension, aspect ratio, resolution class, or downstream layout requirement. Otherwise leave the default behavior in place.

## Shared Parameters

| API field | CLI flag | Default | Values / constraints | Notes |
| --- | --- | --- | --- | --- |
| `model` | `--model` | `gpt-image-2` | GPT Image model string | This skill defaults to `gpt-image-2` by design. |
| `prompt` | `--prompt`, `--prompt-file` | Required | Text, up to 32000 chars for GPT image models | Required for generation and edits. Use the user's actual prompt; do not reuse wording from this reference. |
| `n` | `--count` | `1` | Integer `1` through `10` | Number of generated or edited images. |
| `size` | `--size` | `auto` | `auto` or `WIDTHxHEIGHT` | For `gpt-image-2`, both edges must be multiples of 16, max edge <= 3840, aspect ratio <= 3:1, total pixels between 655360 and 8294400. |
| `quality` | `--quality` | `auto` | `low`, `medium`, `high`, `auto` | GPT image models support these values. |
| `background` | `--background` | `auto` | CLI exposes `auto`, `opaque` | The public API also documents `transparent`, but `gpt-image-2` does not support it, so this CLI does not expose that value. |
| `moderation` | `--moderation` | `auto` | `low`, `auto` | GPT image model moderation strictness. |
| `output_format` | `--output-format` | `png` | `png`, `jpeg`, `webp` | GPT image models return base64 image data. |
| `output_compression` | `--output-compression` | `100` for `jpeg` and `webp` | Integer `0` through `100` | Only valid when `output_format` is `jpeg` or `webp`. |
| `user` | `--user` | Omitted | String | Optional end-user identifier. |

## Edit-Only Parameters

| API field | CLI flag | Default | Values / constraints | Notes |
| --- | --- | --- | --- | --- |
| `images` | `--image` | Omitted | One or more PNG, JPEG, or WebP files | This skill sends local files as base64 data URLs. |
| `mask` | `--mask` | Omitted | PNG/JPEG/WebP data URL | Requires at least one `--image`. The CLI defers exact mask format, dimensions, and alpha-channel validation to the backend; prepare masks to match the source image when possible. |

## Parameters Not Exposed By This CLI

| API field | Reason |
| --- | --- |
| `stream` | This skill currently follows the Codex Images JSON response path instead of streaming partial image events. |
| `partial_images` | Only useful with streaming responses. |
| `response_format` | Only supported by DALL-E models; GPT image models return base64 image data. |
| `style` | DALL-E 3 only. |

## Device-Code Login

When `~/.codex/auth.json` is missing, the script can run the OpenAI Codex device-code login flow:

1. Resolve the OAuth client id from `--client-id`, then `CODEX_APP_SERVER_LOGIN_CLIENT_ID`, then the public Codex default.
2. `POST https://auth.openai.com/api/accounts/deviceauth/usercode`
3. Show `https://auth.openai.com/codex/device` and the returned user code.
4. Poll `POST https://auth.openai.com/api/accounts/deviceauth/token`.
5. Exchange the returned authorization code at `POST https://auth.openai.com/oauth/token`.
6. Save `access_token` and `refresh_token` into `~/.codex/auth.json`.

The default client id is the public Codex OAuth client id used by official Codex login tooling. It is not a secret.
