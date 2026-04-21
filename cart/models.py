from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model
    from django.db.models import Model


class Cart(models.Model):
    creation_date: models.DateTimeField = models.DateTimeField(
        verbose_name=_("creation date"),
        default=timezone.now,
    )
    checked_out: models.BooleanField = models.BooleanField(
        default=False,
        verbose_name=_("checked out"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="carts",
    )
    discount = models.ForeignKey(
        "Discount",
        verbose_name=_("applied discount"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applied_carts",
    )

    class Meta:
        verbose_name = _("cart")
        verbose_name_plural = _("carts")
        ordering = ("-creation_date",)

    def __str__(self) -> str:
        return f"Cart #{self.pk} ({self.items.count()} items)"


class ItemManager(models.Manager["Item"]):
    """Custom manager that allows filtering/getting items by product instance."""

    def _inject_content_type(self, kwargs: dict) -> dict:
        if "product" in kwargs:
            product = kwargs.pop("product")
            kwargs["content_type"] = ContentType.objects.get_for_model(product._meta.model)
            kwargs["object_id"] = product.pk
        return kwargs

    def get(self, *args: Any, **kwargs: Any) -> "Item":
        kwargs = self._inject_content_type(kwargs)
        return super().get(*args, **kwargs)

    def filter(self, *args: Any, **kwargs: Any) -> models.QuerySet["Item"]:
        kwargs = self._inject_content_type(kwargs)
        return super().filter(*args, **kwargs)


class Item(models.Model):
    cart = models.ForeignKey[
        "Cart", "Item"
    ](
        Cart,
        verbose_name=_("cart"),
        on_delete=models.CASCADE,
        related_name="items",
    )
    quantity: int = models.PositiveIntegerField(verbose_name=_("quantity"))
    unit_price: Decimal = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("unit price"),
    )

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id: int = models.PositiveIntegerField()

    objects: ItemManager = ItemManager()

    class Meta:
        verbose_name = _("item")
        verbose_name_plural = _("items")
        ordering = ("cart",)
        unique_together = ("cart", "content_type", "object_id")
        indexes = [
            models.Index(fields=["cart", "content_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.content_type.model} (id={self.object_id})"

    @property
    def total_price(self) -> Decimal:
        return self.quantity * self.unit_price

    @property
    def product(self) -> "Model":
        if not hasattr(self, "_product_cache"):
            self._product_cache = self.content_type.model_class().objects.get(pk=self.object_id)
        return self._product_cache

    @product.setter
    def product(self, product: "Model") -> None:
        self.content_type = ContentType.objects.get_for_model(product._meta.model)
        self.object_id = product.pk


class DiscountType(models.TextChoices):
    PERCENT = "percent", _("Percentage")
    FIXED = "fixed", _("Fixed Amount")


class Discount(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("discount code"),
        help_text=_("Unique code to apply the discount"),
    )
    discount_type = models.CharField(
        max_length=10,
        choices=DiscountType.choices,
        default=DiscountType.PERCENT,
        verbose_name=_("discount type"),
    )
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("discount value"),
        help_text=_("Percentage or fixed amount depending on discount type"),
    )
    min_cart_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("minimum cart value"),
        help_text=_("Minimum cart subtotal required to apply discount"),
    )
    max_uses = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("maximum uses"),
        help_text=_("Maximum number of times this discount can be used (null for unlimited)"),
    )
    current_uses = models.PositiveIntegerField(
        default=0,
        verbose_name=_("current uses"),
    )
    active = models.BooleanField(
        default=True,
        verbose_name=_("active"),
        help_text=_("Whether this discount can be used"),
    )
    valid_from = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("valid from"),
    )
    valid_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("valid until"),
    )

    class Meta:
        verbose_name = _("discount")
        verbose_name_plural = _("discounts")

    def __str__(self) -> str:
        return f"{self.code} ({self.get_discount_type_display()}: {self.value})"

    def is_valid_for_cart(self, cart: "Cart") -> tuple[bool, str]:
        """Check if the discount is valid for the given cart.
        
        Args:
            cart: The cart to validate against.
            
        Returns:
            A tuple of (is_valid, message).
        """
        if not self.active:
            return False, "This discount is no longer active."

        if self.max_uses is not None and self.current_uses >= self.max_uses:
            return False, "This discount has reached its maximum number of uses."

        now = timezone.now()
        if self.valid_from and now < self.valid_from:
            return False, "This discount is not yet valid."

        if self.valid_until and now > self.valid_until:
            return False, "This discount has expired."

        if self.min_cart_value is not None:
            if cart.summary() < self.min_cart_value:
                return False, f"Minimum cart value of {self.min_cart_value} required."

        return True, ""

    def clean(self) -> None:
        """Validate cross-field invariants.

        - A ``PERCENT`` discount cannot claim more than 100% off.
          Django admin forms and any caller using ``full_clean()``
          before ``save()`` rejects such rows before they reach the DB.
          The guard is not a DB ``CheckConstraint`` because the
          ``CheckConstraint(check=…)`` / ``CheckConstraint(condition=…)``
          kwarg renamed between Django 5.0 and 6.0, and the project's
          supported matrix spans both. Once 4.2 drops off the matrix,
          a DB-level constraint can be added without compat pain.
        """
        super().clean()
        if (
            self.discount_type == DiscountType.PERCENT
            and self.value is not None
            and self.value > Decimal("100")
        ):
            raise ValidationError({
                "value": _(
                    "Percentage discounts cannot exceed 100% — "
                    "value must be between 0 and 100."
                ),
            })

    def calculate_discount(self, cart: "Cart") -> Decimal:
        """Calculate the discount amount for the given cart.

        The returned amount is always clamped to the cart's subtotal so
        a misconfigured ``PERCENT`` discount (``value > 100`` — possible
        on legacy rows that pre-date the :meth:`clean` guard) can't
        produce a discount larger than what the cart is worth.

        Args:
            cart: The cart to calculate discount for.

        Returns:
            The discount amount as a Decimal, never exceeding
            ``cart.summary()``.
        """
        subtotal = cart.summary()
        if self.discount_type == DiscountType.PERCENT:
            amount = (subtotal * self.value) / Decimal("100")
            return min(amount, subtotal)
        return min(self.value, subtotal)

    def increment_usage(self) -> None:
        """Atomically increment the usage counter by one.

        Uses an ``F()`` expression so concurrent callers never race: two
        parallel increments always result in ``current_uses += 2``, never
        ``+= 1`` due to a lost-update.

        The in-memory ``self.current_uses`` attribute is stale after this
        call — call ``refresh_from_db()`` if you need the new value.
        """
        Discount.objects.filter(pk=self.pk).update(
            current_uses=F("current_uses") + 1
        )
