#!/usr/bin/env python3
"""CLI for the draw.hugusir.top OpenAI-compatible image relay."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import mimetypes
import os
import stat
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://draw.hugusir.top/api/v1"
DEFAULT_AUTH_FILE = Path.home() / ".codex" / "nano-banana-relay-auth.json"
DEFAULT_MODEL = "Nano Banana2"
SUCCESS_STATES = {"success", "succeeded", "completed", "complete", "done"}
FAILURE_STATES = {"failed", "failure", "error", "cancelled", "canceled"}
IMAGE_KEYS = {"url", "b64_json", "b64Json"}


class ApiError(RuntimeError):
    """Readable API or transport error."""


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def sanitize_for_output(value: Any) -> Any:
    """Keep terminal JSON useful without printing multi-megabyte image payloads."""
    value = parse_json_string(value)
    if isinstance(value, list):
        return [sanitize_for_output(item) for item in value]
    if not isinstance(value, dict):
        return value
    sanitized: dict[str, Any] = {}
    for key, child in value.items():
        if key in {"b64_json", "b64Json"} and isinstance(child, str):
            sanitized[key] = f"<base64 omitted: {len(child)} characters>"
        else:
            sanitized[key] = sanitize_for_output(child)
    return sanitized


def auth_value(auth: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = auth.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def load_auth_file(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        return {}
    if not path.is_file():
        raise ApiError(f"Auth path is not a file: {path}")
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise ApiError(f"Auth file permissions are too open ({mode:04o}); run: chmod 600 {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiError(f"Cannot read auth file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ApiError(f"Auth file must contain one JSON object: {path}")
    return payload


def get_api_key(auth: dict[str, Any], cli_value: str | None) -> str:
    key = (
        auth_value(auth, "NANO_BANANA_API_KEY", "OPENAI_API_KEY", "api_key")
        or cli_value
        or os.environ.get("NANO_BANANA_API_KEY", "")
    )
    if not key:
        raise ApiError(
            "Missing API key. Fill ~/.codex/nano-banana-relay-auth.json or set NANO_BANANA_API_KEY."
        )
    return key


def normalize_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ApiError(f"Invalid base URL: {value!r}")
    return value


def get_origin(base_url: str) -> str:
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def get_base_url(auth: dict[str, Any], configured: str | None) -> str:
    value = (
        auth_value(auth, "NANO_BANANA_BASE_URL", "OPENAI_BASE_URL", "base_url")
        or configured
        or os.environ.get("NANO_BANANA_BASE_URL")
        or DEFAULT_BASE_URL
    )
    return normalize_base_url(value)


def get_async_base_url(base_url: str, auth: dict[str, Any], configured: str | None) -> str:
    auth_configured = auth_value(auth, "NANO_BANANA_ASYNC_BASE_URL", "async_base_url")
    if auth_configured:
        return normalize_base_url(auth_configured)
    if configured:
        return normalize_base_url(configured)
    env_value = os.environ.get("NANO_BANANA_ASYNC_BASE_URL")
    if env_value:
        return normalize_base_url(env_value)
    return f"{get_origin(base_url)}/api/ai-jobs"


def auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "nano-banana-relay-skill/1.0",
    }


def decode_json_body(raw: bytes, content_type: str | None = None) -> Any:
    if not raw:
        return {}
    charset = "utf-8"
    if content_type and "charset=" in content_type:
        charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
    text = raw.decode(charset, errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ApiError(f"Expected JSON response, received: {text[:1000]}") from exc


def embedded_error(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if error:
        if isinstance(error, dict):
            return str(error.get("message") or compact_json(error))
        return str(error)
    code = payload.get("code")
    if code not in (None, 0, "0", 200, "200") and payload.get("data") is None:
        return str(payload.get("msg") or payload.get("message") or compact_json(payload))
    return None


def request_json(
    method: str,
    url: str,
    api_key: str,
    timeout: float,
    payload: Any | None = None,
    body: bytes | None = None,
    content_type: str | None = None,
) -> Any:
    headers = auth_headers(api_key)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        content_type = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            result = decode_json_body(response.read(), response.headers.get("Content-Type"))
    except HTTPError as exc:
        raw = exc.read()
        try:
            detail = decode_json_body(raw, exc.headers.get("Content-Type"))
            message = embedded_error(detail) or compact_json(detail)
        except ApiError:
            message = raw.decode("utf-8", errors="replace")[:2000]
        raise ApiError(f"HTTP {exc.code} from {url}: {message}") from exc
    except URLError as exc:
        raise ApiError(f"Request failed for {url}: {exc.reason}") from exc

    message = embedded_error(result)
    if message:
        raise ApiError(f"API error from {url}: {message}")
    return result


def parse_extra_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ApiError(f"--extra-json must be a JSON object: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ApiError("--extra-json must decode to a JSON object.")
    return parsed


def image_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": args.model,
        "prompt": args.prompt,
        "n": args.n,
        "size": args.size,
        "quality": args.quality,
        "response_format": args.response_format,
    }
    for key in ("style", "background", "output_format", "upscale"):
        value = getattr(args, key, None)
        if value is not None:
            payload[key] = value
    payload.update(parse_extra_json(args.extra_json))
    return payload


def validate_images(paths: Iterable[str]) -> list[Path]:
    resolved = [Path(path).expanduser().resolve() for path in paths]
    if not resolved:
        raise ApiError("At least one --image is required.")
    if len(resolved) > 8:
        raise ApiError("The relay accepts at most 8 reference images.")
    total = 0
    for path in resolved:
        if not path.is_file():
            raise ApiError(f"Reference image does not exist or is not a file: {path}")
        total += path.stat().st_size
    if total > 40 * 1024 * 1024:
        raise ApiError("Reference images exceed the documented 40 MB total limit.")
    return resolved


def multipart_body(fields: dict[str, Any], files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    boundary = f"----nano-banana-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    def add_line(value: str = "") -> None:
        chunks.append(value.encode("utf-8") + b"\r\n")

    for name, value in fields.items():
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            value = compact_json(value)
        add_line(f"--{boundary}")
        add_line(f'Content-Disposition: form-data; name="{name}"')
        add_line()
        add_line(str(value))

    for field_name, path in files:
        filename = path.name.replace('"', "_")
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        add_line(f"--{boundary}")
        add_line(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"')
        add_line(f"Content-Type: {mime_type}")
        add_line()
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")

    add_line(f"--{boundary}--")
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def parse_json_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def find_image_items(value: Any) -> list[dict[str, Any]] | None:
    value = parse_json_string(value)
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            if any(IMAGE_KEYS.intersection(item) for item in value):
                return value
        for item in value:
            found = find_image_items(item)
            if found:
                return found
        return None
    if not isinstance(value, dict):
        return None

    for key in ("data", "images"):
        items = value.get(key)
        if isinstance(items, list) and items and all(isinstance(item, dict) for item in items):
            if any(IMAGE_KEYS.intersection(item) for item in items):
                return items

    for key in ("responseBody", "response_body", "result", "output", "data", "job"):
        if key in value:
            found = find_image_items(value[key])
            if found:
                return found
    return None


def extension_for_item(item: dict[str, Any], output_format: str | None) -> str:
    url = item.get("url")
    if isinstance(url, str):
        suffix = Path(unquote(urlparse(url).path)).suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}:
            return suffix
    mime_type = str(item.get("mimeType") or item.get("mime_type") or "").lower()
    mime_extensions = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/avif": ".avif",
    }
    if mime_type in mime_extensions:
        return mime_extensions[mime_type]
    if output_format:
        return ".jpg" if output_format.lower() in {"jpg", "jpeg"} else f".{output_format.lower()}"
    return ".png"


def extension_for_bytes(data: bytes, fallback: str) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if len(data) >= 12 and data[4:12] in {b"ftypavif", b"ftypavis"}:
        return ".avif"
    return fallback


def unique_output_path(directory: Path, index: int, suffix: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = directory / f"nano-banana-{stamp}-{index:02d}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"nano-banana-{stamp}-{index:02d}-{counter}{suffix}"
        counter += 1
    return candidate


def download_url(url: str, destination: Path, api_key: str, origin: str, timeout: float) -> None:
    absolute_url = urljoin(f"{origin}/", url)
    headers = {"User-Agent": "nano-banana-relay-skill/1.0"}

    def run(current_headers: dict[str, str]) -> bytes:
        request = Request(absolute_url, headers=current_headers, method="GET")
        with urlopen(request, timeout=timeout) as response:
            return response.read()

    try:
        data = run(headers)
    except HTTPError as exc:
        same_origin = get_origin(absolute_url) == origin
        if exc.code not in {401, 403} or not same_origin:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise ApiError(f"Image download failed with HTTP {exc.code}: {detail}") from exc
        headers["Authorization"] = f"Bearer {api_key}"
        try:
            data = run(headers)
        except (HTTPError, URLError) as retry_exc:
            raise ApiError(f"Authenticated image download failed: {retry_exc}") from retry_exc
    except URLError as exc:
        raise ApiError(f"Image download failed: {exc.reason}") from exc

    destination.write_bytes(data)


def save_images(
    payload: Any,
    output_dir: str,
    output_format: str | None,
    api_key: str,
    origin: str,
    timeout: float,
) -> list[str]:
    items = find_image_items(payload)
    if not items:
        raise ApiError("The response did not contain any url or b64_json image entries.")
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []

    for index, item in enumerate(items, start=1):
        suffix = extension_for_item(item, output_format)
        encoded = item.get("b64_json") or item.get("b64Json")
        if encoded:
            encoded = str(encoded)
            if encoded.startswith("data:") and "," in encoded:
                encoded = encoded.split(",", 1)[1]
            try:
                decoded = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ApiError("Invalid Base64 image data in API response.") from exc
            destination = unique_output_path(directory, index, extension_for_bytes(decoded, suffix))
            destination.write_bytes(decoded)
        elif item.get("url"):
            destination = unique_output_path(directory, index, suffix)
            download_url(str(item["url"]), destination, api_key, origin, timeout)
        else:
            continue
        saved.append(str(destination))
    return saved


def candidate_dicts(value: Any) -> Iterable[dict[str, Any]]:
    value = parse_json_string(value)
    if isinstance(value, dict):
        yield value
        for key in ("data", "job", "result", "task"):
            child = value.get(key)
            if child is not None:
                yield from candidate_dicts(child)


def find_job_record(payload: Any) -> dict[str, Any]:
    records = list(candidate_dicts(payload))
    for record in records:
        if any(key in record for key in ("status", "state")):
            return record
    for record in records:
        if any(key in record for key in ("jobId", "job_id", "taskId", "task_id", "id")):
            return record
    return payload if isinstance(payload, dict) else {}


def find_job_id(payload: Any) -> str | None:
    for record in candidate_dicts(payload):
        for key in ("jobId", "job_id", "taskId", "task_id", "id"):
            value = record.get(key)
            if value is not None and str(value).strip():
                return str(value)
    return None


def job_status(payload: Any) -> str:
    record = find_job_record(payload)
    value = record.get("status", record.get("state", "unknown"))
    return str(value).strip().lower()


def job_error(payload: Any) -> str | None:
    record = find_job_record(payload)
    for key in ("errorMessage", "error_message", "message", "error"):
        value = record.get(key)
        if value:
            return compact_json(value) if isinstance(value, (dict, list)) else str(value)
    return None


def wait_for_job(
    async_base_url: str,
    job_id: str,
    api_key: str,
    request_timeout: float,
    wait_timeout: float,
    poll_interval: float,
) -> Any:
    deadline = time.monotonic() + wait_timeout
    status_url = f"{async_base_url}/{quote(job_id, safe='')}"
    previous = None

    while True:
        payload = request_json("GET", status_url, api_key, request_timeout)
        status = job_status(payload)
        if status != previous:
            print(f"Job {job_id}: {status}", file=sys.stderr, flush=True)
            previous = status
        if status in SUCCESS_STATES:
            return payload
        if status in FAILURE_STATES:
            raise ApiError(f"Job {job_id} failed: {job_error(payload) or compact_json(payload)}")
        if time.monotonic() >= deadline:
            raise ApiError(f"Timed out waiting for job {job_id}; last status was {status!r}.")
        time.sleep(max(0.2, poll_interval))


def add_generation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default=os.environ.get("NANO_BANANA_MODEL", DEFAULT_MODEL))
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--size", default="1:1")
    parser.add_argument("--quality", default="high")
    parser.add_argument("--style")
    parser.add_argument("--background")
    parser.add_argument("--response-format", choices=("url", "b64_json"), default="url")
    parser.add_argument("--output-format", choices=("png", "jpeg", "webp"))
    parser.add_argument("--upscale")
    parser.add_argument("--extra-json", help="Merge a forward-compatible JSON object into the request.")


def add_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--no-download", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--auth-file",
        default=os.environ.get("NANO_BANANA_AUTH_FILE", str(DEFAULT_AUTH_FILE)),
        help="Highest-priority auth JSON file.",
    )
    parser.add_argument("--api-key", help="Overridden by a non-empty key in the auth file.")
    parser.add_argument(
        "--base-url",
        help="Overridden by a non-empty base URL in the auth file.",
    )
    parser.add_argument("--async-base-url", help="Overridden by a non-empty async URL in the auth file.")
    parser.add_argument("--request-timeout", type=float, default=600.0)
    parser.add_argument(
        "--include-base64",
        action="store_true",
        help="Print full b64_json fields instead of compact placeholders.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("models", help="List models currently exposed by the relay.")

    generate = subparsers.add_parser("generate", help="Generate an image from text.")
    add_generation_arguments(generate)
    add_output_arguments(generate)
    generate.add_argument("--async", dest="async_mode", action="store_true")
    generate.add_argument("--wait", action="store_true", help="Wait for an async job and download its result.")
    generate.add_argument("--poll-interval", type=float, default=3.0)
    generate.add_argument("--wait-timeout", type=float, default=1200.0)

    edit = subparsers.add_parser("edit", help="Edit or compose one or more reference images.")
    add_generation_arguments(edit)
    add_output_arguments(edit)
    edit.add_argument("--image", action="append", required=True, help="Reference image; repeat up to 8 times.")
    edit.add_argument("--mask")

    status = subparsers.add_parser("status", help="Read one async job status.")
    status.add_argument("job_id")

    wait = subparsers.add_parser("wait", help="Poll an existing async job until completion.")
    wait.add_argument("job_id")
    add_output_arguments(wait)
    wait.add_argument("--output-format", choices=("png", "jpeg", "webp"))
    wait.add_argument("--poll-interval", type=float, default=3.0)
    wait.add_argument("--wait-timeout", type=float, default=1200.0)

    return parser


def command_models(args: argparse.Namespace, api_key: str, base_url: str) -> dict[str, Any]:
    response = request_json("GET", f"{base_url}/models", api_key, args.request_timeout)
    return {"response": response}


def command_generate(
    args: argparse.Namespace,
    api_key: str,
    base_url: str,
    async_base_url: str,
) -> dict[str, Any]:
    if args.n < 1:
        raise ApiError("--n must be at least 1.")
    payload = image_payload(args)
    use_async = args.async_mode or args.wait
    endpoint = f"{async_base_url}/images/generations" if use_async else f"{base_url}/images/generations"
    response = request_json("POST", endpoint, api_key, args.request_timeout, payload=payload)

    if use_async:
        job_id = find_job_id(response)
        if not job_id:
            raise ApiError(f"Async submission did not return a job ID: {compact_json(response)}")
        if not args.wait:
            return {"job_id": job_id, "response": response, "saved_files": []}
        response = wait_for_job(
            async_base_url,
            job_id,
            api_key,
            args.request_timeout,
            args.wait_timeout,
            args.poll_interval,
        )
    else:
        job_id = None

    saved = []
    if not args.no_download:
        saved = save_images(
            response,
            args.output_dir,
            args.output_format,
            api_key,
            get_origin(base_url),
            args.request_timeout,
        )
    result: dict[str, Any] = {"response": response, "saved_files": saved}
    if job_id:
        result["job_id"] = job_id
    return result


def command_edit(args: argparse.Namespace, api_key: str, base_url: str) -> dict[str, Any]:
    if args.n < 1:
        raise ApiError("--n must be at least 1.")
    images = validate_images(args.image)
    payload = image_payload(args)
    fields = {key: value for key, value in payload.items() if value is not None}
    image_field = "image" if len(images) == 1 else "image[]"
    files = [(image_field, path) for path in images]
    if args.mask:
        mask = Path(args.mask).expanduser().resolve()
        if not mask.is_file():
            raise ApiError(f"Mask does not exist or is not a file: {mask}")
        files.append(("mask", mask))
    body, content_type = multipart_body(fields, files)
    response = request_json(
        "POST",
        f"{base_url}/images/edits",
        api_key,
        args.request_timeout,
        body=body,
        content_type=content_type,
    )
    saved = []
    if not args.no_download:
        saved = save_images(
            response,
            args.output_dir,
            args.output_format,
            api_key,
            get_origin(base_url),
            args.request_timeout,
        )
    return {"response": response, "saved_files": saved}


def command_status(
    args: argparse.Namespace,
    api_key: str,
    async_base_url: str,
) -> dict[str, Any]:
    response = request_json(
        "GET",
        f"{async_base_url}/{quote(args.job_id, safe='')}",
        api_key,
        args.request_timeout,
    )
    return {"job_id": args.job_id, "status": job_status(response), "response": response}


def command_wait(
    args: argparse.Namespace,
    api_key: str,
    base_url: str,
    async_base_url: str,
) -> dict[str, Any]:
    response = wait_for_job(
        async_base_url,
        args.job_id,
        api_key,
        args.request_timeout,
        args.wait_timeout,
        args.poll_interval,
    )
    saved = []
    if not args.no_download:
        saved = save_images(
            response,
            args.output_dir,
            args.output_format,
            api_key,
            get_origin(base_url),
            args.request_timeout,
        )
    return {
        "job_id": args.job_id,
        "status": job_status(response),
        "response": response,
        "saved_files": saved,
    }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        auth = load_auth_file(args.auth_file)
        api_key = get_api_key(auth, args.api_key)
        base_url = get_base_url(auth, args.base_url)
        async_base_url = get_async_base_url(base_url, auth, args.async_base_url)

        if args.command == "models":
            result = command_models(args, api_key, base_url)
        elif args.command == "generate":
            result = command_generate(args, api_key, base_url, async_base_url)
        elif args.command == "edit":
            result = command_edit(args, api_key, base_url)
        elif args.command == "status":
            result = command_status(args, api_key, async_base_url)
        elif args.command == "wait":
            result = command_wait(args, api_key, base_url, async_base_url)
        else:
            parser.error(f"Unknown command: {args.command}")
            return 2
        print_json(result if args.include_base64 else sanitize_for_output(result))
        return 0
    except ApiError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
