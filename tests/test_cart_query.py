"""Query methods: count, unique_count, summary, is_empty, __contains__, __len__,
plus decimal/large-number edge cases."""

from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------- #
# Populated cart
# --------------------------------------------------------------------------- #


@pytest.fixture
def cart_with_two_products(cart, product_factory):
    p1 = product_factory(name="A", price="10.00")
    p2 = product_factory(name="B", price="4.00")
    cart.add(p1, Decimal("10.00"), quantity=2)
    cart.add(p2, Decimal("4.00"), quantity=5)
    return cart, p1, p2


def test_count_returns_total_units(cart_with_two_products):
    cart, _, _ = cart_with_two_products

    assert cart.count() == 7


def test_unique_count_returns_distinct_product_count(cart_with_two_products):
    cart, _, _ = cart_with_two_products

    assert cart.unique_count() == 2


def test_summary_returns_sum_of_quantity_times_unit_price(cart_with_two_products):
    cart, _, _ = cart_with_two_products

    assert cart.summary() == Decimal("40.00")


def test_is_empty_returns_false_when_cart_has_items(cart_with_two_products):
    cart, _, _ = cart_with_two_products

    assert cart.is_empty() is False


def test_is_empty_returns_true_after_clear(cart_with_two_products):
    cart, _, _ = cart_with_two_products

    cart.clear()

    assert cart.is_empty() is True


def test_len_matches_count(cart_with_two_products):
    cart, _, _ = cart_with_two_products

    assert len(cart) == cart.count()


def test_contains_returns_true_for_product_in_cart(cart_with_two_products):
    cart, p1, _ = cart_with_two_products

    assert p1 in cart


def test_contains_returns_false_for_product_not_in_cart(
    cart_with_two_products, product_factory
):
    cart, _, _ = cart_with_two_products
    ghost = product_factory(name="Ghost")

    assert ghost not in cart


# --------------------------------------------------------------------------- #
# Empty cart
# --------------------------------------------------------------------------- #


def test_count_on_empty_cart_is_zero(cart):
    assert cart.count() == 0


def test_summary_on_empty_cart_is_zero_decimal(cart):
    assert cart.summary() == Decimal("0.00")


def test_summary_on_empty_cart_returns_a_decimal_instance(cart):
    assert isinstance(cart.summary(), Decimal)


def test_is_empty_on_fresh_cart_is_true(cart):
    assert cart.is_empty() is True


def test_clear_on_empty_cart_is_noop(cart):
    cart.clear()  # must not raise

    assert cart.is_empty() is True


def test_iterating_empty_cart_yields_no_items(cart):
    assert list(cart) == []


# --------------------------------------------------------------------------- #
# Decimal / boundary cases
# --------------------------------------------------------------------------- #


def test_cart_handles_very_large_quantity(cart, product):
    cart.add(product, Decimal("0.01"), quantity=999_999)

    assert cart.count() == 999_999
    assert cart.summary() == Decimal("9999.99")


def test_cart_preserves_small_decimal_precision(cart, product):
    cart.add(product, Decimal("0.01"), quantity=1)
    cart.add(product, Decimal("0.02"), quantity=1)

    assert cart.cart.items.first().unit_price == Decimal("0.02")
    assert cart.summary() == Decimal("0.04")


def test_cart_allows_zero_unit_price(cart, product):
    cart.add(product, Decimal("0.00"), quantity=5)

    assert cart.count() == 5
    assert cart.summary() == Decimal("0.00")


def test_cart_handles_very_large_unit_price(cart, product):
    cart.add(product, Decimal("999999.99"), quantity=1)

    assert cart.summary() == Decimal("999999.99")
