"""Cart discount methods: apply_discount, remove_discount, discount_amount, discount_code."""
from __future__ import annotations

from decimal import Decimal

import pytest

from datetime import timedelta

from django.utils import timezone

from cart.cart import Cart, InvalidDiscountError
from cart.models import Discount, DiscountType


pytestmark = pytest.mark.django_db


@pytest.fixture
def cart_worth_200(cart, product):
    cart.add(product, unit_price=Decimal("100.00"), quantity=2)
    return cart


def test_discount_amount_is_zero_when_no_discount_applied(cart_worth_200):
    assert cart_worth_200.discount_amount() == Decimal("0.00")


def test_discount_code_is_none_when_no_discount_applied(cart_worth_200):
    assert cart_worth_200.discount_code() is None


def test_apply_discount_attaches_the_discount_to_the_cart(cart_worth_200):
    discount = Discount.objects.create(
        code="SAVE10",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
    )

    applied = cart_worth_200.apply_discount("SAVE10")

    assert applied == discount
    assert cart_worth_200.discount_code() == "SAVE10"
    assert cart_worth_200.discount_amount() == Decimal("20.00")


def test_apply_discount_with_unknown_code_raises(cart_worth_200):
    with pytest.raises(InvalidDiscountError, match="does not exist"):
        cart_worth_200.apply_discount("NOPE")


def test_apply_discount_when_one_is_already_applied_raises(cart_worth_200):
    Discount.objects.create(
        code="FIRST",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
    )
    Discount.objects.create(
        code="SECOND",
        discount_type=DiscountType.PERCENT,
        value=Decimal("5.00"),
    )
    cart_worth_200.apply_discount("FIRST")

    with pytest.raises(InvalidDiscountError, match="already applied"):
        cart_worth_200.apply_discount("SECOND")


def test_apply_discount_propagates_is_valid_for_cart_errors(cart_worth_200):
    Discount.objects.create(
        code="MIN1000",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
        min_cart_value=Decimal("1000.00"),
    )

    with pytest.raises(InvalidDiscountError, match="Minimum cart value"):
        cart_worth_200.apply_discount("MIN1000")


def test_remove_discount_clears_the_applied_discount(cart_worth_200):
    Discount.objects.create(
        code="REMOVE",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
    )
    cart_worth_200.apply_discount("REMOVE")

    cart_worth_200.remove_discount()

    assert cart_worth_200.discount_code() is None
    assert cart_worth_200.discount_amount() == Decimal("0.00")


def test_remove_discount_is_a_noop_when_no_discount_is_applied(cart_worth_200):
    cart_worth_200.remove_discount()  # Should not raise.

    assert cart_worth_200.discount_amount() == Decimal("0.00")


def test_applying_discount_invalidates_cart_cache(cart_worth_200):
    """Before applying, the cache holds the pre-discount summary. After
    applying, discount_amount() must reflect the new state — if the cache
    isn't invalidated on apply, the amount stays at 0.00."""
    Discount.objects.create(
        code="CACHE_TEST",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
    )
    _ = cart_worth_200.summary()

    cart_worth_200.apply_discount("CACHE_TEST")

    assert cart_worth_200.discount_amount() == Decimal("20.00")


# --------------------------------------------------------------------------- #
# Discount.increment_usage — direct coverage of the model method
# --------------------------------------------------------------------------- #

def test_discount_increment_usage_increments_the_counter(discount_percent):
    """The method exists on Discount but is never called from Cart today
    (P0-2). Tested directly so the model-level behaviour is covered
    regardless of whether the Cart integration lands."""
    starting = discount_percent.current_uses

    discount_percent.increment_usage()

    discount_percent.refresh_from_db()
    assert discount_percent.current_uses == starting + 1


def test_apply_discount_then_checkout_increments_current_uses(
    cart_worth_200, discount_percent
):
    """After applying a discount and checking out, the discount's
    current_uses should be 1. Today it stays 0."""
    cart_worth_200.apply_discount("PERCENT20")

    cart_worth_200.checkout()

    discount_percent.refresh_from_db()
    assert discount_percent.current_uses == 1


def test_max_uses_enforced_across_carts(cart_worth_200, product, product_factory):
    """A discount with ``max_uses=1`` can be applied + checked out once;
    a second cart applying the same code must fail with a clear error."""
    Discount.objects.create(
        code="ONESHOT",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
        max_uses=1,
    )
    cart_worth_200.apply_discount("ONESHOT")
    cart_worth_200.checkout()

    from django.test import RequestFactory
    request2 = RequestFactory().get("/")
    request2.session = {}
    second = Cart(request2)
    second.add(product, unit_price=Decimal("100.00"), quantity=2)

    with pytest.raises(InvalidDiscountError, match="maximum number of uses"):
        second.apply_discount("ONESHOT")


def test_checkout_with_expired_discount_rolls_back(cart_worth_200, discount_percent):
    """If a discount becomes invalid between apply and checkout (e.g.
    expired), checkout must raise and roll back — the cart stays open
    and the counter never increments."""
    cart_worth_200.apply_discount("PERCENT20")

    discount_percent.valid_until = timezone.now() - timedelta(days=1)
    discount_percent.save(update_fields=["valid_until"])

    with pytest.raises(InvalidDiscountError, match="expired"):
        cart_worth_200.checkout()

    cart_worth_200.cart.refresh_from_db()
    discount_percent.refresh_from_db()
    assert cart_worth_200.cart.checked_out is False
    assert discount_percent.current_uses == 0


def test_checkout_is_idempotent_does_not_double_increment(
    cart_worth_200, discount_percent
):
    """Calling checkout() twice on the same cart must leave
    current_uses=1, not 2. Double-checkout is a no-op."""
    cart_worth_200.apply_discount("PERCENT20")

    cart_worth_200.checkout()
    cart_worth_200.checkout()

    discount_percent.refresh_from_db()
    assert discount_percent.current_uses == 1
