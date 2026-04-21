"""Cart class initialisation and session wiring."""
from __future__ import annotations

import pytest
from django.test import RequestFactory

from cart.cart import CART_ID, Cart
from cart.session import CartSessionAdapter


pytestmark = pytest.mark.django_db


class _RecordingSessionAdapter(CartSessionAdapter):
    """Module-level test double referenced by dotted path in the
    ``CARTS_SESSION_ADAPTER_CLASS`` setting for the P0-3 regression test.

    Implemented via class-level state so the test can assert "the adapter
    saw at least one call" without the adapter instance escaping the
    Cart constructor.
    """

    calls: list = []

    def __init__(self, request):
        self._request = request

    def get(self, key, default=None):
        self.calls.append(("get", key))
        return default

    def set(self, key, value):
        self.calls.append(("set", key, value))

    def delete(self, key):
        self.calls.append(("delete", key))

    def get_or_create_cart_id(self):
        self.calls.append(("get_or_create_cart_id",))
        return None

    def set_cart_id(self, cart_id):
        self.calls.append(("set_cart_id", cart_id))


def test_new_cart_is_created_when_session_has_no_cart_id(rf_request):
    cart = Cart(rf_request)

    assert cart.cart.pk is not None
    assert rf_request.session[CART_ID] == cart.cart.pk


def test_cart_is_reused_across_two_cart_instances_on_same_session(rf_request):
    cart1 = Cart(rf_request)
    cart2 = Cart(rf_request)

    assert cart1.cart.pk == cart2.cart.pk


def test_new_cart_is_created_when_session_points_to_nonexistent_id():
    request = RequestFactory().get("/")
    request.session = {CART_ID: 99999}

    cart = Cart(request)

    assert cart.cart.pk != 99999


def test_new_cart_is_created_when_existing_cart_is_checked_out(rf_request):
    first = Cart(rf_request)
    first.cart.checked_out = True
    first.cart.save()

    second = Cart(rf_request)

    assert second.cart.pk != first.cart.pk


def test_session_id_is_written_back_on_cart_creation(rf_request):
    cart = Cart(rf_request)

    assert CART_ID in rf_request.session
    assert rf_request.session[CART_ID] == cart.cart.pk


def test_shared_session_yields_same_cart_across_requests():
    session = {}
    r1 = RequestFactory().get("/")
    r1.session = session
    r2 = RequestFactory().get("/")
    r2.session = session

    c1 = Cart(r1)
    c2 = Cart(r2)

    assert c1.cart.pk == c2.cart.pk


# --------------------------------------------------------------------------- #
# P0 regression — @xfail until the fix lands
# --------------------------------------------------------------------------- #

@pytest.mark.xfail(
    strict=True,
    reason=(
        "P0-3 — CARTS_SESSION_ADAPTER_CLASS setting is documented in the "
        "README but never read by Cart.__init__. The constructor hardcodes "
        "request.session access. Scheduled for v3.0.13 (see "
        "docs/ROADMAP_2026_04.md §P0-3)."
    ),
)
def test_carts_session_adapter_class_setting_is_honoured(settings, rf_request):
    """Setting the adapter class should cause Cart to route session ops
    through it, leaving request.session untouched."""
    settings.CARTS_SESSION_ADAPTER_CLASS = (
        "tests.test_cart_init._RecordingSessionAdapter"
    )

    Cart(rf_request)

    # Target behaviour: the adapter is used, so request.session stays clean.
    # Current behaviour: Cart ignores the setting and writes CART-ID
    # directly into request.session → assertion fails → xfail expected.
    assert CART_ID not in rf_request.session
