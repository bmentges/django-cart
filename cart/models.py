from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


class Cart(models.Model):
    creation_date = models.DateTimeField(
        verbose_name=_("creation date"),
        default=timezone.now,
    )
    checked_out = models.BooleanField(
        default=False,
        verbose_name=_("checked out"),
    )

    class Meta:
        verbose_name = _("cart")
        verbose_name_plural = _("carts")
        ordering = ("-creation_date",)

    def __str__(self):
        return str(self.creation_date)


class ItemManager(models.Manager):
    """Custom manager that allows filtering/getting items by product instance."""

    def _inject_content_type(self, kwargs: dict) -> dict:
        if "product" in kwargs:
            product = kwargs.pop("product")
            kwargs["content_type"] = ContentType.objects.get_for_model(type(product))
            kwargs["object_id"] = product.pk
        return kwargs

    def get(self, *args, **kwargs):
        kwargs = self._inject_content_type(kwargs)
        return super().get(*args, **kwargs)

    def filter(self, *args, **kwargs):
        kwargs = self._inject_content_type(kwargs)
        return super().filter(*args, **kwargs)


class Item(models.Model):
    cart = models.ForeignKey(
        Cart,
        verbose_name=_("cart"),
        on_delete=models.CASCADE,
        related_name="items",
    )
    quantity = models.PositiveIntegerField(verbose_name=_("quantity"))
    unit_price = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        verbose_name=_("unit price"),
    )

    # product as generic relation
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()

    objects = ItemManager()

    class Meta:
        verbose_name = _("item")
        verbose_name_plural = _("items")
        ordering = ("cart",)
        # Prevent duplicate products in the same cart
        unique_together = ("cart", "content_type", "object_id")

    def __str__(self):
        return f"{self.quantity} × {self.content_type.model} (id={self.object_id})"

    @property
    def total_price(self):
        return self.quantity * self.unit_price

    @property
    def product(self):
        return self.content_type.get_object_for_this_type(pk=self.object_id)

    @product.setter
    def product(self, product):
        self.content_type = ContentType.objects.get_for_model(type(product))
        self.object_id = product.pk
