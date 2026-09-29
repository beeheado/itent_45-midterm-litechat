#!/usr/bin/env python3
"""Capture a real LiteChat model list and raw streaming completion."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://proxy.litechat.ai/v1"
MODELS_ENDPOINT = f"{BASE_URL}/models"
COMPLETIONS_ENDPOINT = f"{BASE_URL}/chat/completions"
DEFAULT_FIXTURE = ROOT / "tests/fixtures/provider_stream.sse"
ALLOWED_RESPONSE_HEADERS = {
    "content-type",
    "date",
    "openai-processing-ms",
    "request-id",
    "retry-after",
    "server",
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-request-id",
}
MAX_MODELS_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_STREAM_BYTES = 2 * 1024 * 1024


class CaptureError(Exception):
    """An expected, safely reportable provider or configuration failure."""

    def __init__(self, message: str, diagnostic: dict[str, object] | None = None):
        super().__init__(message)
        self.diagnostic = diagnostic


class RejectRedirectHandler(HTTPRedirectHandler):
    """Avoid forwarding the bearer token to a redirect target."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def open_url(request: Request, timeout: int):
    return build_opener(RejectRedirectHandler).open(request, timeout=timeout)


def read_api_key(env_path: Path) -> str:
    if not env_path.is_file():
        raise CaptureError(f"Credential file not found: {env_path}")

    for line_number, raw_line in enumerate(
        env_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()

        name, separator, value = line.partition("=")
        if not separator or name.strip() != "LITECHAT_API_KEY":
            continue

        value = value.strip()
        if value[:1] in ("'", '"'):
            quote = value[0]
            end = value.find(quote, 1)
            if end == -1:
                raise CaptureError(
                    f"Malformed LITECHAT_API_KEY value on .env line {line_number}"
                )
            trailing = value[end + 1 :].strip()
            if trailing and not trailing.startswith("#"):
                raise CaptureError(
                    f"Malformed LITECHAT_API_KEY value on .env line {line_number}"
                )
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()

        if not value:
            raise CaptureError("LITECHAT_API_KEY is empty in .env")
        return value

    raise CaptureError("LITECHAT_API_KEY was not found in .env")


def sanitize_headers(headers: object) -> dict[str, str]:
    result: dict[str, str] = {}
    items = getattr(headers, "items", None)
    if not callable(items):
        return result
    for name, value in items():
        normalized_name = name.lower()
        if normalized_name in ALLOWED_RESPONSE_HEADERS:
            result[normalized_name] = (
                str(value).replace("\r", "").replace("\n", "")[:500]
            )
    return result


def safe_http_failure(method: str, endpoint: str, error: HTTPError) -> CaptureError:
    headers = sanitize_headers(error.headers)
    suffix = (
        f"; sanitized_headers={json.dumps(headers, sort_keys=True)}" if headers else ""
    )
    return CaptureError(
        f"{method} {endpoint} returned HTTP {error.code}{suffix}",
        {
            "method": method,
            "endpoint": endpoint,
            "status": error.code,
            "sanitized_headers": headers,
        },
    )


def fetch_models(api_key: str) -> tuple[list[dict[str, object]], int, dict[str, str]]:
    request = Request(
        MODELS_ENDPOINT,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "HeavyChat-provider-capture/1.0",
        },
        method="GET",
    )
    try:
        with open_url(request, timeout=45) as response:
            status = response.status
            headers = sanitize_headers(response.headers)
            body = response.read(MAX_MODELS_RESPONSE_BYTES + 1)
    except HTTPError as error:
        raise safe_http_failure("GET", MODELS_ENDPOINT, error) from None
    except (URLError, TimeoutError, OSError) as error:
        raise CaptureError(f"GET {MODELS_ENDPOINT} failed ({type(error).__name__})") from None

    if len(body) > MAX_MODELS_RESPONSE_BYTES:
        raise CaptureError("Models response exceeded the 2 MiB safety limit")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CaptureError("Models endpoint returned invalid JSON") from None

    records = payload.get("data", payload.get("models")) if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise CaptureError("Models response did not contain a data/models list")
    models = [record for record in records if isinstance(record, dict)]
    return models, status, headers


def model_id(record: dict[str, object]) -> str | None:
    value = record.get("id")
    return value if isinstance(value, str) and value else None


def is_active(record: dict[str, object]) -> bool:
    if record.get("active") is False:
        return False
    status = record.get("status")
    return not (isinstance(status, str) and status.lower() in {"disabled", "inactive"})


def choose_model(models: list[dict[str, object]], requested_model: str | None) -> tuple[str, list[str]]:
    available = [model_id(record) for record in models if model_id(record)]
    active = [
        model_id(record)
        for record in models
        if model_id(record) and is_active(record)
    ]
    if not active:
        raise CaptureError("Models endpoint returned no active model IDs")
    if requested_model:
        if requested_model not in active:
            raise CaptureError("Requested model is not listed as active by the models endpoint")
        return requested_model, [model for model in available if model is not None]
    return active[0], [model for model in available if model is not None]


def read_stream(api_key: str, model: str) -> tuple[bytes, int, dict[str, str]]:
    request_body = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the word READY."}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": 8,
        "temperature": 0,
    }
    request = Request(
        COMPLETIONS_ENDPOINT,
        data=json.dumps(request_body, separators=(",", ":")).encode("utf-8"),
        headers={
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "HeavyChat-provider-capture/1.0",
        },
        method="POST",
    )
    chunks: list[bytes] = []
    total_bytes = 0
    try:
        with open_url(request, timeout=90) as response:
            status = response.status
            headers = sanitize_headers(response.headers)
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_STREAM_BYTES:
                    raise CaptureError("SSE response exceeded the 2 MiB safety limit")
                chunks.append(chunk)
    except HTTPError as error:
        raise safe_http_failure("POST", COMPLETIONS_ENDPOINT, error) from None
    except (URLError, TimeoutError, OSError) as error:
        raise CaptureError(
            f"POST {COMPLETIONS_ENDPOINT} failed ({type(error).__name__})"
        ) from None

    stream = b"".join(chunks)
    if not stream:
        raise CaptureError("Completion endpoint returned an empty stream")
    return stream, status, headers


def inspect_stream(
    stream: bytes,
) -> tuple[int, list[dict[str, object]], bool]:
    data_events = 0
    usage_objects: list[dict[str, object]] = []
    for line in stream.splitlines():
        if not line.startswith(b"data:"):
            continue
        data = line[5:].strip()
        if not data or data == b"[DONE]":
            continue
        try:
            payload = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        data_events += 1
        if isinstance(payload, dict) and isinstance(payload.get("usage"), dict):
            usage = payload["usage"]
            usage_objects.append(
                {
                    key: usage[key]
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                    if isinstance(usage.get(key), int)
                }
            )
    done_found = any(
        line.startswith(b"data:") and line[5:].strip() == b"[DONE]"
        for line in stream.splitlines()
    )
    return data_events, usage_objects, done_found


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def write_failure_metadata(
    output_path: Path, error: CaptureError, model: str | None = None
) -> None:
    if not error.diagnostic:
        return
    metadata_path = output_path.with_name("provider_stream_meta.json")
    failure = error.diagnostic
    metadata = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "capture_client": {
            "transport": "urllib.request",
            "python_version": platform.python_version(),
        },
        "capture_status": "failed",
        "endpoint": failure["endpoint"],
        "method": failure["method"],
        "model": model,
        "status": failure["status"],
        "sanitized_headers": failure["sanitized_headers"],
        "stream_fixture_written": False,
    }
    atomic_write(
        metadata_path,
        (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def capture(output_path: Path, requested_model: str | None) -> Path:
    try:
        api_key = read_api_key(ROOT / ".env")
        models, models_status, models_headers = fetch_models(api_key)
    except CaptureError as error:
        write_failure_metadata(output_path, error)
        raise
    selected_model, returned_models = choose_model(models, requested_model)

    print("Models returned by LiteChat:")
    for item in models:
        identifier = model_id(item)
        if identifier:
            state = "active" if is_active(item) else "inactive"
            print(f"  {identifier} ({state})")
    print(f"Selected model: {selected_model}")

    try:
        stream, completion_status, completion_headers = read_stream(api_key, selected_model)
    except CaptureError as error:
        write_failure_metadata(output_path, error, selected_model)
        raise
    event_count, usage_objects, done_found = inspect_stream(stream)
    atomic_write(output_path, stream)

    metadata = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "capture_client": {
            "transport": "urllib.request",
            "python_version": platform.python_version(),
        },
        "models_endpoint": MODELS_ENDPOINT,
        "models_status": models_status,
        "models_headers": models_headers,
        "models_returned": returned_models,
        "completion_endpoint": COMPLETIONS_ENDPOINT,
        "model": selected_model,
        "status": completion_status,
        "sanitized_headers": completion_headers,
        "request_options": {
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": 8,
            "temperature": 0,
        },
        "sse_bytes": len(stream),
        "sse_sha256": hashlib.sha256(stream).hexdigest(),
        "data_event_count": event_count,
        "usage_objects": usage_objects,
        "done_sentinel_found": done_found,
    }
    metadata_path = output_path.with_name("provider_stream_meta.json")
    atomic_write(
        metadata_path,
        (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )

    print(f"Captured {len(stream)} raw SSE bytes in {output_path}")
    print(f"Metadata written to {metadata_path}")
    print(
        f"SSE data events: {event_count}; "
        f"final usage object(s): {len(usage_objects)}"
    )
    print(f"[DONE] sentinel present: {done_found}")
    return metadata_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        help="active model ID from the proxy's /models response (default: first active model)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_FIXTURE,
        help=f"raw SSE fixture path (default: {DEFAULT_FIXTURE})",
    )
    args = parser.parse_args()
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    try:
        capture(output_path, args.model)
    except CaptureError as error:
        print(f"Capture failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
