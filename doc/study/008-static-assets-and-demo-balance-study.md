# HeavyChat Static Assets and Demo Balance Study

- **Created:** 2026-09-29T09:06:11+00:00
- **Status:** Study complete; execution is authorized by the user's fix request.
- **Scope:** Ensure local static URLs resolve at nested chat routes, verify the CDN assets already in the base template, seed both `luis` and `beeheado` with idempotent personal accounts/profiles, run requested checks, and make the requested fix commit on `main`.

## Verified Facts

- The app's base template already includes Tailwind CDN, HTMX, marked.js, DOMPurify, highlight.js, and the GitHub Dark highlight stylesheet in `<head>`.
- The app stylesheet and JavaScript exist under `chat/static/chat/`; component-specific selectors in `app.css` style the sidebar, navigation, model cards, chat bubbles, and buttons.
- `STATIC_URL` is currently the relative value `static/`. At nested URLs this makes `{% static %}` assets resolve relative to the current route, which can leave the app CSS/JS missing.
- `chat/management/commands/setup_demo.py` currently re-exports the core command; the core implementation creates only `luis` and makes one idempotent 1,000-credit deposit.
- The local SQLite database currently has no `beeheado` user. The existing account/ledger API supports a stable idempotency key and the ledger is append-only.
- The branch is `main` with pre-existing staged changes (including template/navigation cleanup and workflow documents). These changes must be preserved and excluded from this task's commit unless specifically needed.

## Tradeoffs and Risks

- Correct the root cause by making `STATIC_URL` absolute (`/static/`), rather than replacing the existing component stylesheet with Tailwind utilities. The existing LiteChat-style UI is custom CSS and already has matching selectors; Tailwind alone does not style those class names.
- Retain all current CDN dependencies and verify their rendered references in a regression test. No frontend redesign or extra build tooling is needed.
- Provision both named users, with account-specific stable deposit keys, instead of trying to infer an authenticated request user from a management command. Preserve existing passwords and do not rewrite balances; the initial deposit is applied once through `deposit_credits()`.
- Provider/CDN availability is external and cannot be guaranteed by local tests. The automated verification checks markup and local static paths, not CDN network delivery.

## Assumptions and Open Questions

- `beeheado` is a username and should receive account name `[Personal] beeheado` exactly.
- Existing account balance changes from future usage must remain ledger-driven; rerunning the command must not restore spent credits.
- The existing user-specified CDN versions and dark stylesheet remain appropriate.

## Decision

Proceed with an absolute static URL, a chat-owned idempotent demo command that provisions `luis` and `beeheado`, focused regression tests, and documentation sync. Run the requested setup command, Django check, and full pytest suite before committing only this task's changes.
