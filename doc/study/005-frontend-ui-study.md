# HeavyChat Frontend UI Study

- **Created:** 2026-09-29T07:37:28+00:00
- **Status:** Study complete; Phase 5 execution is authorized by the user's request.
- **Scope:** Django-template navigation, model selector, chat/profile/account pages, HTMX interactions, and the approved POST `fetch()` streaming client. No screenshots or image assets are present in the workspace; the UI will follow the supplied LiteChat descriptions.

## Verified Baseline

- Phase 4 exposes an authenticated `POST /api/chat/sessions/<session_id>/completions/` endpoint that consumes JSON and streams SSE bytes in a `StreamingHttpResponse`.
- Phase 4 tests verify raw SSE parsing, content/reasoning separation, usage settlement, insufficient-credit rejection, and reservation release on failure/disconnect.
- `UserProfile`, active `MemoryItem`, `BillingAccount`, `ChatSession`, `ChatMessage.status`, and the three active model tiers already exist. The mock top-up can use the audited `deposit_credits()` service.
- The repository has no template pages, shared shell, static UI assets, or UI view tests yet.
- The approved transport decision is a direct POST `fetch()` reader for chat streaming, avoiding EventSource's GET-only constraint. HTMX remains appropriate for normal fragment interactions.

## Architecture Decisions

### Templates and Navigation Shell

Use Django templates with a shared authenticated shell, a sidebar partial, a top balance/account badge, and focused page templates for the chat landing/session and profile. Put static CSS and JavaScript in `chat/static/chat/`; keep HTML fragments in `chat/templates/chat/partials/`. A custom CSS layer will establish the LiteChat-like visual system while the allowed Tailwind Play CDN supplies utility styling during local development. Use HTMX for loading the model-selector modal, session creation redirects, profile prompt/toggle updates, memory add/delete, and top-up badge refresh.

The model selector uses a server-rendered dialog with an authorized BillingAccount dropdown, a client-only Cards/Compact toggle, and catalog-driven OpenAI model cards. Posting the chosen model/account creates a ChatSession after checking ownership and that the model is active. The selected session determines the account and model used by chat and streaming.

### Fetch-Based SSE Client

The chat form is intentionally not an HTMX SSE/EventSource connection. Vanilla JavaScript intercepts submit, POSTs JSON to the existing Phase 4 endpoint with same-origin credentials and the CSRF token, and reads `response.body.getReader()`. A `TextDecoder` plus buffered SSE framing handles split CRLF/LF separators and multiple `data:` lines. It routes `delta`, `settled`, and `error` events, disables/re-enables controls, and scrolls the conversation as content arrives. The settled event updates all balance badges without a page reload.

This keeps the existing POST contract and avoids a second queue/GET-stream endpoint. Tests should exercise the real browser parsing code where practical or verify its event contract without opening a live provider connection.

### Markdown, Highlighting, and XSS

Model output, user messages, memory, profile text, and session titles are untrusted. Django templates must autoescape and must not mark stored message content safe. For assistant Markdown, render with a pinned `marked.js`, sanitize the resulting HTML with a pinned DOMPurify policy before assigning it to the DOM, then apply `highlight.js` to code blocks. Do not interpolate model text into HTML strings for code-copy controls; construct buttons with DOM APIs and copy code text with `navigator.clipboard`. Sanitize on every streaming re-render because partial Markdown is also untrusted.

The permitted CDN approach avoids adding a Node build system in this phase but introduces an external availability/supply-chain dependency. Pin third-party JavaScript versions in template URLs, keep server-side escaping as the baseline, and document CDN/CSP hardening as a deployment follow-up.

### Profile, Memory, and Mock Billing

The profile page edits only the authenticated user's `UserProfile`. Memory CRUD is scoped by profile, categories come from `MemoryItem.Category`, and the generation toggle controls `ai_memories_enabled`; it does not silently activate another profile's memory. The top-up button is explicitly mock/manual, deposits exactly 500 cents/credits through `deposit_credits()` with a unique idempotency key, and updates the visible balance from the server response. No payment processor or real payment claim is in scope.

### Testing Strategy and Risks

- Use Django's test client for regular template/form views and tests that assert authenticated ownership, model/account selection, profile/memory updates, and ledger-backed top-up.
- Keep streaming tests isolated from the network. Phase 4 already exercises the endpoint with replayed fixture bytes; frontend JavaScript should be structured so SSE framing and DOM updates can be verified without a live provider.
- Avoid coupling templates to reasoning output. The assistant bubble renders only `content`; `reasoning_content` remains server-side and is never passed to Markdown rendering.
- Keep the existing POST endpoint, account reservation, settlement, and failure cleanup unchanged unless UI integration requires a narrowly scoped compatibility fix.
- The current Django 5.1 line is unsupported and SQLite is not a concurrent production ledger; those Phase 2/3 production risks remain.

## Implementation Decision

Proceed with the requested shared shell, accessible model selector, session feed/composer, profile and memory management, mock top-up, and POST fetch-streaming client. Use Django templates and HTMX for page/fragment interactions; use vanilla JavaScript only for streaming, Markdown rendering, auto-scroll, and balance updates. No Phase 6 behavior is included.
