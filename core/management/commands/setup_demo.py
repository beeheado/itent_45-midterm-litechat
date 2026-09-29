import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import BillingAccount, MemoryItem, UserProfile
from core.services import deposit_credits


DEMO_USERNAME = "luis"
DEMO_ACCOUNT_NAME = "[Personal] LUIS CLARENCE MARIANO"
DEMO_DEPOSIT_KEY = "setup-demo:luis:initial-credits-v1"


class Command(BaseCommand):
    help = "Create an idempotent HeavyChat demo user, account, profile, and memory."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Set a new demo password from HEAVYCHAT_DEMO_PASSWORD or generate one.",
        )

    def handle(self, *args, **options):
        demo_password = os.getenv("HEAVYCHAT_DEMO_PASSWORD")
        generated_password = None
        user_model = get_user_model()

        with transaction.atomic():
            user, created = user_model.objects.get_or_create(
                username=DEMO_USERNAME,
                defaults={
                    "first_name": "LUIS CLARENCE",
                    "last_name": "MARIANO",
                    "email": "luis@heavychat.local",
                },
            )
            if created or options["reset_password"] or not user.has_usable_password():
                password = demo_password or secrets.token_urlsafe(18)
                user.set_password(password)
                user.save(update_fields=("password",))
                if not demo_password:
                    generated_password = password

            account, _ = BillingAccount.objects.get_or_create(
                user=user,
                name=DEMO_ACCOUNT_NAME,
                defaults={"credit_balance": 0},
            )
            deposit_credits(account, 1000, DEMO_DEPOSIT_KEY)

            profile, _ = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    "global_system_prompt": (
                        "Be a clear, practical coding assistant. Distinguish verified "
                        "facts from assumptions and ask when requirements are unclear."
                    ),
                    "ai_memories_enabled": True,
                },
            )
            MemoryItem.objects.get_or_create(
                user_profile=profile,
                category=MemoryItem.Category.PREFERENCE,
                content="Prefers concise, structured answers with practical examples.",
                defaults={"is_active": True},
            )

        if generated_password:
            self.stdout.write(
                self.style.WARNING(
                    "Generated one-time local demo password (copy it now): "
                    f"{generated_password}"
                )
            )
        account.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo user '{DEMO_USERNAME}' is ready with {account.credit_balance} "
                f"credits in {DEMO_ACCOUNT_NAME}."
            )
        )
