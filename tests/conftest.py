"""
Shared pytest fixtures for the django-cart test suite.

This module is the single source of test helpers. Per the P-1 test overhaul
(see docs/ANALYSIS.md), test files MUST NOT define their own helper
functions — declare a fixture here instead, or extend an existing one.

See tests/README.md for the canonical test pattern, the rationale, and the
full catalogue.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from django.test import RequestFactory

from cart.cart import Cart
from cart.models import Discount, DiscountType
from tests.test_app.models import FakeProduct, FakeProductNoPrice

# --------------------------------------------------------------------------- #
# Custom-AUTH_USER_MODEL test gating
# --------------------------------------------------------------------------- #
# test_cart_custom_user.py requires AUTH_USER_MODEL to be swapped to
# tests.custom_user_app.CustomUser — a setup that cannot coexist with the
# default suite in a single process (Django's app registry is frozen after
# init). It runs under a dedicated settings module invoked via
# ``pytest --ds=tests.settings_custom_user tests/test_cart_custom_user.py``.
# This hook keeps the default ``pytest`` invocation from collecting the
# file and tripping over the sanity assertion about the active user model.


def pytest_ignore_collect(collection_path, config):
    if collection_path.name == "test_cart_custom_user.py":
        ds = (
            os.environ.get("DJANGO_SETTINGS_MODULE")
            or config.getini("DJANGO_SETTINGS_MODULE")
            or ""
        )
        return ds != "tests.settings_custom_user"
    return False


# --------------------------------------------------------------------------- #
# Request / session
# --------------------------------------------------------------------------- #


@pytest.fixture
def rf_request():
    """A real Django request with an empty dict session attached.

    Prefer this over ``MagicMock``. A real ``RequestFactory`` request exposes
    the full request API (GET, POST, COOKIES, META, etc.) so session-layer
    bugs that a MagicMock would silently hide surface as real failures.

    The session starts empty so the first ``Cart(rf_request)`` creates a
    fresh cart and writes ``CART-ID`` back into it — useful for assertions
    like ``rf_request.session["CART-ID"] == cart.cart.pk``.
    """
    request = RequestFactory().get("/")
    request.session = {}
    return request


# --------------------------------------------------------------------------- #
# Carts
# --------------------------------------------------------------------------- #


@pytest.fixture
def cart(db, rf_request):
    """A fresh ``Cart`` bound to the ``rf_request`` session.

    Because this shares the ``rf_request`` fixture, any assertion about the
    request's session (``rf_request.session["CART-ID"]``) reflects the state
    of ``cart`` too.
    """
    return Cart(rf_request)


@pytest.fixture
def other_cart(db):
    """A second ``Cart`` with its own independent request and session.

    Use when a test needs two carts that must not share state — merges,
    session-isolation checks, guest-to-user login flows, concurrent-user
    scenarios.
    """
    request = RequestFactory().get("/")
    request.session = {}
    return Cart(request)


@pytest.fixture
def user_cart(db, django_user_model):
    """A ``Cart`` bound to a freshly created user account.

    The user is created with username='testuser', email='test@example.com',
    password='testpass123'. Tests that need a specific user should build
    one inline via ``django_user_model`` and call ``bind_to_user`` manually
    rather than adjusting this fixture.
    """
    user = django_user_model.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    request = RequestFactory().get("/")
    request.session = {}
    bound_cart = Cart(request)
    bound_cart.bind_to_user(user)
    return bound_cart


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #


@pytest.fixture
def product(db):
    """The default product: a ``FakeProduct`` named 'Test Product' at $10.00.

    Use for any test that needs "a product" without caring about its specific
    shape. For multiple distinct products use ``product_factory``.
    """
    return FakeProduct.objects.create(name="Test Product", price=Decimal("10.00"))


@pytest.fixture
def product_no_price(db):
    """A ``FakeProductNoPrice`` — a product model without a ``price`` attribute.

    Use to exercise paths that must tolerate products without prices
    (notably ``Cart.add(..., validate_price=True)`` which silently skips
    validation for such products).
    """
    return FakeProductNoPrice.objects.create(name="No Price Product")


@pytest.fixture
def product_factory(db):
    """Callable that creates distinct ``FakeProduct`` instances on demand.

    Usage::

        def test_cart_handles_multiple(cart, product_factory):
            p1 = product_factory(name="Widget", price="5.00")
            p2 = product_factory(name="Gadget", price="12.50")
            cart.add(p1, Decimal("5.00"))
            cart.add(p2, Decimal("12.50"))
            assert cart.unique_count() == 2

    Both arguments are optional; defaults are name='Widget', price='10.00'.
    """

    def _make(name: str = "Widget", price: str = "10.00") -> FakeProduct:
        return FakeProduct.objects.create(name=name, price=Decimal(price))

    return _make


# --------------------------------------------------------------------------- #
# Discounts
# --------------------------------------------------------------------------- #


@pytest.fixture
def discount_percent(db):
    """A percentage discount: code='PERCENT20', 20% off, no restrictions.

    Default choice when a test needs "a working discount" and doesn't care
    about the specific value. For other configurations (min cart value,
    expiry, max uses), build the ``Discount`` inline — do not parameterise
    this fixture.
    """
    return Discount.objects.create(
        code="PERCENT20",
        discount_type=DiscountType.PERCENT,
        value=Decimal("20.00"),
    )


@pytest.fixture
def discount_fixed(db):
    """A fixed-amount discount: code='FIXED10', $10 off, no restrictions.

    Companion to ``discount_percent`` — use when a test must exercise the
    fixed-amount branch of ``Discount.calculate_discount``.
    """
    return Discount.objects.create(
        code="FIXED10",
        discount_type=DiscountType.FIXED,
        value=Decimal("10.00"),
    )
