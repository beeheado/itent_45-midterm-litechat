from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import (
    BillingAccount,
    ChatMessage,
    ChatSession,
    CreditLedger,
    MemoryItem,
    ModelCatalog,
    UserProfile,
)
from core.services import deposit_credits


def create_user_with_account(username="ui-user", balance=0):
    user = get_user_model().objects.create_user(
        username=username,
        first_name="Taylor",
        last_name="Morgan",
    )
    account = BillingAccount.objects.create(
        user=user,
        name="[Personal] Taylor Morgan",
    )
    if balance:
        deposit_credits(account, balance, f"ui-deposit-{username}")
    return user, account


def create_model(model_id="gpt-5.6-luna", tier=ModelCatalog.Tier.LUNA):
    return ModelCatalog.objects.create(
        model_id=model_id,
        display_name=f"GPT-5.6 {tier}",
        tier=tier,
        provider=ModelCatalog.Provider.OPENAI,
        input_rate_per_million=Decimal("0.150000"),
        output_rate_per_million=Decimal("0.600000"),
        is_active=True,
    )


@pytest.mark.django_db
def test_home_renders_heavychat_navigation_and_empty_state(client):
    user, _ = create_user_with_account()
    client.force_login(user)

    response = client.get(reverse("chat:home"))

    assert response.status_code == 200
    assert b"HeavyChat" in response.content
    assert b"SimGen" not in response.content
    assert b"My Profile" in response.content
    assert b"Start a new chat" in response.content
    assert b"Make room" in response.content


@pytest.mark.django_db
def test_session_page_renders_conversation_without_reasoning(client):
    user, account = create_user_with_account("session-ui", balance=500)
    model = create_model()
    session = ChatSession.objects.create(
        owner=user,
        billing_account=account,
        model=model,
        title="Design review",
    )
    ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.USER,
        content="Review this idea",
    )
    ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.ASSISTANT,
        content="Here is a response.",
        reasoning_content="Private reasoning text",
    )
    client.force_login(user)

    response = client.get(reverse("chat:session-detail", args=(session.pk,)))

    assert response.status_code == 200
    assert b"Design review" in response.content
    assert b"Review this idea" in response.content
    assert b"Here is a response." in response.content
    assert b"Private reasoning text" not in response.content
    assert b"data-stream-url" in response.content
    assert b"EventSource" not in response.content


@pytest.mark.django_db
def test_model_selector_lists_tiers_and_session_creation_binds_account(client):
    user, account = create_user_with_account("model-ui")
    sol = create_model("gpt-5.6-sol", ModelCatalog.Tier.SOL)
    terra = create_model("gpt-5.6-terra", ModelCatalog.Tier.TERRA)
    luna = create_model()
    client.force_login(user)

    response = client.get(reverse("chat:model-selector"))

    assert response.status_code == 200
    assert response.content.index(b"GPT-5.6 Sol") < response.content.index(b"GPT-5.6 Terra")
    assert response.content.index(b"GPT-5.6 Terra") < response.content.index(b"GPT-5.6 Luna")
    assert b"Costs for this session will be charged to the selected account" in response.content

    response = client.post(
        reverse("chat:create-session"),
        {"billing_account_id": account.pk, "model_id": terra.pk},
        HTTP_HX_REQUEST="true",
    )

    session = ChatSession.objects.get(owner=user)
    assert response.status_code == 204
    assert response["HX-Redirect"] == reverse("chat:session-detail", args=(session.pk,))
    assert session.billing_account_id == account.pk
    assert session.model_id == terra.pk
    assert session.model_id != luna.pk and session.model_id != sol.pk


@pytest.mark.django_db
def test_model_session_creation_rejects_another_users_account(client):
    user, _ = create_user_with_account("owner-ui")
    _, other_account = create_user_with_account("other-ui")
    model = create_model()
    client.force_login(user)

    response = client.post(
        reverse("chat:create-session"),
        {"billing_account_id": other_account.pk, "model_id": model.pk},
    )

    assert response.status_code == 400
    assert not ChatSession.objects.filter(owner=user).exists()


@pytest.mark.django_db
def test_profile_prompt_toggle_and_memory_crud(client):
    user, _ = create_user_with_account("profile-ui")
    client.force_login(user)
    profile_url = reverse("chat:profile")

    response = client.get(profile_url)
    assert response.status_code == 200
    assert b"Taylor Morgan" in response.content
    assert b"Member since" in response.content

    response = client.post(
        reverse("chat:save-global-prompt"),
        {"global_system_prompt": "Prefer clear, concise answers."},
    )
    profile = UserProfile.objects.get(user=user)
    assert response.status_code == 200
    assert profile.global_system_prompt == "Prefer clear, concise answers."

    response = client.post(
        reverse("chat:toggle-memories"),
        {"ai_memories_enabled": "on"},
    )
    profile.refresh_from_db()
    assert response.status_code == 200
    assert profile.ai_memories_enabled is True

    response = client.post(
        reverse("chat:add-memory"),
        {"category": MemoryItem.Category.PREFERENCE, "content": "Uses metric units."},
    )
    memory = profile.memory_items.get()
    assert response.status_code == 200
    assert b"Uses metric units." in response.content

    response = client.post(reverse("chat:delete-memory", args=(memory.pk,)))
    assert response.status_code == 200
    assert not profile.memory_items.exists()


@pytest.mark.django_db
def test_mock_top_up_updates_balance_badge_and_posts_deposit(client):
    user, account = create_user_with_account("topup-ui")
    client.force_login(user)

    response = client.post(
        reverse("chat:mock-top-up"),
        {"billing_account_id": account.pk},
    )

    account.refresh_from_db()
    assert response.status_code == 200
    assert b"500" in response.content
    assert b"5.00" in response.content
    assert account.credit_balance == 500
    assert CreditLedger.objects.filter(
        billing_account=account,
        kind=CreditLedger.Kind.DEPOSIT,
        amount=500,
    ).exists()
