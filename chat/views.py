from __future__ import annotations

import asyncio
import json
import logging

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse, StreamingHttpResponse

from core.services import InsufficientCredits, LedgerError
from .services.context import (
    InactiveModel,
    SessionNotAvailable,
    estimate_completion_tokens,
    fail_generation,
    finalize_generation,
    prepare_generation,
    retain_settlement_failure,
)
from .services.proxy_stream import ProxyStreamError, stream_completion


logger = logging.getLogger(__name__)


def _sse_event(name: str, payload: dict[str, object]) -> bytes:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {name}\ndata: {data}\n\n".encode("utf-8")


async def _abort_generation(context, partial_content: str) -> None:
    await sync_to_async(fail_generation, thread_sensitive=True)(context, partial_content)


async def _stream_response(context):
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    provider_usage: tuple[int, int] | None = None
    saw_done = False
    finalized = False
    cleaned_up = False
    retained_for_reconciliation = False

    try:
        async for event in stream_completion(
            context.messages,
            context.model_id,
            max_completion_tokens=context.max_completion_tokens,
        ):
            if event.kind == "delta":
                if event.reasoning_content is not None:
                    reasoning_parts.append(event.reasoning_content)
                if event.content is not None:
                    content_parts.append(event.content)
                    if event.content:
                        yield _sse_event("delta", {"content": event.content})
            elif event.kind == "usage":
                if event.prompt_tokens is not None and event.completion_tokens is not None:
                    provider_usage = (event.prompt_tokens, event.completion_tokens)
            elif event.kind == "done":
                saw_done = True

        if not saw_done:
            raise ProxyStreamError("Provider stream did not finish with [DONE]")

        content = "".join(content_parts)
        reasoning = "".join(reasoning_parts)
        if provider_usage is None:
            prompt_tokens = context.estimated_prompt_tokens
            completion_tokens = estimate_completion_tokens(
                content + reasoning,
                context.model_id,
            )
            is_estimated = True
        else:
            prompt_tokens, completion_tokens = provider_usage
            is_estimated = False

        try:
            result = await sync_to_async(finalize_generation, thread_sensitive=True)(
                context,
                content=content,
                reasoning_content=reasoning,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                is_estimated=is_estimated,
            )
        except Exception:
            retained_for_reconciliation = True
            await sync_to_async(retain_settlement_failure, thread_sensitive=True)(
                context,
                content=content,
                reasoning_content=reasoning,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            yield _sse_event(
                "error",
                {
                    "code": "settlement_failed",
                    "message": "The response completed, but usage needs reconciliation.",
                },
            )
            return

        finalized = True
        yield _sse_event(
            "settled",
            {
                "credit_balance": result.credit_balance,
                "credit_debit": result.usage.credit_debit,
                "cost_usd": str(result.usage.cost_usd),
                "is_estimated": result.usage.is_estimated,
            },
        )
    except asyncio.CancelledError:
        if not finalized and not retained_for_reconciliation:
            await _abort_generation(context, "".join(content_parts))
            cleaned_up = True
        raise
    except Exception:
        if not finalized and not retained_for_reconciliation:
            try:
                await _abort_generation(context, "".join(content_parts))
                cleaned_up = True
            except Exception:
                logger.error("Unable to release reservation after stream failure")
        yield _sse_event(
            "error",
            {"code": "upstream_failed", "message": "The completion stream failed."},
        )
    finally:
        if not finalized and not cleaned_up and not retained_for_reconciliation:
            try:
                await _abort_generation(context, "".join(content_parts))
            except Exception:
                logger.error("Unable to release reservation when stream closed")


async def stream_chat_completion(request, session_id: int):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    user = await request.auser()
    if not user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    if not settings.OPENAI_PROXY_KEY:
        return JsonResponse({"error": "Provider is not configured"}, status=503)
    try:
        payload = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "Expected a JSON request body"}, status=400)
    if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
        return JsonResponse({"error": "content must be a string"}, status=400)

    try:
        context = await sync_to_async(prepare_generation, thread_sensitive=True)(
            user.pk,
            session_id,
            payload["content"],
        )
    except InsufficientCredits:
        return HttpResponse(
            _sse_event("error", {"code": "insufficient_credits"}),
            status=402,
            content_type="text/event-stream",
        )
    except LedgerError:
        return JsonResponse({"error": "Unable to reserve credits"}, status=409)
    except SessionNotAvailable:
        return JsonResponse({"error": "Chat session not found"}, status=404)
    except InactiveModel:
        return JsonResponse({"error": "Selected model is inactive"}, status=409)
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)

    response = StreamingHttpResponse(
        _stream_response(context),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
