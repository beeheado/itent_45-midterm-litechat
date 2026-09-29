from __future__ import annotations

import asyncio
import json
import logging
from decimal import Decimal
from uuid import uuid4

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpResponse,
    HttpResponseNotAllowed,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.models import BillingAccount, ChatMessage, ChatSession, MemoryItem, ModelCatalog, UserProfile
from core.services import InsufficientCredits, LedgerError, deposit_credits
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
MODEL_PRESENTATION = {
    ModelCatalog.Tier.SOL: (
        "Premium",
        "OpenAI's deepest-reasoning model for complex coding and analysis.",
    ),
    ModelCatalog.Tier.TERRA: (
        "Standard",
        "OpenAI's balanced model for everyday coding, reasoning, and professional work.",
    ),
    ModelCatalog.Tier.LUNA: (
        "Fast / Low-cost",
        "OpenAI's fast, low-cost model for everyday questions and quick drafts.",
    ),
}
MODEL_TIER_ORDER = {
    ModelCatalog.Tier.SOL: 0,
    ModelCatalog.Tier.TERRA: 1,
    ModelCatalog.Tier.LUNA: 2,
}


def _display_name(user) -> str:
    return user.get_full_name().strip() or user.get_username()


def _default_billing_account(user) -> BillingAccount:
    account = BillingAccount.objects.filter(user=user).order_by("pk").first()
    if account:
        return account
    return BillingAccount.objects.create(
        user=user,
        name=f"[Personal] {_display_name(user)}",
    )


def _shell_context(request, active_session=None) -> dict[str, object]:
    accounts = list(BillingAccount.objects.filter(user=request.user).order_by("pk"))
    if not accounts:
        accounts = [_default_billing_account(request.user)]
    current_account = (
        active_session.billing_account if active_session else accounts[0]
    )
    return {
        "display_name": _display_name(request.user),
        "billing_accounts": accounts,
        "current_account": current_account,
        "balance_usd": Decimal(current_account.credit_balance) / Decimal(100),
        "sessions": ChatSession.objects.filter(owner=request.user)
        .select_related("model", "billing_account")
        .order_by("-updated_at", "-pk")[:15],
        "active_session": active_session,
    }


@login_required
def home(request):
    context = _shell_context(request)
    if context["sessions"]:
        return redirect("chat:session-detail", session_id=context["sessions"][0].pk)
    return render(request, "chat/home.html", context)


@login_required
def session_detail(request, session_id: int):
    session = get_object_or_404(
        ChatSession.objects.select_related("billing_account", "model"),
        pk=session_id,
        owner=request.user,
    )
    context = _shell_context(request, session)
    context["session"] = session
    context["messages"] = session.messages.filter(
        status=ChatMessage.Status.COMPLETE
    ).order_by("created_at", "pk")
    return render(request, "chat/session.html", context)


@login_required
def model_selector(request):
    context = _shell_context(request)
    models = ModelCatalog.objects.filter(
        provider=ModelCatalog.Provider.OPENAI,
        is_active=True,
    )
    context["model_cards"] = [
        {
            "model": model,
            "badge": MODEL_PRESENTATION[model.tier][0],
            "description": MODEL_PRESENTATION[model.tier][1],
        }
        for model in sorted(models, key=lambda item: MODEL_TIER_ORDER.get(item.tier, 99))
    ]
    return render(request, "chat/partials/model_selector.html", context)


@login_required
def close_model_selector(request):
    return HttpResponse("")


@login_required
@require_POST
def create_session(request):
    account = BillingAccount.objects.filter(
        pk=request.POST.get("billing_account_id"),
        user=request.user,
    ).first()
    model = ModelCatalog.objects.filter(
        pk=request.POST.get("model_id"),
        provider=ModelCatalog.Provider.OPENAI,
        is_active=True,
    ).first()
    if account is None or model is None:
        return HttpResponse("Choose an available model and your own billing account.", status=400)
    session = ChatSession(
        owner=request.user,
        billing_account=account,
        model=model,
        title=model.display_name,
    )
    session.full_clean()
    session.save()
    response = HttpResponse(status=204)
    if request.headers.get("HX-Request"):
        response["HX-Redirect"] = reverse("chat:session-detail", args=(session.pk,))
        return response
    return redirect("chat:session-detail", session_id=session.pk)


@login_required
def profile(request):
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    context = _shell_context(request)
    context.update(
        {
            "user_profile": user_profile,
            "memory_items": user_profile.memory_items.order_by("created_at", "pk"),
            "member_since": request.user.date_joined,
            "user_id": request.user.pk,
        }
    )
    return render(request, "chat/profile.html", context)


@login_required
@require_POST
def save_global_prompt(request):
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    prompt = request.POST.get("global_system_prompt", "")
    if len(prompt) > 100_000:
        return HttpResponse("Prompt is too long.", status=400)
    user_profile.global_system_prompt = prompt
    user_profile.save(update_fields=("global_system_prompt",))
    return render(request, "chat/partials/prompt_saved.html")


@login_required
@require_POST
def toggle_ai_memories(request):
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    user_profile.ai_memories_enabled = request.POST.get("ai_memories_enabled") == "on"
    user_profile.save(update_fields=("ai_memories_enabled",))
    return render(
        request,
        "chat/partials/memory_toggle.html",
        {"user_profile": user_profile},
    )


@login_required
@require_POST
def add_memory_item(request):
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    category = request.POST.get("category")
    content = request.POST.get("content", "").strip()
    if category not in MemoryItem.Category.values or not content or len(content) > 10_000:
        return HttpResponse("Choose a category and enter a memory under 10,000 characters.", status=400)
    MemoryItem.objects.create(
        user_profile=user_profile,
        category=category,
        content=content,
    )
    return render(
        request,
        "chat/partials/memory_list.html",
        {"memory_items": user_profile.memory_items.order_by("created_at", "pk")},
    )


@login_required
@require_POST
def delete_memory_item(request, memory_id: int):
    memory = get_object_or_404(
        MemoryItem,
        pk=memory_id,
        user_profile__user=request.user,
    )
    memory.delete()
    return HttpResponse("")


@login_required
@require_POST
def mock_top_up(request):
    account = get_object_or_404(
        BillingAccount,
        pk=request.POST.get("billing_account_id"),
        user=request.user,
    )
    deposit_credits(account, 500, f"mock-top-up:{uuid4().hex}")
    account.refresh_from_db()
    return render(
        request,
        "chat/partials/balance_badge.html",
        {
            "current_account": account,
            "balance_usd": Decimal(account.credit_balance) / Decimal(100),
        },
    )


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
