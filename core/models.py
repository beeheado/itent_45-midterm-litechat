from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    global_system_prompt = models.TextField(blank=True)
    ai_memories_enabled = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"Profile for {self.user}"


class MemoryItem(models.Model):
    class Category(models.TextChoices):
        PREFERENCE = "preference", "Preference"
        FACT = "fact", "Fact"
        INSTRUCTION = "instruction", "Instruction"

    user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="memory_items",
    )
    category = models.CharField(max_length=20, choices=Category.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)

    def __str__(self) -> str:
        return f"{self.category}: {self.content[:40]}"


class BillingAccount(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="billing_accounts",
    )
    name = models.CharField(max_length=255)
    # Credit units are cents: 100 credits equals one USD.
    credit_balance = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(credit_balance__gte=0),
                name="billing_account_balance_nonnegative",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class CreditLedger(models.Model):
    class Kind(models.TextChoices):
        DEPOSIT = "DEPOSIT", "Deposit"
        RESERVE = "RESERVE", "Reserve"
        SETTLE = "SETTLE", "Settle"
        REFUND = "REFUND", "Refund"

    billing_account = models.ForeignKey(
        BillingAccount,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )
    amount = models.IntegerField()
    kind = models.CharField(max_length=10, choices=Kind.choices)
    idempotency_key = models.CharField(max_length=128, unique=True)
    reservation = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="adjustments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(kind="DEPOSIT", amount__gt=0)
                    | Q(kind="RESERVE", amount__lt=0)
                    | Q(kind="SETTLE")
                    | Q(kind="REFUND", amount__gt=0)
                ),
                name="credit_ledger_kind_amount_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(kind__in=("DEPOSIT", "RESERVE"), reservation__isnull=True)
                    | Q(kind__in=("SETTLE", "REFUND"), reservation__isnull=False)
                ),
                name="credit_ledger_reservation_by_kind",
            ),
            models.UniqueConstraint(
                fields=("reservation",),
                condition=Q(kind__in=("SETTLE", "REFUND")),
                name="credit_ledger_one_finalization_per_reservation",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.reservation_id:
            if self.reservation.kind != self.Kind.RESERVE:
                raise ValidationError({"reservation": "Adjustments must reference a reserve entry."})
            if self.reservation.billing_account_id != self.billing_account_id:
                raise ValidationError({"reservation": "Adjustment and reserve accounts must match."})

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise ValidationError("Credit ledger entries are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Credit ledger entries cannot be deleted.")

    def __str__(self) -> str:
        return f"{self.kind} {self.amount} for {self.billing_account}"


class ModelCatalog(models.Model):
    class Tier(models.TextChoices):
        LUNA = "Luna", "Luna"
        TERRA = "Terra", "Terra"
        SOL = "Sol", "Sol"

    class Provider(models.TextChoices):
        OPENAI = "openai", "OpenAI"
        ANTHROPIC = "anthropic", "Anthropic"
        GOOGLE = "google", "Google"

    model_id = models.CharField(max_length=160, unique=True)
    display_name = models.CharField(max_length=160)
    tier = models.CharField(max_length=16, choices=Tier.choices)
    provider = models.CharField(max_length=16, choices=Provider.choices)
    input_rate_per_million = models.DecimalField(max_digits=16, decimal_places=6)
    output_rate_per_million = models.DecimalField(max_digits=16, decimal_places=6)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(input_rate_per_million__gte=0),
                name="catalog_input_rate_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(output_rate_per_million__gte=0),
                name="catalog_output_rate_nonnegative",
            ),
        ]
        ordering = ("tier", "display_name")

    def __str__(self) -> str:
        return self.display_name


class ChatSession(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )
    billing_account = models.ForeignKey(
        BillingAccount,
        on_delete=models.PROTECT,
        related_name="chat_sessions",
    )
    model = models.ForeignKey(
        ModelCatalog,
        on_delete=models.PROTECT,
        related_name="chat_sessions",
    )
    title = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self) -> None:
        super().clean()
        if (
            self.owner_id
            and self.billing_account_id
            and self.billing_account.user_id != self.owner_id
        ):
            raise ValidationError(
                {"billing_account": "The billing account must belong to the session owner."}
            )

    def __str__(self) -> str:
        return self.title or f"Chat session {self.pk}"


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        SYSTEM = "system", "System"
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    reasoning_content = models.TextField(null=True, blank=True)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=Q(prompt_tokens__gte=0),
                name="chat_message_prompt_tokens_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(completion_tokens__gte=0),
                name="chat_message_completion_tokens_nonnegative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.role} message in session {self.session_id}"


class UsageTransaction(models.Model):
    reservation = models.OneToOneField(
        CreditLedger,
        on_delete=models.PROTECT,
        related_name="usage_transaction",
        null=True,
        blank=True,
    )
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.PROTECT,
        related_name="usage_transactions",
    )
    message = models.OneToOneField(
        ChatMessage,
        on_delete=models.PROTECT,
        related_name="usage_transaction",
    )
    prompt_tokens = models.IntegerField()
    completion_tokens = models.IntegerField()
    input_rate_per_million = models.DecimalField(max_digits=16, decimal_places=6)
    output_rate_per_million = models.DecimalField(max_digits=16, decimal_places=6)
    cost_usd = models.DecimalField(max_digits=22, decimal_places=12)
    credit_debit = models.IntegerField()
    is_estimated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(prompt_tokens__gte=0),
                name="usage_prompt_tokens_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(completion_tokens__gte=0),
                name="usage_completion_tokens_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(input_rate_per_million__gte=0),
                name="usage_input_rate_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(output_rate_per_million__gte=0),
                name="usage_output_rate_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(cost_usd__gte=0),
                name="usage_cost_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(credit_debit__gte=0),
                name="usage_credit_debit_nonnegative",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.reservation_id and self.reservation.kind != CreditLedger.Kind.RESERVE:
            raise ValidationError({"reservation": "Usage must link to a reserve ledger entry."})
        if (
            self.reservation_id
            and self.session_id
            and self.reservation.billing_account_id != self.session.billing_account_id
        ):
            raise ValidationError({"reservation": "The reserve must belong to the session account."})
        if self.message_id and self.session_id != self.message.session_id:
            raise ValidationError({"session": "The message must belong to the usage session."})
        if self.message_id and self.message.role != ChatMessage.Role.ASSISTANT:
            raise ValidationError({"message": "Usage must be linked to an assistant message."})

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise ValidationError("Usage transactions are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Usage transactions cannot be deleted.")

    def __str__(self) -> str:
        return f"Usage for message {self.message_id}: {self.credit_debit} credits"
