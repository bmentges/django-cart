"""Shipping calculation system for django-cart.

This module provides a pluggable shipping cost calculation system that can be
extended to support different shipping providers and options.

Usage:
    1. Create a custom shipping calculator:
       class MyShippingCalculator(ShippingCalculator):
           def calculate(self, cart: Cart) -> Decimal:
               return Decimal("9.99")

           def get_options(self, cart: Cart) -> list[dict]:
               return [
                   {'id': 'standard', 'name': 'Standard Shipping', 'price': '5.99'},
                   {'id': 'express', 'name': 'Express Shipping', 'price': '14.99'},
               ]

    2. Configure in settings:
       CART_SHIPPING_CALCULATOR = 'myapp.utils.MyShippingCalculator'

    3. Use in templates or views:
       shipping = cart.shipping()  # Returns Decimal
       options = cart.shipping_options()  # Returns list of options
"""

import warnings
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from cart.cart import Cart


class ShippingOption(TypedDict):
    """Type definition for a shipping option."""

    id: str
    name: str
    price: str


class ShippingCalculator(ABC):
    """Base class for shipping calculators.

    Implement this class to create custom shipping calculation logic for
    your e-commerce platform.

    Example:
        class FlatRateShipping(ShippingCalculator):
            def calculate(self, cart: Cart) -> Decimal:
                return Decimal("5.99")

            def get_options(self, cart: Cart) -> list[dict]:
                return [
                    {'id': 'standard', 'name': 'Standard', 'price': '5.99'},
                ]
    """

    @abstractmethod
    def calculate(self, cart: "Cart") -> Decimal:
        """Calculate shipping cost for the given cart.

        Args:
            cart: The cart to calculate shipping for.

        Returns:
            The shipping cost as a Decimal.

        Raises:
            NotImplementedError: Subclasses must implement this method.
        """
        raise NotImplementedError("Subclasses must implement calculate()")

    @abstractmethod
    def get_options(self, cart: "Cart") -> list[ShippingOption]:
        """Return available shipping options for the cart.

        Args:
            cart: The cart to get shipping options for.

        Returns:
            A list of shipping option dictionaries, each containing:
            - id: Unique identifier for the option
            - name: Display name for the option
            - price: Price as a string (e.g., '5.99')

        Raises:
            NotImplementedError: Subclasses must implement this method.
        """
        raise NotImplementedError("Subclasses must implement get_options()")


class DefaultShippingCalculator(ShippingCalculator):
    """Default shipping calculator that returns zero shipping.

    This is used when no custom calculator is configured via
    CART_SHIPPING_CALCULATOR setting.
    """

    def calculate(self, cart: "Cart") -> Decimal:
        """Return zero shipping cost.

        Args:
            cart: The cart (unused in default implementation).

        Returns:
            Decimal("0.00")
        """
        return Decimal("0.00")

    def get_options(self, cart: "Cart") -> list[ShippingOption]:
        """Return a single free shipping option.

        Args:
            cart: The cart (unused in default implementation).

        Returns:
            A list containing one free shipping option.
        """
        return [
            ShippingOption(id="free", name="Free Shipping", price="0.00"),
        ]


def get_shipping_calculator() -> ShippingCalculator:
    """Get the configured shipping calculator instance.

    Returns:
        An instance of the configured ShippingCalculator subclass,
        or DefaultShippingCalculator if none is configured.
    """
    from django.conf import settings

    calculator_path = getattr(settings, "CART_SHIPPING_CALCULATOR", None)

    if not calculator_path:
        return DefaultShippingCalculator()

    from django.utils.module_loading import import_string

    try:
        calculator_class = import_string(calculator_path)
        return calculator_class()
    except (ImportError, AttributeError) as exc:
        warnings.warn(
            f"CART_SHIPPING_CALCULATOR={calculator_path!r} could not be "
            f"imported ({exc.__class__.__name__}: {exc}). Falling back to "
            f"DefaultShippingCalculator (zero cost).",
            RuntimeWarning,
            stacklevel=2,
        )
        return DefaultShippingCalculator()
