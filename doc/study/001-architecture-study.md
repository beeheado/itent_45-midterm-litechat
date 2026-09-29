# HeavyChat Initial Architecture Study

- **Created:** 2026-09-29T04:56:16+00:00
- **Updated:** 2026-09-29T05:07:22+00:00
- **Status:** Revised after user review; awaiting approval of the corresponding plan before execution.
- **Scope:** Initial architecture for HeavyChat's billing accounts, credit accounting, model catalog, user profile, chat history, provider streaming, and usage audit.

## Recommendation

Implement the initial architecture with Django 5.x on Python 3.11+, Django templates, HTMX, and ASGI. This fits a server-rendered application with authenticated relational data and one-way token streaming. Use SQLite for local development and tests, but do not treat it as a concurrency-safe production ledger for multiple workers or simultaneous spending. Keep accounting mutations short and atomic, make the append-only ledger the source of truth, and require a database with effective row-level locking (for example PostgreSQL) before enabling concurrent production billing. Never hold a database transaction open while waiting for provider tokens.

The user reports that valid LiteChat proxy keys have been supplied in `.env`. No secret values were read. At the time of this revision, there was no `.env` file at the repository root, so access by the planned capture script is not independently verified. The prior plain GET to `https://proxy.litechat.ai/v1` returned HTTP 404; this does not test the specified `/models` endpoint or authenticated completion API. The first implementation activity must be the authorized provider capture described below. Do not finalize the parser contract or claim proxy behavior until it produces a real capture.

The supplied product and accounting decisions are adopted: chat sessions bind to a selected `BillingAccount`; model choices are branded into Luna, Terra, and Sol tiers; the profile has a global system prompt and tagged memory items; 1 credit is $0.01 USD; usage debits round up to a whole credit; absent final usage is estimated with `tiktoken` and explicitly marked; and deposits are mock/manual top-ups rather than payment processing.

## Framework and Delivery Tradeoffs

### Django ASGI versus WSGI

- **ASGI is recommended.** It supports asynchronous views and streaming responses for long-lived SSE connections while retaining Django templates, authentication, forms, and ORM. It also leaves room for async provider calls without introducing a second web framework.
- **WSGI is simpler for conventional request/response traffic**, but its synchronous worker model is a poor fit for many simultaneous long-lived streams and would complicate the chosen async OpenAI client path.
- **ASGI does not make every Django operation asynchronous.** ORM transactions and some integrations remain synchronous or have limitations in Django 5.x. Put ledger mutations behind short synchronous transactional service boundaries (or supported async ORM operations), and do not assume an async view makes SQLite writes safe under contention.
- Deploy behind an ASGI server and a proxy configuration that disables response buffering for the SSE route and allows long-lived connections. Verify disconnect and timeout behavior in the actual deployment stack.

### HTMX SSE versus WebSockets

- **HTMX plus its SSE extension is recommended for the first version.** Chat submission is ordinary HTTP; tokens, completion status, and a finalized balance update flow one way from server to browser. SSE gives browser-native reconnection semantics and is simpler to authorize and operate than a bidirectional socket protocol.
- **WebSockets are not justified yet.** They add connection lifecycle and routing complexity without a current need for client-to-server messages during generation. Reconsider only if requirements add live cancellation/control or interactive bidirectional events that normal HTTP cannot handle cleanly.
- **SSE is text/event-stream, not a raw provider pipe.** The server should parse provider events, persist the finalized assistant result and billing facts, then emit a documented browser event format. Send useful event IDs/statuses and handle cancellation, provider errors, and reconnects without duplicating a charge.
- Use the HTMX SSE extension compatible with the pinned HTMX version. Confirm CDN/pinning and deployment CSP policy. Render model output as Markdown with `marked.js` and syntax highlighting with `highlight.js` in the browser; sanitize rendered HTML (or use a strict safe renderer) because model Markdown is untrusted input.

## Domain and ORM Design

### Users, Billing Accounts, and Profiles

- **Django User:** Authentication identity. Use Django's authentication system rather than duplicating credentials in a parallel user table.
- **UserAccount/Profile:** One-to-one user-owned preferences, including the **Global System Prompt**, profile settings, and the model-catalog presentation preference (Cards or Compact) if that preference should persist across visits. Keep profile data distinct from account funds.
- **BillingAccount:** The entity that owns credits and is charged for model usage. A ChatSession references the specific selected billing account (for example, `[Personal] <Name>`). Support membership/ownership checks so a user may select only accounts they are allowed to use. The account label is presentation data, not an authorization boundary.
- **CreditLedger:** Append-only signed integer-credit entries owned by a BillingAccount. Include deposits/top-ups, reservations, usage debits, and releases/refunds; record kind, timestamp, actor/source, unique idempotency key, and optional usage link. The ledger is authoritative. Any cached balance must be updated in the same transaction and reconcilable from entries. Never edit or delete a posted entry to correct accounting.
- **ModelCatalog:** Provider/model identifier, display metadata, context limit, availability, provider/base URL reference, and input/output rates per million tokens. Store rates as `Decimal`, never binary floating point, and snapshot model identity and rates used for each completion so later catalog edits do not rewrite history.
- **Model tiers:** Associate each catalog model with one branded tier: **Luna** for Fast/low-cost, **Terra** for Standard/balanced, and **Sol** for Premium/deep-reasoning. The model selector supports **Cards** and **Compact** layouts. Tier descriptions are product labels; actual rate and context data must come from verified catalog configuration, not be inferred from tier names.
- **ChatSession:** Owner, selected BillingAccount, title, timestamps, selected model/default instructions, and state. Enforce both session ownership and billing-account access in every query. Record the account selected for the session so charges cannot silently move to a different account.
- **ChatMessage:** Session, role, content, sequence/order, timestamps, provider/model metadata, finish status, and token metadata when known. Keep system instructions distinct from user-visible conversation messages. Persist pending/partial assistant output only as needed for recovery, and never treat an interrupted response as a successful billable completion.
- **MemoryItem:** User-owned tagged snippet (for example, tag `Preference`) that can be injected into context for the user's chat sessions. Allow users to inspect and manage these items; do not mix another user's memory into a request.
- **UsageTransaction:** Immutable, one-per-provider-completion audit record linked to the BillingAccount, session, assistant message, and provider request/completion ID where available. Store token counts and their source (provider-reported or estimated), `is_estimated`, input/output rate snapshots, USD cost, integer credit debit, and timestamps. Enforce idempotency so retrying finalization cannot double-charge.

### Profile Context and Prompt Construction

Apply the user's Global System Prompt to every chat session. Include the user's active MemoryItems in the constructed context as tagged, clearly delimited reference data. A memory snippet is user-provided content, not a privileged instruction; it should not be allowed to override application policy or system-level safety instructions. Define a deterministic ordering and include the global prompt and selected memory items in prompt token estimation and context-window budgeting. Avoid logging these potentially sensitive profile values in ordinary application logs.

### Ledger Integrity and Concurrency

The ORM should enforce non-negative token counts, valid entry kinds, unique idempotency keys, and required foreign-key relationships. Restrict ledger and usage records from ordinary admin edits/deletes; a privileged admin top-up should append a new ledger entry, never rewrite history. Application-level immutability is not a substitute for a privileged database boundary, so add database-level protections if the threat model requires tamper evidence.

Balance changes and ledger entries must be atomic. A usage request should reserve sufficient credits before provider work (or use another explicitly approved overspend policy), then settle against final usage and release the unused reservation. Provider failures and client disconnects must follow a deterministic release/charge policy. Keep each mutation short; never wrap an entire streamed generation in `transaction.atomic()`.

SQLite is adequate to develop schema and exercise single-process invariants, but `select_for_update()` does not provide effective row-level serialization there. Concurrent requests can race on available balance. Require explicit concurrency tests against the production database engine before allowing concurrent billing; do not claim SQLite proves those guarantees.

### Credit and Currency Policy

The approved denomination is **1 credit = $0.01 USD**, or **100 credits = $1.00 USD**. Catalog input/output rates are USD per one million tokens. For prompt token count `P`, completion token count `C`, input rate `Ri`, and output rate `Ro`:

```text
input_cost_usd  = P * Ri / 1_000_000
output_cost_usd = C * Ro / 1_000_000
total_cost_usd  = input_cost_usd + output_cost_usd
credit_debit    = ceil(total_cost_usd / 0.01)
```

Perform all rate and cost calculations with `Decimal`. Sum input and output USD costs first, then apply ceiling once to the total credit debit; do not round each component separately. Any positive cost smaller than one credit therefore debits at least one credit. A zero-cost completion debits zero. Preserve the unrounded USD cost, token counts, rate snapshot, and integer debit on the audit record so the debit can be reproduced. Tax, fees, and non-USD provider rates are not specified; do not silently include them in this formula.

### Deposits

No external payment processor is in scope. Provide a basic mock/manual top-up UI that appends **+500 credits** to the selected BillingAccount, and a Django admin action for the same kind of audited top-up. Record the actor/source, timestamp, and idempotency key. Clearly label the user-facing control as a mock/manual credit top-up; it must not imply a real payment was taken. Restrict who can issue top-ups and which BillingAccount may receive them.

## Proxy API and Stream Data

### Evidence and First Capture

The configured base URL is `https://proxy.litechat.ai/v1`. The user reports valid proxy keys are in `.env`; however, the repository-root `.env` file was not present when this revision was made. This discrepancy must be resolved for the script's runtime environment without exposing key values. No authenticated model-list response, SSE event, delta, completion chunk, or final `usage` object has yet been captured. The prior HTTP 404 was from a plain GET to the base URL, not `/models`, and is not conclusive evidence about the authenticated API.

The **first implementation activity** is to create and run the automated `scripts/capture_proxy.py` capture. It must:

1. Load credentials from the configured environment/`.env` without printing or persisting them, then request `https://proxy.litechat.ai/v1/models` and select a model confirmed by the returned catalog.
2. Send a minimal synthetic chat-completion request with streaming enabled and request final usage if the proxy supports the OpenAI-compatible option.
3. Save the raw SSE response bytes exactly as received to `tests/fixtures/provider_stream.sse`, including observed delta events, completion/finish events, final usage (if supplied), and `[DONE]` sentinel. Do not substitute a hand-authored example if the request fails.
4. Record sanitized provenance separately: UTC capture time, endpoint, model, SDK/version, sanitized request options, status, and allowlisted non-secret response headers. Never write authorization headers or key values to logs, fixtures, or metadata. Use synthetic prompt content and review the captured output for personal data before retaining it.
5. Report model-list or completion errors without dumping credentials. If the capture cannot be completed, stop provider-dependent parser work and report the blocker.

Before staging artifacts, ensure `.env` is excluded from version control. The raw fixture is a real provider artifact and must not be normalized or replaced during parser development; generated edge-case test streams must be clearly separate from it.

### Expected Shape to Verify, Not Assume

The following are common OpenAI Chat Completions conventions, not yet observations from this proxy:

- Streaming is requested with `stream: true`.
- Some compatible services require `stream_options: {"include_usage": true}` to include aggregate usage. When supported, usage may arrive in a final chunk with an empty `choices` list before `data: [DONE]`; individual content deltas commonly have no token counts.
- Choice deltas may carry role, content fragments, tool-call fragments, or other fields. Finish reason and usage may be absent on intermediate chunks. Consumers must not assume every event contains text.
- Non-stream responses commonly expose aggregate `usage.prompt_tokens` and `usage.completion_tokens`; exact shape and availability must be recorded from the proxy, not inferred from another provider.

SSE parsing must work across arbitrary network read boundaries and handle observed line endings, multiple `data:` lines, empty deltas, final usage, `[DONE]`, malformed JSON, and provider error events. Do not log full production prompts, completions, or raw event streams by default; they can contain user data. Apply retention and access controls separately from sanitized synthetic fixtures.

## Pricing and Usage Math

Use provider-reported aggregate token usage when the final usage object is present. If a stream completes successfully but omits final usage, estimate prompt and completion tokens with `tiktoken`, calculate cost with the same request-time rate snapshot and credit-ceiling policy, and set `UsageTransaction.is_estimated=True`. Record the estimation method/encoding and preserve estimated token counts distinctly from provider-reported counts. `tiktoken` may not use the proxy's exact tokenizer and does not automatically reproduce every provider's message framing or hidden overhead, so an estimated debit is explicitly approximate. Include assembled system instructions, the Global System Prompt, selected MemoryItems, conversation history, and completion text in the estimator input; document framing assumptions and token-budget handling. Do not silently label an estimate as provider-reported usage. A provider error, interrupted stream, or client disconnect is not a successful usage-free completion; follow the failure/release policy rather than estimating and charging an incomplete response.

Common streaming APIs provide authoritative usage in an aggregate final event, not on every content delta. Recommended billing unit remains one immutable `UsageTransaction` per completed provider request, linked to its assistant message and provider completion identity; do not create a charge per delta. Preserve chunk/event details in the provider fixture or separately governed diagnostics only when needed. If the product requires a transaction row per event, define how aggregate final counts/cost are allocated before implementation to prevent duplicate or fabricated per-chunk charges.

## Verification and Remaining Questions

- Capture and inspect actual `/models` and streamed completion responses before finalizing the provider parser, model-catalog import, or persistence contract.
- Resolve the reported `.env` availability mismatch without displaying or committing credential values.
- Decide whether provider completion audit is definitively request-level or requires a separate non-billing event record; never split aggregate usage across deltas without a defined allocation rule.
- Identify the intended production database before promising concurrent billing.
- Define retention and access policy for real provider fixtures and user profile memory, which may contain sensitive content.
- Verify whether provider rates are USD and define behavior if the proxy/catalog reports another currency; the adopted credit formula is USD-based.

**Implementation decision:** Proceed with the recommended architecture after the user approves the revised plan. The credit conversion, rounding, missing-usage fallback, mock top-up scope, and profile/model-tier features are now decided as stated above. The proxy's actual response shape remains an external dependency and must be captured by `scripts/capture_proxy.py` before parser contracts are finalized. No application code or capture script was written or run during this study revision.
