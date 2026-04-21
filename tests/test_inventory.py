"""InventoryChecker behaviour + Cart.add(check_inventory=True) integration."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from cart.cart import InsufficientStock
from cart.inventory import (
    DefaultInventoryChecker,
    InventoryChecker,
    get_inventory_checker,
)


class PassingInventoryChecker(InventoryChecker):
    """Module-level test double — always reports stock available."""

    def check(self, product, quantity):
        return True

    def reserve(self, product, quantity):
        return True


class FailingInventoryChecker(InventoryChecker):
    """Module-level test double — always reports stock unavailable."""

    def check(self, product, quantity):
        return False

    def reserve(self, product, quantity):
        return False


# --------------------------------------------------------------------------- #
# InventoryChecker interface
# --------------------------------------------------------------------------- #

def test_default_inventory_checker_always_reports_available():
    assert DefaultInventoryChecker().check(MagicMock(), 1) is True


def test_default_inventory_checker_release_returns_true():
    assert DefaultInventoryChecker().release(MagicMock(), 1) is True


def test_get_inventory_checker_returns_default_when_setting_unset():
    assert isinstance(get_inventory_checker(), DefaultInventoryChecker)


@pytest.mark.django_db
def test_get_inventory_checker_loads_custom_class_from_settings(settings):
    settings.CART_INVENTORY_CHECKER = "tests.test_inventory.PassingInventoryChecker"

    assert isinstance(get_inventory_checker(), PassingInventoryChecker)


def test_custom_inventory_checker_subclass_is_usable_inline():
    class QuantityBoundedChecker(InventoryChecker):
        def check(self, product, quantity):
            return quantity <= 5

        def reserve(self, product, quantity):
            return quantity <= 5

    checker = QuantityBoundedChecker()
    assert checker.check(MagicMock(), 3) is True
    assert checker.check(MagicMock(), 10) is False


# --------------------------------------------------------------------------- #
# Cart.add integration (check_inventory parameter)
# --------------------------------------------------------------------------- #

def test_add_without_check_inventory_skips_the_checker(cart, product):
    item = cart.add(product, unit_price=Decimal("100.00"), quantity=2)

    assert item is not None
    assert item.quantity == 2


def test_add_with_check_inventory_raises_when_checker_fails(cart, product, settings):
    settings.CART_INVENTORY_CHECKER = "tests.test_inventory.FailingInventoryChecker"

    with pytest.raises(InsufficientStock):
        cart.add(
            product,
            unit_price=Decimal("100.00"),
            quantity=2,
            check_inventory=True,
        )


def test_add_with_check_inventory_succeeds_when_checker_passes(cart, product, settings):
    settings.CART_INVENTORY_CHECKER = "tests.test_inventory.PassingInventoryChecker"

    item = cart.add(
        product,
        unit_price=Decimal("100.00"),
        quantity=2,
        check_inventory=True,
    )

    assert item is not None
