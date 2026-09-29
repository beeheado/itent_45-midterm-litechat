# HeavyChat Architecture

## Application Status

HeavyChat is a server-rendered AI chat application with account-bound credit billing, append-only ledger entries, model tiers, profile/memory context, asynchronous provider streaming, and a responsive template UI. Simulation behavior is not implemented. Phase 6 adds a reproducible local demo user and final verification documentation.

## Runtime and Project Layout

- Python runtime used for the foundation: 3.12.3.
- Django project package: `heavychat/`.
- Management entry point: root `manage.py`.
- ASGI application: `heavychat.asgi.application`.
- ASGI server: Uvicorn; Django's generated WSGI module is retained only as scaffold.
- `core/`: profiles, memories, billing accounts, immutable ledger/usage audits, model catalog, sessions, and messages.
- `chat/`: template views, model selector, profile/account flows, and fetch-streamed SSE integration.
- Tests: `tests/`, with provider fixtures under `tests/fixtures/`.
- Development database: SQLite at `db.sqlite3`, excluded from version control.

Run the ASGI application locally with:

```sh
.venv/bin/uvicorn heavychat.asgi:application --host 127.0.0.1 --port 8000 --reload
```

`manage.py check` verifies Django's configured components, while the smoke test imports the ASGI application. Neither check exercises LiteChat connectivity, SSE delivery through a deployment proxy, or production load.

## Pinned Direct Dependencies

`requirements.txt` pins the direct packages used by this foundation:

| Package | Version |
| --- | ---: |
| Django | 5.1.15 |
| openai | 3.20.0 |
| pytest | 9.1.1 |
| pytest-django | 4.14.0 |
| python-dotenv | 1.2.3 |
| tiktoken | 0.14.0 |
| uvicorn | 0.54.0 |

These are exact direct pins; transitive dependencies are resolved by pip from package metadata and are not hash-locked.

## Django Support Risk

The explicit requirement `Django>=5.0,<5.2` selected the latest package in range, Django 5.1.15. Django's official release table marks the 5.1 series unsupported, with extended support ending December 3, 2025. Django 5.2 is the supported LTS line but is excluded by the current constraint. This foundation is for local development only; revisit the version constraint and upgrade to a supported release before production deployment.

## Environment and Settings

`heavychat/settings.py` loads the ignored repository `.env` with `python-dotenv` and does not override variables already set by the process environment. Supported settings:

- `SECRET_KEY`: Required whenever `DEBUG=false`. When omitted in local debug mode, a process-local random key is generated; signed sessions/cookies do not survive a process restart.
- `DEBUG`: Parsed as a boolean; defaults to `true` for local development only.
- `OPENAI_PROXY_KEY`: Optional string setting used by the chat streaming client. It is not logged or tested by value.
- `LITECHAT_PROXY_BASE_URL`: Defaults to `https://proxy.litechat.ai/openai/v1` and has trailing slashes removed.
- `ALLOWED_HOSTS`: Comma-separated, defaulting to localhost and Django's test host.

`.env.example` contains placeholders only. `.env` is ignored and must not be committed. Never copy real credentials into documentation, tests, or logs.

## Local Setup and Verification

For a new checkout, create a virtual environment, install the pinned dependencies, and populate a local `.env` from the placeholder file without committing that local file. After setting a provider key if live completions are needed, initialize the project with:

```sh
.venv/bin/python manage.py migrate
.venv/bin/python manage.py loaddata model_catalog
.venv/bin/python manage.py setup_demo
.venv/bin/uvicorn heavychat.asgi:application --host 127.0.0.1 --port 8000 --reload
```

Run the tests separately with `.venv/bin/python -m pytest` and Django configuration checks with `.venv/bin/python manage.py check`.

`pytest.ini` sets `DJANGO_SETTINGS_MODULE=heavychat.settings`. `tests/test_foundation.py` verifies Django initialization, the Django 5 version, ASGI application import/configuration, SQLite selection, and resolved setting types without inspecting secret values.

## Chat and Billing Flow

An authenticated `ChatSession` selects one owned `BillingAccount` and active `ModelCatalog` entry. The fetch client submits the prompt to the async completion route. The server builds system/profile/memory/history context, reserves credits, streams only content deltas, stores reasoning separately, then settles actual or estimated usage. Failures/disconnects release the reservation; completed provider output with a settlement problem is retained for reconciliation.

One credit equals one cent. Catalog rates are Decimal USD per million tokens. The user's Phase 4 baselines are configuration and are not inferred from the SSE fixture.

## Final Demo Seed

After applying migrations and loading `model_catalog`, `.venv/bin/python manage.py setup_demo` idempotently creates the local `luis` user, `[Personal] LUIS CLARENCE MARIANO` account, sample profile/memory, and a 1,000-credit ledger deposit. It generates and prints a one-time password on first creation unless `HEAVYCHAT_DEMO_PASSWORD` is set. It never stores a plaintext password or re-adds the seed deposit on rerun.
