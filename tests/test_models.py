from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.models import (
    BillingAccount,
    ChatMessage,
    ChatSession,
    MemoryItem,
    ModelCatalog,
    UserProfile,
)
from core.services import deposit_credits, reserve_credits, settle_usage


@pytest.mark.django_db
def test_user_profile_and_memory_item_associations():
    user = get_user_model().objects.create_user(username="profile-user")
    profile = UserProfile.objects.create(
        user=user,
        global_system_prompt="Use concise answers.",
        ai_memories_enabled=True,
    )
    memory = MemoryItem.objects.create(
        user_profile=profile,
        category=MemoryItem.Category.PREFERENCE,
        content="Prefers concise answers.",
    )

    assert user.profile == profile
    assert profile.memory_items.get() == memory
    assert profile.ai_memories_enabled is True


@pytest.mark.django_db
def test_model_catalog_fixture_has_unpriced_luna_placeholder():
    call_command("loaddata", "model_catalog", verbosity=0)

    model = ModelCatalog.objects.get(model_id="gpt-5.6-luna")
    assert model.display_name == "GPT-5.6 Luna"
    assert model.tier == ModelCatalog.Tier.LUNA
    assert model.provider == ModelCatalog.Provider.OPENAI
    assert model.input_rate_per_million == 0
    assert model.output_rate_per_million == 0
    assert model.is_active is False


@pytest.mark.django_db
def test_billing_account_rejects_negative_balance_at_database_layer():
    user = get_user_model().objects.create_user(username="negative-balance-user")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            BillingAccount.objects.create(
                user=user,
                name="[Personal] Test User",
                credit_balance=-1,
            )


@pytest.mark.django_db
def test_chat_session_requires_owner_billing_account_match():
    user = get_user_model().objects.create_user(username="session-owner")
    other_user = get_user_model().objects.create_user(username="other-owner")
    account = BillingAccount.objects.create(user=other_user, name="[Personal] Other")
    model = ModelCatalog.objects.create(
        model_id="test-owner-model",
        display_name="Owner Test",
        tier=ModelCatalog.Tier.LUNA,
        provider=ModelCatalog.Provider.OPENAI,
        input_rate_per_million=0,
        output_rate_per_million=0,
    )
    session = ChatSession(
        owner=user,
        billing_account=account,
        model=model,
        title="Invalid owner pairing",
    )

    with pytest.raises(ValidationError, match="must belong to the session owner"):
        session.full_clean()


@pytest.mark.django_db
def test_usage_transaction_is_immutable_and_unique_per_message():
    user = get_user_model().objects.create_user(username="usage-user")
    account = BillingAccount.objects.create(user=user, name="[Personal] Usage")
    model = ModelCatalog.objects.create(
        model_id="test-usage-model",
        display_name="Usage Test",
        tier=ModelCatalog.Tier.TERRA,
        provider=ModelCatalog.Provider.OPENAI,
        input_rate_per_million=Decimal("1.000000"),
        output_rate_per_million=Decimal("2.000000"),
    )
    session = ChatSession.objects.create(
        owner=user,
        billing_account=account,
        model=model,
        title="Usage test",
    )
    message = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.ASSISTANT,
        content="Done",
    )
    deposit_credits(account, 1, "usage-model-deposit")
    reservation = reserve_credits(account, 1, "usage-model-reservation")
    usage = settle_usage(
        reservation.idempotency_key,
        session=session,
        message=message,
        prompt_tokens=1,
        completion_tokens=1,
        input_rate_per_million=model.input_rate_per_million,
        output_rate_per_million=model.output_rate_per_million,
        is_estimated=False,
        idempotency_key="usage-model-settlement",
    )

    usage.is_estimated = True
    with pytest.raises(ValidationError, match="immutable"):
        usage.save()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        usage.delete()
