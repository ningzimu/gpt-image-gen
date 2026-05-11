#!/usr/bin/env python3
"""Generate GPT Image outputs through Codex OAuth.

This CLI intentionally does not use OPENAI_API_KEY. It reads the local Codex
OAuth session, then calls the Codex Responses backend with the image_generation
tool. The request shape follows the route used by Codex-integrated agents such
as OpenClaw.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import mimetypes
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib import parse
from urllib import error, request
import webbrowser


DEFAULT_CODEX_AUTH_FILE = "~/.codex/auth.json"
DEFAULT_CODEX_RESPONSES_BASE_URL = "https://chatgpt.com/backend-api/codex"
OPENAI_AUTH_BASE_URL = "https://auth.openai.com"
OPENAI_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_CODEX_DEVICE_CALLBACK_URL = f"{OPENAI_AUTH_BASE_URL}/deviceauth/callback"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_RESPONSES_MODEL = "gpt-5.5"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "high"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_TIMEOUT = 180
DEFAULT_COUNT = 1
DEVICE_CODE_TIMEOUT = 15 * 60
DEVICE_CODE_DEFAULT_INTERVAL = 5
DEVICE_CODE_MIN_INTERVAL = 1
MAX_COUNT = 4
MAX_INPUT_IMAGES = 5
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_BASE64_CHARS = 64 * 1024 * 1024
SUPPORTED_QUALITIES = {"low", "medium", "high", "auto"}
SUPPORTED_OUTPUT_FORMATS = {"png", "jpeg", "jpg", "webp"}
SUPPORTED_BACKGROUNDS = {"transparent", "opaque", "auto"}
GPT_IMAGE_2_MIN_PIXELS = 655_360
GPT_IMAGE_2_MAX_PIXELS = 8_294_400
GPT_IMAGE_2_MAX_EDGE = 3840
GPT_IMAGE_2_MAX_RATIO = 3.0


class CliError(RuntimeError):
    pass


@dataclass
class DeviceCode:
    device_auth_id: str
    user_code: str
    verification_url: str
    interval: int


@dataclass
class DeviceAuthorization:
    authorization_code: str
    code_verifier: str


@dataclass
class CodexAuth:
    access_token: str
    account_id: str | None = None
    last_refresh: str | None = None


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def die(message: str, code: int = 1) -> None:
    eprint(f"Error: {message}")
    raise SystemExit(code)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CliError(f"File not found: {path}") from exc
    except OSError as exc:
        raise CliError(f"Cannot read {path}: {exc}") from exc


def codex_auth_file() -> Path:
    raw = os.getenv("CODEX_AUTH_FILE", DEFAULT_CODEX_AUTH_FILE)
    return Path(raw).expanduser()


def auth_headers(content_type: str) -> dict[str, str]:
    return {
        "Content-Type": content_type,
        "originator": "codex-gpt-image",
        "User-Agent": "codex-gpt-image-skill/0.1.0",
    }


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=auth_headers("application/json"),
    )
    return read_json_response(req, timeout)


def post_form(url: str, payload: dict[str, str], timeout: int) -> dict[str, Any]:
    req = request.Request(
        url,
        data=parse.urlencode(payload).encode("utf-8"),
        method="POST",
        headers=auth_headers("application/x-www-form-urlencoded"),
    )
    return read_json_response(req, timeout)


def read_json_response(req: request.Request, timeout: int) -> dict[str, Any]:
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            text = resp.read(MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise CliError(f"HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise CliError(f"Request failed: {exc.reason}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError(f"Expected JSON response, got: {text[:500]}") from exc
    if not isinstance(data, dict):
        raise CliError("Expected JSON object response.")
    return data


def decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def infer_account_id(access_token: str) -> str | None:
    payload = decode_jwt_payload(access_token)
    for key in (
        "https://api.openai.com/auth",
        "https://api.openai.com/account_id",
        "account_id",
        "sub",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("account_id") or value.get("accountId")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def request_device_code(timeout: int) -> DeviceCode:
    data = post_json(
        f"{OPENAI_AUTH_BASE_URL}/api/accounts/deviceauth/usercode",
        {"client_id": OPENAI_CODEX_CLIENT_ID},
        timeout,
    )
    device_auth_id = str(data.get("device_auth_id") or "").strip()
    user_code = str(data.get("user_code") or data.get("usercode") or "").strip()
    interval_raw = data.get("interval")
    try:
        interval = int(interval_raw)
    except (TypeError, ValueError):
        interval = DEVICE_CODE_DEFAULT_INTERVAL
    if not device_auth_id or not user_code:
        raise CliError("Device-code response did not include device_auth_id and user_code.")
    return DeviceCode(
        device_auth_id=device_auth_id,
        user_code=user_code,
        verification_url=f"{OPENAI_AUTH_BASE_URL}/codex/device",
        interval=max(DEVICE_CODE_MIN_INTERVAL, interval),
    )


def poll_device_code(device_code: DeviceCode, timeout: int) -> DeviceAuthorization:
    deadline = time.time() + DEVICE_CODE_TIMEOUT
    while time.time() < deadline:
        try:
            data = post_json(
                f"{OPENAI_AUTH_BASE_URL}/api/accounts/deviceauth/token",
                {
                    "device_auth_id": device_code.device_auth_id,
                    "user_code": device_code.user_code,
                },
                timeout,
            )
        except CliError as exc:
            text = str(exc)
            if "HTTP 403" in text or "HTTP 404" in text:
                time.sleep(min(device_code.interval, max(DEVICE_CODE_MIN_INTERVAL, int(deadline - time.time()))))
                continue
            raise
        authorization_code = str(data.get("authorization_code") or "").strip()
        code_verifier = str(data.get("code_verifier") or "").strip()
        if not authorization_code or not code_verifier:
            raise CliError("Device authorization response did not include exchange code fields.")
        return DeviceAuthorization(
            authorization_code=authorization_code,
            code_verifier=code_verifier,
        )
    raise CliError("OpenAI Codex device authorization timed out after 15 minutes.")


def exchange_device_code(authz: DeviceAuthorization, timeout: int) -> dict[str, Any]:
    data = post_form(
        f"{OPENAI_AUTH_BASE_URL}/oauth/token",
        {
            "grant_type": "authorization_code",
            "code": authz.authorization_code,
            "redirect_uri": OPENAI_CODEX_DEVICE_CALLBACK_URL,
            "client_id": OPENAI_CODEX_CLIENT_ID,
            "code_verifier": authz.code_verifier,
        },
        timeout,
    )
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    if not isinstance(access, str) or not access.strip():
        raise CliError("Token exchange succeeded but did not return access_token.")
    if not isinstance(refresh, str) or not refresh.strip():
        raise CliError("Token exchange succeeded but did not return refresh_token.")
    return data


def write_codex_auth(tokens: dict[str, Any]) -> Path:
    path = codex_auth_file()
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(read_text(path))
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            existing = {}
    access = str(tokens["access_token"]).strip()
    refresh = str(tokens["refresh_token"]).strip()
    account_id = infer_account_id(access)
    existing["auth_mode"] = existing.get("auth_mode") or "chatgpt"
    existing["last_refresh"] = datetime.now(timezone.utc).isoformat()
    existing["tokens"] = {
        "access_token": access,
        "refresh_token": refresh,
        **({"id_token": tokens["id_token"]} if isinstance(tokens.get("id_token"), str) else {}),
        **({"account_id": account_id} if account_id else {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def login_device_code(args: argparse.Namespace) -> CodexAuth:
    eprint("Requesting Codex device code...")
    device_code = request_device_code(args.timeout)
    print()
    print("Open this URL in your browser and enter the code:")
    print(f"URL:  {device_code.verification_url}")
    print(f"Code: {device_code.user_code}")
    print("The code expires in about 15 minutes. Never share it.")
    print()
    if args.open_browser:
        try:
            webbrowser.open(device_code.verification_url)
        except Exception:
            eprint(f"Could not open browser automatically. Open manually: {device_code.verification_url}")
    eprint("Waiting for browser authorization...")
    authz = poll_device_code(device_code, args.timeout)
    eprint("Exchanging device code for Codex OAuth tokens...")
    tokens = exchange_device_code(authz, args.timeout)
    path = write_codex_auth(tokens)
    eprint(f"Codex OAuth saved to {path}.")
    return load_codex_auth()


def load_or_login_codex_auth(args: argparse.Namespace) -> CodexAuth:
    try:
        return load_codex_auth()
    except CliError:
        if getattr(args, "login_if_missing", False):
            return login_device_code(args)
        raise


def load_codex_auth() -> CodexAuth:
    path = codex_auth_file()
    if not path.exists():
        raise CliError(
            f"Codex auth file not found: {path}. Run `codex login` or sign in with Codex first."
        )
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise CliError(f"Codex auth file is not valid JSON: {path}") from exc

    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        raise CliError(f"Codex auth file has no tokens object: {path}")
    token = tokens.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise CliError(
            f"Codex access token is missing in {path}. Run `codex login` again."
        )
    account_id = tokens.get("account_id")
    return CodexAuth(
        access_token=token.strip(),
        account_id=account_id if isinstance(account_id, str) else None,
        last_refresh=data.get("last_refresh") if isinstance(data.get("last_refresh"), str) else None,
    )


def redact(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 8:
        return "<redacted>"
    return f"{value[:4]}...{value[-4:]}"


def canonicalize_codex_base_url(base_url: str | None) -> str:
    raw = (base_url or os.getenv("CODEX_RESPONSES_BASE_URL") or DEFAULT_CODEX_RESPONSES_BASE_URL).strip()
    if not raw:
        return DEFAULT_CODEX_RESPONSES_BASE_URL
    if re.fullmatch(r"https?://chatgpt\.com/backend-api(?:/codex)?(?:/v1)?/?", raw, re.I):
        return DEFAULT_CODEX_RESPONSES_BASE_URL
    return raw.rstrip("/")


def response_url(base_url: str | None) -> str:
    return f"{canonicalize_codex_base_url(base_url)}/responses"


def read_prompt(prompt: str | None, prompt_file: str | None) -> str:
    if prompt and prompt_file:
        raise CliError("Use --prompt or --prompt-file, not both.")
    if prompt_file:
        text = read_text(Path(prompt_file)).strip()
    elif prompt:
        text = prompt.strip()
    else:
        raise CliError("Missing prompt. Use --prompt or --prompt-file.")
    if not text:
        raise CliError("Prompt is empty.")
    return text


def normalize_output_format(value: str | None) -> str:
    fmt = (value or DEFAULT_OUTPUT_FORMAT).lower()
    if fmt not in SUPPORTED_OUTPUT_FORMATS:
        raise CliError("output format must be png, jpeg, jpg, or webp.")
    return "jpeg" if fmt == "jpg" else fmt


def validate_quality(value: str) -> None:
    if value not in SUPPORTED_QUALITIES:
        raise CliError("quality must be low, medium, high, or auto.")


def validate_background(value: str | None) -> None:
    if value is not None and value not in SUPPORTED_BACKGROUNDS:
        raise CliError("background must be transparent, opaque, or auto.")


def parse_size(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"([1-9][0-9]*)x([1-9][0-9]*)", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def is_gpt_image_2(model: str) -> bool:
    return "gpt-image-2" in model


def validate_size(size: str, model: str) -> None:
    if size == "auto":
        return
    parsed = parse_size(size)
    if parsed is None:
        raise CliError("size must be auto or WIDTHxHEIGHT, for example 1024x1024.")
    width, height = parsed
    if not is_gpt_image_2(model):
        if size not in {"1024x1024", "1536x1024", "1024x1536"}:
            raise CliError("this image model only supports 1024x1024, 1536x1024, 1024x1536, or auto.")
        return
    max_edge = max(width, height)
    min_edge = min(width, height)
    pixels = width * height
    if max_edge > GPT_IMAGE_2_MAX_EDGE:
        raise CliError("gpt-image-2 max edge must be <= 3840.")
    if width % 16 != 0 or height % 16 != 0:
        raise CliError("gpt-image-2 width and height must be multiples of 16.")
    if max_edge / min_edge > GPT_IMAGE_2_MAX_RATIO:
        raise CliError("gpt-image-2 long-to-short ratio must be <= 3:1.")
    if pixels < GPT_IMAGE_2_MIN_PIXELS or pixels > GPT_IMAGE_2_MAX_PIXELS:
        raise CliError("gpt-image-2 total pixels must be between 655,360 and 8,294,400.")


def guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    if mime and mime.startswith("image/"):
        return mime
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


def image_to_data_url(path: Path) -> str:
    if not path.exists():
        raise CliError(f"Input image not found: {path}")
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{guess_mime(path)};base64,{encoded}"


def build_content(prompt: str, image_paths: list[str]) -> list[dict[str, Any]]:
    if len(image_paths) > MAX_INPUT_IMAGES:
        raise CliError(f"At most {MAX_INPUT_IMAGES} input images are supported.")
    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    for raw in image_paths:
        path = Path(raw)
        content.append(
            {
                "type": "input_image",
                "image_url": image_to_data_url(path),
                "detail": "auto",
            }
        )
    return content


def build_body(args: argparse.Namespace, prompt: str, image_paths: list[str]) -> dict[str, Any]:
    image_model = args.model
    if args.background == "transparent" and image_model == DEFAULT_IMAGE_MODEL:
        image_model = "gpt-image-1.5"
    validate_quality(args.quality)
    validate_background(args.background)
    validate_size(args.size, image_model)

    tool: dict[str, Any] = {
        "type": "image_generation",
        "model": image_model,
        "size": args.size,
        "quality": args.quality,
    }
    if args.output_format:
        tool["output_format"] = normalize_output_format(args.output_format)
    if args.background:
        tool["background"] = args.background

    return {
        "model": args.responses_model,
        "input": [{"role": "user", "content": build_content(prompt, image_paths)}],
        "instructions": "You are an image generation assistant.",
        "tools": [tool],
        "tool_choice": {"type": "image_generation"},
        "stream": True,
        "store": False,
    }


def post_json_sse(url: str, token: str, body: dict[str, Any], timeout: int) -> str:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "User-Agent": "codex-gpt-image-skill/0.1.0",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = resp.read(1024 * 64)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise CliError("Codex image response exceeded size limit.")
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise CliError(f"Codex Responses request failed (HTTP {exc.code}): {detail}") from exc
    except error.URLError as exc:
        raise CliError(f"Codex Responses request failed: {exc.reason}") from exc


def parse_sse_events(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def extract_image_payloads(body: str) -> list[tuple[str, str | None]]:
    events = parse_sse_events(body)
    for event in events:
        if event.get("type") in {"response.failed", "error"}:
            error_obj = event.get("error")
            if isinstance(error_obj, dict):
                message = error_obj.get("message") or error_obj.get("code")
            else:
                message = event.get("message")
            raise CliError(str(message or "OpenAI Codex image generation failed."))

    payloads: list[tuple[str, str | None]] = []
    for event in events:
        item = event.get("item")
        if (
            event.get("type") == "response.output_item.done"
            and isinstance(item, dict)
            and item.get("type") == "image_generation_call"
            and isinstance(item.get("result"), str)
        ):
            payloads.append((item["result"], item.get("revised_prompt")))

    if payloads:
        return payloads

    for event in events:
        if event.get("type") != "response.completed":
            continue
        response_obj = event.get("response")
        output = response_obj.get("output") if isinstance(response_obj, dict) else None
        if not isinstance(output, list):
            continue
        for item in output:
            if (
                isinstance(item, dict)
                and item.get("type") == "image_generation_call"
                and isinstance(item.get("result"), str)
            ):
                payloads.append((item["result"], item.get("revised_prompt")))
    return payloads


def write_images(payloads: list[tuple[str, str | None]], out: str, output_format: str) -> list[Path]:
    if not payloads:
        raise CliError("No image payload found in Codex response.")
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    ext = "jpg" if output_format == "jpeg" else output_format
    multi = len(payloads) > 1
    written: list[Path] = []
    for index, (payload, _revised_prompt) in enumerate(payloads, start=1):
        if len(payload) > MAX_BASE64_CHARS:
            raise CliError("Image payload exceeded size limit.")
        data = base64.b64decode(payload)
        path = target
        if multi:
            stem = target.stem or "image"
            suffix = target.suffix or f".{ext}"
            path = target.with_name(f"{stem}-{index:02d}{suffix}")
        path.write_bytes(data)
        written.append(path)
    return written


def cmd_auth_status(args: argparse.Namespace) -> int:
    auth = load_or_login_codex_auth(args)
    payload = {
        "auth_file": str(codex_auth_file()),
        "has_access_token": True,
        "account_id": redact(auth.account_id),
        "last_refresh": auth.last_refresh,
        "base_url": canonicalize_codex_base_url(args.base_url),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("Codex OAuth is available.")
        print(f"Auth file: {payload['auth_file']}")
        if payload["account_id"]:
            print(f"Account: {payload['account_id']}")
        if payload["last_refresh"]:
            print(f"Last refresh: {payload['last_refresh']}")
        print(f"Responses base URL: {payload['base_url']}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    prompt = read_prompt(args.prompt, args.prompt_file)
    image_paths = args.image or []
    if args.count < 1 or args.count > MAX_COUNT:
        raise CliError(f"--count must be between 1 and {MAX_COUNT}.")
    auth = load_or_login_codex_auth(args)
    output_format = normalize_output_format(args.output_format)
    url = response_url(args.base_url)
    body = build_body(args, prompt, image_paths)

    if args.dry_run:
        summary = {
            "url": url,
            "auth": "Codex OAuth access token from local auth file",
            "responses_model": body["model"],
            "image_model": body["tools"][0]["model"],
            "size": body["tools"][0]["size"],
            "quality": body["tools"][0].get("quality"),
            "output_format": output_format,
            "input_images": len(image_paths),
            "count": args.count,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    all_payloads: list[tuple[str, str | None]] = []
    start = time.time()
    for _ in range(args.count):
        body_once = dict(body)
        text = post_json_sse(url, auth.access_token, body_once, args.timeout)
        all_payloads.extend(extract_image_payloads(text))
    written = write_images(all_payloads, args.out, output_format)
    for path in written:
        print(path)
    eprint(f"Generated {len(written)} image(s) via Codex OAuth in {time.time() - start:.1f}s.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate GPT Image outputs through Codex OAuth, without OPENAI_API_KEY."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth-status", help="Check whether local Codex OAuth auth is readable.")
    auth.add_argument("--base-url", default=None)
    auth.add_argument("--login-if-missing", action="store_true")
    auth.add_argument("--open-browser", action="store_true")
    auth.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    auth.add_argument("--json", action="store_true")
    auth.set_defaults(func=cmd_auth_status)

    login = sub.add_parser("login", help="Run OpenAI Codex device-code login and save ~/.codex/auth.json.")
    login.add_argument("--open-browser", action="store_true")
    login.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    login.set_defaults(func=lambda args: 0 if login_device_code(args) else 1)

    gen = sub.add_parser("generate", help="Generate or edit an image through Codex OAuth.")
    gen.add_argument("--prompt", "-p")
    gen.add_argument("--prompt-file")
    gen.add_argument("--image", "-i", action="append", help="Reference/edit image path. Repeatable.")
    gen.add_argument("--out", "-o", default="output/codex-gpt-image/output.png")
    gen.add_argument("--model", default=os.getenv("CODEX_GPT_IMAGE_MODEL", DEFAULT_IMAGE_MODEL))
    gen.add_argument("--responses-model", default=os.getenv("CODEX_RESPONSES_MODEL", DEFAULT_RESPONSES_MODEL))
    gen.add_argument("--size", default=DEFAULT_SIZE)
    gen.add_argument("--quality", default=DEFAULT_QUALITY)
    gen.add_argument("--output-format", default=DEFAULT_OUTPUT_FORMAT)
    gen.add_argument("--background", choices=sorted(SUPPORTED_BACKGROUNDS))
    gen.add_argument("--count", type=int, default=DEFAULT_COUNT)
    gen.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    gen.add_argument("--base-url", default=None)
    gen.add_argument("--login-if-missing", action="store_true")
    gen.add_argument("--open-browser", action="store_true")
    gen.add_argument("--dry-run", action="store_true")
    gen.set_defaults(func=cmd_generate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except CliError as exc:
        die(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
