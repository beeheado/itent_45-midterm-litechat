# HeavyChat Streaming Plan

- **Created:** 2026-09-29T06:23:50+00:00
- **Updated:** 2026-09-29T06:55:13+00:00
- **Study:** [`doc/study/004-streaming-service-study.md`](../study/004-streaming-service-study.md)
- **Status:** Implementation and verification complete; commit/merge pending.
- **Scope:** Async LiteChat transport, fixture-compatible SSE parser, context injection, streaming view, and credit/usage recovery. Do not build Phase 5 templates or browser UI.

## Execution Checklist

### 1. Catalog and Message State

- [x] Update the `gpt-5.6-luna` fixture/database record to active at input/output rates `0.150000` / `0.600000` USD per million tokens.
- [x] Add active `gpt-5.6-terra` (`0.500000` / `2.000000`) and `gpt-5.6-sol` (`2.500000` / `10.000000`) catalog records, all provider `openai`; treat these as user-supplied baseline configuration, not captured response data.
- [x] Add `MemoryItem.is_active` (default true) and `ChatMessage.status` (`pending`, `complete`, `failed`, default complete), then generate/apply migrations. Create generated assistant messages as pending and mark them complete only after settlement.

### 2. Async Proxy Stream and SSE Parser

- [x] Implement `chat/services/proxy_stream.py` using `AsyncOpenAI` at `https://proxy.litechat.ai/openai/v1` and `OPENAI_PROXY_KEY`; use `with_streaming_response.create()` / raw `iter_bytes()` and disable automatic retries for streamed requests.
- [x] Normalize the known legacy `LITECHAT_PROXY_BASE_URL=https://proxy.litechat.ai/v1` to the verified `/openai/v1` route in runtime settings without changing `.env`.
- [x] Parse SSE incrementally across arbitrary byte boundaries, combining `data:` lines and handling LF/CRLF. Parse fixture-compatible JSON chunks, separate `delta.content` and `delta.reasoning_content`, capture `finish_reason`, parse the choices-empty final usage object, and recognize `[DONE]`.
- [x] Fail incomplete streams that end without `[DONE]`; sanitize upstream failures. On successful `[DONE]` without authoritative usage, estimate prompt/completion tokens with `tiktoken` and set `is_estimated=True`.
- [x] Keep reasoning out of client events and completed-message history. Yield only user-facing content deltas; return final token usage/estimate state separately for settlement.

### 3. Context, View, and Credit Lifecycle

- [x] Build context from the authorized session: optional `UserProfile.global_system_prompt`, active `MemoryItem` records only when `ai_memories_enabled=True`, complete prior history, and the new user prompt. Treat memory text as delimited untrusted context and exclude reasoning history.
- [x] Add an async view in `chat/views.py` and URL route returning an async-iterator `StreamingHttpResponse` with `text/event-stream`, no-cache, and anti-buffering headers. Use `request.auser()` and sync-to-async wrappers for ORM/transaction work.
- [x] In a short atomic preflight, validate session/account ownership, reserve at least 50 credits plus estimated prompt/max-output exposure, then persist the user message and pending assistant message. Return HTTP 402 with an SSE error event before contacting the provider if the reserve fails.
- [x] Emit JSON-encoded `event: delta` messages for content only. On clean stream completion, persist content/reasoning/tokens/status, call `settle_usage()` with request-time rates, create one usage audit, and emit `event: settled` with actual balance and debit.
- [x] On upstream failure, truncated stream, or client cancellation, mark the assistant message failed, release the reservation exactly once, do not create a successful usage audit, and re-raise cancellation after cleanup. Do not refund a completed provider response if settlement fails; retain it for safe reconciliation and emit a settlement error.

### 4. Tests, Documentation, and Rendezvous

- [x] Add `tests/test_streaming.py` for fixture parsing under fragmented reads, reasoning/content separation, final usage and `[DONE]`, successful mocked async view settlement, zero-balance HTTP 402, and upstream failure/disconnect reservation release.
- [x] Run `.venv/bin/python -m pytest`, `.venv/bin/python manage.py check`, and `makemigrations --check --dry-run`; verify no live provider call is needed for tests.
- [x] Update `doc/wiki/streaming-architecture.md` with the parser contract, context precedence, SSE event format, reserve/settle/release behavior, fallback usage estimation, and SQLite/deployment caveats.
- [x] Review the staged diff and ensure `.env`, SQLite data, and unrelated user files are excluded.
- [ ] Commit with `feat: implement async sse proxy streaming and usage settlement` and merge into `main` only after verification passes.

## Verification Record

- `.venv/bin/python -m pytest`: 22 passed.
- `.venv/bin/python manage.py check`: no issues.
- `makemigrations --check --dry-run`: no changes detected.
- Streaming tests replay the captured fixture and mock the SDK raw response; no live provider request was made.

## Stop Condition

Complete Phase 4 only. Do not implement Phase 5 templates, model cards, profile/account pages, or frontend wiring. After tests, documentation sync, commit, and merge, halt for user review.
