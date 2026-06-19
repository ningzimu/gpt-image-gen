#!/usr/bin/env python3
"""Generate GPT Image outputs through Codex OAuth.

This CLI intentionally does not use OPENAI_API_KEY. It reads the local Codex
OAuth session, then calls the Codex Images backend used by Codex-integrated
agents.
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
DEFAULT_CODEX_IMAGES_BASE_URL = "https://chatgpt.com/backend-api/codex"
OPENAI_AUTH_BASE_URL = "https://auth.openai.com"
# Public OAuth client id used by official Codex login; override with
# CODEX_APP_SERVER_LOGIN_CLIENT_ID or --client-id for staging/private clients.
DEFAULT_OPENAI_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_CLIENT_ID_ENV_VAR = "CODEX_APP_SERVER_LOGIN_CLIENT_ID"
OPENAI_CODEX_DEVICE_CALLBACK_URL = f"{OPENAI_AUTH_BASE_URL}/deviceauth/callback"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_SIZE = "auto"
DEFAULT_QUALITY = "auto"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_OUTPUT_COMPRESSION = 100
DEFAULT_BACKGROUND = "auto"
DEFAULT_MODERATION = "auto"
DEFAULT_TIMEOUT = 600
DEFAULT_COUNT = 1
DEVICE_CODE_TIMEOUT = 15 * 60
DEVICE_CODE_DEFAULT_INTERVAL = 5
DEVICE_CODE_MIN_INTERVAL = 1
MAX_COUNT = 10
MAX_INPUT_IMAGES = 16
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_BASE64_CHARS = 64 * 1024 * 1024
MAX_IMAGE_DATA_URL_CHARS = 20_971_520
SUPPORTED_QUALITIES = {"low", "medium", "high", "auto"}
SUPPORTED_OUTPUT_FORMATS = {"png", "jpeg", "jpg", "webp"}
SUPPORTED_BACKGROUNDS = {"opaque", "auto"}
SUPPORTED_MODERATIONS = {"low", "auto"}
CHATGPT_AUTH_CLAIM = "https://api.openai.com/auth"
CHATGPT_ACCOUNT_ID_CLAIM = "chatgpt_account_id"
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


def openai_codex_client_id(args: argparse.Namespace) -> str:
    raw = (
        getattr(args, "client_id", None)
        or os.getenv(CODEX_CLIENT_ID_ENV_VAR)
        or DEFAULT_OPENAI_CODEX_CLIENT_ID
    )
    client_id = str(raw).strip()
    if not client_id:
        raise CliError("Codex OAuth client id is empty.")
    return client_id


def auth_headers(content_type: str) -> dict[str, str]:
    return {"Content-Type": content_type}


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


def infer_account_id_from_tokens(tokens: dict[str, Any]) -> str | None:
    account_id = tokens.get("account_id")
    if isinstance(account_id, str) and account_id.strip():
        return account_id.strip()

    id_token = tokens.get("id_token")
    if not isinstance(id_token, str) or not id_token.strip():
        return None

    auth_claim = decode_jwt_payload(id_token).get(CHATGPT_AUTH_CLAIM)
    if not isinstance(auth_claim, dict):
        return None
    chatgpt_account_id = auth_claim.get(CHATGPT_ACCOUNT_ID_CLAIM)
    if isinstance(chatgpt_account_id, str) and chatgpt_account_id.strip():
        return chatgpt_account_id.strip()
    return None


def request_device_code(timeout: int, client_id: str) -> DeviceCode:
    data = post_json(
        f"{OPENAI_AUTH_BASE_URL}/api/accounts/deviceauth/usercode",
        {"client_id": client_id},
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


def exchange_device_code(authz: DeviceAuthorization, timeout: int, client_id: str) -> dict[str, Any]:
    data = post_form(
        f"{OPENAI_AUTH_BASE_URL}/oauth/token",
        {
            "grant_type": "authorization_code",
            "code": authz.authorization_code,
            "redirect_uri": OPENAI_CODEX_DEVICE_CALLBACK_URL,
            "client_id": client_id,
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
    account_id = infer_account_id_from_tokens(tokens)
    existing["auth_mode"] = "chatgpt"
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
    client_id = openai_codex_client_id(args)
    device_code = request_device_code(args.timeout, client_id)
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
    tokens = exchange_device_code(authz, args.timeout, client_id)
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
    raw = (
        base_url
        or os.getenv("CODEX_IMAGES_BASE_URL")
        or DEFAULT_CODEX_IMAGES_BASE_URL
    ).strip()
    if not raw:
        return DEFAULT_CODEX_IMAGES_BASE_URL
    if re.fullmatch(r"https?://chatgpt\.com/backend-api(?:/codex)?(?:/v1)?/?", raw, re.I):
        return DEFAULT_CODEX_IMAGES_BASE_URL
    return raw.rstrip("/")


def image_endpoint_url(base_url: str | None, operation: str) -> str:
    endpoint = "images/edits" if operation == "edit" else "images/generations"
    return f"{canonicalize_codex_base_url(base_url)}/{endpoint}"


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
        raise CliError("background must be auto or opaque.")


def validate_moderation(value: str | None) -> None:
    if value is not None and value not in SUPPORTED_MODERATIONS:
        raise CliError("moderation must be low or auto.")


def validate_output_compression(value: int | None, output_format: str) -> None:
    if value is None:
        return
    if value < 0 or value > 100:
        raise CliError("output-compression must be between 0 and 100.")
    if output_format not in {"jpeg", "webp"}:
        raise CliError("output-compression is only supported for jpeg or webp output.")


def default_output_compression(output_format: str) -> int | None:
    if output_format in {"jpeg", "webp"}:
        return DEFAULT_OUTPUT_COMPRESSION
    return None


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


def guess_mime(path: Path, data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    mime, _ = mimetypes.guess_type(str(path))
    if mime in {"image/png", "image/jpeg", "image/webp"}:
        return mime
    raise CliError(f"Input image must be PNG, JPEG, or WebP: {path}")


def image_to_data_url(path: Path) -> str:
    if not path.exists():
        raise CliError(f"Input image not found: {path}")
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    data_url = f"data:{guess_mime(path, data)};base64,{encoded}"
    if len(data_url) > MAX_IMAGE_DATA_URL_CHARS:
        raise CliError(f"Input image exceeds data URL limit: {path}")
    return data_url


def image_reference(path: Path) -> dict[str, str]:
    return {"image_url": image_to_data_url(path)}


def build_image_body(args: argparse.Namespace, prompt: str, image_paths: list[str]) -> tuple[str, str, dict[str, Any]]:
    if len(image_paths) > MAX_INPUT_IMAGES:
        raise CliError(f"At most {MAX_INPUT_IMAGES} input images are supported.")
    if args.mask and not image_paths:
        raise CliError("--mask can only be used with at least one --image input.")

    image_model = args.model
    output_format = normalize_output_format(args.output_format)
    output_compression = (
        args.output_compression
        if args.output_compression is not None
        else default_output_compression(output_format)
    )

    validate_quality(args.quality)
    validate_background(args.background)
    validate_moderation(args.moderation)
    validate_output_compression(output_compression, output_format)
    validate_size(args.size, image_model)

    body: dict[str, Any] = {
        "prompt": prompt,
        "model": image_model,
        "n": args.count,
        "size": args.size,
        "quality": args.quality,
        "output_format": output_format,
    }
    if args.background:
        body["background"] = args.background
    if args.moderation:
        body["moderation"] = args.moderation
    if output_compression is not None:
        body["output_compression"] = output_compression
    if args.user:
        body["user"] = args.user

    operation = "edit" if image_paths else "generate"
    if image_paths:
        body["images"] = [image_reference(Path(raw)) for raw in image_paths]
        if args.mask:
            body["mask"] = image_reference(Path(args.mask))

    return operation, image_model, body


def codex_image_headers(auth: CodexAuth) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {auth.access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "originator": "codex-gpt-image",
        "User-Agent": "codex-gpt-image-skill/0.1.0",
    }
    if auth.account_id:
        headers["ChatGPT-Account-ID"] = auth.account_id
    return headers


def post_image_json(
    url: str,
    auth: CodexAuth,
    body: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        method="POST",
        headers=codex_image_headers(auth),
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            text = resp.read(MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise CliError(f"Codex Images request failed (HTTP {exc.code}): {detail}") from exc
    except error.URLError as exc:
        raise CliError(f"Codex Images request failed: {exc.reason}") from exc
    try:
        response = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError(f"Expected JSON image response, got: {text[:500]}") from exc
    if not isinstance(response, dict):
        raise CliError("Expected JSON object image response.")
    return response


def extract_image_payloads(response: dict[str, Any]) -> list[tuple[str, str | None]]:
    error_obj = response.get("error")
    if isinstance(error_obj, dict):
        message = error_obj.get("message") or error_obj.get("code")
        raise CliError(str(message or "OpenAI Codex image generation failed."))

    data = response.get("data")
    if not isinstance(data, list):
        raise CliError("Image response did not include a data array.")
    payloads: list[tuple[str, str | None]] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("b64_json"), str):
            revised_prompt = item.get("revised_prompt")
            payloads.append(
                (
                    item["b64_json"],
                    revised_prompt if isinstance(revised_prompt, str) else None,
                )
            )
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
        print(f"Images base URL: {payload['base_url']}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    prompt = read_prompt(args.prompt, args.prompt_file)
    image_paths = args.image or []
    if args.count < 1 or args.count > MAX_COUNT:
        raise CliError(f"--count must be between 1 and {MAX_COUNT}.")
    output_format = normalize_output_format(args.output_format)
    operation, image_model, body = build_image_body(args, prompt, image_paths)
    url = image_endpoint_url(args.base_url, operation)

    if args.dry_run:
        summary = {
            "url": url,
            "auth": "Codex OAuth access token (not loaded during dry-run)",
            "operation": operation,
            "image_model": image_model,
            "size": body["size"],
            "quality": body.get("quality"),
            "output_format": output_format,
            "background": body.get("background"),
            "moderation": body.get("moderation"),
            "output_compression": body.get("output_compression"),
            "input_images": len(image_paths),
            "mask": bool(args.mask),
            "count": args.count,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    auth = load_or_login_codex_auth(args)
    start = time.time()
    response = post_image_json(url, auth, body, args.timeout)
    written = write_images(extract_image_payloads(response), args.out, output_format)
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
    auth.add_argument("--client-id", help="Override the Codex OAuth client id for device-code login.")
    auth.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    auth.add_argument("--json", action="store_true")
    auth.set_defaults(func=cmd_auth_status)

    login = sub.add_parser("login", help="Run OpenAI Codex device-code login and save ~/.codex/auth.json.")
    login.add_argument("--open-browser", action="store_true")
    login.add_argument("--client-id", help="Override the Codex OAuth client id for device-code login.")
    login.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    login.set_defaults(func=lambda args: 0 if login_device_code(args) else 1)

    gen = sub.add_parser("generate", help="Generate or edit an image through Codex OAuth.")
    gen.add_argument("--prompt", "-p")
    gen.add_argument("--prompt-file")
    gen.add_argument("--image", "-i", action="append", help="Reference/edit image path. Repeatable.")
    gen.add_argument("--mask", help="Mask image path for edits. Requires at least one --image.")
    gen.add_argument("--out", "-o", default="output/codex-gpt-image/output.png")
    gen.add_argument("--model", default=os.getenv("CODEX_GPT_IMAGE_MODEL", DEFAULT_IMAGE_MODEL))
    gen.add_argument("--size", default=DEFAULT_SIZE)
    gen.add_argument("--quality", default=DEFAULT_QUALITY, choices=sorted(SUPPORTED_QUALITIES))
    gen.add_argument("--output-format", default=DEFAULT_OUTPUT_FORMAT, choices=sorted(SUPPORTED_OUTPUT_FORMATS))
    gen.add_argument("--background", default=DEFAULT_BACKGROUND, choices=sorted(SUPPORTED_BACKGROUNDS))
    gen.add_argument("--moderation", default=DEFAULT_MODERATION, choices=sorted(SUPPORTED_MODERATIONS))
    gen.add_argument("--output-compression", type=int, help="Compression level 0-100. Only valid for jpeg/webp.")
    gen.add_argument("--user")
    gen.add_argument("--count", type=int, default=DEFAULT_COUNT, help="Number of images, 1-10.")
    gen.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    gen.add_argument("--base-url", default=None)
    gen.add_argument("--login-if-missing", action="store_true")
    gen.add_argument("--open-browser", action="store_true")
    gen.add_argument("--client-id", help="Override the Codex OAuth client id when --login-if-missing runs.")
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
