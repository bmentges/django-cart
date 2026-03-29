from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from . import models

try:
    from .signals import (
        cart_item_added,
        cart_item_removed,
        cart_item_updated,
        cart_checked_out,
        cart_cleared,
    )
except ImportError:
    cart_item_added = None
    cart_item_removed = None
    cart_item_updated = None
    cart_checked_out = None
    cart_cleared = None

CART_ID = "CART-ID"


class CartException(Exception):
    """Base exception for all cart errors."""


class ItemAlreadyExists(CartException):
    """Raised when attempting to add a product that is already in the cart."""


class ItemDoesNotExist(CartException):
    """Raised when attempting to operate on a product not in the cart."""


class InvalidQuantity(CartException):
    """Raised when a quantity value is invalid (e.g. negative)."""


class Cart:
    """
    Session-backed shopping cart.

    Associates a :class:`cart.models.Cart` database record with the current
    session and exposes a clean API for managing its items.

    Usage::

        cart = Cart(request)
        cart.add(product, unit_price=Decimal("9.99"), quantity=2)
        cart.remove(product)
        total = cart.summary()
    """

    def __init__(self, request):
        cart_id = request.session.get(CART_ID)
        cart = None
        if cart_id:
            cart = models.Cart.objects.filter(id=cart_id, checked_out=False).first()
        if cart is None:
            cart = self._new(request)
        self.cart = cart

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _new(self, request) -> models.Cart:
        cart = models.Cart.objects.create(creation_date=timezone.now())
        request.session[CART_ID] = cart.id
        return cart

    def _get_item(self, product) -> models.Item | None:
        return models.Item.objects.filter(cart=self.cart, product=product).first()

    # ------------------------------------------------------------------
    # Iteration / dunder helpers
    # ------------------------------------------------------------------

    def __iter__(self):
        return iter(self.cart.items.select_related("content_type").all())

    def __len__(self):
        return self.count()

    def __contains__(self, product):
        return self._get_item(product) is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, product, unit_price: Decimal, quantity: int = 1) -> models.Item:
        """
        Add *product* to the cart.

        If the product is already present its quantity is incremented and the
        unit price is updated to *unit_price*.

        :param product: Any Django model instance.
        :param unit_price: Price per unit as a :class:`~decimal.Decimal`.
        :param quantity: Number of units to add (must be ≥ 1).
        :returns: The :class:`~cart.models.Item` that was created or updated.
        :raises InvalidQuantity: if *quantity* is less than 1.
        """
        if int(quantity) < 1:
            raise InvalidQuantity("Quantity must be at least 1.")

        with transaction.atomic():
            item = self._get_item(product)
            if item:
                item.unit_price = unit_price
                item.quantity += int(quantity)
                item.save(update_fields=["unit_price", "quantity"])
            else:
                item = models.Item.objects.create(
                    cart=self.cart,
                    product=product,
                    unit_price=unit_price,
                    quantity=int(quantity),
                )
        if cart_item_added is not None:
            cart_item_added.send(sender=self.__class__, cart=self.cart, item=item)
        return item

    def remove(self, product) -> None:
        """
        Remove *product* from the cart entirely.

        :raises ItemDoesNotExist: if the product is not in the cart.
        """
        item = self._get_item(product)
        if item is None:
            raise ItemDoesNotExist(f"Product {product!r} is not in this cart.")
        item.delete()
        if cart_item_removed is not None:
            cart_item_removed.send(sender=self.__class__, cart=self.cart, product=product)

    def update(self, product, quantity: int, unit_price: Decimal | None = None) -> models.Item:
        """
        Update the quantity (and optionally the unit price) for *product*.

        Passing *quantity* = 0 removes the item entirely.

        :raises ItemDoesNotExist: if the product is not in the cart.
        :raises InvalidQuantity: if *quantity* is negative.
        """
        if int(quantity) < 0:
            raise InvalidQuantity("Quantity cannot be negative.")

        with transaction.atomic():
            item = self._get_item(product)
            if item is None:
                raise ItemDoesNotExist(f"Product {product!r} is not in this cart.")

            if int(quantity) == 0:
                item.delete()
                if cart_item_updated is not None:
                    cart_item_updated.send(sender=self.__class__, cart=self.cart, item=item, deleted=True)
                return item

            item.quantity = int(quantity)
            update_fields = ["quantity"]
            if unit_price is not None:
                item.unit_price = unit_price
                update_fields.append("unit_price")
            item.save(update_fields=update_fields)
        if cart_item_updated is not None:
            cart_item_updated.send(sender=self.__class__, cart=self.cart, item=item)
        return item

    def count(self) -> int:
        """Return the total number of *units* across all items."""
        result = self.cart.items.aggregate(total=Sum("quantity"))["total"]
        return result or 0

    def unique_count(self) -> int:
        """Return the number of distinct products in the cart."""
        return self.cart.items.count()

    def summary(self) -> Decimal:
        """Return the grand total price for all items."""
        result = self.cart.items.aggregate(
            total=Sum(F("quantity") * F("unit_price"))
        )["total"]
        return result or Decimal("0.00")

    def clear(self) -> None:
        """Remove all items from the cart (but keep the cart record)."""
        self.cart.items.all().delete()
        if cart_cleared is not None:
            cart_cleared.send(sender=self.__class__, cart=self.cart)

    def checkout(self) -> None:
        """Mark the cart as checked out."""
        self.cart.checked_out = True
        self.cart.save(update_fields=["checked_out"])
        if cart_checked_out is not None:
            cart_checked_out.send(sender=self.__class__, cart=self.cart)

    def is_empty(self) -> bool:
        """Return ``True`` if the cart contains no items."""
        return self.count() == 0

    def cart_serializable(self) -> dict:
        """
        Return a JSON-serialisable dict representation of the cart.

        Example output::

            {
                "42": {"total_price": "19.98", "quantity": 2, "unit_price": "9.99"},
                ...
            }
        """
        return {
            str(item.object_id): {
                "total_price": str(item.total_price),
                "unit_price": str(item.unit_price),
                "quantity": item.quantity,
            }
            for item in self.cart.items.all()
        }

    @classmethod
    def from_serializable(cls, request, data: dict) -> "Cart":
        """
        Restore a cart from serializable data.

        :param request: Django request object.
        :param data: Dict as produced by :meth:`cart_serializable`.
        :returns: A :class:`Cart` instance with the restored items.

        Example::

            cart_data = {
                "42": {"total_price": "19.98", "quantity": 2, "unit_price": "9.99"},
            }
            cart = Cart.from_serializable(request, cart_data)
        """
        cart = cls(request)
        for object_id, item_data in data.items():
            from django.contrib.contenttypes.models import ContentType
            item = models.Item.objects.filter(
                cart=cart.cart,
                object_id=object_id
            ).first()
            if item:
                item.quantity = item_data.get("quantity", item.quantity)
                if "unit_price" in item_data:
                    item.unit_price = Decimal(item_data["unit_price"])
                item.save()
        return cart
