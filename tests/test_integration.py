"""
Integration tests for django-cart
=================================

Tests HTTP-level interactions using Django's test client.
"""

import time
from decimal import Decimal
from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, RequestFactory

from cart.cart import Cart, CART_ID
from tests.test_app.models import FakeProduct


def make_request(session=None):
    """Return a minimal mock request with a dict-based session."""
    request = MagicMock()
    request.session = session if session is not None else {}
    return request


def make_product(name="IntegrationProduct", price="9.99"):
    """Create and persist a FakeProduct instance."""
    return FakeProduct.objects.create(name=name, price=Decimal(price))


class CartViewIntegrationTest(TestCase):
    """Integration tests using Django request factory."""

    def setUp(self):
        self.factory = RequestFactory()
        self.product = make_product()

    def test_cart_add_via_request(self):
        """Adding item via request should update cart correctly."""
        request = make_request()
        cart = Cart(request)
        cart.add(self.product, Decimal("10.00"), quantity=2)
        self.assertEqual(cart.count(), 2)

    def test_cart_remove_via_request(self):
        """Removing item via request should update cart correctly."""
        request = make_request()
        cart = Cart(request)
        cart.add(self.product, Decimal("10.00"), quantity=1)
        cart.remove(self.product)
        self.assertTrue(cart.is_empty())

    def test_cart_update_via_request(self):
        """Updating item via request should update cart correctly."""
        request = make_request()
        cart = Cart(request)
        cart.add(self.product, Decimal("10.00"), quantity=1)
        cart.update(self.product, quantity=5)
        self.assertEqual(cart.count(), 5)

    def test_multiple_operations_in_sequence(self):
        """Multiple cart operations should work correctly in sequence."""
        request = make_request()
        cart = Cart(request)
        product1 = make_product("Product1")
        product2 = make_product("Product2")

        cart.add(product1, Decimal("10.00"), quantity=1)
        cart.add(product2, Decimal("20.00"), quantity=2)
        self.assertEqual(cart.count(), 3)
        self.assertEqual(cart.summary(), Decimal("50.00"))

        cart.remove(product1)
        self.assertEqual(cart.count(), 2)

        cart.update(product2, quantity=10)
        self.assertEqual(cart.count(), 10)
        self.assertEqual(cart.summary(), Decimal("200.00"))


class CartSessionIntegrationTest(TestCase):
    """Integration tests for session handling."""

    def setUp(self):
        self.product = make_product()

    def test_cart_persists_across_requests(self):
        """Cart should persist in session across multiple requests."""
        session = {}

        request1 = make_request(session=session)
        cart1 = Cart(request1)
        cart1.add(self.product, Decimal("10.00"), quantity=1)

        request2 = make_request(session=session)
        cart2 = Cart(request2)

        self.assertEqual(cart1.cart.pk, cart2.cart.pk)
        self.assertEqual(cart2.count(), 1)

    def test_different_sessions_have_different_carts(self):
        """Different sessions should have different carts."""
        session1 = {}
        session2 = {}

        request1 = make_request(session=session1)
        request2 = make_request(session=session2)

        cart1 = Cart(request1)
        cart2 = Cart(request2)

        self.assertNotEqual(cart1.cart.pk, cart2.cart.pk)

    def test_session_updated_on_cart_creation(self):
        """Session should be updated when new cart is created."""
        request = make_request()
        cart = Cart(request)
        self.assertIn(CART_ID, request.session)
        self.assertEqual(request.session[CART_ID], cart.cart.pk)

    def test_existing_cart_reused_on_request(self):
        """Existing cart should be reused when request has cart ID in session."""
        session = {}
        request1 = make_request(session=session)
        cart1 = Cart(request1)

        request2 = make_request(session=session)
        cart2 = Cart(request2)

        self.assertEqual(cart1.cart, cart2.cart)

    def test_checked_out_cart_not_reused(self):
        """Checked out cart should not be reused."""
        session = {}
        request1 = make_request(session=session)
        cart1 = Cart(request1)
        cart1.checkout()

        request2 = make_request(session=session)
        cart2 = Cart(request2)

        self.assertNotEqual(cart1.cart.pk, cart2.cart.pk)


class CartSerializationIntegrationTest(TestCase):
    """Integration tests for cart serialization."""

    def test_cart_serializable_full_flow(self):
        """Test full serialization and data integrity."""
        request = make_request()
        cart = Cart(request)
        product1 = make_product("Serial1")
        product2 = make_product("Serial2")

        cart.add(product1, Decimal("15.00"), quantity=2)
        cart.add(product2, Decimal("25.00"), quantity=3)

        data = cart.cart_serializable()

        self.assertEqual(len(data), 2)
        self.assertIn(str(product1.pk), data)
        self.assertIn(str(product2.pk), data)
        self.assertEqual(data[str(product1.pk)]["quantity"], 2)
        self.assertEqual(data[str(product1.pk)]["unit_price"], "15.00")
        self.assertEqual(data[str(product1.pk)]["total_price"], "30.00")

    def test_cart_serializable_empty_cart(self):
        """Empty cart should serialize to empty dict."""
        request = make_request()
        cart = Cart(request)
        self.assertEqual(cart.cart_serializable(), {})

    def test_cart_serializable_with_unicode(self):
        """Serialization should handle unicode product names."""
        request = make_request()
        cart = Cart(request)
        product = make_product("Produkt mit Ümläuten")
        cart.add(product, Decimal("10.00"), quantity=2)
        data = cart.cart_serializable()
        self.assertIn(str(product.pk), data)


class V240EdgeCaseTest(TestCase):
    """Edge case tests for v2.4.0 features."""

    def test_performance_with_decimal_precision(self):
        """Performance should not degrade with decimal precision."""
        request = make_request()
        cart = Cart(request)
        product = make_product("Precision")

        cart.add(product, Decimal("0.01"), quantity=1)
        cart.add(product, Decimal("0.02"), quantity=1)

        start = time.perf_counter()
        summary = cart.summary()
        elapsed = time.perf_counter() - start

        self.assertEqual(summary, Decimal("0.04"))
        self.assertLess(elapsed, 0.05)

    def test_integration_with_custom_session_backend(self):
        """Cart should work with custom session backends."""
        request = make_request()
        cart = Cart(request)
        product = make_product("SessionTest")

        cart.add(product, Decimal("10.00"), quantity=1)

        session_key = request.session.get(CART_ID)
        self.assertIsNotNone(session_key)

        request2 = make_request(session=request.session)
        cart2 = Cart(request2)

        self.assertEqual(cart.cart.pk, cart2.cart.pk)
