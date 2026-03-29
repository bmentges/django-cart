"""
Tests for template tags.
"""

from decimal import Decimal

from django.test import TestCase, RequestFactory
from django.template import Context

from cart.cart import Cart
from cart.templatetags.cart_tags import (
    cart_item_count,
    cart_summary,
    cart_is_empty,
    cart_link,
)
from tests.test_app.models import FakeProduct


class TemplateTagTestMixin:
    """Mixin providing common setup for template tag tests."""

    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get("/")
        self.request.session = {}

    def make_context(self, **extra):
        """Create a template context with request."""
        context = {"request": self.request}
        context.update(extra)
        return Context(context)


class CartItemCountTagTest(TemplateTagTestMixin, TestCase):
    """Tests for cart_item_count template tag."""

    def test_returns_zero_for_empty_cart(self):
        """Returns 0 for empty cart."""
        context = self.make_context()
        result = cart_item_count(context)
        self.assertEqual(result, 0)

    def test_returns_correct_count(self):
        """Returns correct item count."""
        product = FakeProduct.objects.create(name="Test Product", price=Decimal("9.99"))

        cart = Cart(self.request)
        cart.add(product, unit_price=Decimal("9.99"), quantity=3)

        context = self.make_context()
        result = cart_item_count(context)
        self.assertEqual(result, 3)

    def test_returns_zero_without_request(self):
        """Returns 0 when request not in context."""
        context = Context({})
        result = cart_item_count(context)
        self.assertEqual(result, 0)


class CartSummaryTagTest(TemplateTagTestMixin, TestCase):
    """Tests for cart_summary template tag."""

    def test_returns_zero_for_empty_cart(self):
        """Returns $0.00 for empty cart."""
        context = self.make_context()
        result = cart_summary(context)
        self.assertEqual(result, "$0.00")

    def test_returns_formatted_total(self):
        """Returns formatted cart total."""
        product = FakeProduct.objects.create(name="Test Product", price=Decimal("9.99"))

        cart = Cart(self.request)
        cart.add(product, unit_price=Decimal("9.99"), quantity=2)

        context = self.make_context()
        result = cart_summary(context)
        self.assertEqual(result, "$19.98")

    def test_returns_zero_without_request(self):
        """Returns $0.00 when request not in context."""
        context = Context({})
        result = cart_summary(context)
        self.assertEqual(result, "$0.00")


class CartIsEmptyTagTest(TemplateTagTestMixin, TestCase):
    """Tests for cart_is_empty template tag."""

    def test_returns_true_for_empty_cart(self):
        """Returns True for empty cart."""
        context = self.make_context()
        result = cart_is_empty(context)
        self.assertTrue(result)

    def test_returns_false_for_nonempty_cart(self):
        """Returns False for non-empty cart."""
        product = FakeProduct.objects.create(name="Test Product", price=Decimal("9.99"))

        cart = Cart(self.request)
        cart.add(product, unit_price=Decimal("9.99"), quantity=1)

        context = self.make_context()
        result = cart_is_empty(context)
        self.assertFalse(result)

    def test_returns_true_without_request(self):
        """Returns True when request not in context."""
        context = Context({})
        result = cart_is_empty(context)
        self.assertTrue(result)


class CartLinkTagTest(TemplateTagTestMixin, TestCase):
    """Tests for cart_link template tag."""

    def test_returns_basic_link(self):
        """Returns basic link without class."""
        context = self.make_context()
        result = cart_link(context)
        self.assertIn('<a href="/cart/', result)
        self.assertIn(">View Cart</a>", result)

    def test_returns_link_with_custom_text(self):
        """Returns link with custom text."""
        context = self.make_context()
        result = cart_link(context, text="Go to Cart")
        self.assertIn(">Go to Cart</a>", result)

    def test_returns_link_with_css_class(self):
        """Returns link with CSS class."""
        context = self.make_context()
        result = cart_link(context, text="Cart", css_class="btn btn-primary")
        self.assertIn('class="btn btn-primary"', result)

    def test_returns_link_without_request(self):
        """Returns link to /cart/ when no request."""
        context = Context({})
        result = cart_link(context)
        self.assertIn('<a href="/cart/">View Cart</a>', result)
