import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import BillingAccount, MemoryItem, UserProfile
from core.services import deposit_credits


DEMO_USERS = (
    {
        "username": "luis",
        "first_name": "LUIS CLARENCE",
        "last_name": "MARIANO",
        "email": "luis@heavychat.local",
        "account_name": "[Personal] LUIS CLARENCE MARIANO",
    },
    {
        "username": "beeheado",
        "first_name": "",
        "last_name": "",
        "email": "beeheado@heavychat.local",
        "account_name": "[Personal] beeheado",
    },
)


class Command(BaseCommand):
    help = "Create idempotent HeavyChat demo users, personal accounts, and profiles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Reset luis's password from HEAVYCHAT_DEMO_PASSWORD or generate one.",
        )

    def handle(self, *args, **options):
        demo_password = os.getenv("HEAVYCHAT_DEMO_PASSWORD")
        generated_passwords = []
        user_model = get_user_model()
        seeded_accounts = []

        with transaction.atomic():
            for demo_user in DEMO_USERS:
                username = demo_user["username"]
                user, created = user_model.objects.get_or_create(
                    username=username,
                    defaults={
                        "first_name": demo_user["first_name"],
                        "last_name": demo_user["last_name"],
                        "email": demo_user["email"],
                    },
                )
                if (
                    created
                    or (username == "luis" and options["reset_password"])
                    or not user.has_usable_password()
                ):
                    password = demo_password or secrets.token_urlsafe(18)
                    user.set_password(password)
                    user.save(update_fields=("password",))
                    if not demo_password:
                        generated_passwords.append((username, password))

                account, _ = BillingAccount.objects.get_or_create(
                    user=user,
                    name=demo_user["account_name"],
                    defaults={"credit_balance": 0},
                )
                deposit_credits(
                    account,
                    1000,
                    f"setup-demo:{username}:initial-credits-v1",
                )
                UserProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "global_system_prompt": (
                            "Be a clear, practical coding assistant. Distinguish verified "
                            "facts from assumptions and ask when requirements are unclear."
                        ),
                        "ai_memories_enabled": True,
                    },
                )
                if username == "luis":
                    profile = UserProfile.objects.get(user=user)
                    MemoryItem.objects.get_or_create(
                        user_profile=profile,
                        category=MemoryItem.Category.PREFERENCE,
                        content="Prefers concise, structured answers with practical examples.",
                        defaults={"is_active": True},
                    )
                seeded_accounts.append((username, account))

        for username, password in generated_passwords:
            self.stdout.write(
                self.style.WARNING(
                    f"Generated one-time local demo password for '{username}' "
                    f"(copy it now): {password}"
                )
            )

        for username, account in seeded_accounts:
            account.refresh_from_db()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Demo user '{username}' is ready with {account.credit_balance} "
                    f"credits in {account.name}."
                )
            )
