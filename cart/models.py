from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator
from django.db import models
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
        "auth.User",
        verbose_name=_("user"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="carts",
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
