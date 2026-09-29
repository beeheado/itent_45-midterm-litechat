# HeavyChat Frontend UI

## Interface Structure

The Phase 5 UI uses Django templates and app static assets under `chat/templates/chat/` and `chat/static/chat/`.

- `base.html` provides the responsive dark workspace shell, HeavyChat branding, Chat/SimGen/Profile navigation, session list, and the current BillingAccount/credits/USD badge.
- `home.html` is the no-session landing page. The `+` and primary action load the model selector using HTMX.
- `partials/model_selector.html` provides an account selector, cost caption, Cards/Compact toggle, and active OpenAI Luna/Terra/Sol cards. Session creation validates account ownership and model activity on the server before redirecting.
- `session.html` renders completed messages and a composer. User-visible assistant content is rendered as Markdown; `reasoning_content` is never rendered.
- `profile.html` edits the global prompt, AI memory opt-in, memory records, and an explicit mock +500-credit top-up.
- `simgen.html` is a placeholder only.

Default personal BillingAccounts are created lazily for authenticated users. Session lists, profile actions, memory CRUD, and billing account operations are scoped to the authenticated user. The top-up appends a 500-credit `DEPOSIT` through `deposit_credits()` and does not process payment.

## HTMX and Chat Streaming

HTMX handles normal navigation fragments: model selector/modal loading, session creation redirect, prompt save, memory toggle/add/delete, and top-up balance badge refresh. Chat submission and streaming use vanilla `fetch()` per the approved decision:

1. POST JSON `{ "content": "..." }` to `/api/chat/sessions/<session_id>/completions/` with same-origin credentials and the CSRF token.
2. Read the async response body with `ReadableStream.getReader()` and `TextDecoder`; frame events across arbitrary byte chunks and CRLF/LF boundaries.
3. `event: delta` appends only user-facing content. `event: error` displays a safe failure status. `event: settled` updates credits and USD badges without a page reload.

The chat view disables the composer during generation, supports Enter-to-send and Shift+Enter for newlines, streams into an active assistant bubble, and auto-scrolls the feed. The server remains responsible for session ownership, preflight reservation, settlement, and failure release.

## Markdown and Security

The UI loads pinned HTMX 2.0.8, marked.js 15.0.12, DOMPurify 3.2.6, and highlight.js 11.11.1 from CDNs; Tailwind Play CDN is used for the initial development styling layer. CDN availability and CSP/SRI hardening remain deployment concerns.

Model/user text is never marked safe in Django templates. The browser parses Markdown with marked.js, sanitizes each render with DOMPurify, then highlights code blocks. Copy controls are created with DOM APIs and copy `textContent`; model strings are not interpolated into HTML. Reasoning is kept out of the browser stream. Django forms use CSRF tokens, and every mutation view validates ownership server-side.

## Verification

`tests/test_views.py` covers home/session rendering, model/account selection and ownership, profile settings, memory CRUD, and ledger-backed top-up. `tests/test_streaming.py` continues to replay the provider fixture and verifies the fetch endpoint's SSE/settlement behavior with mocked upstream responses. Tests do not make a live provider request.

## Local Run Commands

```sh
.venv/bin/python manage.py migrate
.venv/bin/python manage.py loaddata model_catalog
.venv/bin/uvicorn heavychat.asgi:application --host 127.0.0.1 --port 8000 --reload
```
