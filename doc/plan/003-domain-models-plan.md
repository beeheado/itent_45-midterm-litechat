# HeavyChat Domain Models Plan

- **Created:** 2026-09-29T05:52:39+00:00
- **Updated:** 2026-09-29T06:13:01+00:00
- **Study:** [`doc/study/003-domain-models-study.md`](../study/003-domain-models-study.md)
- **Status:** Implementation and verification complete; commit/merge pending.
- **Scope:** Add the `core` relational domain, model migrations, catalog fixture, deterministic Decimal pricing, and atomic credit-ledger services/tests. Do not add chat views, templates, provider calls, or SSE parsing.

## Execution Checklist

### 1. Core ORM Schema

- [x] Create the `core` Django app and register it in `INSTALLED_APPS`.
- [x] Add `UserProfile` one-to-one with the auth user, with `global_system_prompt` and opt-in `ai_memories_enabled`.
- [x] Add `MemoryItem` with profile FK, `preference`/`fact`/`instruction` category choices, and text content.
- [x] Add `BillingAccount` with user FK, display name, integer cent/credit balance, and a database non-negative check constraint.
- [x] Add immutable `CreditLedger` rows with account FK, signed amount, `DEPOSIT`/`RESERVE`/`SETTLE`/`REFUND` kinds, globally unique idempotency key, timestamp, and reserve self-reference for adjustments.
- [x] Add `ModelCatalog` with unique model ID, display name, Luna/Terra/Sol tier, openai/anthropic/google provider, Decimal per-million input/output rates, and active flag.
- [x] Add `ChatSession` (owner, billing account, model, title) and validate the billing account is owned by the same user.
- [x] Add `ChatMessage` (session, role, content, nullable reasoning content, nonnegative token counts).
- [x] Add immutable `UsageTransaction` linked one-to-one to an assistant message and session, with an optional one-to-one link to the originating reserve for new settlements; store nonnegative token counts, USD cost, integer credit debit, estimated flag, creation time, and request-time rate snapshots.
- [x] Add model/database constraints for nonnegative balances, tokens, rates, costs, and debits; generate and apply migrations.

### 2. Pricing and Ledger Services

- [x] Implement `calculate_cost_and_credits(prompt_tokens, completion_tokens, input_rate, output_rate)` with Decimal rates per million tokens and one ceiling conversion `ceil(cost_usd * 100)`.
- [x] Implement `deposit_credits` as a short atomic positive balance update plus idempotent `DEPOSIT` ledger row.
- [x] Implement `reserve_credits` with sufficient-balance checking, atomic subtraction, and a negative idempotent `RESERVE` row.
- [x] Implement `settle_usage` to reconcile the reserve against actual debit (including a positive remainder or negative overage), append one `SETTLE`, and create the immutable `UsageTransaction` atomically using the request-time rate snapshot.
- [x] Implement `release_reservation` to append a positive `REFUND` and return all reserved credits exactly once.
- [x] Return existing rows for equivalent idempotent retries; reject conflicting key reuse, insufficient balance, and repeat finalization without changing balance or audit rows.

### 3. Fixture and Verification

- [x] Add `core/fixtures/model_catalog.json` for `gpt-5.6-luna` (`GPT-5.6 Luna`, Luna, openai). No verified rates were supplied; use zero placeholder rates and `is_active=false`, and clearly document that this record must not be activated until rates are verified.
- [x] Add `tests/test_models.py` covering profile/memory associations, account ownership, model fixture loading, database constraints, and usage audit immutability.
- [x] Add `tests/test_ledger.py` covering $0.0012 => 1 credit, $0 => 0, nonnegative balance, insufficient funds, deposit/reserve/settle/release invariants, idempotency, and atomic rollback behavior.
- [x] Run migrations, load the catalog fixture for local use, run `python3 -m pytest`, and run `python3 manage.py check` from the project virtual environment.
- [x] Update `doc/wiki/domain-models.md` with relationships, units, idempotency semantics, settlement math, fixture rate caveat, and SQLite concurrency limitations.
- [x] Review the staged diff and verify `.env`, SQLite data, generated caches, and unrelated untracked files are not committed.
- [ ] Commit with `feat: implement billing accounts, credit ledger, and domain models` and merge into `main` only after verification passes.

## Verification Record

- `python3 -m pytest`: 14 passed.
- `python3 manage.py check`: no issues.
- `makemigrations --check --dry-run`: no changes detected.
- `pip check`: no broken requirements.
- Applied migrations `0001_initial` and `0002_usagetransaction_reservation`, then loaded `model_catalog` in the ignored development SQLite database.
- The Luna fixture remains inactive with placeholder zero rates pending verified pricing.

## Stop Condition

Complete Phase 3 only. No Phase 4 parser, provider client, ASGI streaming endpoint, or chat UI work is authorized by this plan. After merge and documentation sync, halt for user review.
