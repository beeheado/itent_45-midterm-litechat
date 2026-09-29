from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command, get_commands

from core.models import BillingAccount, CreditLedger, MemoryItem, UserProfile


def test_setup_demo_command_is_exposed_by_chat_app():
    assert get_commands()["setup_demo"] == "chat"


@pytest.mark.django_db
def test_setup_demo_is_idempotent_and_posts_initial_credit_once(monkeypatch):
    monkeypatch.delenv("HEAVYCHAT_DEMO_PASSWORD", raising=False)
    first_output = StringIO()
    call_command("setup_demo", stdout=first_output)

    user = get_user_model().objects.get(username="luis")
    account = BillingAccount.objects.get(
        user=user,
        name="[Personal] LUIS CLARENCE MARIANO",
    )
    profile = UserProfile.objects.get(user=user)
    memory = MemoryItem.objects.get(user_profile=profile)
    password_line = next(
        line
        for line in first_output.getvalue().splitlines()
        if line.startswith("Generated one-time local demo password")
    )
    generated_password = password_line.rsplit(": ", 1)[1]

    assert user.check_password(generated_password)
    assert user.get_full_name() == "LUIS CLARENCE MARIANO"
    assert account.credit_balance == 1000
    assert profile.ai_memories_enabled is True
    assert profile.global_system_prompt
    assert memory.category == MemoryItem.Category.PREFERENCE
    assert memory.is_active is True
    assert CreditLedger.objects.filter(
        billing_account=account,
        kind=CreditLedger.Kind.DEPOSIT,
        amount=1000,
        idempotency_key="setup-demo:luis:initial-credits-v1",
    ).count() == 1

    second_output = StringIO()
    call_command("setup_demo", stdout=second_output)
    account.refresh_from_db()
    assert account.credit_balance == 1000
    assert CreditLedger.objects.filter(
        idempotency_key="setup-demo:luis:initial-credits-v1"
    ).count() == 1
    assert "Generated one-time local demo password" not in second_output.getvalue()

    monkeypatch.setenv("HEAVYCHAT_DEMO_PASSWORD", "controlled-test-password")
    reset_output = StringIO()
    call_command("setup_demo", reset_password=True, stdout=reset_output)
    user.refresh_from_db()
    assert user.check_password("controlled-test-password")
    assert "controlled-test-password" not in reset_output.getvalue()
    account.refresh_from_db()
    assert account.credit_balance == 1000
