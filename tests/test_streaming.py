import asyncio
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import AsyncClient
from django.urls import reverse

from chat.services.proxy_stream import (
    ProxyStreamError,
    StreamEvent,
    parse_sse_chunks,
    stream_completion,
)
from core.models import (
    BillingAccount,
    ChatMessage,
    ChatSession,
    CreditLedger,
    MemoryItem,
    ModelCatalog,
    UsageTransaction,
    UserProfile,
)
from core.services import deposit_credits


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "provider_stream.sse"


async def byte_chunks(data: bytes, size: int):
    for offset in range(0, len(data), size):
        yield data[offset : offset + size]


async def collect_events(iterator):
    return [event async for event in iterator]


@pytest.mark.django_db
def test_parser_reads_fixture_across_fragmented_bytes():
    raw = FIXTURE_PATH.read_bytes()
    events = asyncio.run(collect_events(parse_sse_chunks(byte_chunks(raw, 13))))

    deltas = [event for event in events if event.kind == "delta"]
    reasoning = [event for event in deltas if event.reasoning_content is not None]
    content = [event.content for event in deltas if event.content is not None]
    usage = [event for event in events if event.kind == "usage"]

    assert len(reasoning) == 47
    assert content == ["Hello", ".", ""]
    assert deltas[-1].finish_reason == "stop"
    assert len(usage) == 1
    assert usage[0].prompt_tokens == 208
    assert usage[0].completion_tokens == 49
    assert events[-1].kind == "done"


@pytest.mark.django_db
def test_parser_rejects_truncated_stream_without_done():
    raw = FIXTURE_PATH.read_bytes().split(b"data: [DONE]")[0]

    async def collect():
        return [event async for event in parse_sse_chunks(byte_chunks(raw, 37))]

    with pytest.raises(ProxyStreamError, match=r"before the \[DONE\]"):
        asyncio.run(collect())


def test_openai_sdk_uses_raw_async_stream_and_provider_endpoint(monkeypatch):
    captured = {}
    fixture_bytes = FIXTURE_PATH.read_bytes()

    class FakeRawResponse:
        status_code = 200

        async def iter_bytes(self):
            async for chunk in byte_chunks(fixture_bytes, 29):
                yield chunk

    class FakeResponseContext:
        async def __aenter__(self):
            return FakeRawResponse()

        async def __aexit__(self, *args):
            return None

    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return FakeResponseContext()

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    with_streaming_response=FakeCompletions()
                )
            )

        async def close(self):
            captured["closed"] = True

    monkeypatch.setattr("chat.services.proxy_stream.AsyncOpenAI", FakeClient)
    monkeypatch.setattr("chat.services.proxy_stream.settings.OPENAI_PROXY_KEY", "test-key")

    events = asyncio.run(
        collect_events(
            stream_completion(
                [{"role": "user", "content": "Say hello"}],
                "gpt-5.6-luna",
                max_completion_tokens=2048,
            )
        )
    )

    assert captured["client"]["base_url"] == "https://proxy.litechat.ai/openai/v1"
    assert captured["client"]["max_retries"] == 0
    assert captured["client"]["api_key"] == "test-key"
    assert captured["request"]["model"] == "gpt-5.6-luna"
    assert captured["request"]["stream"] is True
    assert captured["request"]["stream_options"] == {"include_usage": True}
    assert captured["closed"] is True
    assert events[-1].kind == "done"


def create_user_session(username: str, starting_credits: int = 0):
    user = get_user_model().objects.create_user(username=username)
    account = BillingAccount.objects.create(user=user, name=f"[Personal] {username}")
    if starting_credits:
        deposit_credits(account, starting_credits, f"deposit-{username}")
    model = ModelCatalog.objects.get(model_id="gpt-5.6-luna")
    session = ChatSession.objects.create(
        owner=user,
        billing_account=account,
        model=model,
        title="Streaming test",
    )
    return user, account, session


def make_async_client(user):
    client = AsyncClient()
    client.force_login(user)
    return client


@pytest.mark.django_db(transaction=True)
def test_async_view_streams_content_persists_reasoning_and_settles(monkeypatch):
    call_command("loaddata", "model_catalog", verbosity=0)
    user, account, session = create_user_session("stream-success", 200)
    profile = UserProfile.objects.create(
        user=user,
        global_system_prompt="Follow this profile prompt.",
        ai_memories_enabled=True,
    )
    MemoryItem.objects.create(
        user_profile=profile,
        category=MemoryItem.Category.PREFERENCE,
        content="Use metric units.",
        is_active=True,
    )
    MemoryItem.objects.create(
        user_profile=profile,
        category=MemoryItem.Category.FACT,
        content="Inactive note.",
        is_active=False,
    )
    ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.USER,
        content="Earlier question",
    )
    ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.ASSISTANT,
        content="Earlier answer",
        reasoning_content="Private prior reasoning",
    )
    seen = {}
    raw = FIXTURE_PATH.read_bytes()

    async def replay(messages, model_id, *, max_completion_tokens):
        seen["messages"] = messages
        seen["model_id"] = model_id
        seen["max_completion_tokens"] = max_completion_tokens
        async for event in parse_sse_chunks(byte_chunks(raw, 17)):
            yield event

    monkeypatch.setattr("chat.views.stream_completion", replay)
    monkeypatch.setattr("chat.views.settings.OPENAI_PROXY_KEY", "test-key")
    client = make_async_client(user)

    async def request_and_consume():
        response = await client.post(
            reverse("chat:stream-completion", args=(session.pk,)),
            data=json.dumps({"content": "Say hello"}),
            content_type="application/json",
        )
        chunks = [chunk async for chunk in response.streaming_content]
        return response, b"".join(chunks)

    response, body = asyncio.run(request_and_consume())

    account.refresh_from_db()
    session.refresh_from_db()
    assistant = session.messages.filter(
        role=ChatMessage.Role.ASSISTANT,
        status=ChatMessage.Status.COMPLETE,
    ).latest("pk")
    usage = UsageTransaction.objects.get(message=assistant)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/event-stream")
    assert b'event: delta\ndata: {"content":"Hello"}' in body
    assert b"reasoning_content" not in body
    assert "Private prior reasoning" not in str(seen["messages"])
    assert "Follow this profile prompt." in seen["messages"][0]["content"]
    assert "Use metric units." in str(seen["messages"])
    assert "Inactive note." not in str(seen["messages"])
    assert seen["model_id"] == "gpt-5.6-luna"
    assert seen["max_completion_tokens"] == 2048
    assert assistant.content == "Hello."
    assert assistant.reasoning_content
    assert (assistant.prompt_tokens, assistant.completion_tokens) == (208, 49)
    assert usage.cost_usd == Decimal("0.0000606")
    assert usage.credit_debit == 1
    assert usage.is_estimated is False
    assert usage.reservation_id is not None
    assert account.credit_balance == 199
    assert b'event: settled\ndata: {"credit_balance":199' in body


@pytest.mark.django_db(transaction=True)
def test_successful_stream_without_usage_uses_marked_tiktoken_estimate(monkeypatch):
    call_command("loaddata", "model_catalog", verbosity=0)
    user, account, session = create_user_session("stream-estimated", 100)
    monkeypatch.setattr("chat.views.settings.OPENAI_PROXY_KEY", "test-key")

    async def no_usage_stream(messages, model_id, *, max_completion_tokens):
        yield StreamEvent(kind="delta", content="Estimated answer")
        yield StreamEvent(kind="done")

    monkeypatch.setattr("chat.views.stream_completion", no_usage_stream)
    client = make_async_client(user)

    async def request_and_consume():
        response = await client.post(
            reverse("chat:stream-completion", args=(session.pk,)),
            data=json.dumps({"content": "Estimate this prompt"}),
            content_type="application/json",
        )
        body = b"".join([chunk async for chunk in response.streaming_content])
        return response, body

    response, body = asyncio.run(request_and_consume())
    assistant = session.messages.get(role=ChatMessage.Role.ASSISTANT)
    usage = UsageTransaction.objects.get(message=assistant)

    assert response.status_code == 200
    assert usage.is_estimated is True
    assert usage.prompt_tokens > 0
    assert usage.completion_tokens > 0
    assert usage.credit_debit >= 0
    assert b'"is_estimated":true' in body


@pytest.mark.django_db(transaction=True)
def test_zero_balance_is_rejected_before_provider_call(monkeypatch):
    call_command("loaddata", "model_catalog", verbosity=0)
    user, account, session = create_user_session("stream-empty")
    monkeypatch.setattr("chat.views.settings.OPENAI_PROXY_KEY", "test-key")

    async def unexpected_provider_call(*args, **kwargs):
        raise AssertionError("Provider must not be called when reservation fails")
        yield

    monkeypatch.setattr("chat.views.stream_completion", unexpected_provider_call)
    client = make_async_client(user)

    async def send():
        return await client.post(
            reverse("chat:stream-completion", args=(session.pk,)),
            data=json.dumps({"content": "Say hello"}),
            content_type="application/json",
        )

    response = asyncio.run(send())
    account.refresh_from_db()
    assert response.status_code == 402
    assert response["Content-Type"].startswith("text/event-stream")
    assert b"insufficient_credits" in response.content
    assert account.credit_balance == 0
    assert not session.messages.exists()
    assert not CreditLedger.objects.filter(billing_account=account).exists()


@pytest.mark.django_db(transaction=True)
def test_upstream_failure_releases_reservation_and_marks_message_failed(monkeypatch):
    call_command("loaddata", "model_catalog", verbosity=0)
    user, account, session = create_user_session("stream-failure", 100)
    monkeypatch.setattr("chat.views.settings.OPENAI_PROXY_KEY", "test-key")

    async def fail_after_partial(messages, model_id, *, max_completion_tokens):
        yield StreamEvent(kind="delta", content="partial")
        raise ProxyStreamError("mock provider failure")

    monkeypatch.setattr("chat.views.stream_completion", fail_after_partial)
    client = make_async_client(user)

    async def request_and_consume():
        response = await client.post(
            reverse("chat:stream-completion", args=(session.pk,)),
            data=json.dumps({"content": "Say hello"}),
            content_type="application/json",
        )
        chunks = [chunk async for chunk in response.streaming_content]
        return response, b"".join(chunks)

    response, body = asyncio.run(request_and_consume())

    account.refresh_from_db()
    assistant = session.messages.get(role=ChatMessage.Role.ASSISTANT)
    assert response.status_code == 200
    assert b'event: delta\ndata: {"content":"partial"}' in body
    assert b"upstream_failed" in body
    assert account.credit_balance == 100
    assert assistant.status == ChatMessage.Status.FAILED
    assert assistant.content == "partial"
    assert assistant.reasoning_content is None
    assert not UsageTransaction.objects.filter(message=assistant).exists()
    assert CreditLedger.objects.filter(
        billing_account=account,
        kind=CreditLedger.Kind.REFUND,
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_client_disconnect_releases_reservation(monkeypatch):
    call_command("loaddata", "model_catalog", verbosity=0)
    user, account, session = create_user_session("stream-disconnect", 100)
    monkeypatch.setattr("chat.views.settings.OPENAI_PROXY_KEY", "test-key")
    waiting = asyncio.Event()
    upstream_started = asyncio.Event()

    async def wait_for_disconnect(messages, model_id, *, max_completion_tokens):
        yield StreamEvent(kind="delta", content="partial")
        upstream_started.set()
        await waiting.wait()

    monkeypatch.setattr("chat.views.stream_completion", wait_for_disconnect)
    client = make_async_client(user)

    async def start_and_close():
        response = await client.post(
            reverse("chat:stream-completion", args=(session.pk,)),
            data=json.dumps({"content": "Say hello"}),
            content_type="application/json",
        )
        iterator = response.streaming_content.__aiter__()
        first_chunk = await iterator.__anext__()
        pending_chunk = asyncio.create_task(iterator.__anext__())
        await asyncio.wait_for(upstream_started.wait(), timeout=2)
        pending_chunk.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending_chunk
        return response, first_chunk

    response, first_chunk = asyncio.run(start_and_close())

    account.refresh_from_db()
    assistant = session.messages.get(role=ChatMessage.Role.ASSISTANT)
    assert response.status_code == 200
    assert b'event: delta\ndata: {"content":"partial"}' in first_chunk
    assert account.credit_balance == 100
    assert assistant.status == ChatMessage.Status.FAILED
    assert CreditLedger.objects.filter(
        billing_account=account,
        kind=CreditLedger.Kind.REFUND,
    ).exists()
    assert not UsageTransaction.objects.filter(message=assistant).exists()
