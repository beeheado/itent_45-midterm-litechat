from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from core.models import (
    BillingAccount,
    ChatMessage,
    ChatSession,
    CreditLedger,
    ModelCatalog,
    UsageTransaction,
)
from core.services import (
    IdempotencyConflict,
    InsufficientCredits,
    ReservationFinalized,
    calculate_cost_and_credits,
    deposit_credits,
    release_reservation,
    reserve_credits,
    settle_usage,
)


def make_account(starting_credits=0):
    user = get_user_model().objects.create_user(username=f"ledger-user-{BillingAccount.objects.count()}")
    account = BillingAccount.objects.create(user=user, name=f"[Personal] {user.username}")
    if starting_credits:
        deposit_credits(account, starting_credits, f"deposit-{user.username}")
    return user, account


def make_session(account, input_rate="100.000000", output_rate="0.000000"):
    model = ModelCatalog.objects.create(
        model_id=f"test-model-{ChatSession.objects.count()}",
        display_name="Ledger Test Model",
        tier=ModelCatalog.Tier.LUNA,
        provider=ModelCatalog.Provider.OPENAI,
        input_rate_per_million=Decimal(input_rate),
        output_rate_per_million=Decimal(output_rate),
        is_active=True,
    )
    return ChatSession.objects.create(
        owner=account.user,
        billing_account=account,
        model=model,
        title="Ledger test",
    )


@pytest.mark.parametrize(
    ("prompt_tokens", "input_rate", "expected_cost", "expected_credits"),
    [
        (12, "100.000000", Decimal("0.0012"), 1),
        (0, "100.000000", Decimal("0"), 0),
    ],
)
def test_calculate_cost_and_credits_uses_ceiling(
    prompt_tokens, input_rate, expected_cost, expected_credits
):
    cost_usd, credit_debit = calculate_cost_and_credits(
        prompt_tokens,
        0,
        input_rate,
        "0.000000",
    )

    assert cost_usd == expected_cost
    assert credit_debit == expected_credits


def test_calculate_cost_rejects_negative_inputs():
    with pytest.raises(ValueError):
        calculate_cost_and_credits(-1, 0, 1, 1)
    with pytest.raises(ValueError):
        calculate_cost_and_credits(0, 0, -1, 1)


@pytest.mark.django_db
def test_deposit_and_reservation_retries_are_idempotent():
    _, account = make_account()
    deposit = deposit_credits(account, 100, "deposit-once")
    repeated_deposit = deposit_credits(account, 100, "deposit-once")
    reservation = reserve_credits(account, 60, "reserve-once")
    repeated_reservation = reserve_credits(account, 60, "reserve-once")

    account.refresh_from_db()
    assert repeated_deposit.pk == deposit.pk
    assert repeated_reservation.pk == reservation.pk
    assert account.credit_balance == 40
    assert CreditLedger.objects.count() == 2

    with pytest.raises(IdempotencyConflict):
        reserve_credits(account, 50, "reserve-once")

    deposit.amount = 101
    with pytest.raises(ValidationError, match="append-only"):
        deposit.save()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        deposit.delete()


@pytest.mark.django_db
def test_insufficient_reserve_does_not_change_balance_or_write_ledger():
    _, account = make_account(starting_credits=10)

    with pytest.raises(InsufficientCredits):
        reserve_credits(account, 11, "too-large-reserve")

    account.refresh_from_db()
    assert account.credit_balance == 10
    assert not CreditLedger.objects.filter(kind=CreditLedger.Kind.RESERVE).exists()


@pytest.mark.django_db
def test_settlement_returns_unused_reserve_and_creates_usage_audit_once():
    user, account = make_account(starting_credits=100)
    session = make_session(account)
    message = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.ASSISTANT,
        content="Hello.",
    )
    input_rate = session.model.input_rate_per_million
    output_rate = session.model.output_rate_per_million
    reservation = reserve_credits(account, 50, "reserve-for-answer")
    ModelCatalog.objects.filter(pk=session.model_id).update(
        input_rate_per_million=Decimal("200.000000")
    )

    usage = settle_usage(
        reservation.idempotency_key,
        session=session,
        message=message,
        prompt_tokens=12,
        completion_tokens=0,
        input_rate_per_million=input_rate,
        output_rate_per_million=output_rate,
        is_estimated=False,
        idempotency_key="settle-answer",
    )
    repeated_usage = settle_usage(
        reservation.idempotency_key,
        session=session,
        message=message,
        prompt_tokens=12,
        completion_tokens=0,
        input_rate_per_million=input_rate,
        output_rate_per_million=output_rate,
        is_estimated=False,
        idempotency_key="settle-answer",
    )

    account.refresh_from_db()
    message.refresh_from_db()
    settlement = CreditLedger.objects.get(idempotency_key="settle-answer")
    assert repeated_usage.pk == usage.pk
    assert account.credit_balance == 99
    assert settlement.amount == 49
    assert usage.session_id == session.pk
    assert usage.message_id == message.pk
    assert usage.reservation_id == reservation.pk
    assert usage.cost_usd == Decimal("0.0012")
    assert usage.credit_debit == 1
    assert usage.input_rate_per_million == Decimal("100.000000")
    assert usage.is_estimated is False
    assert (message.prompt_tokens, message.completion_tokens) == (12, 0)
    assert UsageTransaction.objects.count() == 1
    assert user.pk == account.user_id


@pytest.mark.django_db
def test_settlement_charges_overage_and_rolls_back_if_unaffordable():
    _, account = make_account(starting_credits=3)
    session = make_session(account, input_rate="1000.000000")
    message = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.ASSISTANT,
        content="Answer",
    )
    reservation = reserve_credits(account, 1, "reserve-small")

    usage = settle_usage(
        reservation.idempotency_key,
        session=session,
        message=message,
        prompt_tokens=12,
        completion_tokens=0,
        input_rate_per_million=session.model.input_rate_per_million,
        output_rate_per_million=session.model.output_rate_per_million,
        is_estimated=True,
        idempotency_key="settle-overage",
    )

    account.refresh_from_db()
    settlement = CreditLedger.objects.get(idempotency_key="settle-overage")
    assert usage.cost_usd == Decimal("0.012")
    assert usage.credit_debit == 2
    assert settlement.amount == -1
    assert account.credit_balance == 1

    _, empty_account = make_account(starting_credits=1)
    empty_session = make_session(empty_account, input_rate="1000.000000")
    empty_message = ChatMessage.objects.create(
        session=empty_session,
        role=ChatMessage.Role.ASSISTANT,
        content="Answer",
    )
    empty_reservation = reserve_credits(empty_account, 1, "reserve-empty")
    with pytest.raises(InsufficientCredits):
        settle_usage(
            empty_reservation.idempotency_key,
            session=empty_session,
            message=empty_message,
            prompt_tokens=12,
            completion_tokens=0,
            input_rate_per_million=empty_session.model.input_rate_per_million,
            output_rate_per_million=empty_session.model.output_rate_per_million,
            is_estimated=False,
            idempotency_key="settle-unaffordable-overage",
        )

    empty_account.refresh_from_db()
    assert empty_account.credit_balance == 0
    assert not CreditLedger.objects.filter(
        reservation=empty_reservation,
        kind=CreditLedger.Kind.SETTLE,
    ).exists()
    assert not UsageTransaction.objects.filter(message=empty_message).exists()


@pytest.mark.django_db
def test_release_refunds_reservation_once_and_cannot_follow_settlement():
    _, account = make_account(starting_credits=25)
    reservation = reserve_credits(account, 20, "reserve-to-release")

    refund = release_reservation(reservation.idempotency_key, "release-once")
    repeated_refund = release_reservation(reservation.idempotency_key, "release-once")
    account.refresh_from_db()

    assert refund.pk == repeated_refund.pk
    assert refund.amount == 20
    assert account.credit_balance == 25
    with pytest.raises(ReservationFinalized):
        release_reservation(reservation.idempotency_key, "release-again")
