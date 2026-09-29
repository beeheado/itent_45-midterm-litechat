#!/usr/bin/env python3
"""Capture a raw LiteChat Chat Completions stream."""

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
BASE_URL = "https://proxy.litechat.ai/openai/v1"
COMPLETIONS_ENDPOINT = f"{BASE_URL}/chat/completions"
DEFAULT_MODEL = "gpt-5.6-luna"
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
) -> dict[str, object]:
    data_events = 0
    usage_objects: list[dict[str, object]] = []
    reasoning_content_deltas = 0
    content_deltas = 0
    finish_reasons: list[str] = []
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
        if not isinstance(payload, dict):
            continue
        choices = payload.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    if delta.get("reasoning_content") is not None:
                        reasoning_content_deltas += 1
                    if delta.get("content") is not None:
                        content_deltas += 1
                finish_reason = choice.get("finish_reason")
                if (
                    isinstance(finish_reason, str)
                    and finish_reason not in finish_reasons
                ):
                    finish_reasons.append(finish_reason)
        if isinstance(payload.get("usage"), dict):
            usage = payload["usage"]
            usage_record = {
                key: usage[key]
                for key in (
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "prompt_cache_hit_tokens",
                    "prompt_cache_miss_tokens",
                )
                if isinstance(usage.get(key), int)
            }
            completion_details = usage.get("completion_tokens_details")
            if isinstance(completion_details, dict) and isinstance(
                completion_details.get("reasoning_tokens"), int
            ):
                usage_record["reasoning_tokens"] = completion_details[
                    "reasoning_tokens"
                ]
            usage_objects.append(usage_record)
    done_found = any(
        line.startswith(b"data:") and line[5:].strip() == b"[DONE]"
        for line in stream.splitlines()
    )
    return {
        "data_event_count": data_events,
        "reasoning_content_delta_count": reasoning_content_deltas,
        "content_delta_count": content_deltas,
        "finish_reasons": finish_reasons,
        "usage_objects": usage_objects,
        "done_sentinel_found": done_found,
    }


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


def capture(output_path: Path, model: str) -> Path:
    try:
        api_key = read_api_key(ROOT / ".env")
    except CaptureError as error:
        write_failure_metadata(output_path, error)
        raise
    print(f"Using model: {model}")

    try:
        stream, completion_status, completion_headers = read_stream(
            api_key, model
        )
    except CaptureError as error:
        write_failure_metadata(output_path, error, model)
        raise
    observations = inspect_stream(stream)
    atomic_write(output_path, stream)

    metadata = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "capture_client": {
            "transport": "urllib.request",
            "python_version": platform.python_version(),
        },
        "endpoint": COMPLETIONS_ENDPOINT,
        "model": model,
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
        **observations,
    }
    metadata_path = output_path.with_name("provider_stream_meta.json")
    atomic_write(
        metadata_path,
        (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )

    print(f"Captured {len(stream)} raw SSE bytes in {output_path}")
    print(f"Metadata written to {metadata_path}")
    print(
        f"SSE data events: {observations['data_event_count']}; "
        f"final usage object(s): {len(observations['usage_objects'])}"
    )
    print(f"[DONE] sentinel present: {observations['done_sentinel_found']}")
    return metadata_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"model ID to capture (default: {DEFAULT_MODEL})",
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
