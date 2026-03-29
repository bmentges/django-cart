"""
Tests for session adapter classes.
"""

from unittest.mock import Mock, MagicMock

from django.test import TestCase

from cart.session import (
    CartSessionAdapter,
    DjangoSessionAdapter,
    CookieSessionAdapter,
)


class CartSessionAdapterTest(TestCase):
    """Tests for abstract base class."""

    def test_cannot_instantiate_directly(self):
        """CartSessionAdapter cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            CartSessionAdapter()


class DjangoSessionAdapterTest(TestCase):
    """Tests for DjangoSessionAdapter."""

    def setUp(self):
        self.mock_request = Mock()
        self.mock_request.session = {}
        self.adapter = DjangoSessionAdapter(self.mock_request)

    def test_get_returns_default(self):
        """get returns default when key doesn't exist."""
        result = self.adapter.get("nonexistent", "default")
        self.assertEqual(result, "default")

    def test_get_returns_value(self):
        """get returns stored value."""
        self.mock_request.session["key"] = "value"
        result = self.adapter.get("key")
        self.assertEqual(result, "value")

    def test_set_stores_value(self):
        """set stores value in session."""
        self.adapter.set("key", "value")
        self.assertEqual(self.mock_request.session["key"], "value")

    def test_delete_removes_value(self):
        """delete removes value from session."""
        self.mock_request.session["key"] = "value"
        self.adapter.delete("key")
        self.assertNotIn("key", self.mock_request.session)

    def test_get_or_create_cart_id_returns_none_when_not_set(self):
        """Returns None when CART-ID not in session."""
        result = self.adapter.get_or_create_cart_id()
        self.assertIsNone(result)

    def test_get_or_create_cart_id_returns_value(self):
        """Returns cart ID when set."""
        self.adapter.set_cart_id(42)
        result = self.adapter.get_or_create_cart_id()
        self.assertEqual(result, 42)


class CookieSessionAdapterTest(TestCase):
    """Tests for CookieSessionAdapter."""

    def setUp(self):
        self.mock_response = Mock()
        self.mock_response.set_cookie = Mock()
        self.mock_response.delete_cookie = Mock()
        self.adapter = CookieSessionAdapter(response=self.mock_response)

    def test_get_returns_default(self):
        """get returns default when key doesn't exist."""
        result = self.adapter.get("nonexistent", "default")
        self.assertEqual(result, "default")

    def test_get_returns_value(self):
        """get returns stored value."""
        self.adapter._cookies["key"] = "value"
        result = self.adapter.get("key")
        self.assertEqual(result, "value")

    def test_set_stores_value(self):
        """set stores value in cookies and sets cookie."""
        self.adapter.set("key", "value")
        self.assertEqual(self.adapter._cookies["key"], "value")
        self.mock_response.set_cookie.assert_called_with("key", "value")

    def test_delete_removes_value(self):
        """delete removes value and clears cookie."""
        self.adapter._cookies["key"] = "value"
        self.adapter.delete("key")
        self.assertNotIn("key", self.adapter._cookies)
        self.mock_response.delete_cookie.assert_called_with("key")

    def test_get_or_create_cart_id_returns_none_when_not_set(self):
        """Returns None when CART-ID not in cookies."""
        result = self.adapter.get_or_create_cart_id()
        self.assertIsNone(result)

    def test_get_or_create_cart_id_returns_int(self):
        """Returns cart ID as int when set."""
        self.adapter._cookies["CART-ID"] = "42"
        result = self.adapter.get_or_create_cart_id()
        self.assertEqual(result, 42)

    def test_get_or_create_cart_id_handles_invalid_value(self):
        """Handles invalid cart ID value gracefully."""
        self.adapter._cookies["CART-ID"] = "not-a-number"
        result = self.adapter.get_or_create_cart_id()
        self.assertIsNone(result)
