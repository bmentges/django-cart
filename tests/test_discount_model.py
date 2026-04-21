"""Discount model behaviour: creation, calculation, validity, cart field wiring."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from cart.models import Cart as CartModel, Discount, DiscountType


pytestmark = pytest.mark.django_db


@pytest.fixture
def cart_worth_200(cart, product):
    """A cart whose summary() is Decimal('200.00'). Default reference state for
    discount calculations throughout this file."""
    cart.add(product, unit_price=Decimal("100.00"), quantity=2)
    assert cart.summary() == Decimal("200.00")
    return cart


# --------------------------------------------------------------------------- #
# DiscountType enum
# --------------------------------------------------------------------------- #

def test_discount_type_values_are_percent_and_fixed():
    assert DiscountType.PERCENT == "percent"
    assert DiscountType.FIXED == "fixed"


# --------------------------------------------------------------------------- #
# Create / unique constraint / __str__
# --------------------------------------------------------------------------- #

def test_create_percent_discount_defaults_to_active():
    discount = Discount.objects.create(
        code="SAVE20",
        discount_type=DiscountType.PERCENT,
        value=Decimal("20.00"),
    )

    assert discount.code == "SAVE20"
    assert discount.discount_type == "percent"
    assert discount.value == Decimal("20.00")
    assert discount.active is True


def test_create_fixed_discount_stores_fixed_type():
    discount = Discount.objects.create(
        code="FLAT10",
        discount_type=DiscountType.FIXED,
        value=Decimal("10.00"),
    )

    assert discount.discount_type == "fixed"
    assert discount.value == Decimal("10.00")


def test_discount_code_must_be_unique():
    Discount.objects.create(code="UNIQUE", value=Decimal("10.00"))

    with pytest.raises(IntegrityError):
        Discount.objects.create(code="UNIQUE", value=Decimal("20.00"))


def test_discount_str_includes_code():
    discount = Discount.objects.create(
        code="TEST",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
    )

    assert "TEST" in str(discount)


# --------------------------------------------------------------------------- #
# calculate_discount
# --------------------------------------------------------------------------- #

def test_percent_discount_calculation(cart_worth_200):
    discount = Discount.objects.create(
        code="SAVE20",
        discount_type=DiscountType.PERCENT,
        value=Decimal("20.00"),
    )

    assert discount.calculate_discount(cart_worth_200) == Decimal("40.00")


def test_fixed_discount_calculation_returns_face_value(cart_worth_200):
    discount = Discount.objects.create(
        code="FLAT25",
        discount_type=DiscountType.FIXED,
        value=Decimal("25.00"),
    )

    assert discount.calculate_discount(cart_worth_200) == Decimal("25.00")


def test_fixed_discount_cannot_exceed_cart_subtotal(cart_worth_200):
    discount = Discount.objects.create(
        code="BIGFLAT",
        discount_type=DiscountType.FIXED,
        value=Decimal("500.00"),
    )

    assert discount.calculate_discount(cart_worth_200) == Decimal("200.00")


# --------------------------------------------------------------------------- #
# is_valid_for_cart
# --------------------------------------------------------------------------- #

def test_discount_with_no_restrictions_is_valid(cart_worth_200):
    discount = Discount.objects.create(
        code="NO_RESTRICT",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
    )

    is_valid, message = discount.is_valid_for_cart(cart_worth_200)

    assert is_valid is True
    assert message == ""


def test_discount_below_min_cart_value_is_invalid(cart_worth_200):
    discount = Discount.objects.create(
        code="MIN500",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
        min_cart_value=Decimal("500.00"),
    )

    is_valid, message = discount.is_valid_for_cart(cart_worth_200)

    assert is_valid is False
    assert "Minimum cart value" in message


def test_discount_at_or_above_min_cart_value_is_valid(cart_worth_200):
    discount = Discount.objects.create(
        code="MIN100",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
        min_cart_value=Decimal("100.00"),
    )

    is_valid, _ = discount.is_valid_for_cart(cart_worth_200)

    assert is_valid is True


def test_discount_at_max_uses_is_invalid(cart_worth_200):
    discount = Discount.objects.create(
        code="LIMITED",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
        max_uses=1,
        current_uses=1,
    )

    is_valid, message = discount.is_valid_for_cart(cart_worth_200)

    assert is_valid is False
    assert "maximum number of uses" in message


def test_inactive_discount_is_invalid(cart_worth_200):
    discount = Discount.objects.create(
        code="INACTIVE",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
        active=False,
    )

    is_valid, message = discount.is_valid_for_cart(cart_worth_200)

    assert is_valid is False
    assert "no longer active" in message


def test_discount_not_yet_valid_is_invalid(cart_worth_200):
    discount = Discount.objects.create(
        code="FUTURE",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
        valid_from=timezone.now() + timedelta(days=1),
    )

    is_valid, message = discount.is_valid_for_cart(cart_worth_200)

    assert is_valid is False
    assert "not yet valid" in message


def test_expired_discount_is_invalid(cart_worth_200):
    discount = Discount.objects.create(
        code="EXPIRED",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
        valid_until=timezone.now() - timedelta(days=1),
    )

    is_valid, message = discount.is_valid_for_cart(cart_worth_200)

    assert is_valid is False
    assert "expired" in message


# --------------------------------------------------------------------------- #
# Cart.discount field wiring
# --------------------------------------------------------------------------- #

def test_new_cart_has_no_discount():
    cart_model = CartModel.objects.create()

    assert cart_model.discount is None


def test_cart_can_store_and_retrieve_a_discount():
    cart_model = CartModel.objects.create()
    discount = Discount.objects.create(
        code="ATTACHED",
        discount_type=DiscountType.PERCENT,
        value=Decimal("5.00"),
    )

    cart_model.discount = discount
    cart_model.save()
    cart_model.refresh_from_db()

    assert cart_model.discount == discount
