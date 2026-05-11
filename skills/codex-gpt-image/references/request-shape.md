# Codex OAuth Image Request Shape

This skill uses the Codex Responses backend instead of the public OpenAI Images API.

Endpoint:

```text
POST https://chatgpt.com/backend-api/codex/responses
```

Headers:

```text
Authorization: Bearer <access token from ~/.codex/auth.json>
Accept: text/event-stream
Content-Type: application/json
```

Body shape:

```json
{
  "model": "gpt-5.5",
  "input": [
    {
      "role": "user",
      "content": [
        { "type": "input_text", "text": "prompt" }
      ]
    }
  ],
  "instructions": "You are an image generation assistant.",
  "tools": [
    {
      "type": "image_generation",
      "model": "gpt-image-2",
      "size": "1024x1024",
      "quality": "high",
      "output_format": "png"
    }
  ],
  "tool_choice": { "type": "image_generation" },
  "stream": true,
  "store": false
}
```

Reference images are encoded as `input_image` data URLs in the same `content` array.

## Device-Code Login

When `~/.codex/auth.json` is missing, the script can run the OpenAI Codex device-code login flow:

1. `POST https://auth.openai.com/api/accounts/deviceauth/usercode`
2. Show `https://auth.openai.com/codex/device` and the returned user code
3. Poll `POST https://auth.openai.com/api/accounts/deviceauth/token`
4. Exchange the returned authorization code at `POST https://auth.openai.com/oauth/token`
5. Save `access_token` and `refresh_token` into `~/.codex/auth.json`

The client id is the Codex OAuth client id used by Codex-integrated tooling.
