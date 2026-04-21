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


def test_carts_session_adapter_class_setting_is_honoured(settings, rf_request):
    """Setting the adapter class should cause Cart to route session ops
    through it, leaving request.session untouched."""
    settings.CARTS_SESSION_ADAPTER_CLASS = (
        "tests.test_cart_init._RecordingSessionAdapter"
    )

    Cart(rf_request)

    assert CART_ID not in rf_request.session


def test_adapter_receives_the_new_cart_id_on_creation(settings, rf_request):
    """The adapter's set_cart_id must be called with the freshly-created
    cart's pk when the session had no prior cart."""
    settings.CARTS_SESSION_ADAPTER_CLASS = (
        "tests.test_cart_init._RecordingSessionAdapter"
    )
    _RecordingSessionAdapter.calls.clear()

    cart = Cart(rf_request)

    assert ("get_or_create_cart_id",) in _RecordingSessionAdapter.calls
    assert ("set_cart_id", cart.cart.pk) in _RecordingSessionAdapter.calls


def test_setting_accepts_a_class_object_not_just_a_dotted_string(settings, rf_request):
    """The README advertises both
    ``CARTS_SESSION_ADAPTER_CLASS = MyAdapter`` and
    ``= "dotted.path.MyAdapter"`` — both must work."""
    settings.CARTS_SESSION_ADAPTER_CLASS = _RecordingSessionAdapter
    _RecordingSessionAdapter.calls.clear()

    Cart(rf_request)

    assert CART_ID not in rf_request.session
    assert ("get_or_create_cart_id",) in _RecordingSessionAdapter.calls


def test_bad_dotted_path_raises_loudly_no_silent_fallback(settings, rf_request):
    """Session storage is too critical to silently fall back to the
    default on a typo — unlike the tax / shipping / inventory
    factories. A bad dotted path must raise."""
    settings.CARTS_SESSION_ADAPTER_CLASS = "nonexistent.module.FakeAdapter"

    with pytest.raises(ImportError):
        Cart(rf_request)
