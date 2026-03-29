"""
Tax calculation hooks for django-cart.

Allows customizable tax calculation through pluggable calculators.
"""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cart.cart import Cart


class TaxCalculator(ABC):
    """Base class for tax calculators."""

    @abstractmethod
    def calculate(self, cart: "Cart") -> Decimal:
        """
        Calculate tax for the given cart.

        Args:
            cart: The cart to calculate tax for.

        Returns:
            The tax amount as a Decimal.
        """
        raise NotImplementedError


class DefaultTaxCalculator(TaxCalculator):
    """Default tax calculator that returns zero tax."""

    def calculate(self, cart: "Cart") -> Decimal:
        """Return zero tax by default."""
        return Decimal("0.00")


def get_tax_calculator() -> TaxCalculator:
    """
    Get the configured tax calculator.

    Returns:
        A TaxCalculator instance.
    """
    from django.conf import settings

    calculator_class = getattr(settings, "CART_TAX_CALCULATOR", None)

    if calculator_class is None:
        return DefaultTaxCalculator()

    if isinstance(calculator_class, str):
        from django.utils.module_loading import import_string

        calculator_class = import_string(calculator_class)

    return calculator_class()


def calculate_tax(cart: "Cart") -> Decimal:
    """
    Calculate tax for a cart using the configured calculator.

    Args:
        cart: The cart to calculate tax for.

    Returns:
        The tax amount.
    """
    calculator = get_tax_calculator()
    return calculator.calculate(cart)
