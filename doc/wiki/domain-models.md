# Domain Models and Credit Ledger

## Scope

Phase 3 adds relational records and accounting services in the Django `core` app. It does not add chat views, provider calls, or streaming endpoints. The project currently targets Django 5.1.15 as explicitly constrained; that version is unsupported and must be upgraded before production.

## Schema

- `UserProfile` has a one-to-one link to Django's auth user, a global system prompt, and `ai_memories_enabled` (default false).
- `MemoryItem` belongs to one profile and stores a category (`preference`, `fact`, or `instruction`) plus text content.
- `BillingAccount` belongs to a user and stores a display name and nonnegative integer `credit_balance`.
- `CreditLedger` is an append-only record with a globally unique idempotency key, signed amount, kind, timestamp, account, and optional reference to the reservation being adjusted.
- `ModelCatalog` stores unique provider model IDs, display name, Luna/Terra/Sol tier, provider, Decimal rates per million tokens, and active state.
- `ChatSession` links its owner, selected billing account, and model. `full_clean()` validates that the account belongs to the owner; settlement also enforces the relationship.
- `ChatMessage` stores system/user/assistant role, content, nullable `reasoning_content`, and nonnegative prompt/completion token counts.
- `UsageTransaction` is one-to-one with an assistant message, links the session, and optionally links its originating reserve (always populated for new settlements). It snapshots rates and stores tokens, USD cost, integer credit debit, estimate flag, and creation time. Ordinary model updates/deletes are rejected.

## Credit Units and Pricing

The account balance and ledger amount use the same integer unit: one credit is one cent, so 100 credits equal $1.00. Do not apply a second cents conversion to ledger amounts.

`calculate_cost_and_credits(prompt_tokens, completion_tokens, input_rate, output_rate)` accepts USD per-million-token rates and computes:

```text
cost_usd = (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000
credit_debit = ceil(cost_usd * 100)
```

It uses `Decimal`, sums the input/output cost before rounding, rejects negative inputs, and rounds once. Example: `$0.0012` costs one credit; `$0.0000` costs zero credits.

## Ledger Lifecycle

- `deposit_credits` appends a positive `DEPOSIT` and increments the account in one transaction.
- `reserve_credits` checks available balance, decrements it, and appends a negative `RESERVE` in one transaction.
- `settle_usage` receives the request's rate snapshot, computes actual cost/debit, appends a signed `SETTLE` adjustment, updates message token counts, and creates one immutable usage audit atomically.
- `release_reservation` appends a positive `REFUND` and returns all reserved credits if the reservation has not already been finalized.

If `r` credits were reserved and actual use costs `d`, the settlement adjustment is `r - d`: positive for unused reserve, negative for an overage, and zero for exact usage. Reserve plus settlement therefore nets to `-d`. A release nets the reserve back to zero. Unique idempotency keys, a one-finalization-per-reservation constraint, and one usage audit per message prevent duplicate charging. Reusing a key for different parameters raises `IdempotencyConflict`.

## Catalog Fixture

`core/fixtures/model_catalog.json` provides `gpt-5.6-luna` with the requested Luna/OpenAI display identity. No authoritative rates were supplied, so the fixture's zero rates are explicitly placeholders and `is_active` is false. Do not activate or offer this record until real pricing is supplied. Load it for a local development database with:

```sh
.venv/bin/python manage.py loaddata model_catalog
```

This catalog seed is configuration, not a captured provider response.

## Integrity and Operational Limits

Database constraints enforce nonnegative balances, token counts, costs, rates, and credit debits; foreign keys and unique constraints enforce relationships/idempotency. ORM guards reject ordinary ledger and usage record updates/deletes, but privileged raw SQL or bulk `QuerySet.update()` can bypass application immutability.

Ledger services use short `transaction.atomic()` blocks, conditional `F()` balance updates, and row locks where supported. SQLite does not provide effective row-level `select_for_update()` locking, so current tests verify single-process behavior only. Validate concurrent ledger operations against the eventual production database, preferably PostgreSQL, before multi-worker billing.

Run migrations and verification with:

```sh
.venv/bin/python manage.py migrate
.venv/bin/python -m pytest
.venv/bin/python manage.py check
```
