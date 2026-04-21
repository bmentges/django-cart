"""Cart.merge: three strategies + error cases + guest-to-user flow."""

from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "strategy,cart_qty,other_qty,expected",
    [
        ("add", 2, 3, 5),
        ("replace", 2, 5, 5),
        ("keep_higher", 3, 7, 7),
        ("keep_higher", 7, 3, 7),
    ],
    ids=[
        "add-combines",
        "replace-overwrites",
        "keep-higher-picks-other",
        "keep-higher-picks-self",
    ],
)
def test_merge_strategy_resolves_existing_item_quantity(
    cart, other_cart, product, strategy, cart_qty, other_qty, expected
):
    cart.add(product, Decimal("10.00"), quantity=cart_qty)
    other_cart.add(product, Decimal("10.00"), quantity=other_qty)

    cart.merge(other_cart, strategy=strategy)

    assert cart.cart.items.first().quantity == expected


def test_merge_default_strategy_is_add(cart, other_cart, product):
    cart.add(product, Decimal("10.00"), quantity=2)
    other_cart.add(product, Decimal("10.00"), quantity=3)

    cart.merge(other_cart)

    assert cart.cart.items.first().quantity == 5


def test_merge_adds_products_not_present_in_target_cart(
    cart, other_cart, product_factory
):
    a = product_factory(name="A")
    b = product_factory(name="B")
    cart.add(a, Decimal("10.00"), quantity=1)
    other_cart.add(b, Decimal("20.00"), quantity=2)

    cart.merge(other_cart)

    assert cart.unique_count() == 2
    assert cart.count() == 3


def test_merge_clears_the_source_cart(cart, other_cart, product):
    cart.add(product, Decimal("10.00"), quantity=1)
    other_cart.add(product, Decimal("10.00"), quantity=2)

    cart.merge(other_cart)

    assert other_cart.is_empty() is True


def test_merge_updates_unit_price_from_source(cart, other_cart, product):
    cart.add(product, Decimal("10.00"), quantity=1)
    other_cart.add(product, Decimal("15.00"), quantity=2)

    cart.merge(other_cart)

    assert cart.cart.items.first().unit_price == Decimal("15.00")


# --------------------------------------------------------------------------- #
# Error paths
# --------------------------------------------------------------------------- #


def test_merge_with_invalid_strategy_raises(cart, other_cart):
    with pytest.raises(ValueError):
        cart.merge(other_cart, strategy="invalid-strategy")


def test_merge_preserves_target_cart_on_invalid_strategy(cart, other_cart, product):
    cart.add(product, Decimal("10.00"), quantity=5)

    with pytest.raises(ValueError):
        cart.merge(other_cart, strategy="invalid-strategy")

    assert cart.count() == 5


def test_merge_with_self_raises(cart, product):
    cart.add(product, Decimal("10.00"), quantity=1)

    with pytest.raises(ValueError):
        cart.merge(cart)


def test_merge_from_empty_source_is_a_noop(cart, other_cart, product):
    cart.add(product, Decimal("10.00"), quantity=1)

    cart.merge(other_cart)

    assert cart.count() == 1


# --------------------------------------------------------------------------- #
# Integration — guest cart → user cart
# --------------------------------------------------------------------------- #


def test_guest_cart_merges_into_user_cart_on_login_flow(
    cart, other_cart, product, django_user_model
):
    user = django_user_model.objects.create_user(
        username="loginuser",
        email="login@example.com",
        password="pass123",
    )
    guest, user_cart = other_cart, cart
    guest.add(product, Decimal("10.00"), quantity=1)
    user_cart.bind_to_user(user)

    user_cart.merge(guest, strategy="add")

    assert user_cart.count() == 1
    assert guest.is_empty() is True


def test_merge_preserves_user_binding_on_target(
    cart, other_cart, product, django_user_model
):
    user = django_user_model.objects.create_user(
        username="mergeuser",
        email="merge@example.com",
        password="pass123",
    )
    cart.bind_to_user(user)
    cart.add(product, Decimal("10.00"), quantity=1)
    other_cart.add(product, Decimal("10.00"), quantity=2)

    cart.merge(other_cart)

    cart.cart.refresh_from_db()
    assert cart.cart.user == user
