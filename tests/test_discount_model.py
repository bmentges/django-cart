"""Discount model behaviour: creation, calculation, validity, cart field wiring."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from cart.models import Cart as CartModel
from cart.models import Discount, DiscountType

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


def test_percent_discount_amount_cannot_exceed_cart_subtotal(cart_worth_200):
    """P2 regression: a ``PERCENT`` discount with ``value > 100`` must
    still never return more than the cart's subtotal.

    Before v3.0.14, ``calculate_discount`` computed
    ``summary * value / 100`` with no clamp, so a (mis)configured
    150%-off discount on a $200 cart yielded a $300 discount amount —
    nonsense for any UI displaying "You saved $X" that doesn't also
    call :meth:`Cart.total`. ``FIXED`` already clamped via ``min``;
    ``PERCENT`` now matches. See docs/ANALYSIS.md §0 (P2 list).
    """
    discount = Discount.objects.create(
        code="BIGPCT",
        discount_type=DiscountType.PERCENT,
        value=Decimal("150.00"),
    )

    assert discount.calculate_discount(cart_worth_200) == Decimal("200.00")


# --------------------------------------------------------------------------- #
# clean() — PERCENT discounts can't exceed 100%
# --------------------------------------------------------------------------- #


def test_full_clean_rejects_percent_discount_value_above_100():
    """Admin forms and any caller that goes through ``full_clean``
    (Django's standard pre-save validation hook) must reject a
    percentage discount that claims to take more than 100% off.
    """
    from django.core.exceptions import ValidationError

    discount = Discount(
        code="BAD_PCT",
        discount_type=DiscountType.PERCENT,
        value=Decimal("150.00"),
    )

    with pytest.raises(ValidationError) as exc:
        discount.full_clean()
    assert "value" in exc.value.message_dict
    assert "100" in str(exc.value.message_dict["value"])


def test_full_clean_accepts_percent_discount_value_exactly_100():
    """100% off = cart is free. That's a legitimate promo and must
    pass validation."""
    discount = Discount(
        code="FREE",
        discount_type=DiscountType.PERCENT,
        value=Decimal("100.00"),
    )

    discount.full_clean()  # must not raise


def test_full_clean_accepts_fixed_discount_value_above_100():
    """The PERCENT ≤ 100 guard must not leak into FIXED discounts —
    a $500 off voucher is a perfectly normal configuration."""
    discount = Discount(
        code="BIG_FIXED",
        discount_type=DiscountType.FIXED,
        value=Decimal("500.00"),
    )

    discount.full_clean()  # must not raise


# --------------------------------------------------------------------------- #
# clean() — valid_from must precede valid_until when both are set
# --------------------------------------------------------------------------- #


def test_full_clean_rejects_valid_from_after_valid_until():
    """P2 regression: an admin could previously create a discount with
    ``valid_from`` *after* ``valid_until`` (e.g. a copy-paste with the
    dates swapped). The resulting row is never valid for any cart —
    ``is_valid_for_cart`` falls through every window check. Nothing in
    the library rejected the input, so the misconfiguration was only
    discoverable at promo-launch-day-not-working time."""
    from django.core.exceptions import ValidationError

    now = timezone.now()
    discount = Discount(
        code="INVERTED",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
        valid_from=now + timedelta(days=5),
        valid_until=now,
    )

    with pytest.raises(ValidationError) as exc:
        discount.full_clean()
    assert "valid_until" in exc.value.message_dict


def test_full_clean_accepts_equal_valid_from_and_valid_until():
    """Edge case: an exactly-at-the-same-instant validity window is
    a degenerate but not nonsensical config (a one-tick flash sale).
    Allow it — rejecting would be over-tight."""
    now = timezone.now()
    discount = Discount(
        code="INSTANT",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
        valid_from=now,
        valid_until=now,
    )

    discount.full_clean()


def test_full_clean_accepts_missing_validity_bounds():
    """One or both of ``valid_from`` / ``valid_until`` may be ``None``
    — indicates an open-ended window and must not trigger the check."""
    discount = Discount(
        code="OPEN_ENDED",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
    )

    discount.full_clean()


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
