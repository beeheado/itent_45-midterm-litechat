# HeavyChat Frontend UI Plan

- **Created:** 2026-09-29T07:38:54+00:00
- **Updated:** 2026-09-29T08:02:17+00:00
- **Study:** [`doc/study/005-frontend-ui-study.md`](../study/005-frontend-ui-study.md)
- **Status:** Phase 5 complete and merged to `main`; awaiting Phase 6 approval.
- **Scope:** Server-rendered shell and pages, HTMX fragment interactions, a secure fetch-based SSE client, and view/template tests. Do not change ledger semantics or start Phase 6.

## Execution Checklist

### 1. Routes, View Context, and Templates

- [x] Add authenticated home/session/profile/model-modal views and routes. Ensure all session, BillingAccount, UserProfile, and MemoryItem lookups are scoped to the authenticated user.
- [x] Ensure a new user has a default `[Personal] <Display Name>` BillingAccount without exposing another user's account.
- [x] Build a responsive shared shell with HeavyChat branding, Chat/SimGen navigation, Profile navigation, session list/new-session button, current BillingAccount, and a live credits/USD balance badge.
- [x] Build an HTMX-loaded model selector with authorized BillingAccount dropdown, cost caption, Cards/Compact toggle, and active OpenAI models ordered Sol/Terra/Luna with the supplied tier copy and rates.
- [x] Create/bind a ChatSession only after validating the selected account belongs to the user and the selected ModelCatalog record is active; redirect into the session.
- [x] Render completed user/assistant messages, exclude reasoning content from the visible feed, and provide a scrollable composer with Enter-to-send and Shift+Enter newline behavior.
- [x] Add a responsive Profile page with display identity/member date, global prompt update, AI memory toggle, active memory list/add/delete, and explicit mock +500-credit top-up via `deposit_credits()`.

### 2. HTMX and Fetch Streaming Client

- [x] Use standard HTMX for modal loading/session creation, profile changes, memory CRUD, and top-up balance fragment refreshes. Keep the Phase 4 completion endpoint's POST contract.
- [x] Add a vanilla JavaScript submit handler using `fetch()` with same-origin credentials and CSRF token, then read `ReadableStream` chunks via `response.body.getReader()` and a streaming `TextDecoder`.
- [x] Parse SSE events across arbitrary byte boundaries, render `delta` content as incrementally sanitized Markdown, apply syntax highlighting, and add code-copy buttons using DOM APIs.
- [x] On `settled`, update all credits/USD balance badges without navigation. On SSE/fetch errors, show a safe status and restore the composer controls.
- [x] Sanitize every Markdown render with DOMPurify; do not mark model output safe or pass `reasoning_content` into the visible renderer. Pin HTMX/marked/DOMPurify/highlight.js CDN versions and document their deployment/CSP caveat.

### 3. Tests, Documentation, and Rendezvous

- [x] Add `tests/test_views.py` for landing/session rendering, model/account selection and ownership, profile prompt updates, memory toggle/add/delete, and mock top-up ledger/balance changes.
- [x] Keep streaming tests using the captured fixture/mocks; add coverage for browser event parsing/rendering boundaries where feasible without live provider calls.
- [x] Run `.venv/bin/python -m pytest` and `.venv/bin/python manage.py check` from the project environment.
- [x] Update `doc/wiki/frontend-ui.md` with routes, shell/template composition, CSRF/ownership rules, fetch SSE event flow, XSS controls, and local setup.
- [x] Review the staged diff and ensure `.env`, SQLite data, generated caches, and unrelated untracked files are excluded.
- [x] Commit with `feat: build heavychat ui with fetch sse streaming, profile, and model modal` and merge into `main` only after verification passes.

## Verification Record

- `.venv/bin/python -m pytest`: 28 passed.
- `.venv/bin/python manage.py check`: no issues.
- JavaScript syntax check (`node --check chat/static/chat/js/app.js`): passed.
- Migrations are current and `pip check` reports no broken requirements.
- Tests use local fixtures/mocks; no live provider call or payment processor was invoked.
- Feature commit `8bf5222` was fast-forward merged into `main`.

## Stop Condition

Complete Phase 5 only. Do not begin Phase 6 or add payment processing, SimGen behavior, additional model providers, or unapproved UI workflows. After verification, docs sync, commit, and merge, halt for the user's next instruction.
