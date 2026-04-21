"""Session adapter behaviour: DjangoSessionAdapter and CookieSessionAdapter.

These adapters wrap how a cart id is stored on the request side. They are
tested in isolation from the Cart class — P0-3 and P0-4 (see
docs/ROADMAP_2026_04.md) will wire them into Cart and add an end-to-end
cookie round-trip test against a real HTTP flow.

This file is the reference implementation for the pytest-first test
pattern described in tests/README.md. Future phases migrate other files
against the conventions demonstrated here.
"""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from cart.session import CookieSessionAdapter, DjangoSessionAdapter


# --------------------------------------------------------------------------- #
# DjangoSessionAdapter
# --------------------------------------------------------------------------- #

@pytest.fixture
def django_adapter():
    """A ``DjangoSessionAdapter`` wrapping an in-memory dict session.

    Exposes ``.request.session`` so state-inspection assertions can reach
    the backing store directly.
    """
    request = Mock()
    request.session = {}
    adapter = DjangoSessionAdapter(request)
    adapter.request = request
    return adapter


def test_django_get_returns_default_when_key_missing(django_adapter):
    assert django_adapter.get("nonexistent", "default") == "default"


def test_django_get_returns_stored_value(django_adapter):
    django_adapter.request.session["key"] = "value"

    assert django_adapter.get("key") == "value"


def test_django_set_stores_value_in_session(django_adapter):
    django_adapter.set("key", "value")

    assert django_adapter.request.session["key"] == "value"


def test_django_delete_removes_value_from_session(django_adapter):
    django_adapter.request.session["key"] = "value"

    django_adapter.delete("key")

    assert "key" not in django_adapter.request.session


def test_django_get_or_create_cart_id_returns_none_when_unset(django_adapter):
    assert django_adapter.get_or_create_cart_id() is None


def test_django_get_or_create_cart_id_returns_stored_id(django_adapter):
    django_adapter.set_cart_id(42)

    assert django_adapter.get_or_create_cart_id() == 42


# --------------------------------------------------------------------------- #
# CookieSessionAdapter
# --------------------------------------------------------------------------- #

@pytest.fixture
def cookie_adapter():
    """A ``CookieSessionAdapter`` paired with a mock response.

    Exposes ``.cookies`` (the internal ``_cookies`` dict) for state
    inspection and ``.response`` for asserting ``set_cookie`` /
    ``delete_cookie`` side effects.
    """
    response = Mock()
    adapter = CookieSessionAdapter(response=response)
    adapter.cookies = adapter._cookies
    adapter.response = response
    return adapter


def test_cookie_get_returns_default_when_key_missing(cookie_adapter):
    assert cookie_adapter.get("nonexistent", "default") == "default"


def test_cookie_get_returns_stored_value(cookie_adapter):
    cookie_adapter.cookies["key"] = "value"

    assert cookie_adapter.get("key") == "value"


def test_cookie_set_stores_value_in_cookies_dict(cookie_adapter):
    cookie_adapter.set("key", "value")

    assert cookie_adapter.cookies["key"] == "value"


def test_cookie_set_calls_response_set_cookie(cookie_adapter):
    cookie_adapter.set("key", "value")

    cookie_adapter.response.set_cookie.assert_called_once_with("key", "value")


def test_cookie_delete_removes_value_from_cookies_dict(cookie_adapter):
    cookie_adapter.cookies["key"] = "value"

    cookie_adapter.delete("key")

    assert "key" not in cookie_adapter.cookies


def test_cookie_delete_calls_response_delete_cookie(cookie_adapter):
    cookie_adapter.cookies["key"] = "value"

    cookie_adapter.delete("key")

    cookie_adapter.response.delete_cookie.assert_called_once_with("key")


def test_cookie_get_or_create_cart_id_returns_none_when_unset(cookie_adapter):
    assert cookie_adapter.get_or_create_cart_id() is None


def test_cookie_get_or_create_cart_id_parses_string_to_int(cookie_adapter):
    cookie_adapter.cookies["CART-ID"] = "42"

    assert cookie_adapter.get_or_create_cart_id() == 42


@pytest.mark.parametrize(
    "bad_value",
    ["not-a-number", "3.14", "abc123", "-", " "],
    ids=["letters", "float-literal", "alphanumeric", "dash-only", "space-only"],
)
def test_cookie_get_or_create_cart_id_returns_none_for_non_integer(
    cookie_adapter, bad_value
):
    cookie_adapter.cookies["CART-ID"] = bad_value

    assert cookie_adapter.get_or_create_cart_id() is None


def test_cookie_set_cart_id_serialises_int_as_string(cookie_adapter):
    """set_cart_id coerces to str so the cookie value is HTTP-transport-safe.
    Covers cart/session.py lines 107-108 — previously dead since no test
    called set_cart_id on the cookie adapter."""
    cookie_adapter.set_cart_id(42)

    assert cookie_adapter.cookies["CART-ID"] == "42"
    cookie_adapter.response.set_cookie.assert_called_once_with("CART-ID", "42")


def test_cookie_adapter_without_response_stores_in_memory_only():
    """Without a response, set/delete still mutate the in-memory dict but
    skip the response.set_cookie / response.delete_cookie side effects.
    Covers the ``if self._response is not None`` branches."""
    adapter = CookieSessionAdapter()

    adapter.set("key", "value")
    assert adapter._cookies["key"] == "value"

    adapter.delete("key")
    assert "key" not in adapter._cookies


def test_cookie_adapter_delete_on_missing_key_is_noop():
    """Covers the ``if key in self._cookies`` branch of delete()."""
    adapter = CookieSessionAdapter()

    adapter.delete("never-set")  # must not raise

    assert "never-set" not in adapter._cookies


# --------------------------------------------------------------------------- #
# P0 regression — @xfail until the fix lands
# --------------------------------------------------------------------------- #

@pytest.mark.xfail(
    strict=True,
    reason=(
        "P0-4 — CookieSessionAdapter.__init__ never populates self._cookies "
        "from request.COOKIES, so a cart id set on one request is not "
        "recoverable on the next. The in-memory round-trip works (previous "
        "tests); the HTTP round-trip does not. Scheduled for v3.0.14 "
        "(see docs/ROADMAP_2026_04.md §P0-4)."
    ),
)
def test_cookie_session_adapter_round_trips_via_real_request_cookies():
    """Two sequential requests sharing a cookie jar should see the same
    cart id — the canonical cookie-session-adapter contract."""
    from django.http import HttpResponse
    from django.test import RequestFactory

    # Request 1: adapter writes cart id to the response's Set-Cookie.
    response = HttpResponse()
    writer = CookieSessionAdapter(response=response)
    writer.set_cart_id(42)

    cart_id_cookie = response.cookies["CART-ID"].value

    # Request 2: browser echoes the cookie back; Django populates
    # request.COOKIES from it. The adapter must hydrate from that.
    request = RequestFactory().get("/", COOKIES={"CART-ID": cart_id_cookie})
    reader = CookieSessionAdapter(request=request)

    assert reader.get_or_create_cart_id() == 42
