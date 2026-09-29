from decimal import Decimal, InvalidOperation, ROUND_CEILING

from django.db import IntegrityError, transaction
from django.db.models import F

from .models import (
    BillingAccount,
    ChatMessage,
    ChatSession,
    CreditLedger,
    UsageTransaction,
)


class LedgerError(Exception):
    """Base class for rejected credit-ledger operations."""


class InsufficientCredits(LedgerError):
    """Raised when an operation would make a billing balance negative."""


class IdempotencyConflict(LedgerError):
    """Raised when an idempotency key is reused for a different operation."""


class ReservationFinalized(LedgerError):
    """Raised when a reservation already has a settle or release entry."""


def _integer(value: int, name: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < 0 or (positive and value == 0):
        qualifier = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be {qualifier}")
    return value


def _rate(value: Decimal | int | str, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{name} must be a decimal value") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"{name} must be a finite, nonnegative decimal")
    return result


def _idempotency_key(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError("idempotency_key must contain 1 to 128 characters")
    return value


def _account_id(account: BillingAccount | int) -> int:
    account_id = account.pk if isinstance(account, BillingAccount) else account
    if isinstance(account_id, bool) or not isinstance(account_id, int):
        raise ValueError("billing_account must be a saved account or integer ID")
    return account_id


def _idempotent_entry(
    key: str, *, billing_account_id: int, kind: str, amount: int, reservation_id: int | None = None
) -> CreditLedger | None:
    entry = CreditLedger.objects.filter(idempotency_key=key).first()
    if entry is None:
        return None
    if (
        entry.billing_account_id != billing_account_id
        or entry.kind != kind
        or entry.amount != amount
        or entry.reservation_id != reservation_id
    ):
        raise IdempotencyConflict("Idempotency key was already used for another operation")
    return entry


def calculate_cost_and_credits(
    prompt_tokens: int,
    completion_tokens: int,
    input_rate: Decimal | int | str,
    output_rate: Decimal | int | str,
) -> tuple[Decimal, int]:
    prompt_tokens = _integer(prompt_tokens, "prompt_tokens")
    completion_tokens = _integer(completion_tokens, "completion_tokens")
    input_rate = _rate(input_rate, "input_rate")
    output_rate = _rate(output_rate, "output_rate")

    cost_usd = (
        Decimal(prompt_tokens) * input_rate
        + Decimal(completion_tokens) * output_rate
    ) / Decimal(1_000_000)
    credit_debit = int((cost_usd * Decimal(100)).to_integral_value(rounding=ROUND_CEILING))
    return cost_usd, credit_debit


def deposit_credits(
    billing_account: BillingAccount | int,
    amount: int,
    idempotency_key: str,
) -> CreditLedger:
    account_id = _account_id(billing_account)
    amount = _integer(amount, "amount", positive=True)
    key = _idempotency_key(idempotency_key)
    expected = {
        "billing_account_id": account_id,
        "kind": CreditLedger.Kind.DEPOSIT,
        "amount": amount,
    }
    try:
        with transaction.atomic():
            existing = _idempotent_entry(key, **expected)
            if existing:
                return existing
            BillingAccount.objects.select_for_update().get(pk=account_id)
            BillingAccount.objects.filter(pk=account_id).update(
                credit_balance=F("credit_balance") + amount
            )
            return CreditLedger.objects.create(
                **expected,
                idempotency_key=key,
            )
    except IntegrityError:
        existing = _idempotent_entry(key, **expected)
        if existing:
            return existing
        raise


def reserve_credits(
    billing_account: BillingAccount | int,
    amount: int,
    idempotency_key: str,
) -> CreditLedger:
    account_id = _account_id(billing_account)
    amount = _integer(amount, "amount", positive=True)
    key = _idempotency_key(idempotency_key)
    expected = {
        "billing_account_id": account_id,
        "kind": CreditLedger.Kind.RESERVE,
        "amount": -amount,
    }
    try:
        with transaction.atomic():
            existing = _idempotent_entry(key, **expected)
            if existing:
                return existing
            BillingAccount.objects.select_for_update().get(pk=account_id)
            updated = BillingAccount.objects.filter(
                pk=account_id,
                credit_balance__gte=amount,
            ).update(credit_balance=F("credit_balance") - amount)
            if not updated:
                raise InsufficientCredits("Billing account has insufficient credits")
            return CreditLedger.objects.create(
                **expected,
                idempotency_key=key,
            )
    except IntegrityError:
        existing = _idempotent_entry(key, **expected)
        if existing:
            return existing
        raise


def settle_usage(
    reservation_key: str,
    *,
    session: ChatSession,
    message: ChatMessage,
    prompt_tokens: int,
    completion_tokens: int,
    input_rate_per_million: Decimal | int | str,
    output_rate_per_million: Decimal | int | str,
    is_estimated: bool,
    idempotency_key: str,
) -> UsageTransaction:
    reservation_key = _idempotency_key(reservation_key)
    key = _idempotency_key(idempotency_key)
    prompt_tokens = _integer(prompt_tokens, "prompt_tokens")
    completion_tokens = _integer(completion_tokens, "completion_tokens")
    input_rate = _rate(input_rate_per_million, "input_rate_per_million")
    output_rate = _rate(output_rate_per_million, "output_rate_per_million")
    if not isinstance(is_estimated, bool):
        raise ValueError("is_estimated must be a boolean")
    if session.pk is None or message.pk is None:
        raise ValueError("session and message must be saved")

    try:
        with transaction.atomic():
            reservation = CreditLedger.objects.select_for_update().get(
                idempotency_key=reservation_key,
                kind=CreditLedger.Kind.RESERVE,
            )
            current_session = ChatSession.objects.select_related("billing_account").get(
                pk=session.pk
            )
            current_message = ChatMessage.objects.select_for_update().get(pk=message.pk)
            if current_session.billing_account_id != reservation.billing_account_id:
                raise LedgerError("Reservation account does not match the chat session")
            if current_session.billing_account.user_id != current_session.owner_id:
                raise LedgerError("Billing account must belong to the session owner")
            if current_message.session_id != current_session.pk:
                raise LedgerError("Assistant message must belong to the chat session")
            if current_message.role != ChatMessage.Role.ASSISTANT:
                raise LedgerError("Usage must settle against an assistant message")

            cost_usd, credit_debit = calculate_cost_and_credits(
                prompt_tokens,
                completion_tokens,
                input_rate,
                output_rate,
            )
            adjustment = -reservation.amount - credit_debit
            expected = {
                "billing_account_id": reservation.billing_account_id,
                "kind": CreditLedger.Kind.SETTLE,
                "amount": adjustment,
                "reservation_id": reservation.pk,
            }
            existing = _idempotent_entry(key, **expected)
            if existing:
                usage = UsageTransaction.objects.filter(message_id=current_message.pk).first()
                if usage is None or not _usage_matches(
                    usage,
                    session_id=current_session.pk,
                    reservation_id=reservation.pk,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    input_rate=input_rate,
                    output_rate=output_rate,
                    cost_usd=cost_usd,
                    credit_debit=credit_debit,
                    is_estimated=is_estimated,
                ):
                    raise IdempotencyConflict("Settlement key does not match its usage audit")
                return usage
            if reservation.adjustments.exists():
                raise ReservationFinalized("Reservation has already been settled or released")
            if UsageTransaction.objects.filter(message_id=current_message.pk).exists():
                raise IdempotencyConflict("Assistant message already has a usage transaction")

            account = BillingAccount.objects.select_for_update().get(
                pk=reservation.billing_account_id
            )
            if adjustment < 0:
                updated = BillingAccount.objects.filter(
                    pk=account.pk,
                    credit_balance__gte=-adjustment,
                ).update(credit_balance=F("credit_balance") + adjustment)
                if not updated:
                    raise InsufficientCredits("Balance cannot cover usage above its reservation")
            elif adjustment > 0:
                BillingAccount.objects.filter(pk=account.pk).update(
                    credit_balance=F("credit_balance") + adjustment
                )

            ChatMessage.objects.filter(pk=current_message.pk).update(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            usage = UsageTransaction.objects.create(
                reservation=reservation,
                session=current_session,
                message=current_message,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                input_rate_per_million=input_rate,
                output_rate_per_million=output_rate,
                cost_usd=cost_usd,
                credit_debit=credit_debit,
                is_estimated=is_estimated,
            )
            CreditLedger.objects.create(
                **expected,
                idempotency_key=key,
            )
            return usage
    except IntegrityError:
        existing = CreditLedger.objects.filter(idempotency_key=key).first()
        if existing:
            reservation = CreditLedger.objects.get(idempotency_key=reservation_key)
            cost_usd, credit_debit = calculate_cost_and_credits(
                prompt_tokens,
                completion_tokens,
                input_rate,
                output_rate,
            )
            expected_adjustment = -reservation.amount - credit_debit
            if (
                existing.kind == CreditLedger.Kind.SETTLE
                and existing.billing_account_id == reservation.billing_account_id
                and existing.reservation_id == reservation.pk
                and existing.amount == expected_adjustment
            ):
                usage = UsageTransaction.objects.filter(message_id=message.pk).first()
                if usage and _usage_matches(
                    usage,
                    session_id=current_session.pk,
                    reservation_id=reservation.pk,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    input_rate=input_rate,
                    output_rate=output_rate,
                    cost_usd=cost_usd,
                    credit_debit=credit_debit,
                    is_estimated=is_estimated,
                ):
                    return usage
            raise IdempotencyConflict("Settlement key was concurrently used by another operation")
        if CreditLedger.objects.filter(
            reservation__idempotency_key=reservation_key,
            kind__in=(CreditLedger.Kind.SETTLE, CreditLedger.Kind.REFUND),
        ).exists():
            raise ReservationFinalized("Reservation has already been settled or released") from None
        raise


def release_reservation(reservation_key: str, idempotency_key: str) -> CreditLedger:
    reservation_key = _idempotency_key(reservation_key)
    key = _idempotency_key(idempotency_key)
    try:
        with transaction.atomic():
            reservation = CreditLedger.objects.select_for_update().get(
                idempotency_key=reservation_key,
                kind=CreditLedger.Kind.RESERVE,
            )
            refund_amount = -reservation.amount
            expected = {
                "billing_account_id": reservation.billing_account_id,
                "kind": CreditLedger.Kind.REFUND,
                "amount": refund_amount,
                "reservation_id": reservation.pk,
            }
            existing = _idempotent_entry(key, **expected)
            if existing:
                return existing
            if reservation.adjustments.exists():
                raise ReservationFinalized("Reservation has already been settled or released")

            BillingAccount.objects.select_for_update().get(
                pk=reservation.billing_account_id
            )
            BillingAccount.objects.filter(pk=reservation.billing_account_id).update(
                credit_balance=F("credit_balance") + refund_amount
            )
            return CreditLedger.objects.create(
                **expected,
                idempotency_key=key,
            )
    except IntegrityError:
        reservation = CreditLedger.objects.get(
            idempotency_key=reservation_key,
            kind=CreditLedger.Kind.RESERVE,
        )
        expected = {
            "billing_account_id": reservation.billing_account_id,
            "kind": CreditLedger.Kind.REFUND,
            "amount": -reservation.amount,
            "reservation_id": reservation.pk,
        }
        existing = CreditLedger.objects.filter(idempotency_key=key).first()
        if existing:
            return _idempotent_entry(key, **expected)
        if CreditLedger.objects.filter(
            reservation__idempotency_key=reservation_key,
            kind__in=(CreditLedger.Kind.SETTLE, CreditLedger.Kind.REFUND),
        ).exists():
            raise ReservationFinalized("Reservation has already been settled or released") from None
        raise


def _usage_matches(
    usage: UsageTransaction,
    *,
    session_id: int,
    reservation_id: int,
    prompt_tokens: int,
    completion_tokens: int,
    input_rate: Decimal,
    output_rate: Decimal,
    cost_usd: Decimal,
    credit_debit: int,
    is_estimated: bool,
) -> bool:
    return (
        usage.session_id == session_id
        and usage.reservation_id == reservation_id
        and usage.prompt_tokens == prompt_tokens
        and usage.completion_tokens == completion_tokens
        and usage.input_rate_per_million == input_rate
        and usage.output_rate_per_million == output_rate
        and usage.cost_usd == cost_usd
        and usage.credit_debit == credit_debit
        and usage.is_estimated == is_estimated
    )
