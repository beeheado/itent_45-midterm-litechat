# HeavyChat Streaming Service Study

- **Created:** 2026-09-29T06:22:59+00:00
- **Updated:** 2026-09-29T07:13:36+00:00
- **Status:** Study complete; Phase 4 execution is authorized by the user's request.
- **Scope:** Async LiteChat completion transport, fixture-shaped SSE parsing, prompt/context assembly, ASGI browser streaming, and credit/message recovery.

## Verified Inputs

- The provider route is `https://proxy.litechat.ai/openai/v1/chat/completions`; model discovery is not available on this gateway.
- `tests/fixtures/provider_stream.sse` contains 51 JSON `data:` events, `reasoning_content` and `content` deltas, a `finish_reason: "stop"` chunk, a separate usage-only chunk, and `data: [DONE]`.
- The observed usage event reports 208 prompt tokens, 49 completion tokens, and 46 reasoning tokens. The fixture's response status was reported as 200; HTTP response headers were not provided.
- Phase 3 services are synchronous ORM functions protected by short `transaction.atomic()` blocks. `settle_usage()` accepts explicit input/output rate snapshots and creates the audit linked to an assistant message and reservation.
- The current `MemoryItem` model has no active flag, and `ChatMessage` has no completion state. Phase 4 needs both to construct only active context and to distinguish pending/failed partial messages from completed, billable messages.
- The installed official OpenAI SDK (`openai 3.20.0`) supports `AsyncOpenAI` and `with_streaming_response.create()`. Its raw async response exposes `iter_bytes()`, allowing the application parser to inspect provider SSE bytes without using the SDK's parsed chunk iterator. Django 5.1 provides `HttpRequest.auser()` for async auth access.
- The currently resolved `LITECHAT_PROXY_BASE_URL` is the legacy `https://proxy.litechat.ai/v1`; Phase 4 routing requires `/openai/v1`. This non-secret configuration value was inspected without reading credential values. Normalize this exact legacy value in settings at runtime and leave the user-owned `.env` untouched.

## Async Transport and SSE Parser

Use `AsyncOpenAI` with the verified provider-prefixed base URL and `OPENAI_PROXY_KEY`. Normalize the known legacy LiteChat base path to `https://proxy.litechat.ai/openai/v1` in settings; preserve other explicitly configured base URLs. Set `max_retries=0` for this streaming call to avoid silently replaying a request after partial output has been yielded. Call `with_streaming_response.create(stream=True, stream_options={"include_usage": true}, ...)` and consume the raw response's async byte iterator. This retains the official SDK's auth, timeout, and HTTP transport while preserving the fixture's SSE representation for the application parser.

Implement an incremental byte parser rather than decoding each network chunk independently. It must buffer split lines and events, recognize the fixture's `data:` JSON records separated by blank lines, decode UTF-8 only after an event is complete, and terminate only on `data: [DONE]`. It should handle CRLF/LF and arbitrary read boundaries, reject malformed JSON/provider error events, and fail an unexpectedly closed stream that never reaches `[DONE]`.

Observed chunk behavior requires independent channels:

- `choices[0].delta.content` is user-visible output and is emitted as browser `event: delta` JSON data.
- `choices[0].delta.reasoning_content` is accumulated separately and never merged into or sent through the user-facing content event.
- A choice chunk with `finish_reason: "stop"` is not the end of billing data. Continue reading the following `choices: []` usage-only event and then `[DONE]`.
- A successful `[DONE]` without authoritative usage uses the Phase 1 policy: estimate prompt/completion tokens with `tiktoken` and set `UsageTransaction.is_estimated=True`. Upstream failure or disconnect is not a successful usage-free completion and must not be estimated/settled.

The captured fixture contains reasoning text. Store reasoning separately as explicitly requested and avoid returning it in browser events, logs, or future renderers by default.

## Context Construction and Data Evolution

Construct provider messages from the selected session, not request-supplied ownership/model IDs. In order, include the user's nonempty `global_system_prompt`, a clearly delimited memory-context message when the profile opts in, completed session history, and the new user prompt. Query only `MemoryItem.is_active=True`; add this boolean (default true for existing memory rows) because the Phase 3 schema has no per-item active state. The profile's `ai_memories_enabled` remains the master opt-in.

Memory content is user-provided data, including items categorized as `instruction`; clearly frame it as reference data and do not let it supersede application/system policy. Do not include stored `reasoning_content` in history. Add `ChatMessage.status` (`pending`, `complete`, `failed`, default `complete`) so a pre-created assistant row can be marked complete only after `[DONE]` and successful settlement; incomplete rows must not be sent as completed history.

Pricing configuration is supplied by the user for Phase 4. Activate `gpt-5.6-luna` at $0.15/$0.60 per million, and seed active Terra ($0.50/$2.00) and Sol ($2.50/$10.00) entries. These are user-supplied baseline rates, not values observed in the SSE stream. Keep the captured fixture/model identity unchanged.

## ASGI View, Credit Reservation, and Recovery

Return an async `StreamingHttpResponse` backed by an async iterator and `text/event-stream`. Django requires the iterator to be async under ASGI. Use `await request.auser()` and perform ORM/context preparation inside a short sync function via `sync_to_async(thread_sensitive=True)`. Do not issue synchronous ORM calls inside the async generator and do not keep an atomic transaction open during provider I/O.

Before starting the response, validate session ownership, construct context, create a unique reservation key, reserve an estimated conservative amount (at least 50 credits, with request-token/output-limit estimate considered), and create pending user/assistant messages atomically. Insufficient funds return HTTP 402 with an SSE `event: error` payload before any provider request.

On clean `[DONE]`, finalize the assistant content/reasoning, token counts, usage audit, and reservation settlement through a short synchronous atomic service boundary. Emit a final `event: settled` with the actual balance/debit. On provider errors, malformed/truncated SSE, or client cancellation, mark the assistant message failed, do not create a successful usage audit, and release the reservation using an idempotency key. Handle `asyncio.CancelledError` explicitly and re-raise after cleanup. If an unexpectedly large actual debit exceeds the reserve and remaining balance, report a settlement error and retain a recoverable reservation rather than silently zeroing or overcharging the account.

SSE event payloads must be JSON-encoded to prevent control characters in model output from injecting event framing. Configure `Cache-Control: no-cache` and disable reverse-proxy buffering for the route. Django's response behavior does not prove production proxy buffering/timeouts; keep that an operations verification item.

## Tests and Implementation Decision

### Phase 5 HTMX SSE Integration Gate

The current stream route accepts POST with the user prompt in its JSON body. The HTMX SSE extension uses browser `EventSource`, which only issues GET requests and cannot submit that body. Phase 4 keeps the POST streaming contract. Before Phase 5 connects `sse-connect` directly to this endpoint, resolve the mismatch. The recommended design is a POST preparation endpoint that creates the user/pending assistant messages and reservation, returns a one-time GET stream URL, and persists the reservation/rate snapshot needed for that GET request. Do not put the prompt or secrets in the URL. An alternative is to revise the Phase 5 client requirement to use `fetch()` streaming instead of the SSE extension.

Use the captured raw fixture to test parsing without external calls. Mock the SDK raw byte stream for async end-to-end view tests, and assert content delivery, separate reasoning persistence, usage settlement and balance events, 402 preflight behavior, and release on upstream failure/disconnect. Preserve a safe test DB boundary with pytest-django.

SQLite lacks effective row-level `select_for_update()` semantics. The current phase can verify transaction/service behavior in local tests, but simultaneous multi-worker spending and streaming cancellation under production load must be tested with the eventual production database/server before launch.

**Implementation decision:** Proceed with the requested Phase 4 work, add the minimal `MemoryItem.is_active` and `ChatMessage.status` schema changes, preserve reasoning separately, use the official SDK's raw streaming response, and keep Phase 5 UI work out of scope. User-provided model rates will be seeded as active configuration; no pricing values will be inferred from provider chunks.
