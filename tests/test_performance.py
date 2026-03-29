"""
Performance tests for django-cart
=================================

Tests for v2.4.0 - verifies performance characteristics of core cart operations.
"""

import time
from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase

from cart.cart import Cart
from tests.test_app.models import FakeProduct


def make_request(session=None):
    """Return a minimal mock request with a dict-based session."""
    request = MagicMock()
    request.session = session if session is not None else {}
    return request


def make_product(name="PerfProduct", price="10.00"):
    """Create and persist a FakeProduct instance."""
    return FakeProduct.objects.create(name=name, price=Decimal(price))


class CartPerformanceTest(TestCase):
    """Performance tests for cart operations."""

    def test_add_single_item_performance(self):
        """Adding 50 items should complete in under 2 seconds."""
        request = make_request()
        cart = Cart(request)

        start = time.perf_counter()
        for i in range(50):
            product = make_product(f"PerfProduct{i}")
            cart.add(product, Decimal("10.00"), quantity=1)
        elapsed = time.perf_counter() - start

        self.assertEqual(cart.count(), 50)
        self.assertLess(elapsed, 2.0, f"Add operations took {elapsed:.2f}s")

    def test_large_cart_summary_performance(self):
        """Summary calculation on large cart should be fast."""
        request = make_request()
        cart = Cart(request)

        for i in range(100):
            product = make_product(f"LargeCart{i}")
            cart.add(product, Decimal("10.00"), quantity=1)

        start = time.perf_counter()
        summary = cart.summary()
        elapsed = time.perf_counter() - start

        self.assertEqual(summary, Decimal("1000.00"))
        self.assertLess(elapsed, 0.1, f"Summary took {elapsed:.3f}s")

    def test_iteration_performance(self):
        """Iterating over cart items should be efficient."""
        request = make_request()
        cart = Cart(request)

        for i in range(50):
            product = make_product(f"IterProduct{i}")
            cart.add(product, Decimal("10.00"), quantity=1)

        start = time.perf_counter()
        items = list(cart)
        elapsed = time.perf_counter() - start

        self.assertEqual(len(items), 50)
        self.assertLess(elapsed, 0.5, f"Iteration took {elapsed:.3f}s")
