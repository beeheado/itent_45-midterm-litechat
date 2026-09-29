# HeavyChat Initial Architecture Plan

- **Created:** 2026-09-29T04:57:26+00:00
- **Updated:** 2026-09-29T05:15:00+00:00
- **Study:** [`doc/study/001-architecture-study.md`](../study/001-architecture-study.md)
- **Status:** Approved; Phase 1 was attempted and is blocked at provider model discovery.
- **Scope:** Establish the initial HeavyChat architecture, including real proxy capture, billing accounts, model tiers, profile context, usage pricing, credit integrity, streaming, and the initial UI. This checklist is the execution boundary; changes outside it require a new study and plan.

## Resolved Product Decisions

- Chat sessions bind to a selected `BillingAccount`; usage charges that account.
- Model selector tiers are Luna (Fast/low-cost), Terra (Standard/balanced), and Sol (Premium/deep-reasoning), with Cards and Compact layouts.
- User profile includes a Global System Prompt and tagged MemoryItems, such as `Preference`, injected into request context.
- 1 credit = $0.01 USD. Calculate costs with `Decimal`, sum input and output USD costs, then round the total debit up to the nearest integer credit.
- If the final provider usage object is missing, estimate prompt/completion tokens with `tiktoken` and mark `UsageTransaction.is_estimated=True`.
- Deposits are mock/manual only: a +500-credit UI top-up and a Django admin action; no payment processor.

## Remaining Dependencies and Design Questions

- [ ] Resolve the `/v1/models` HTTP 404 and verify provider access; a non-empty `LITECHAT_API_KEY` was found in `.env`, but the response does not establish whether the key is valid.
- [ ] Confirm whether usage audit is one billable `UsageTransaction` per provider completion (recommended) with events associated separately, or whether a non-billing event record is also needed. Do not allocate aggregate final usage across deltas without an explicit rule.
- [ ] Identify the intended production database before enabling concurrent billing. SQLite is the local-development default, not proof of concurrent ledger safety.
- [ ] Confirm provider catalog rates are USD; define behavior if the provider reports another currency. Do not silently apply the USD-to-credit formula to an unknown currency.
- [ ] Define retention and access rules for captured provider output and profile memory, which can contain sensitive content.

## Execution Checklist

### 1. Capture the Real Provider Contract First

- [x] Ensure `.env` is excluded from version control and available to the capture process without displaying credential values.
- [x] Create `scripts/capture_proxy.py` to load the API key from `.env` securely and support model discovery and raw streaming capture.
- [x] Run `scripts/capture_proxy.py`; the `GET /v1/models` request carrying the bearer authorization header returned HTTP 404. See the Phase 1 execution note below.
- [ ] After model discovery succeeds, make a minimal synthetic streaming completion request, request final usage if supported, and capture actual SSE bytes including deltas, finish/completion events, usage, and `[DONE]` behavior.
- [ ] Save unchanged raw SSE bytes to `tests/fixtures/provider_stream.sse` and sanitized success metadata (UTC time, endpoint, model, capture transport/runtime version, sanitized options, status, and allowlisted response headers). No stream fixture exists yet.
- [ ] Review the real fixture for personal data and secrets. If model listing or completion fails again, preserve safe diagnostic facts and stop provider-dependent parser work; never substitute a fabricated response.

#### Phase 1 Execution Note

- Latest attempt at `2026-09-29T05:15:00Z` by running `python3 scripts/capture_proxy.py`.
- `GET https://proxy.litechat.ai/v1/models` returned HTTP 404 (`content-type: text/plain; charset=utf-8`; request ID `req_u34MlSunYED7xBkIZeiPwWCuTt47TEY6MHVKHrtjeW4`). No models were returned, so no completion POST was sent.
- `tests/fixtures/provider_stream_meta.json` contains the sanitized failure metadata. `tests/fixtures/provider_stream.sse` was intentionally not created because no real stream was received.

### 2. Establish the Application Foundation

- [ ] Create the Python 3.11+/Django 5.x project and configure it to run through ASGI; use SQLite for local development.
- [ ] Add the official `openai` SDK, `tiktoken`, pytest, and pytest-django with pinned, supportable versions; configure project settings and test discovery.
- [ ] Configure provider base URL and credentials through environment-based settings. Ensure `.env` is ignored and secrets are excluded from logs, fixtures, and documentation.

### 3. Implement Identity, Billing, Catalog, and Profile Records

- [ ] Use Django authentication and add a user profile containing the `GlobalSystemPrompt` applied to each chat, manageable tagged `MemoryItem` records (such as `Preference`), and a Cards/Compact model presentation preference if it should persist.
- [ ] Define the `BillingAccount` model and access/membership rules. Bind every `ChatSession` to one selected authorized BillingAccount and ensure model charges cannot silently move to another account.
- [ ] Define `CreditLedger` as append-only signed integer-credit entries owned by BillingAccount. Record deposits/top-ups, reservations, debits, and releases with actor/source, idempotency key, and timestamps. Any cached balance must be updated atomically and reconcile to the ledger.
- [ ] Define `ModelCatalog` with verified provider/model identifiers, context sizes, USD input/output rates per million tokens, availability, and branded tier aliases: Luna (Fast/low-cost), Terra (Standard/balanced), and Sol (Premium/deep-reasoning). Keep tier labels separate from actual rate data.
- [ ] Define `ChatSession`, `ChatMessage`, and immutable `UsageTransaction` records. Snapshot model/rates per request; store token source and `is_estimated`; link the audit to the selected BillingAccount, session, assistant message, and provider completion ID where available.
- [ ] Apply the Global System Prompt to every session and include active, tagged MemoryItems as clearly delimited context. Enforce ownership, deterministic ordering, context budgeting, and protection against memory text overriding system/application policy.
- [ ] Make a UI model-selector layout toggle for Cards and Compact while preserving Luna/Terra/Sol tier grouping.

### 4. Implement Metering, Accounting, and Deposits

- [ ] Calculate USD costs with `Decimal`: `prompt_tokens * input_rate / 1_000_000` plus `completion_tokens * output_rate / 1_000_000`. Sum the costs, then calculate the integer debit as `ceil(total_cost_usd / 0.01)` (100 credits per USD); round up once to the next whole credit and preserve the unrounded USD cost.
- [ ] Use provider final usage when available. If a stream completes successfully without final usage, estimate prompt and completion tokens with `tiktoken`, document framing/encoding assumptions, and set `UsageTransaction.is_estimated=True`. Do not estimate/charge an interrupted stream as a successful completion.
- [ ] Implement short atomic reserve/settle/release mutations. Define deterministic handling for provider errors, missing-usage estimates, retries, duplicate finalization, and client disconnects. Never keep a DB transaction open for a stream.
- [ ] Limit deposits to the user-facing mock/manual +500-credit top-up and Django admin action. Both append auditable ledger entries, require authorization, and clearly state that no real payment is processed; payment processors and payment flows are out of scope.
- [ ] Document SQLite concurrency limitations. Add concurrency verification against the selected production database before enabling concurrent production spending.

### 5. Integrate and Stream Completions

- [ ] Implement the async OpenAI SDK client using the verified LiteChat base URL and captured request/response contract.
- [ ] Parse real captured SSE bytes independently of network read boundaries; handle observed deltas, role/tool fields as applicable, finish events, final aggregate usage, `[DONE]`, provider errors, malformed input, and missing usage.
- [ ] Persist session messages and finalize an idempotent usage audit without charging once per text delta. Preserve estimated usage as estimated, never as provider-reported.
- [ ] Expose a Django ASGI SSE response for browser token/status/balance events. Handle disconnects/timeouts without duplicate charges and configure deployment proxies not to buffer SSE.

### 6. Build and Verify the Initial Interface

- [ ] Add Django template chat/session/profile/account views and HTMX interactions, including authorized BillingAccount selection, memory management, and manual +500-credit top-up.
- [ ] Use the compatible HTMX SSE extension. Render Markdown with `marked.js` and code highlighting with `highlight.js`; sanitize untrusted model output and align CDN/pinning with CSP policy.
- [ ] Enforce user/session/BillingAccount ownership in every relevant query and update the displayed balance only after accounting settlement.
- [ ] Add tests for the real captured provider fixture and parser boundaries; model constraints; pricing and ceiling edge cases; provider-reported versus estimated usage and `is_estimated`; ledger atomicity/idempotency; account authorization; profile prompt/memory assembly; top-ups; streaming failure/disconnect behavior; and session ownership.
- [ ] Run pytest, migrations/system checks, and production-database concurrency tests before claiming concurrent billing correctness. Review fixtures and repository changes for credential leakage and personal data.
- [ ] Update `doc/wiki/` with implemented architecture, provider observations and fixture provenance, accounting decisions, and operational caveats.
- [ ] Commit only scoped changes with conventional commit messages. Merge into `main` only after verification succeeds; report external-provider or database blockers rather than claiming completion.

## Stop Condition

The plan is approved, but Phase 1 is blocked at the authenticated model-list request. Do not proceed to provider parsing or later implementation phases until `/v1/models` returns an active model and a real completion stream is captured. No synthetic stream may be used to clear this gate.
