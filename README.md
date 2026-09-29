# HeavyChat

HeavyChat is a Django-based AI chat workbench with account-bound billing, an auditable credit ledger, profile context, model tiers, and streaming assistant responses. See [`HANDOFF.md`](HANDOFF.md) for the release architecture, provider contract, model tiers, and local evaluation guide.

## Architecture Overview

- Django 5.1.15 serves Django templates and the ASGI application through Uvicorn.
- HTMX handles navigation and profile/model/account form interactions.
- Chat prompts are posted with `fetch()` and streamed through a `ReadableStream` SSE parser. The UI renders Markdown with marked.js, sanitizes it with DOMPurify, and highlights code with highlight.js.
- SQLite is the local development database. `core` owns users' profiles, memories, BillingAccounts, ModelCatalog, sessions/messages, append-only CreditLedger, and immutable UsageTransactions. `chat` owns the UI and streaming integration.
- One credit equals $0.01. Model rates are Decimal USD per million tokens, and usage debits round up to an integer credit.

## Fresh-Clone Setup

1. Create a virtual environment and install the pinned dependencies:

   ```sh
   python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
   ```

2. Create a local environment file only if one is not already present:

   ```sh
   [ -f .env ] || cp .env.example .env
   ```

   Set `OPENAI_PROXY_KEY` in `.env` to enable live proxy requests. Never commit `.env`. Local `DEBUG=true` can use a process-local generated secret; set a persistent `SECRET_KEY` for non-debug deployments.

3. Initialize the database, model catalog, and demo user, then run the ASGI development server:

   ```sh
   .venv/bin/python manage.py migrate
   .venv/bin/python manage.py loaddata model_catalog
   .venv/bin/python manage.py setup_demo
   .venv/bin/uvicorn heavychat.asgi:application --host 127.0.0.1 --port 8000 --reload
   ```

On first creation, `setup_demo` prints a generated local password once. Copy it from that terminal output to log in as `luis`. Set `HEAVYCHAT_DEMO_PASSWORD` in `.env` before seeding if you prefer a chosen local password. The command is idempotent and does not reset the password or add the 1,000-credit initial deposit again. It seeds `[Personal] LUIS CLARENCE MARIANO`, a profile, and a Preference memory.

The UI and demo seed can run without a provider key, but live completions return a configuration error until `OPENAI_PROXY_KEY` is present.

## Verification

```sh
.venv/bin/python -m pytest -v
.venv/bin/python manage.py check
```

Tests use the captured fixture and mocked upstream streams; they do not make live provider calls or incur provider charges.

## Provider Contract and Exogenous Inputs

The routed Chat Completions endpoint is `https://proxy.litechat.ai/openai/v1/chat/completions`; this gateway does not map `/models`. The live fixture at [`tests/fixtures/provider_stream.sse`](tests/fixtures/provider_stream.sse) uses `gpt-5.6-luna`. It demonstrates separate `choices[0].delta.reasoning_content` and `content` fields, a finish-reason chunk, a usage-only chunk, and the terminal `data: [DONE]` sentinel. The parser preserves reasoning separately and waits for aggregate usage before successful settlement.

The fixture and its provenance are described in [`doc/wiki/provider-contract.md`](doc/wiki/provider-contract.md). Catalog baseline rates are user-supplied configuration and were not extracted from the captured stream.

## Autonomous Workflow

Follow the repository workflow for each outcome:

**study => plan => execute => rendezvous => sync docs**

Timestamped studies and checklists live under `doc/study/` and `doc/plan/`; living architecture and tactical decisions live under `doc/wiki/`. Keep commits conventionally scoped, run tests/checks before merging to `main`, and report external or verification blockers honestly.

## Known Deployment Risks

- The requested Django `<5.2` constraint pins Django 5.1.15, which is unsupported. Upgrade to a supported Django release before production.
- SQLite and its local tests do not establish concurrent multi-worker ledger safety. Validate billing concurrency against the production database, preferably PostgreSQL.
- Configure reverse proxies not to buffer SSE and set suitable streaming timeouts. Review CDN availability, CSP, and SRI before deployment.
