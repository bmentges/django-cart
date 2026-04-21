"""
Smoke tests for the scaffolding itself.

Every fixture declared in tests/conftest.py has a matching test here that
verifies the fixture produces what its docstring promises. If any of these
fail, the whole suite is unreliable — fix these before anything else.

Keep this file lean: one test per fixture, happy-path only. Behavioural
assertions about Cart, Discount, etc. live in their own test_*.py files.
"""

from __future__ import annotations

from decimal import Decimal

from django.http import HttpRequest

from cart.cart import Cart
from cart.models import Discount, DiscountType
from tests.test_app.models import FakeProduct, FakeProductNoPrice


def test_rf_request_is_a_real_django_request(rf_request):
    assert isinstance(rf_request, HttpRequest)
    assert rf_request.method == "GET"
    assert rf_request.path == "/"
    assert isinstance(rf_request.session, dict)
    assert rf_request.session == {}


def test_cart_fixture_creates_persisted_cart(cart, rf_request):
    assert isinstance(cart, Cart)
    assert cart.cart.pk is not None
    assert cart.count() == 0
    assert cart.is_empty() is True
    assert rf_request.session["CART-ID"] == cart.cart.pk


def test_other_cart_is_independent_from_cart(cart, other_cart):
    assert cart.cart.pk != other_cart.cart.pk
    assert cart.is_empty() is True
    assert other_cart.is_empty() is True


def test_user_cart_is_bound_to_a_user(user_cart, django_user_model):
    assert user_cart.cart.user is not None
    assert user_cart.cart.user.username == "testuser"
    assert user_cart.cart.user.email == "test@example.com"
    assert django_user_model.objects.filter(username="testuser").count() == 1


def test_product_has_default_name_and_price(product):
    assert isinstance(product, FakeProduct)
    assert product.pk is not None
    assert product.name == "Test Product"
    assert product.price == Decimal("10.00")


def test_product_no_price_has_no_price_field(product_no_price):
    assert isinstance(product_no_price, FakeProductNoPrice)
    assert product_no_price.pk is not None
    assert product_no_price.name == "No Price Product"
    # The defining characteristic of this fixture: the model has no price
    # field at all (distinct from a nullable price). Exercised by the
    # validate_price=True skip path in Cart.add().
    assert not hasattr(product_no_price, "price")


def test_product_factory_creates_distinct_products(product_factory):
    alpha = product_factory(name="Alpha", price="5.00")
    beta = product_factory(name="Beta", price="12.50")

    assert alpha.pk != beta.pk
    assert alpha.name == "Alpha"
    assert alpha.price == Decimal("5.00")
    assert beta.name == "Beta"
    assert beta.price == Decimal("12.50")


def test_product_factory_applies_defaults(product_factory):
    widget = product_factory()

    assert widget.name == "Widget"
    assert widget.price == Decimal("10.00")


def test_discount_percent_is_a_20_percent_discount(discount_percent):
    assert isinstance(discount_percent, Discount)
    assert discount_percent.pk is not None
    assert discount_percent.code == "PERCENT20"
    assert discount_percent.discount_type == DiscountType.PERCENT
    assert discount_percent.value == Decimal("20.00")
    assert discount_percent.active is True
    assert discount_percent.current_uses == 0


def test_discount_fixed_is_a_10_dollar_discount(discount_fixed):
    assert isinstance(discount_fixed, Discount)
    assert discount_fixed.pk is not None
    assert discount_fixed.code == "FIXED10"
    assert discount_fixed.discount_type == DiscountType.FIXED
    assert discount_fixed.value == Decimal("10.00")
    assert discount_fixed.active is True
    assert discount_fixed.current_uses == 0
