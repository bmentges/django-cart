from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum, QuerySet
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


class PriceMismatchError(CartException):
    """Raised when price doesn't match product's actual price."""


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
        self._cache: dict = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _new(self, request) -> models.Cart:
        cart = models.Cart.objects.create(creation_date=timezone.now())
        request.session[CART_ID] = cart.id
        return cart

    def _get_item(self, product) -> models.Item | None:
        return models.Item.objects.filter(cart=self.cart, product=product).first()

    def _invalidate_cache(self) -> None:
        """Invalidate the summary and count cache."""
        self._cache = {}

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

    def add(self, product, unit_price: Decimal, quantity: int = 1, validate_price: bool = False) -> models.Item:
        """
        Add *product* to the cart.

        If the product is already present its quantity is incremented and the
        unit price is updated to *unit_price*.

        :param product: Any Django model instance.
        :param unit_price: Price per unit as a :class:`~decimal.Decimal`.
        :param quantity: Number of units to add (must be ≥ 1).
        :param validate_price: If True, validate that unit_price matches product.price.
        :returns: The :class:`~cart.models.Item` that was created or updated.
        :raises InvalidQuantity: if *quantity* is less than 1 or exceeds CART_MAX_QUANTITY_PER_ITEM.
        :raises PriceMismatchError: if validate_price=True and price doesn't match product.price.
        """
        if int(quantity) < 1:
            raise InvalidQuantity("Quantity must be at least 1.")

        if validate_price:
            actual_price = getattr(product, 'price', None)
            if actual_price is not None and unit_price != actual_price:
                raise PriceMismatchError(
                    f"Price mismatch: expected {actual_price}, got {unit_price}."
                )

        max_qty = getattr(settings, 'CART_MAX_QUANTITY_PER_ITEM', None)
        if max_qty is not None and int(quantity) > max_qty:
            raise InvalidQuantity(f"Quantity cannot exceed {max_qty}.")

        with transaction.atomic():
            item = self._get_item(product)
            if item:
                item.unit_price = unit_price
                item.quantity += int(quantity)
                if max_qty is not None and item.quantity > max_qty:
                    raise InvalidQuantity(f"Quantity cannot exceed {max_qty}.")
                item.save(update_fields=["unit_price", "quantity"])
            else:
                item = models.Item.objects.create(
                    cart=self.cart,
                    product=product,
                    unit_price=unit_price,
                    quantity=int(quantity),
                )
        self._invalidate_cache()
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
        self._invalidate_cache()
        if cart_item_removed is not None:
            cart_item_removed.send(sender=self.__class__, cart=self.cart, product=product)

    def update(self, product, quantity: int, unit_price: Decimal | None = None, validate_price: bool = False) -> models.Item:
        """
        Update the quantity (and optionally the unit price) for *product*.

        Passing *quantity* = 0 removes the item entirely.

        :param product: Any Django model instance.
        :param quantity: New quantity (0 = remove item).
        :param unit_price: New unit price (optional).
        :param validate_price: If True, validate that unit_price matches product.price.
        :raises ItemDoesNotExist: if the product is not in the cart.
        :raises InvalidQuantity: if *quantity* is negative or exceeds CART_MAX_QUANTITY_PER_ITEM.
        :raises PriceMismatchError: if validate_price=True and price doesn't match product.price.
        """
        if int(quantity) < 0:
            raise InvalidQuantity("Quantity cannot be negative.")

        if validate_price and unit_price is not None:
            actual_price = getattr(product, 'price', None)
            if actual_price is not None and unit_price != actual_price:
                raise PriceMismatchError(
                    f"Price mismatch: expected {actual_price}, got {unit_price}."
                )

        max_qty = getattr(settings, 'CART_MAX_QUANTITY_PER_ITEM', None)
        if max_qty is not None and int(quantity) > max_qty:
            raise InvalidQuantity(f"Quantity cannot exceed {max_qty}.")

        with transaction.atomic():
            item = self._get_item(product)
            if item is None:
                raise ItemDoesNotExist(f"Product {product!r} is not in this cart.")

            if int(quantity) == 0:
                item.delete()
                self._invalidate_cache()
                if cart_item_updated is not None:
                    cart_item_updated.send(sender=self.__class__, cart=self.cart, item=item, deleted=True)
                return item

            item.quantity = int(quantity)
            update_fields = ["quantity"]
            if unit_price is not None:
                item.unit_price = unit_price
                update_fields.append("unit_price")
            item.save(update_fields=update_fields)
        self._invalidate_cache()
        if cart_item_updated is not None:
            cart_item_updated.send(sender=self.__class__, cart=self.cart, item=item)
        return item

    def count(self) -> int:
        """Return the total number of *units* across all items."""
        if 'count' in self._cache:
            return self._cache['count']
        result = self.cart.items.aggregate(total=Sum("quantity"))["total"]
        count = result or 0
        self._cache['count'] = count
        return count

    def unique_count(self) -> int:
        """Return the number of distinct products in the cart."""
        return self.cart.items.count()

    def summary(self) -> Decimal:
        """Return the grand total price for all items."""
        if 'summary' in self._cache:
            return self._cache['summary']
        result = self.cart.items.aggregate(
            total=Sum(F("quantity") * F("unit_price"))
        )["total"]
        summary = result or Decimal("0.00")
        self._cache['summary'] = summary
        return summary

    def clear(self) -> None:
        """Remove all items from the cart (but keep the cart record)."""
        self.cart.items.all().delete()
        self._invalidate_cache()
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

    def merge(self, other_cart: "Cart", strategy: str = "add") -> None:
        """
        Merge another cart into this one.

        :param other_cart: The cart to merge from.
        :param strategy: Merge strategy - 'add', 'replace', or 'keep_higher'.
        :raises ValueError: if strategy is invalid or cart is merged with itself.
        """
        if other_cart is self:
            raise ValueError("Cannot merge a cart with itself.")

        if strategy not in ("add", "replace", "keep_higher"):
            raise ValueError(
                f"Invalid merge strategy '{strategy}'. "
                "Must be 'add', 'replace', or 'keep_higher'."
            )

        if other_cart.is_empty():
            return

        max_qty = getattr(settings, 'CART_MAX_QUANTITY_PER_ITEM', None)

        with transaction.atomic():
            for other_item in other_cart.cart.items.all():
                existing_item = self._get_item(other_item.product)

                if existing_item:
                    if strategy == "add":
                        new_quantity = existing_item.quantity + other_item.quantity
                    elif strategy == "replace":
                        new_quantity = other_item.quantity
                    else:
                        new_quantity = max(existing_item.quantity, other_item.quantity)

                    if max_qty is not None and new_quantity > max_qty:
                        new_quantity = max_qty

                    existing_item.quantity = new_quantity
                    existing_item.unit_price = other_item.unit_price
                    existing_item.save(update_fields=["quantity", "unit_price"])
                else:
                    new_quantity = other_item.quantity
                    if max_qty is not None and new_quantity > max_qty:
                        new_quantity = max_qty

                    models.Item.objects.create(
                        cart=self.cart,
                        product=other_item.product,
                        unit_price=other_item.unit_price,
                        quantity=new_quantity,
                    )

            other_cart.clear()

        self._invalidate_cache()

    def bind_to_user(self, user) -> None:
        """
        Bind this cart to a user account for persistence.

        :param user: Django User model instance.
        """
        self.cart.user = user
        self.cart.save(update_fields=["user"])

    @classmethod
    def get_user_carts(cls, user) -> QuerySet[models.Cart]:
        """
        Get all carts associated with a user.

        :param user: Django User model instance.
        :returns: QuerySet of Cart objects.
        """
        return models.Cart.objects.filter(user=user)

    def add_bulk(self, items: list[dict]) -> list[models.Item]:
        """
        Add multiple items efficiently.

        :param items: List of dicts with 'product', 'unit_price', 'quantity' keys.
        :returns: List of created/updated Item instances.
        :raises InvalidQuantity: if any item exceeds CART_MAX_QUANTITY_PER_ITEM.

        Example::

            cart.add_bulk([
                {'product': product1, 'unit_price': Decimal("10.00"), 'quantity': 2},
                {'product': product2, 'unit_price': Decimal("20.00"), 'quantity': 1},
            ])
        """
        if not items:
            return []

        max_qty = getattr(settings, 'CART_MAX_QUANTITY_PER_ITEM', None)
        result = []

        with transaction.atomic():
            for item_data in items:
                product = item_data['product']
                unit_price = item_data['unit_price']
                quantity = int(item_data['quantity'])

                if quantity < 1:
                    raise InvalidQuantity("Quantity must be at least 1.")

                if max_qty is not None and quantity > max_qty:
                    raise InvalidQuantity(f"Quantity cannot exceed {max_qty}.")

                item = self._get_item(product)
                if item:
                    item.unit_price = unit_price
                    item.quantity = quantity
                    item.save(update_fields=["unit_price", "quantity"])
                else:
                    item = models.Item.objects.create(
                        cart=self.cart,
                        product=product,
                        unit_price=unit_price,
                        quantity=quantity,
                    )
                result.append(item)

        self._invalidate_cache()
        return result
