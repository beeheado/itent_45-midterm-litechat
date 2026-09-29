from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from typing import Literal

from django.conf import settings
from openai import AsyncOpenAI


MAX_SSE_EVENT_BYTES = 1024 * 1024


class ProxyStreamError(Exception):
    """A safely reportable provider response or SSE parsing failure."""


@dataclass(frozen=True)
class StreamEvent:
    kind: Literal["delta", "usage", "done"]
    content: str | None = None
    reasoning_content: str | None = None
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class SSEByteParser:
    """Incrementally frame SSE data fields across arbitrary network chunks."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._data_lines: list[bytes] = []
        self._event_size = 0

    def feed(self, chunk: bytes) -> list[bytes]:
        if not isinstance(chunk, bytes):
            raise ProxyStreamError("Provider stream yielded a non-byte chunk")
        self._buffer.extend(chunk)
        events = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                if len(self._buffer) + self._event_size > MAX_SSE_EVENT_BYTES:
                    raise ProxyStreamError("Provider SSE event exceeded the size limit")
                break
            line = bytes(self._buffer[:newline])
            del self._buffer[: newline + 1]
            event = self._consume_line(line)
            if event is not None:
                events.append(event)
        return events

    def finish(self) -> list[bytes]:
        events = []
        if self._buffer:
            event = self._consume_line(bytes(self._buffer))
            self._buffer.clear()
            if event is not None:
                events.append(event)
        if self._data_lines:
            events.append(self._take_event())
        return events

    def _consume_line(self, line: bytes) -> bytes | None:
        if line.endswith(b"\r"):
            line = line[:-1]
        if not line:
            return self._take_event() if self._data_lines else None
        if line.startswith(b":"):
            return None
        field, separator, value = line.partition(b":")
        if field != b"data" or not separator:
            return None
        if value.startswith(b" "):
            value = value[1:]
        self._event_size += len(value)
        if self._event_size > MAX_SSE_EVENT_BYTES:
            raise ProxyStreamError("Provider SSE event exceeded the size limit")
        self._data_lines.append(value)
        return None

    def _take_event(self) -> bytes:
        payload = b"\n".join(self._data_lines)
        self._data_lines.clear()
        self._event_size = 0
        return payload


def _token_count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _events_from_data(data: bytes) -> list[StreamEvent]:
    if data.strip() == b"[DONE]":
        return [StreamEvent(kind="done")]
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProxyStreamError("Provider returned malformed SSE JSON") from None
    if not isinstance(payload, dict):
        raise ProxyStreamError("Provider SSE event must contain a JSON object")
    if "error" in payload:
        raise ProxyStreamError("Provider returned an SSE error event")

    events = []
    choices = payload.get("choices", [])
    if not isinstance(choices, list):
        raise ProxyStreamError("Provider SSE choices field must be a list")
    for choice in choices:
        if not isinstance(choice, dict):
            raise ProxyStreamError("Provider SSE choice must be an object")
        delta = choice.get("delta") or {}
        if not isinstance(delta, dict):
            raise ProxyStreamError("Provider SSE delta must be an object")
        content = delta.get("content")
        reasoning = delta.get("reasoning_content")
        finish_reason = choice.get("finish_reason")
        if content is not None and not isinstance(content, str):
            raise ProxyStreamError("Provider content delta must be text or null")
        if reasoning is not None and not isinstance(reasoning, str):
            raise ProxyStreamError("Provider reasoning delta must be text or null")
        if finish_reason is not None and not isinstance(finish_reason, str):
            raise ProxyStreamError("Provider finish reason must be text or null")
        if content is not None or reasoning is not None or finish_reason is not None:
            events.append(
                StreamEvent(
                    kind="delta",
                    content=content,
                    reasoning_content=reasoning,
                    finish_reason=finish_reason,
                )
            )

    usage = payload.get("usage")
    if isinstance(usage, dict):
        events.append(
            StreamEvent(
                kind="usage",
                prompt_tokens=_token_count(usage.get("prompt_tokens")),
                completion_tokens=_token_count(usage.get("completion_tokens")),
            )
        )
    return events


async def parse_sse_chunks(chunks: AsyncIterable[bytes]) -> AsyncIterator[StreamEvent]:
    parser = SSEByteParser()
    done = False
    async for chunk in chunks:
        for data in parser.feed(chunk):
            for event in _events_from_data(data):
                yield event
                if event.kind == "done":
                    done = True
                    return
    for data in parser.finish():
        for event in _events_from_data(data):
            yield event
            if event.kind == "done":
                done = True
                return
    if not done:
        raise ProxyStreamError("Provider stream ended before the [DONE] sentinel")


async def stream_completion(
    messages: list[dict[str, str]],
    model_id: str,
    *,
    max_completion_tokens: int,
) -> AsyncIterator[StreamEvent]:
    api_key = settings.OPENAI_PROXY_KEY
    if not api_key:
        raise ProxyStreamError("Provider API key is not configured")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=settings.LITECHAT_PROXY_BASE_URL,
        max_retries=0,
        timeout=90,
    )
    try:
        async with client.chat.completions.with_streaming_response.create(
            model=model_id,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            max_completion_tokens=max_completion_tokens,
        ) as response:
            if response.status_code >= 400:
                raise ProxyStreamError(
                    f"Provider returned HTTP {response.status_code}"
                )
            async for event in parse_sse_chunks(response.iter_bytes()):
                yield event
    except asyncio.CancelledError:
        raise
    except ProxyStreamError:
        raise
    except Exception as error:
        raise ProxyStreamError("Provider streaming request failed") from error
    finally:
        await client.close()
