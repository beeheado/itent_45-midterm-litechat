# HeavyChat Session Handoff

## Current State

Phases 1 through 6 are implemented on `main`:

1. Captured and documented the LiteChat OpenAI-compatible streaming contract and checked in the reference SSE fixture with provenance.
2. Established the Django project, ASGI entry point, pinned dependencies, environment settings, SQLite development database, and pytest setup.
3. Added profiles, memories, model catalog, billing accounts, an append-only credit ledger, chat sessions/messages, and immutable usage records.
4. Implemented asynchronous provider streaming, context assembly, preflight credit reservation, token/cost settlement, and failure/disconnect cleanup.
5. Built the responsive chat/profile UI, model selector, HTMX form/navigation flows, and browser `fetch()` streaming client.
6. Added repeatable demo-user setup, final release documentation, and root-relative static URLs so local styles/scripts work from nested routes.

## Stack and Architecture

- Python 3.12+; the current environment is Python 3.12.3.
- Django 5.1.x (`5.1.15`) with `heavychat.asgi:application` served by Uvicorn.
- SQLite for local development. `core` owns domain/accounting models; `chat` owns pages and streaming integration.
- Django templates and responsive, dark LiteChat-inspired shell. Tailwind CSS is available from its CDN; component layout and styling are in `chat/static/chat/css/app.css`, served with JavaScript at root-relative `/static/` URLs.
- HTMX handles navigation and form/modal interactions. Vanilla JavaScript `fetch()` submits prompts and reads the POST SSE stream incrementally.
- marked.js renders Markdown, DOMPurify sanitizes it, and highlight.js highlights code with a dark stylesheet.

## Provider Contract

- Base URL: `https://proxy.litechat.ai/openai/v1`.
- Request: `POST /openai/v1/chat/completions` (full URL: `https://proxy.litechat.ai/openai/v1/chat/completions`).
- Set `OPENAI_PROXY_KEY` in local `.env` for live requests. It is not required to run the UI or tests and must never be committed.
- The stream parser handles `choices[0].delta.content` independently from `reasoning_content`. Reasoning is stored separately and is not sent to the browser or mixed into conversation history.
- Continue after the finish-reason event to read the final usage-only event (`prompt_tokens`, `completion_tokens`), then treat `[DONE]` as successful stream termination. If final usage is missing, token counts are estimated and recorded as estimated.
- The checked-in capture is `tests/fixtures/provider_stream.sse`; its observed shape and provenance are in `doc/wiki/provider-contract.md`. Tests replay the capture or mock the SDK; they do not call the provider.

## Model Catalog

The active local catalog contains the following models and configured baseline USD rates per million tokens. Rates are user-supplied configuration, not pricing observed in the captured stream.

| Tier | Model ID | Input / 1M | Output / 1M |
| --- | --- | ---: | ---: |
| Luna | `gpt-5.6-luna` | $0.15 | $0.60 |
| Terra | `gpt-5.6-terra` | $0.50 | $2.00 |
| Sol | `gpt-5.6-sol` | $2.50 | $10.00 |

## Accounting and Ledger

- One credit equals $0.01 USD. Usage cost is calculated from request-time Decimal rates, and credit debit is `ceil(cost_usd * 100)`.
- Before contacting the provider, HeavyChat estimates request exposure and reserves `max(50 credits, estimated debit + 50 credits)`.
- On a complete stream, the server reads final usage (or records an estimate) and atomically settles the reservation, assistant message, and immutable usage transaction.
- Upstream errors, truncated streams, and client disconnects fail the assistant message and release/refund the reservation idempotently. A completed provider response that cannot be reconciled for insufficient funds retains its reservation/output for reconciliation rather than being treated as a failed, free call.
- Credit deposits, reservations, settlements, and refunds are append-only `CreditLedger` entries with idempotency keys. SQLite tests do not establish multi-worker locking guarantees.

## Frontend Features

- Responsive dark workspace shell with sidebar chat/profile navigation, session history, current account/balance badge, and a mobile navigation drawer.
- Model selector modal offers Cards and Compact layouts and selects a user-owned billing account.
- Conversation view streams assistant content into the active message, auto-scrolls, and updates the balance after settlement. Reasoning remains hidden.
- Profile page edits the global system prompt and memory opt-in/items; a mock `+500` credit top-up exercises the ledger without processing a payment.
- Tailwind, HTMX, marked.js, highlight.js, and DOMPurify load from the base template head. App CSS/JS URLs use `/static/`, including on nested session and profile routes.

## Demo Users

Run `setup_demo` to provision both seeded users and their default profiles:

| Username | Personal BillingAccount | Initial balance |
| --- | --- | ---: |
| `luis` | `[Personal] LUIS CLARENCE MARIANO` | 1,000 credits ($10.00) |
| `beeheado` | `[Personal] beeheado` | 1,000 credits ($10.00) |

Each initial balance is posted as a separate, idempotent `DEPOSIT`. Re-running setup does not repeat deposits or reset existing passwords. New users receive a generated local password printed once; alternatively set `HEAVYCHAT_DEMO_PASSWORD` before setup. `--reset-password` intentionally rotates `luis`'s password.

## Setup, Verification, and Run

Create the virtual environment, install dependencies, and prepare `.env` from the placeholder (keep real credentials local):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
```

Initialize the database and demo users:

```sh
.venv/bin/python manage.py migrate
.venv/bin/python manage.py loaddata model_catalog
.venv/bin/python manage.py setup_demo
```

Start the server, then sign in at `http://127.0.0.1:8000/accounts/login/` as `luis` or `beeheado`. The login page honors protected-page redirects and returns direct logins to `/`. If a generated local password was not saved, use Django's `manage.py shell` to set a new password for that account; do not put it in committed files.

Run verification and start the ASGI development server:

```sh
.venv/bin/python -m pytest -v
.venv/bin/uvicorn heavychat.asgi:application --host 127.0.0.1 --port 8000 --reload
```

The current suite contains 31 tests, including the static-asset regression test. Open `http://127.0.0.1:8000/` after setup. Live completions require a valid `OPENAI_PROXY_KEY`.

## Operational Limitations

- Django 5.1.15 is unsupported; upgrade to a supported Django release before production.
- SQLite is for local development and does not establish multi-worker ledger concurrency. Validate billing against the intended production database before real usage.
- CDN/provider uptime, deployed SSE proxy behavior, CSP/SRI, and browser-level accessibility are not covered by the automated tests.
