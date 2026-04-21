"""clean_carts management command — delete abandoned cart records."""
from __future__ import annotations

import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from cart.models import Cart as CartModel, Item
from tests.test_app.models import FakeProduct


pytestmark = pytest.mark.django_db


def _call(**kwargs):
    out = io.StringIO()
    call_command("clean_carts", stdout=out, **kwargs)
    return out.getvalue()


def _old_cart(days=100, checked_out=False):
    return CartModel.objects.create(
        creation_date=timezone.now() - timedelta(days=days),
        checked_out=checked_out,
    )


def _fresh_cart():
    return CartModel.objects.create(creation_date=timezone.now())


# --------------------------------------------------------------------------- #
# Success paths
# --------------------------------------------------------------------------- #

def test_deletes_old_abandoned_carts():
    old = _old_cart(days=100)
    fresh = _fresh_cart()

    _call(days=90)

    assert CartModel.objects.filter(pk=old.pk).exists() is False
    assert CartModel.objects.filter(pk=fresh.pk).exists() is True


def test_does_not_delete_carts_under_the_age_threshold():
    recent = _old_cart(days=10)

    _call(days=90)

    assert CartModel.objects.filter(pk=recent.pk).exists() is True


def test_default_days_threshold_is_90():
    old = _old_cart(days=91)

    _call()

    assert CartModel.objects.filter(pk=old.pk).exists() is False


def test_does_not_delete_checked_out_carts_by_default():
    checked_out = _old_cart(days=100, checked_out=True)

    _call(days=90)

    assert CartModel.objects.filter(pk=checked_out.pk).exists() is True


def test_include_checked_out_flag_deletes_checked_out_carts():
    checked_out = _old_cart(days=100, checked_out=True)

    _call(days=90, include_checked_out=True)

    assert CartModel.objects.filter(pk=checked_out.pk).exists() is False


def test_dry_run_preserves_rows_and_announces_intent():
    old = _old_cart(days=100)

    output = _call(days=90, dry_run=True)

    assert CartModel.objects.filter(pk=old.pk).exists() is True
    assert "DRY RUN" in output


def test_output_reports_deletion_count():
    _old_cart(days=100)
    _old_cart(days=200)

    output = _call(days=90)

    assert "2" in output


def test_nothing_to_delete_produces_an_informative_message():
    output = _call(days=90)

    assert "Nothing to delete" in output


# --------------------------------------------------------------------------- #
# Error paths
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("invalid_days", [0, -5])
def test_non_positive_days_raises_command_error(invalid_days):
    with pytest.raises(CommandError):
        _call(days=invalid_days)


# --------------------------------------------------------------------------- #
# Boundaries and cascades
# --------------------------------------------------------------------------- #

def test_cart_exactly_over_boundary_is_deleted():
    boundary = CartModel.objects.create(
        creation_date=timezone.now() - timedelta(days=90, seconds=1),
    )

    _call(days=90)

    assert CartModel.objects.filter(pk=boundary.pk).exists() is False


def test_cart_just_under_boundary_is_preserved():
    recent = CartModel.objects.create(
        creation_date=timezone.now() - timedelta(days=89, hours=23, minutes=59),
    )

    _call(days=90)

    assert CartModel.objects.filter(pk=recent.pk).exists() is True


def test_deleting_a_cart_cascades_to_its_items(product):
    old = _old_cart(days=100)
    ct = ContentType.objects.get_for_model(FakeProduct)
    item = Item.objects.create(
        cart=old,
        content_type=ct,
        object_id=product.pk,
        unit_price=Decimal("1.00"),
        quantity=1,
    )

    _call(days=90)

    assert Item.objects.filter(pk=item.pk).exists() is False
