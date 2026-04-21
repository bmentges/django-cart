"""Inventory checking system for django-cart.

This module provides a pluggable inventory validation system that can be
extended to support different inventory management backends.

Usage:
    1. Create a custom inventory checker:
       class MyInventoryChecker(InventoryChecker):
           def check(self, product, quantity: int) -> bool:
               # Check if product has enough stock
               return product.stock >= quantity

           def reserve(self, product, quantity: int) -> bool:
               # Reserve inventory for purchase
               if product.stock >= quantity:
                   product.stock -= quantity
                   product.save()
                   return True
               return False

    2. Configure in settings:
       CART_INVENTORY_CHECKER = 'myapp.utils.MyInventoryChecker'

    3. Use with cart operations:
       cart.add(product, price, quantity=2, check_inventory=True)
"""

import warnings
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class InventoryChecker(ABC):
    """Base class for inventory checking.

    Implement this class to create custom inventory validation logic for
    your e-commerce platform.

    Example:
        class DatabaseInventoryChecker(InventoryChecker):
            def check(self, product, quantity: int) -> bool:
                return Product.objects.get(pk=product.pk).stock >= quantity

            def reserve(self, product, quantity: int) -> bool:
                obj = Product.objects.get(pk=product.pk)
                if obj.stock >= quantity:
                    obj.stock -= quantity
                    obj.save()
                    return True
                return False
    """

    @abstractmethod
    def check(self, product: Any, quantity: int) -> bool:
        """Check if the requested quantity is available.

        Args:
            product: The product to check.
            quantity: The quantity requested.

        Returns:
            True if the quantity is available, False otherwise.

        Raises:
            NotImplementedError: Subclasses must implement this method.
        """
        raise NotImplementedError("Subclasses must implement check()")

    @abstractmethod
    def reserve(self, product: Any, quantity: int) -> bool:
        """Reserve inventory for a purchase.

        This method should atomically reserve the specified quantity
        for the product. Returns True if successful, False otherwise.

        Args:
            product: The product to reserve.
            quantity: The quantity to reserve.

        Returns:
            True if reservation was successful, False otherwise.

        Raises:
            NotImplementedError: Subclasses must implement this method.
        """
        raise NotImplementedError("Subclasses must implement reserve()")

    def release(self, product: Any, quantity: int) -> bool:
        """Release previously reserved inventory.

        Override this method if your inventory system supports reservation
        tracking and needs explicit release functionality.

        Args:
            product: The product to release.
            quantity: The quantity to release.

        Returns:
            True if release was successful, False otherwise.
        """
        return True


class DefaultInventoryChecker(InventoryChecker):
    """Default inventory checker that always allows operations.

    This is used when no custom checker is configured via
    CART_INVENTORY_CHECKER setting, or when inventory checking
    is disabled.
    """

    def check(self, product: Any, quantity: int) -> bool:
        """Always return True (unlimited inventory).

        Args:
            product: The product (unused).
            quantity: The quantity (unused).

        Returns:
            True
        """
        return True

    def reserve(self, product: Any, quantity: int) -> bool:
        """Always return True (always successful).

        Args:
            product: The product (unused).
            quantity: The quantity (unused).

        Returns:
            True
        """
        return True


def get_inventory_checker() -> InventoryChecker:
    """Get the configured inventory checker instance.

    Returns:
        An instance of the configured InventoryChecker subclass,
        or DefaultInventoryChecker if none is configured.
    """
    from django.conf import settings

    checker_path = getattr(settings, "CART_INVENTORY_CHECKER", None)

    if not checker_path:
        return DefaultInventoryChecker()

    from django.utils.module_loading import import_string

    try:
        checker_class = import_string(checker_path)
        return checker_class()
    except (ImportError, AttributeError) as exc:
        warnings.warn(
            f"CART_INVENTORY_CHECKER={checker_path!r} could not be imported "
            f"({exc.__class__.__name__}: {exc}). Falling back to "
            f"DefaultInventoryChecker (always allows).",
            RuntimeWarning,
            stacklevel=2,
        )
        return DefaultInventoryChecker()
