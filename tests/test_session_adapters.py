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
