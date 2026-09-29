# HeavyChat Handoff

## System Architecture

HeavyChat is a Django 5.1 ASGI application. Django templates render the UI; HTMX handles navigation and forms, while vanilla JavaScript `fetch()` reads the POST-based completion response incrementally. The browser renders Markdown with marked.js, sanitizes it with DOMPurify, and highlights code with highlight.js.

The `chat` app owns views and provider streaming. The `core` app owns profiles, memories, model catalog, chat sessions/messages, billing accounts, and usage records. SQLite is the local database. Credit changes go through transactional services and an append-only ledger; completed usage records retain token counts, request-time rates, cost, and credit debit. One credit is $0.01.

## Provider Contract

- OpenAI-compatible chat endpoint: `https://proxy.litechat.ai/openai/v1/chat/completions`.
- Set `OPENAI_PROXY_KEY` in the ignored local `.env` file for live completions. The key is not needed to start the app or use local UI flows.
- The server sends chat-completion requests and parses SSE `data:` events. It keeps `choices[0].delta.content` separate from `reasoning_content`, reads the usage-only event after `finish_reason`, and treats `[DONE]` as the successful stream terminator.
- The browser receives user-facing content deltas, not reasoning. The server persists reasoning separately and settles credit usage from provider token counts when available.
- The checked-in reference stream is `tests/fixtures/provider_stream.sse`; its supplied provenance and missing capture metadata are recorded in `doc/wiki/provider-contract.md`. Automated tests replay this fixture/mock streams and do not call the live provider.

## Model Tiers

The local `model_catalog` fixture contains these active models and user-supplied baseline rates. These rates are configuration and were not observed in the captured provider response.

| Tier | Model ID | Input / 1M tokens | Output / 1M tokens |
| --- | --- | ---: | ---: |
| Luna | `gpt-5.6-luna` | $0.15 | $0.60 |
| Terra | `gpt-5.6-terra` | $0.50 | $2.00 |
| Sol | `gpt-5.6-sol` | $2.50 | $10.00 |

## Local Setup and Run

From the repository root, create the environment and install dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
```

Optionally set `OPENAI_PROXY_KEY` in `.env` to enable live completions. Then initialize the database and demo account:

```sh
.venv/bin/python manage.py migrate
.venv/bin/python manage.py loaddata model_catalog
.venv/bin/python manage.py setup_demo
```

Start the ASGI server:

```sh
.venv/bin/uvicorn heavychat.asgi:application --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000/` and sign in as `luis`. On first setup, the command prints a generated local password once; alternatively set `HEAVYCHAT_DEMO_PASSWORD` before running it. The idempotent command creates a personal account with 1,000 credits ($10.00) and a default profile without depositing those credits again on subsequent runs.

Run the suite with `.venv/bin/python -m pytest`. The tests do not require a provider key or live network access.

## Release Limitations

- Django 5.1.15 is unsupported; upgrade to a supported Django release before production deployment.
- SQLite is for local use and does not validate multi-worker ledger locking/concurrency. Validate billing against the intended production database before real usage.
- Live provider availability and deployment proxy behavior are not tested. Configure streaming proxies to avoid buffering and allow long-lived responses.
- Frontend libraries are loaded from CDNs; evaluate availability, CSP, and SRI for deployment.
