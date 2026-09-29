# HeavyChat Domain Models and Accounting Study

- **Created:** 2026-09-29T05:50:57+00:00
- **Updated:** 2026-09-29T06:07:07+00:00
- **Status:** Study complete; Phase 3 execution is authorized by the user's request.
- **Scope:** Relational Django models for profiles, memories, billing accounts, ledger entries, model catalog, chat sessions/messages, immutable usage audits, and atomic credit accounting services with tests and an initial model fixture.

## Verified Inputs and Gaps

- The project runs Django 5.1.15 with SQLite and pytest-django. Phase 2 explicitly marks this Django series unsupported for production.
- Phase 1 contains a live `gpt-5.6-luna` stream, including aggregate prompt/completion usage and a `reasoning_content` field. It does not contain catalog pricing rates.
- The user defines 1 credit as $0.01 USD. `BillingAccount.credit_balance` is described as cents, while ledger amounts are credits; these are the same integer unit under that denomination: 100 credits/cents equals $1.
- No verified input/output rates for `gpt-5.6-luna` were provided. Do not infer its rate from the Luna tier name or synthesize a provider price.

## Recommended Relational Schema

### User Profile and Memory

- `UserProfile.user` is a one-to-one foreign key to Django's configured auth user. Store `global_system_prompt` as text and `ai_memories_enabled` as a boolean.
- Default `ai_memories_enabled` to `False` so stored memory is not injected without user opt-in. `MemoryItem` belongs to a profile, has a `category` choice (`preference`, `fact`, `instruction`), and text `content`.
- The relational key guarantees memory ownership. `ChatSession` remains linked to the auth `User`, not a profile, so identity and chat ownership use Django's canonical user row.

### Billing Account and Credit Ledger

- `BillingAccount.user` owns the account; `name` is display text and must not be used for authorization. `credit_balance` is an integer number of cents/credits with a database `CHECK credit_balance >= 0` constraint.
- `CreditLedger.billing_account` links every signed integer `amount` to its account. `kind` uses the requested `DEPOSIT`, `RESERVE`, `SETTLE`, and `REFUND` choices; `idempotency_key` is globally unique; `created_at` is immutable audit time.
- Add a self-reference from adjustment entries to their originating reserve entry. This is needed to settle or release the correct reservation idempotently; it does not replace the unique idempotency key.
- Treat the ledger as the audit trail and `credit_balance` as an atomically maintained spendable-balance projection. Ledger rows reject ordinary updates/deletes. Deposit and usage services write the ledger entry and balance change in the same short `transaction.atomic()` block.
- Ledger amount semantics: deposits are positive; reservations are negative. For a reserve of `r` and actual usage debit `d`, a `SETTLE` adjustment records `r - d` (positive unused credit returned, negative overage collected, zero if exact). A release writes a positive `REFUND` of the full reserved amount. Thus reserve plus settle nets to `-d`, while release nets to zero.
- Replaying an idempotency key with the same account, kind, amount, and reservation returns the original ledger row. Reusing it for a different operation raises a conflict; a unique database constraint remains the final race-safe guard.
- Include a small audited deposit service to support the `DEPOSIT` ledger kind and establish starting test/dev credit without directly mutating the balance. Payment/top-up UI remains out of scope for this phase.

### Chat and Catalog

- `ModelCatalog` has unique `model_id`, `display_name`, tier choices (`Luna`, `Terra`, `Sol`), provider choices (`openai`, `anthropic`, `google`), decimal input/output rates per million tokens, and `is_active`.
- `ChatSession` links an auth-user `owner`, selected `BillingAccount`, and `ModelCatalog`, plus `title`. Enforce that the selected billing account belongs to the owner in model validation/service boundaries; ordinary SQL constraints cannot enforce equality across these related rows.
- `ChatMessage` links to a session, has role choices (`system`, `user`, `assistant`), text content, nullable `reasoning_content`, and nonnegative prompt/completion token counts. Keep reasoning separate from user-visible content.

### Immutable Usage Audit

- `UsageTransaction` is a one-to-one audit for a completed assistant message and also links its session and (for new settlements) originating reserve entry. The reserve link is nullable to preserve historical usage audits during migration. One audit per message and one per populated reserve prevent duplicate usage settlement and provide a direct path from the audit to its ledger settlement/refund history.
- Store nonnegative prompt/completion tokens, nonnegative decimal `cost_usd`, nonnegative integer `credit_debit`, `is_estimated`, and creation time. Snapshot the input/output rates used on each transaction so future catalog price changes cannot rewrite the basis of historical costs.
- Enforce token/cost/debit bounds with database constraints. Reject ordinary usage-row updates/deletes at the model boundary; services create the audit once, as part of settlement.

## Pricing and Service Semantics

For USD rates per million tokens, compute with `Decimal`:

```text
cost_usd = (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000
credit_debit = ceil(cost_usd * 100)
```

Sum costs before rounding. `$0.0012` therefore debits 1 credit; `$0.0000` debits 0. Reject negative token counts and negative rates. Avoid binary floats and preserve the unrounded cost on `UsageTransaction`.

Recommended service contracts:

- `deposit_credits(account, amount, idempotency_key)` appends a positive `DEPOSIT` and updates the balance atomically.
- `reserve_credits(account, amount, idempotency_key)` requires a positive amount and sufficient balance, subtracts it, and writes a negative `RESERVE`.
- `settle_usage(reservation_key, session, message, token counts, request-time rate snapshots, estimate flag, idempotency_key)` computes the final debit, records the reserve-relative adjustment, adds or collects any delta atomically, and creates the immutable `UsageTransaction` once. Callers pass the rates captured when the request was priced so catalog edits during a long completion cannot change its audit cost.
- `release_reservation(reservation_key, idempotency_key)` refunds the unused full reservation if no settlement/release already finalized it.

Insufficient funds, conflicting idempotency reuse, or attempts to finalize a reservation twice must leave the balance and ledger unchanged. All operations are short transactions; never hold a DB transaction while streaming from the provider.

## Concurrency and SQLite Tradeoff

Use `transaction.atomic()`, conditional `F()` updates for available-balance checks, `select_for_update()` where supported, unique idempotency constraints, and rollback on any ledger insert failure. SQLite does not provide effective row-level locking for concurrent account spending; these tests establish single-process invariants, not production concurrency guarantees. Validate concurrent reserve/settle behavior against the eventual production database (prefer PostgreSQL) before enabling multi-worker billing.

## Initial Model Fixture and Pricing Gap

Add the requested `gpt-5.6-luna` / `GPT-5.6 Luna` / `Luna` / `openai` catalog fixture. Since no verified prices were supplied, use zero rates only as an explicitly documented placeholder and set `is_active=False`; this prevents an unpriced model from being billed or offered as usable. Load the fixture for tests and provide the `loaddata` command for local development. Replace both placeholder rates from an authoritative catalog before activating the model. This is seed configuration, not a captured provider response.

## Risks and Implementation Decision

- The cent/credit fields must use one documented integer unit consistently; avoid multiplying by 100 a second time when moving ledger values.
- The cached balance and append-only ledger can diverge if application code mutates the balance directly. Keep balance writes inside ledger services and add tests for their atomic behavior.
- The requested immutable guarantees are application-level; a database owner can bypass ORM guards. Defer database triggers/tamper-proofing unless the threat model requires it.
- Fixture rates are missing external input. The unpriced model must remain inactive until verified rates are supplied.
- Django 5.1 is unsupported, and SQLite cannot validate production row-lock behavior; both remain deployment gates from Phase 2.

**Implementation decision:** Proceed with the requested relational domain and accounting records, using Django's auth user, SQLite constraints, immutable ORM records, atomic ledger services, and the explicitly inactive zero-rate catalog placeholder. Do not implement chat views, templates, provider calls, or SSE parsing in this phase.
