# Operations

## Local Environment

Use Python 3.11 or newer. `.env` is ignored and contains local-only configuration. Set `OPENAI_PROXY_KEY` for live completions; the base route defaults/normalizes to `https://proxy.litechat.ai/openai/v1`. Never commit or print credentials. `DEBUG=false` requires a persistent `SECRET_KEY`.

## Database and Demo User

Initialize local schema and the active model catalog with:

```sh
.venv/bin/python manage.py migrate
.venv/bin/python manage.py loaddata model_catalog
```

Create the repeatable grader account and sample context with:

```sh
.venv/bin/python manage.py setup_demo
```

The command creates username `luis`, display/account name `LUIS CLARENCE MARIANO` / `[Personal] LUIS CLARENCE MARIANO`, a 1,000-credit initial DEPOSIT, a global profile prompt, and a Preference memory. The deposit uses a stable idempotency key. On first creation a random password is printed once; alternatively set `HEAVYCHAT_DEMO_PASSWORD` in `.env`. Existing credentials and balances are not reset when rerunning. Use `--reset-password` only when intentionally rotating the local demo password.

All three OpenAI tier catalog rows load as active from user-supplied baseline rates: Luna `$0.15/$0.60`, Terra `$0.50/$2.00`, and Sol `$2.50/$10.00` input/output per million. These are not provider-captured pricing data.

## Run and Test

Start the actual ASGI application with:

```sh
.venv/bin/uvicorn heavychat.asgi:application --host 127.0.0.1 --port 8000 --reload
```

Run the verification suite and Django checks with:

```sh
.venv/bin/python -m pytest -v
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python -m pip check
```

The tests replay the saved provider stream and mock upstream responses. They do not validate provider uptime, CDN availability, proxy buffering, or production concurrency.

## Runtime and Release Caveats

- `.env`, `.venv/`, SQLite data, pytest cache, and Python bytecode are excluded by `.gitignore`.
- The model stream uses POST `fetch()` with SSE response events; reverse proxies must disable response buffering and allow long-lived requests.
- SQLite is for local development. Use the selected production database for row-lock and multi-worker ledger tests before real billing.
- Django 5.1.15 is unsupported due to the requested `<5.2` pin. The current package is for local midterm demonstration, not production deployment.
- SimGen is a placeholder only, and external payment processing is not implemented.
