# Async Streaming Architecture

## Provider Transport

`chat/services/proxy_stream.py` uses the official `AsyncOpenAI` SDK with its raw streaming-response interface. The request base is `https://proxy.litechat.ai/openai/v1`, which resolves to `https://proxy.litechat.ai/openai/v1/chat/completions`; `max_retries=0` avoids silently replaying a partially delivered completion. The repository `.env` currently contains the former `/v1` base, so settings normalize that exact legacy value to the provider-prefixed route without modifying `.env`. The API key comes from `OPENAI_PROXY_KEY` and is never logged.

The Django endpoint is `POST /api/chat/sessions/<session_id>/completions/` with a JSON `content` string. It requires an authenticated session owner and an active selected model.

### Phase 5 HTMX SSE Integration Gate

The current completion endpoint accepts POST so the prompt can be submitted with the request body. Browser `EventSource`, which the HTMX SSE extension uses, only opens GET requests and cannot submit this body. Phase 5 must either add a POST preparation step that returns a one-time GET stream URL (persisting enough pending-generation state for the GET request), or revise the client requirement to use `fetch()` streaming. The Phase 4 endpoint should not be connected directly with `sse-connect` until this method mismatch is resolved.

The parser consumes raw async response bytes and buffers line/event boundaries independently of network chunk boundaries. It accepts fixture-shaped `data:` JSON events, LF/CRLF, and multiple data lines; malformed JSON, upstream error events, and EOF without `[DONE]` fail the completion. It does not rely on every event containing a choice or text.

## Observed Event Contract

The reference stream is [`tests/fixtures/provider_stream.sse`](../../tests/fixtures/provider_stream.sse). Observed ordering is:

1. Content and/or reasoning deltas in `choices[0].delta`.
2. A choice event with `finish_reason: "stop"`.
3. A usage-only event with `choices: []` and aggregate token counts.
4. `data: [DONE]`.

`delta.content` is sent to the browser as JSON-encoded `event: delta`. `delta.reasoning_content` is buffered separately and persisted to `ChatMessage.reasoning_content` only on successful completion; it is never mixed into browser content or prior conversation context. The stream must be read through the usage-only event after `finish_reason` and terminate only on `[DONE]`.

If a stream reaches `[DONE]` without authoritative usage, prompt tokens are estimated from the assembled request with `tiktoken`, completion tokens from generated content plus reasoning, and `UsageTransaction.is_estimated` is set. Provider failures or disconnects are failed generations, not usage-free completions.

## Context and Message State

The authenticated user owns the session and must own its selected `BillingAccount`. Provider context is assembled server-side in this order: optional `UserProfile.global_system_prompt`, opt-in active memory records, completed session history, and the current user prompt. Memory is encoded as delimited JSON reference data so its content is not privileged policy. Previous `reasoning_content` is excluded from history.

New user messages are saved complete and new assistant messages start `pending`. A clean completion changes the assistant message to `complete` together with settlement. Upstream errors/disconnects mark it `failed`; incomplete assistant messages are excluded from subsequent context history.

## Reservation and Settlement

Preflight estimates request exposure using `tiktoken`, the selected model's request-time rates, and the maximum completion cap. The reserved amount is the greater of 50 credits or the estimated debit plus a 50-credit buffer. Reservation and message creation are a short atomic operation before any provider request. Insufficient funds return HTTP 402 with an SSE `event: error` before streaming starts.

During a successful stream, content is forwarded incrementally. On `[DONE]`, the service commits content/reasoning/token metadata and invokes `settle_usage()` with the request-time input/output rate snapshots. The response ends with `event: settled` containing the actual balance and credit debit. If a successful provider response cannot be reconciled because actual cost exceeds available funds, the assistant row remains pending with its output recorded, the reservation is retained, and a settlement error is sent for reconciliation rather than refunding a completed provider call.

On provider failure, truncated stream, or client cancellation, the assistant message is marked failed and the reservation is released idempotently. No successful `UsageTransaction` is created on those failure paths. Cleanup uses sync-to-async bridges around the synchronous transactional ledger services; no database transaction spans provider I/O.

## Catalog Rates

The seeded active records use the user-supplied Phase 4 rates:

| Model | Tier | Input / 1M | Output / 1M |
| --- | --- | ---: | ---: |
| `gpt-5.6-luna` | Luna | $0.15 | $0.60 |
| `gpt-5.6-terra` | Terra | $0.50 | $2.00 |
| `gpt-5.6-sol` | Sol | $2.50 | $10.00 |

These are supplied baseline configuration, not rates observed in the provider SSE fixture.

## Operations and Verification Boundaries

Run through ASGI with `.venv/bin/uvicorn heavychat.asgi:application`. Streaming responses require proxy buffering to be disabled and suitable timeouts in deployment; this is not exercised by Django's test client.

SQLite does not provide effective row-level `select_for_update()` semantics. Unit/integration tests verify single-process reservation and settlement, not concurrent production spending. Use the production database (preferably PostgreSQL) for concurrency tests before multi-worker billing.

The Phase 4 tests replay `tests/fixtures/provider_stream.sse` and mock the SDK stream; they do not make paid live provider calls. Phase 5 frontend work remains out of scope.
