"""Tax calculation system for django-cart.

This module provides a pluggable tax calculation system that can be extended
to support different tax rules and regions.

Usage:
    1. Create a custom tax calculator:
       class MyTaxCalculator(TaxCalculator):
           def calculate(self, cart: Cart) -> Decimal:
               # Your tax logic here
               return cart.summary() * Decimal("0.10")

    2. Configure in settings:
       CART_TAX_CALCULATOR = 'myapp.utils.MyTaxCalculator'

    3. Use in templates or views:
       tax = cart.tax()  # Returns Decimal
"""

import warnings
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cart.cart import Cart


class TaxCalculator(ABC):
    """Base class for tax calculators.
    
    Implement this class to create custom tax calculation logic for your
    e-commerce platform. The calculate method must return the tax amount
    as a Decimal.
    
    Example:
        class USStateTax(TaxCalculator):
            def calculate(self, cart: Cart) -> Decimal:
                # Calculate based on cart contents
                subtotal = cart.summary()
                return subtotal * Decimal("0.0825")  # 8.25% tax
    """

    @abstractmethod
    def calculate(self, cart: "Cart") -> Decimal:
        """Calculate tax for the given cart.
        
        Args:
            cart: The cart to calculate tax for.
            
        Returns:
            The tax amount as a Decimal.
            
        Raises:
            NotImplementedError: Subclasses must implement this method.
        """
        raise NotImplementedError("Subclasses must implement calculate()")


class DefaultTaxCalculator(TaxCalculator):
    """Default tax calculator that returns zero tax.
    
    This is used when no custom calculator is configured via
    CART_TAX_CALCULATOR setting.
    """

    def calculate(self, cart: "Cart") -> Decimal:
        """Return zero tax.
        
        Args:
            cart: The cart (unused in default implementation).
            
        Returns:
            Decimal("0.00")
        """
        return Decimal("0.00")


def get_tax_calculator() -> TaxCalculator:
    """Get the configured tax calculator instance.
    
    Returns:
        An instance of the configured TaxCalculator subclass,
        or DefaultTaxCalculator if none is configured.
    """
    from django.conf import settings
    
    calculator_path = getattr(settings, 'CART_TAX_CALCULATOR', None)
    
    if not calculator_path:
        return DefaultTaxCalculator()
    
    from django.utils.module_loading import import_string
    
    try:
        calculator_class = import_string(calculator_path)
        return calculator_class()
    except (ImportError, AttributeError) as exc:
        warnings.warn(
            f"CART_TAX_CALCULATOR={calculator_path!r} could not be imported "
            f"({exc.__class__.__name__}: {exc}). Falling back to "
            f"DefaultTaxCalculator (zero tax).",
            RuntimeWarning,
            stacklevel=2,
        )
        return DefaultTaxCalculator()
