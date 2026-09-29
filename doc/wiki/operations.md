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

Open `http://127.0.0.1:8000/accounts/login/` to sign in as `luis` or `beeheado`. When redirected from a protected page, the successful login returns to the requested page. New demo-user passwords are printed once during seeding. If a password was not saved, reset it locally without exposing it in source control:

```sh
.venv/bin/python manage.py shell -c "from django.contrib.auth import get_user_model; u = get_user_model().objects.get(username='beeheado'); u.set_password('choose-a-local-password'); u.save(update_fields=['password'])"
```

The command creates users `luis` and `beeheado`, personal accounts `[Personal] LUIS CLARENCE MARIANO` and `[Personal] beeheado`, and a default profile with a 1,000-credit initial DEPOSIT for each. `luis` also receives a Preference memory. Deposits use separate stable idempotency keys. On first creation a random password is printed once for each user; alternatively set `HEAVYCHAT_DEMO_PASSWORD` in `.env`. Existing credentials and balances are not reset when rerunning. Use `--reset-password` only when intentionally rotating `luis`'s local demo password.

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
- `STATIC_URL` is root-relative (`/static/`) so local CSS/JavaScript resolves from nested routes as well as `/`.
- The model stream uses POST `fetch()` with SSE response events; reverse proxies must disable response buffering and allow long-lived requests.
- SQLite is for local development. Use the selected production database for row-lock and multi-worker ledger tests before real billing.
- Django 5.1.15 is unsupported due to the requested `<5.2` pin. The current package is for local midterm demonstration, not production deployment.
- SimGen is a placeholder only, and external payment processing is not implemented.
