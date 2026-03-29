"""
Tests for Django signals in cart operations.
"""

from decimal import Decimal

from django.test import TestCase, RequestFactory

from cart.cart import Cart
from cart.models import Cart as CartModel
from cart.signals import (
    cart_item_added,
    cart_item_removed,
    cart_item_updated,
    cart_checked_out,
    cart_cleared,
)
from tests.test_app.models import FakeProduct


class SignalTestMixin:
    """Mixin providing signal handler setup/teardown."""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.request = self.factory.get("/")
        self.request.session = {}
        self.signal_handlers = {
            "added": [],
            "removed": [],
            "updated": [],
            "checked_out": [],
            "cleared": [],
        }
        self._connect_handlers()

    def _connect_handlers(self):
        cart_item_added.connect(self._handle_added, sender=Cart)
        cart_item_removed.connect(self._handle_removed, sender=Cart)
        cart_item_updated.connect(self._handle_updated, sender=Cart)
        cart_checked_out.connect(self._handle_checked_out, sender=Cart)
        cart_cleared.connect(self._handle_cleared, sender=Cart)

    def _handle_added(self, sender, cart, item, **kwargs):
        self.signal_handlers["added"].append({"cart": cart, "item": item})

    def _handle_removed(self, sender, cart, product, **kwargs):
        self.signal_handlers["removed"].append({"cart": cart, "product": product})

    def _handle_updated(self, sender, cart, item, **kwargs):
        self.signal_handlers["updated"].append({
            "cart": cart,
            "item": item,
            "deleted": kwargs.get("deleted", False)
        })

    def _handle_checked_out(self, sender, cart, **kwargs):
        self.signal_handlers["checked_out"].append({"cart": cart})

    def _handle_cleared(self, sender, cart, **kwargs):
        self.signal_handlers["cleared"].append({"cart": cart})

    def tearDown(self):
        cart_item_added.disconnect(self._handle_added, sender=Cart)
        cart_item_removed.disconnect(self._handle_removed, sender=Cart)
        cart_item_updated.disconnect(self._handle_updated, sender=Cart)
        cart_checked_out.disconnect(self._handle_checked_out, sender=Cart)
        cart_cleared.disconnect(self._handle_cleared, sender=Cart)
        super().tearDown()


class CartItemAddedSignalTest(SignalTestMixin, TestCase):
    """Tests for cart_item_added signal."""

    def test_signal_emitted_on_add(self):
        """Signal should be emitted when adding a product."""
        product = FakeProduct.objects.create(name="Test Product", price=Decimal("9.99"))

        cart = Cart(self.request)
        item = cart.add(product, unit_price=Decimal("9.99"), quantity=2)

        self.assertEqual(len(self.signal_handlers["added"]), 1)
        self.assertEqual(self.signal_handlers["added"][0]["cart"], cart.cart)
        self.assertEqual(self.signal_handlers["added"][0]["item"], item)

    def test_signal_emitted_on_existing_item(self):
        """Signal should be emitted when adding to existing item."""
        product = FakeProduct.objects.create(name="Test Product", price=Decimal("9.99"))

        cart = Cart(self.request)
        cart.add(product, unit_price=Decimal("9.99"), quantity=2)
        cart.add(product, unit_price=Decimal("9.99"), quantity=1)

        self.assertEqual(len(self.signal_handlers["added"]), 2)


class CartItemRemovedSignalTest(SignalTestMixin, TestCase):
    """Tests for cart_item_removed signal."""

    def test_signal_emitted_on_remove(self):
        """Signal should be emitted when removing a product."""
        product = FakeProduct.objects.create(name="Test Product", price=Decimal("9.99"))

        cart = Cart(self.request)
        cart.add(product, unit_price=Decimal("9.99"), quantity=2)
        cart.remove(product)

        self.assertEqual(len(self.signal_handlers["removed"]), 1)
        self.assertEqual(self.signal_handlers["removed"][0]["cart"], cart.cart)
        self.assertEqual(self.signal_handlers["removed"][0]["product"], product)


class CartItemUpdatedSignalTest(SignalTestMixin, TestCase):
    """Tests for cart_item_updated signal."""

    def test_signal_emitted_on_update(self):
        """Signal should be emitted when updating an item."""
        product = FakeProduct.objects.create(name="Test Product", price=Decimal("9.99"))

        cart = Cart(self.request)
        cart.add(product, unit_price=Decimal("9.99"), quantity=2)
        cart.update(product, quantity=5, unit_price=Decimal("11.99"))

        self.assertEqual(len(self.signal_handlers["updated"]), 1)
        self.assertEqual(self.signal_handlers["updated"][0]["cart"], cart.cart)
        self.assertFalse(self.signal_handlers["updated"][0]["deleted"])

    def test_signal_emitted_on_update_to_zero(self):
        """Signal should be emitted when updating quantity to 0."""
        product = FakeProduct.objects.create(name="Test Product", price=Decimal("9.99"))

        cart = Cart(self.request)
        cart.add(product, unit_price=Decimal("9.99"), quantity=2)
        cart.update(product, quantity=0)

        self.assertEqual(len(self.signal_handlers["updated"]), 1)
        self.assertEqual(self.signal_handlers["updated"][0]["cart"], cart.cart)
        self.assertTrue(self.signal_handlers["updated"][0]["deleted"])


class CartCheckedOutSignalTest(SignalTestMixin, TestCase):
    """Tests for cart_checked_out signal."""

    def test_signal_emitted_on_checkout(self):
        """Signal should be emitted when checking out."""
        cart = Cart(self.request)
        cart.checkout()

        self.assertEqual(len(self.signal_handlers["checked_out"]), 1)
        self.assertEqual(self.signal_handlers["checked_out"][0]["cart"], cart.cart)


class CartClearedSignalTest(SignalTestMixin, TestCase):
    """Tests for cart_cleared signal."""

    def test_signal_emitted_on_clear(self):
        """Signal should be emitted when clearing the cart."""
        product = FakeProduct.objects.create(name="Test Product", price=Decimal("9.99"))

        cart = Cart(self.request)
        cart.add(product, unit_price=Decimal("9.99"), quantity=2)
        cart.clear()

        self.assertEqual(len(self.signal_handlers["cleared"]), 1)
        self.assertEqual(self.signal_handlers["cleared"][0]["cart"], cart.cart)
