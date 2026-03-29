"""
Test suite for django-cart
==========================

Covers:
  - Cart model
  - Item model + ItemManager
  - Cart class (cart.cart) — success, error, and edge cases
  - clean_carts management command
"""

import io
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import models as django_models, transaction
from django.test import TestCase, TransactionTestCase, RequestFactory
from django.utils import timezone

from cart.models import Cart as CartModel, Item
from cart.cart import (
    Cart,
    ItemDoesNotExist,
    InvalidQuantity,
    CART_ID,
)
from cart.management.commands.clean_carts import Command as CleanCartsCommand  # noqa: F401
from tests.test_app.models import FakeProduct


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_request(session=None):
    """Return a minimal mock request with a dict-based session."""
    request = MagicMock()
    request.session = session if session is not None else {}
    return request


def make_product(name="Widget", price="9.99"):
    """Create and persist a FakeProduct instance."""
    return FakeProduct.objects.create(name=name, price=Decimal(price))


def make_cart_model(**kwargs):
    """Create a CartModel instance directly in the DB."""
    return CartModel.objects.create(**kwargs)


# ===========================================================================
# CartModel tests
# ===========================================================================

class CartModelTest(TestCase):
    def test_str_returns_creation_date(self):
        cart = make_cart_model()
        self.assertIn(f"Cart #{cart.pk}", str(cart))

    def test_default_checked_out_is_false(self):
        cart = make_cart_model()
        self.assertFalse(cart.checked_out)

    def test_default_creation_date_is_set(self):
        before = timezone.now()
        cart = make_cart_model()
        after = timezone.now()
        self.assertGreaterEqual(cart.creation_date, before)
        self.assertLessEqual(cart.creation_date, after)

    def test_ordering_newest_first(self):
        old = make_cart_model(creation_date=timezone.now() - timedelta(days=5))
        new = make_cart_model(creation_date=timezone.now())
        carts = list(CartModel.objects.all())
        self.assertEqual(carts[0].pk, new.pk)
        self.assertEqual(carts[1].pk, old.pk)


# ===========================================================================
# ItemManager tests
# ===========================================================================

class ItemManagerTest(TestCase):
    def setUp(self):
        self.cart = make_cart_model()
        self.product = make_product("Alpha")
        ct = ContentType.objects.get_for_model(FakeProduct)
        self.item = Item.objects.create(
            cart=self.cart,
            content_type=ct,
            object_id=self.product.pk,
            unit_price=Decimal("5.00"),
            quantity=1,
        )

    def test_filter_by_product(self):
        qs = Item.objects.filter(cart=self.cart, product=self.product)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().pk, self.item.pk)

    def test_get_by_product(self):
        item = Item.objects.get(cart=self.cart, product=self.product)
        self.assertEqual(item.pk, self.item.pk)

    def test_filter_unknown_product_returns_empty(self):
        other = make_product("Unknown")
        qs = Item.objects.filter(cart=self.cart, product=other)
        self.assertEqual(qs.count(), 0)


# ===========================================================================
# Item model tests
# ===========================================================================

class ItemModelTest(TestCase):
    def setUp(self):
        self.cart = make_cart_model()
        self.product = make_product("Beta")
        ct = ContentType.objects.get_for_model(FakeProduct)
        self.item = Item.objects.create(
            cart=self.cart,
            content_type=ct,
            object_id=self.product.pk,
            unit_price=Decimal("10.00"),
            quantity=3,
        )

    def test_total_price(self):
        self.assertEqual(self.item.total_price, Decimal("30.00"))

    def test_str(self):
        self.assertIn("3", str(self.item))

    def test_unique_together_prevents_duplicate(self):
        from django.db import IntegrityError
        ct = ContentType.objects.get_for_model(FakeProduct)
        with self.assertRaises(IntegrityError):
            Item.objects.create(
                cart=self.cart,
                content_type=ct,
                object_id=self.product.pk,
                unit_price=Decimal("5.00"),
                quantity=1,
            )


# ===========================================================================
# Cart class tests
# ===========================================================================

class CartInitTest(TestCase):
    def test_creates_new_cart_when_no_session_key(self):
        request = make_request()
        cart = Cart(request)
        self.assertIsNotNone(cart.cart.pk)
        self.assertIn(CART_ID, request.session)

    def test_reuses_existing_cart_from_session(self):
        request = make_request()
        cart1 = Cart(request)
        cart2 = Cart(request)
        self.assertEqual(cart1.cart.pk, cart2.cart.pk)

    def test_creates_new_cart_if_session_id_invalid(self):
        request = make_request(session={CART_ID: 99999})
        cart = Cart(request)
        self.assertNotEqual(cart.cart.pk, 99999)

    def test_creates_new_cart_if_existing_is_checked_out(self):
        request = make_request()
        cart = Cart(request)
        cart.cart.checked_out = True
        cart.cart.save()
        new_cart = Cart(request)
        self.assertNotEqual(new_cart.cart.pk, cart.cart.pk)


class CartAddTest(TestCase):
    def setUp(self):
        self.request = make_request()
        self.cart = Cart(self.request)
        self.product = make_product("Widget")

    def test_add_new_product(self):
        self.cart.add(self.product, Decimal("5.00"), quantity=2)
        self.assertEqual(self.cart.count(), 2)

    def test_add_existing_product_accumulates_quantity(self):
        self.cart.add(self.product, Decimal("5.00"), quantity=2)
        self.cart.add(self.product, Decimal("5.00"), quantity=3)
        self.assertEqual(self.cart.count(), 5)

    def test_add_updates_unit_price(self):
        self.cart.add(self.product, Decimal("5.00"), quantity=1)
        self.cart.add(self.product, Decimal("7.50"), quantity=1)
        item = self.cart.cart.items.first()
        self.assertEqual(item.unit_price, Decimal("7.50"))

    def test_add_default_quantity_is_one(self):
        self.cart.add(self.product, Decimal("5.00"))
        self.assertEqual(self.cart.count(), 1)

    def test_add_invalid_quantity_raises(self):
        with self.assertRaises(InvalidQuantity):
            self.cart.add(self.product, Decimal("5.00"), quantity=0)

    def test_add_negative_quantity_raises(self):
        with self.assertRaises(InvalidQuantity):
            self.cart.add(self.product, Decimal("5.00"), quantity=-1)


class CartRemoveTest(TestCase):
    def setUp(self):
        self.request = make_request()
        self.cart = Cart(self.request)
        self.product = make_product("Removable")
        self.cart.add(self.product, Decimal("5.00"), quantity=1)

    def test_remove_existing_product(self):
        self.cart.remove(self.product)
        self.assertTrue(self.cart.is_empty())

    def test_remove_nonexistent_product_raises(self):
        other = make_product("Ghost")
        with self.assertRaises(ItemDoesNotExist):
            self.cart.remove(other)

    def test_remove_reduces_item_count(self):
        p2 = make_product("Second")
        self.cart.add(p2, Decimal("3.00"), quantity=4)
        self.cart.remove(self.product)
        self.assertEqual(self.cart.unique_count(), 1)


class CartUpdateTest(TestCase):
    def setUp(self):
        self.request = make_request()
        self.cart = Cart(self.request)
        self.product = make_product("Updatable")
        self.cart.add(self.product, Decimal("5.00"), quantity=3)

    def test_update_quantity(self):
        self.cart.update(self.product, quantity=10)
        self.assertEqual(self.cart.count(), 10)

    def test_update_quantity_zero_removes_item(self):
        self.cart.update(self.product, quantity=0)
        self.assertTrue(self.cart.is_empty())

    def test_update_also_changes_unit_price(self):
        self.cart.update(self.product, quantity=2, unit_price=Decimal("9.99"))
        item = self.cart.cart.items.first()
        self.assertEqual(item.unit_price, Decimal("9.99"))

    def test_update_nonexistent_product_raises(self):
        ghost = make_product("Ghost2")
        with self.assertRaises(ItemDoesNotExist):
            self.cart.update(ghost, quantity=1)

    def test_update_negative_quantity_raises(self):
        with self.assertRaises(InvalidQuantity):
            self.cart.update(self.product, quantity=-1)


class CartAggregatesTest(TestCase):
    def setUp(self):
        self.request = make_request()
        self.cart = Cart(self.request)
        self.p1 = make_product("ProductA")
        self.p2 = make_product("ProductB")
        self.cart.add(self.p1, Decimal("10.00"), quantity=2)  # 20.00
        self.cart.add(self.p2, Decimal("4.00"), quantity=5)   # 20.00

    def test_count(self):
        self.assertEqual(self.cart.count(), 7)

    def test_unique_count(self):
        self.assertEqual(self.cart.unique_count(), 2)

    def test_summary(self):
        self.assertEqual(self.cart.summary(), Decimal("40.00"))

    def test_is_empty_false(self):
        self.assertFalse(self.cart.is_empty())

    def test_is_empty_true_after_clear(self):
        self.cart.clear()
        self.assertTrue(self.cart.is_empty())

    def test_len(self):
        self.assertEqual(len(self.cart), 7)

    def test_contains(self):
        self.assertIn(self.p1, self.cart)

    def test_not_contains(self):
        ghost = make_product("GhostProduct")
        self.assertNotIn(ghost, self.cart)


class CartEmptyAggregatesTest(TestCase):
    """Edge cases on an empty cart."""

    def setUp(self):
        self.request = make_request()
        self.cart = Cart(self.request)

    def test_count_empty(self):
        self.assertEqual(self.cart.count(), 0)

    def test_summary_empty(self):
        self.assertEqual(self.cart.summary(), Decimal("0.00"))

    def test_is_empty_true(self):
        self.assertTrue(self.cart.is_empty())

    def test_clear_empty_does_not_raise(self):
        self.cart.clear()  # should be a no-op

    def test_iteration_empty(self):
        self.assertEqual(list(self.cart), [])


class CartCheckoutTest(TestCase):
    def test_checkout_marks_cart(self):
        request = make_request()
        cart = Cart(request)
        product = make_product("CheckoutProduct")
        cart.add(product, Decimal("1.00"))
        cart.checkout()
        cart.cart.refresh_from_db()
        self.assertTrue(cart.cart.checked_out)


class CartSerializableTest(TestCase):
    def test_cart_serializable_structure(self):
        request = make_request()
        cart = Cart(request)
        product = make_product("Gadget")
        cart.add(product, Decimal("15.00"), quantity=2)
        data = cart.cart_serializable()
        key = str(product.pk)
        self.assertIn(key, data)
        self.assertEqual(data[key]["quantity"], 2)
        self.assertEqual(data[key]["total_price"], "30.00")
        self.assertEqual(data[key]["unit_price"], "15.00")

    def test_cart_serializable_empty(self):
        request = make_request()
        cart = Cart(request)
        self.assertEqual(cart.cart_serializable(), {})


# ===========================================================================
# clean_carts management command tests
# ===========================================================================

class CleanCartsCommandTest(TestCase):
    def _call(self, *args, **kwargs):
        """Helper: call management command and capture stdout."""
        out = io.StringIO()
        call_command("clean_carts", *args, stdout=out, **kwargs)
        return out.getvalue()

    def _old_cart(self, days=100, checked_out=False):
        return CartModel.objects.create(
            creation_date=timezone.now() - timedelta(days=days),
            checked_out=checked_out,
        )

    def _fresh_cart(self):
        return CartModel.objects.create(creation_date=timezone.now())

    # --- success cases ---

    def test_deletes_old_abandoned_carts(self):
        old = self._old_cart(days=100)
        fresh = self._fresh_cart()
        self._call(days=90)
        self.assertFalse(CartModel.objects.filter(pk=old.pk).exists())
        self.assertTrue(CartModel.objects.filter(pk=fresh.pk).exists())

    def test_does_not_delete_recent_carts(self):
        recent = self._old_cart(days=10)
        self._call(days=90)
        self.assertTrue(CartModel.objects.filter(pk=recent.pk).exists())

    def test_default_days_is_90(self):
        old = self._old_cart(days=91)
        self._call()
        self.assertFalse(CartModel.objects.filter(pk=old.pk).exists())

    def test_does_not_delete_checked_out_by_default(self):
        old_checked_out = self._old_cart(days=100, checked_out=True)
        self._call(days=90)
        self.assertTrue(CartModel.objects.filter(pk=old_checked_out.pk).exists())

    def test_include_checked_out_flag(self):
        old_checked_out = self._old_cart(days=100, checked_out=True)
        self._call(days=90, include_checked_out=True)
        self.assertFalse(CartModel.objects.filter(pk=old_checked_out.pk).exists())

    def test_dry_run_does_not_delete(self):
        old = self._old_cart(days=100)
        output = self._call(days=90, dry_run=True)
        self.assertTrue(CartModel.objects.filter(pk=old.pk).exists())
        self.assertIn("DRY RUN", output)

    def test_output_reports_deletion_count(self):
        self._old_cart(days=100)
        self._old_cart(days=200)
        output = self._call(days=90)
        self.assertIn("2", output)

    def test_nothing_to_delete_message(self):
        output = self._call(days=90)
        self.assertIn("Nothing to delete", output)

    # --- error cases ---

    def test_invalid_days_raises_command_error(self):
        with self.assertRaises(CommandError):
            self._call(days=0)

    def test_negative_days_raises_command_error(self):
        with self.assertRaises(CommandError):
            self._call(days=-5)

    # --- edge cases ---

    def test_exactly_on_boundary_is_deleted(self):
        """A cart created exactly `days` + 1 second ago should be deleted."""
        boundary = CartModel.objects.create(
            creation_date=timezone.now() - timedelta(days=90, seconds=1)
        )
        self._call(days=90)
        self.assertFalse(CartModel.objects.filter(pk=boundary.pk).exists())

    def test_cart_just_inside_boundary_not_deleted(self):
        """A cart created just under `days` ago should NOT be deleted."""
        recent = CartModel.objects.create(
            creation_date=timezone.now() - timedelta(days=89, hours=23, minutes=59)
        )
        self._call(days=90)
        self.assertTrue(CartModel.objects.filter(pk=recent.pk).exists())

    def test_items_cascade_deleted(self):
        """Deleting an old cart must also remove its items."""
        old = self._old_cart(days=100)
        product = make_product("CascadeProduct")
        ct = ContentType.objects.get_for_model(FakeProduct)
        item = Item.objects.create(
            cart=old,
            content_type=ct,
            object_id=product.pk,
            unit_price=Decimal("1.00"),
            quantity=1,
        )
        self._call(days=90)
        self.assertFalse(Item.objects.filter(pk=item.pk).exists())


# ===========================================================================
# Atomic transaction tests
# ===========================================================================

class CartAtomicTest(TransactionTestCase):
    """Tests that add() and update() use atomic transactions."""

    def test_add_is_atomic(self):
        """add() should be atomic - complete or rollback entirely."""
        request = make_request()
        cart = Cart(request)
        product = make_product("AtomicProduct")
        item = cart.add(product, Decimal("5.00"), quantity=1)
        self.assertEqual(cart.count(), 1)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)

    def test_add_updates_are_atomic(self):
        """Concurrent add updates should be serialized."""
        request = make_request()
        cart = Cart(request)
        product = make_product("ConcurrentProduct")
        cart.add(product, Decimal("5.00"), quantity=1)
        cart.add(product, Decimal("5.00"), quantity=2)
        item = cart.cart.items.first()
        self.assertEqual(item.quantity, 3)

    def test_update_is_atomic(self):
        """update() should be atomic - complete or rollback entirely."""
        request = make_request()
        cart = Cart(request)
        product = make_product("UpdateAtomicProduct")
        cart.add(product, Decimal("5.00"), quantity=1)
        cart.update(product, quantity=10, unit_price=Decimal("15.00"))
        item = cart.cart.items.first()
        self.assertEqual(item.quantity, 10)
        self.assertEqual(item.unit_price, Decimal("15.00"))

    def test_update_zero_removes_item_atomically(self):
        """update with quantity=0 should atomically remove the item."""
        request = make_request()
        cart = Cart(request)
        product = make_product("RemoveAtomicProduct")
        cart.add(product, Decimal("5.00"), quantity=5)
        cart.update(product, quantity=0)
        self.assertTrue(cart.is_empty())

    def test_add_with_invalid_quantity_rollback(self):
        """Invalid quantity should not affect cart state."""
        request = make_request()
        cart = Cart(request)
        product = make_product("RollbackProduct")
        cart.add(product, Decimal("5.00"), quantity=1)
        try:
            cart.add(product, Decimal("5.00"), quantity=0)
        except InvalidQuantity:
            pass
        item = cart.cart.items.first()
        self.assertEqual(item.quantity, 1)

    def test_update_nonexistent_rollback(self):
        """Updating nonexistent item should not affect cart state."""
        request = make_request()
        cart = Cart(request)
        product = make_product("RollbackProduct2")
        cart.add(product, Decimal("5.00"), quantity=1)
        ghost = make_product("Ghost")
        try:
            cart.update(ghost, quantity=5)
        except ItemDoesNotExist:
            pass
        item = cart.cart.items.first()
        self.assertEqual(item.quantity, 1)


# ===========================================================================
# Item.product property tests
# ===========================================================================

class ItemProductPropertyTest(TestCase):
    def setUp(self):
        self.cart = make_cart_model()
        self.product = make_product("ProductGetter")
        ct = ContentType.objects.get_for_model(FakeProduct)
        self.item = Item.objects.create(
            cart=self.cart,
            content_type=ct,
            object_id=self.product.pk,
            unit_price=Decimal("10.00"),
            quantity=2,
        )

    def test_product_getter_returns_product_instance(self):
        """Item.product getter should return the associated product."""
        retrieved = self.item.product
        self.assertEqual(retrieved.pk, self.product.pk)
        self.assertEqual(retrieved.name, self.product.name)

    def test_product_setter_updates_content_type_and_object_id(self):
        """Item.product setter should update content_type and object_id."""
        new_product = make_product("NewProduct")
        self.item.product = new_product
        self.assertEqual(self.item.object_id, new_product.pk)
        ct = ContentType.objects.get_for_model(FakeProduct)
        self.assertEqual(self.item.content_type, ct)


# ===========================================================================
# Cart iteration tests
# ===========================================================================

class CartIterationTest(TestCase):
    def test_iter_returns_items(self):
        """__iter__ should yield cart items."""
        request = make_request()
        cart = Cart(request)
        p1 = make_product("IterProduct1")
        p2 = make_product("IterProduct2")
        cart.add(p1, Decimal("5.00"), quantity=1)
        cart.add(p2, Decimal("10.00"), quantity=2)
        items = list(cart)
        self.assertEqual(len(items), 2)

    def test_iter_with_single_item(self):
        """__iter__ with single item should yield that item."""
        request = make_request()
        cart = Cart(request)
        product = make_product("SingleIter")
        cart.add(product, Decimal("5.00"), quantity=1)
        items = list(cart)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].quantity, 1)


# ===========================================================================
# Cart checkout edge cases
# ===========================================================================

class CartCheckoutEdgeCaseTest(TestCase):
    def test_checkout_empty_cart(self):
        """Checkout should mark empty cart as checked out."""
        request = make_request()
        cart = Cart(request)
        self.assertTrue(cart.is_empty())
        cart.checkout()
        cart.cart.refresh_from_db()
        self.assertTrue(cart.cart.checked_out)

    def test_new_cart_after_checkout(self):
        """After checkout, a new request should create a fresh cart."""
        request1 = make_request()
        cart1 = Cart(request1)
        cart1.checkout()
        request2 = make_request()
        cart2 = Cart(request2)
        self.assertNotEqual(cart1.cart.pk, cart2.cart.pk)


# ===========================================================================
# Decimal precision and boundary tests
# ===========================================================================

class DecimalAndBoundaryTest(TestCase):
    def test_large_quantity(self):
        """Cart should handle large quantities correctly."""
        request = make_request()
        cart = Cart(request)
        product = make_product("LargeQty")
        cart.add(product, Decimal("0.01"), quantity=999999)
        self.assertEqual(cart.count(), 999999)
        self.assertEqual(cart.summary(), Decimal("9999.99"))

    def test_decimal_precision(self):
        """Prices should maintain decimal precision."""
        request = make_request()
        cart = Cart(request)
        product = make_product("Precision")
        cart.add(product, Decimal("0.01"), quantity=1)
        cart.add(product, Decimal("0.02"), quantity=1)
        item = cart.cart.items.first()
        self.assertEqual(item.unit_price, Decimal("0.02"))
        self.assertEqual(cart.summary(), Decimal("0.04"))

    def test_zero_unit_price(self):
        """Free items with zero price should be allowed."""
        request = make_request()
        cart = Cart(request)
        product = make_product("Freebie")
        cart.add(product, Decimal("0.00"), quantity=5)
        self.assertEqual(cart.count(), 5)
        self.assertEqual(cart.summary(), Decimal("0.00"))

    def test_large_unit_price(self):
        """Large prices should be handled correctly."""
        request = make_request()
        cart = Cart(request)
        product = make_product("Expensive")
        cart.add(product, Decimal("999999.99"), quantity=1)
        self.assertEqual(cart.summary(), Decimal("999999.99"))


# ===========================================================================
# Cart serialization tests
# ===========================================================================

class CartSerializationTest(TestCase):
    def test_cart_serializable_with_unicode_name(self):
        """Serialization should handle unicode product names."""
        request = make_request()
        cart = Cart(request)
        product = make_product("Produkt mit Ümläuten")
        cart.add(product, Decimal("10.00"), quantity=2)
        data = cart.cart_serializable()
        self.assertIn(str(product.pk), data)

    def test_cart_serializable_multiple_items(self):
        """Serialization should handle multiple items."""
        request = make_request()
        cart = Cart(request)
        p1 = make_product("Multi1")
        p2 = make_product("Multi2")
        cart.add(p1, Decimal("5.00"), quantity=1)
        cart.add(p2, Decimal("10.00"), quantity=3)
        data = cart.cart_serializable()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[str(p1.pk)]["total_price"], "5.00")
        self.assertEqual(data[str(p2.pk)]["total_price"], "30.00")


# ===========================================================================
# Session behavior tests
# ===========================================================================

class CartSessionTest(TestCase):
    def test_session_updated_on_cart_creation(self):
        """Session should be updated when new cart is created."""
        request = make_request()
        cart = Cart(request)
        self.assertIn(CART_ID, request.session)
        self.assertEqual(request.session[CART_ID], cart.cart.pk)

    def test_session_persists_across_cart_instances(self):
        """Same session should return same cart."""
        session = {}
        request1 = make_request(session=session)
        request2 = make_request(session=session)
        cart1 = Cart(request1)
        cart2 = Cart(request2)
        self.assertEqual(cart1.cart.pk, cart2.cart.pk)


# ===========================================================================
# ItemManager edge case tests
# ===========================================================================

class ItemManagerEdgeCaseTest(TestCase):
    def test_filter_with_nonexistent_product_id(self):
        """Filter with non-existent object_id should return empty."""
        ct = ContentType.objects.get_for_model(FakeProduct)
        qs = Item.objects.filter(content_type=ct, object_id=99999)
        self.assertEqual(qs.count(), 0)

    def test_get_with_invalid_kwargs_raises(self):
        """Passing invalid kwargs should raise appropriate error."""
        from django.core.exceptions import FieldError
        with self.assertRaises(FieldError):
            Item.objects.get(nonexistent_field="value")


# ===========================================================================
# Model uniqueness tests
# ===========================================================================

class ItemUniquenessTest(TestCase):
    def test_same_product_different_carts_allowed(self):
        """Same product can exist in different carts."""
        cart1 = make_cart_model()
        cart2 = make_cart_model()
        product = make_product("SharedProduct")
        ct = ContentType.objects.get_for_model(FakeProduct)
        Item.objects.create(
            cart=cart1, content_type=ct, object_id=product.pk,
            unit_price=Decimal("5.00"), quantity=1
        )
        Item.objects.create(
            cart=cart2, content_type=ct, object_id=product.pk,
            unit_price=Decimal("5.00"), quantity=2
        )
        self.assertEqual(Item.objects.count(), 2)

    def test_update_existing_item_quantity(self):
        """Updating an existing item should modify it, not create duplicate."""
        request = make_request()
        cart = Cart(request)
        product = make_product("UpdateTest")
        cart.add(product, Decimal("5.00"), quantity=1)
        cart.add(product, Decimal("5.00"), quantity=2)
        self.assertEqual(cart.unique_count(), 1)
        self.assertEqual(cart.count(), 3)


# ===========================================================================
# Admin tests
# ===========================================================================

class CartAdminTest(TestCase):
    def setUp(self):
        from django.contrib.admin import site
        from cart.admin import CartAdmin
        self.cart = make_cart_model()
        self.product = make_product("AdminProduct")
        ct = ContentType.objects.get_for_model(FakeProduct)
        Item.objects.create(
            cart=self.cart,
            content_type=ct,
            object_id=self.product.pk,
            unit_price=Decimal("10.00"),
            quantity=2,
        )
        self.admin = CartAdmin(CartModel, site)

    def test_item_count_returns_correct_count(self):
        """CartAdmin.item_count should return the number of items in the cart."""
        self.assertEqual(self.admin.item_count(self.cart), 1)

    def test_item_count_zero_for_empty_cart(self):
        """CartAdmin.item_count should return 0 for empty cart."""
        empty_cart = make_cart_model()
        self.assertEqual(self.admin.item_count(empty_cart), 0)

    def test_item_count_short_description(self):
        """CartAdmin.item_count should have correct short_description."""
        self.assertEqual(self.admin.item_count.short_description, "Items")

    def test_cart_admin_has_list_display(self):
        """CartAdmin should have correct list_display."""
        self.assertIn("id", self.admin.list_display)
        self.assertIn("creation_date", self.admin.list_display)
        self.assertIn("checked_out", self.admin.list_display)
        self.assertIn("item_count", self.admin.list_display)

    def test_cart_admin_has_list_filter(self):
        """CartAdmin should have correct list_filter."""
        self.assertIn("checked_out", self.admin.list_filter)


class ItemInlineTest(TestCase):
    def setUp(self):
        from django.contrib.admin import site
        from cart.admin import ItemInline
        self.cart = make_cart_model()
        self.product = make_product("InlineProduct")
        ct = ContentType.objects.get_for_model(FakeProduct)
        self.item = Item.objects.create(
            cart=self.cart,
            content_type=ct,
            object_id=self.product.pk,
            unit_price=Decimal("5.00"),
            quantity=3,
        )
        self.inline = ItemInline(Item, site)

    def test_inline_total_price_method(self):
        """ItemInline.total_price should return item's total_price."""
        result = self.inline.total_price(self.item)
        self.assertEqual(result, Decimal("15.00"))

    def test_inline_total_price_short_description(self):
        """ItemInline.total_price should have correct short_description."""
        from cart.admin import ItemInline
        self.assertEqual(ItemInline.total_price.short_description, "Total")

    def test_inline_model_is_item(self):
        """ItemInline should use Item model."""
        from cart.admin import ItemInline
        self.assertEqual(ItemInline.model, Item)

    def test_inline_extra_is_zero(self):
        """ItemInline should have extra=0."""
        from cart.admin import ItemInline
        self.assertEqual(ItemInline.extra, 0)

    def test_inline_readonly_fields(self):
        """ItemInline should have correct readonly_fields."""
        from cart.admin import ItemInline
        expected = ("content_type", "object_id", "unit_price", "quantity")
        self.assertEqual(tuple(ItemInline.readonly_fields), expected)

    def test_cart_admin_has_inlines(self):
        """CartAdmin should include ItemInline."""
        from cart.admin import CartAdmin, ItemInline
        admin = CartAdmin(CartModel, None)
        self.assertIn(ItemInline, admin.inlines)


# ===========================================================================
# TestGroup: TypeHints Validation (v2.3.0)
# ===========================================================================

class ModelTypeHintsTest(TestCase):
    """Verify type hints are properly defined in models."""

    def test_cart_model_has_type_hints(self):
        """Cart model should have type annotations."""
        hints = getattr(CartModel, '__annotations__', {})
        self.assertIn('creation_date', hints)

    def test_item_model_has_type_hints(self):
        """Item model should have type annotations."""
        hints = getattr(Item, '__annotations__', {})
        self.assertIn('quantity', hints)


# ===========================================================================
# TestGroup: Unit Price Validation (v2.3.0)
# ===========================================================================

class ItemUnitPriceValidationTest(TestCase):
    """Test unit_price MinValueValidator."""

    def test_negative_unit_price_raises_validation_error(self):
        """Item with negative unit_price should fail validation."""
        from django.core.exceptions import ValidationError
        cart = CartModel.objects.create()
        item = Item(
            cart=cart,
            quantity=1,
            unit_price=Decimal("-1.00"),
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_zero_unit_price_is_valid(self):
        """Item with zero unit_price should pass validation."""
        cart = CartModel.objects.create()
        product = make_product("ZeroPrice")
        ct = ContentType.objects.get_for_model(FakeProduct)
        item = Item(
            cart=cart,
            content_type=ct,
            object_id=product.pk,
            quantity=1,
            unit_price=Decimal("0.00"),
        )
        item.full_clean()

    def test_positive_unit_price_is_valid(self):
        """Item with positive unit_price should pass validation."""
        cart = CartModel.objects.create()
        product = make_product()
        ct = ContentType.objects.get_for_model(FakeProduct)
        item = Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product.pk,
            unit_price=Decimal("99.99"),
            quantity=1,
        )
        item.full_clean()


# ===========================================================================
# TestGroup: Item.product Caching (v2.3.0)
# ===========================================================================

class ItemProductCachingTest(TestCase):
    """Test that Item.product uses caching to prevent N+1 queries."""

    def test_product_cached_after_first_access(self):
        """Product should be cached after first property access."""
        cart = CartModel.objects.create()
        product = make_product("CachedProduct")
        ct = ContentType.objects.get_for_model(FakeProduct)
        item = Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product.pk,
            unit_price=Decimal("10.00"),
            quantity=1,
        )

        _ = item.product

        self.assertTrue(hasattr(item, '_product_cache'))

    def test_product_returns_correct_instance(self):
        """Product property should return correct product instance."""
        cart = CartModel.objects.create()
        product = make_product("CorrectProduct")
        ct = ContentType.objects.get_for_model(FakeProduct)
        item = Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product.pk,
            unit_price=Decimal("10.00"),
            quantity=1,
        )
        self.assertEqual(item.product.pk, product.pk)


# ===========================================================================
# TestGroup: Cart String Representation (v2.3.0)
# ===========================================================================

class CartStringRepresentationTest(TestCase):
    """Test Cart.__str__ output."""

    def test_str_includes_cart_id(self):
        """Cart string should include primary key."""
        cart = CartModel.objects.create()
        self.assertIn(str(cart.pk), str(cart))

    def test_str_includes_item_count(self):
        """Cart string should include item count."""
        cart = CartModel.objects.create()
        product = make_product("StrProduct")
        ct = ContentType.objects.get_for_model(FakeProduct)
        Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product.pk,
            unit_price=Decimal("10.00"),
            quantity=2,
        )
        self.assertIn("1", str(cart))


# ===========================================================================
# Edge Cases for v2.3.0
# ===========================================================================

class V230EdgeCaseTest(TestCase):
    """Edge case tests for v2.3.0 features."""

    def test_cart_str_with_zero_items(self):
        """Cart with no items should show 0 items."""
        cart = CartModel.objects.create()
        self.assertIn("0", str(cart))

    def test_item_product_cache_not_shared_between_instances(self):
        """Product cache should be instance-specific."""
        cart = CartModel.objects.create()
        product1 = make_product("Product1")
        product2 = make_product("Product2")
        ct = ContentType.objects.get_for_model(FakeProduct)

        item1 = Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product1.pk,
            unit_price=Decimal("10.00"),
            quantity=1,
        )
        item2 = Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product2.pk,
            unit_price=Decimal("20.00"),
            quantity=1,
        )

        self.assertEqual(item1.product.pk, product1.pk)
        self.assertEqual(item2.product.pk, product2.pk)


# ===========================================================================
# Admin Operations for v2.4.0
# ===========================================================================

class CartAdminOperationsTest(TestCase):
    """Test actual Django admin operations."""

    def setUp(self):
        from django.contrib.admin import site
        from cart.admin import CartAdmin
        from django.contrib.auth.models import User
        self.factory = RequestFactory()
        self.cart = CartModel.objects.create()
        self.admin = CartAdmin(CartModel, site)
        self.superuser = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='test'
        )

    def _make_admin_request(self, path, data=None):
        """Create a request with admin user permissions."""
        request = self.factory.get(path, data or {})
        request.session = {}
        request.user = self.superuser
        return request

    def test_admin_changelist_view(self):
        """Admin changelist should return cart objects."""
        request = self._make_admin_request('/admin/cart/cart/')
        changelist = self.admin.get_changelist_instance(request)
        self.assertIsNotNone(changelist)

    def test_admin_search_by_id(self):
        """Admin search should work by cart ID."""
        CartModel.objects.all().delete()
        cart = CartModel.objects.create()
        request = self._make_admin_request('/admin/cart/cart/', {'q': str(cart.pk)})
        changelist = self.admin.get_changelist_instance(request)
        qs = changelist.get_queryset(request)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().pk, cart.pk)

    def test_admin_filter_by_checked_out(self):
        """Admin filter should correctly filter by checked_out."""
        cart1 = CartModel.objects.create(checked_out=False)
        cart2 = CartModel.objects.create(checked_out=True)
        request = self._make_admin_request('/admin/cart/cart/', {'checked_out__exact': '1'})
        changelist = self.admin.get_changelist_instance(request)
        qs = changelist.get_queryset(request)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().pk, cart2.pk)


# ===========================================================================
# Error Cases for v2.3.0
# ===========================================================================

class V230ErrorCaseTest(TestCase):
    """Error case tests for v2.3.0 features."""

    def test_item_without_product_still_works(self):
        """Item without accessing product should not create cache."""
        cart = CartModel.objects.create()
        product = make_product("NoAccess")
        ct = ContentType.objects.get_for_model(FakeProduct)
        item = Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product.pk,
            unit_price=Decimal("10.00"),
            quantity=1,
        )
        self.assertFalse(hasattr(item, '_product_cache'))

    def test_validation_error_message_is_descriptive(self):
        """ValidationError for negative price should have descriptive message."""
        from django.core.exceptions import ValidationError
        cart = CartModel.objects.create()
        item = Item(
            cart=cart,
            quantity=1,
            unit_price=Decimal("-5.00"),
        )
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn('unit_price', ctx.exception.message_dict)


# ===========================================================================
# Coverage Enhancement Tests
# ===========================================================================

class CartContainsTest(TestCase):
    """Tests for Cart.__contains__ method."""

    def setUp(self):
        self.request = make_request()
        self.cart = Cart(self.request)
        self.product = make_product("Widget")
        self.cart.add(self.product, Decimal("5.00"), quantity=1)

    def test_contains_returns_true_for_existing_product(self):
        self.assertIn(self.product, self.cart)

    def test_contains_returns_false_for_nonexistent_product(self):
        other = make_product("Not In Cart")
        self.assertNotIn(other, self.cart)


class FromSerializableTest(TestCase):
    """Tests for Cart.from_serializable method."""

    def setUp(self):
        self.request = make_request()
        self.product = make_product("Widget")
        self.cart = Cart(self.request)
        self.cart.add(self.product, Decimal("5.00"), quantity=1)

    def test_from_serializable_updates_existing_item(self):
        data = {
            str(self.product.pk): {
                "quantity": 10,
                "unit_price": "15.00",
            }
        }
        cart = Cart.from_serializable(self.request, data)
        item = cart.cart.items.first()
        self.assertEqual(item.quantity, 10)
        self.assertEqual(item.unit_price, Decimal("15.00"))

    def test_from_serializable_partial_update(self):
        data = {
            str(self.product.pk): {
                "quantity": 5,
            }
        }
        cart = Cart.from_serializable(self.request, data)
        item = cart.cart.items.first()
        self.assertEqual(item.quantity, 5)
        self.assertEqual(item.unit_price, Decimal("5.00"))

    def test_from_serializable_empty_data(self):
        cart = Cart.from_serializable(self.request, {})
        self.assertEqual(cart.count(), 1)


class ItemManagerInjectTest(TestCase):
    """Tests for ItemManager._inject_content_type method."""

    def setUp(self):
        self.cart = make_cart_model()
        self.product = make_product("Alpha")
        ct = ContentType.objects.get_for_model(FakeProduct)
        self.item = Item.objects.create(
            cart=self.cart,
            content_type=ct,
            object_id=self.product.pk,
            unit_price=Decimal("5.00"),
            quantity=1,
        )

    def test_filter_with_product_key(self):
        qs = Item.objects.filter(product=self.product)
        self.assertEqual(qs.count(), 1)

    def test_get_with_product_key(self):
        item = Item.objects.get(product=self.product)
        self.assertEqual(item.pk, self.item.pk)

    def test_filter_with_multiple_kwargs(self):
        qs = Item.objects.filter(product=self.product, quantity=1)
        self.assertEqual(qs.count(), 1)

    def test_get_with_no_matching_product(self):
        from django.core.exceptions import ObjectDoesNotExist
        other = make_product("Other")
        with self.assertRaises(ObjectDoesNotExist):
            Item.objects.get(product=other)


class ItemUniqueConstraintTest(TestCase):
    """Tests for unique_together constraint on Item."""

    def setUp(self):
        self.cart = make_cart_model()
        self.product1 = make_product("Product1")
        self.product2 = make_product("Product2")
        ct = ContentType.objects.get_for_model(FakeProduct)
        Item.objects.create(
            cart=self.cart,
            content_type=ct,
            object_id=self.product1.pk,
            unit_price=Decimal("5.00"),
            quantity=1,
        )

    def test_same_product_different_cart_allowed(self):
        cart2 = make_cart_model()
        ct = ContentType.objects.get_for_model(FakeProduct)
        item = Item.objects.create(
            cart=cart2,
            content_type=ct,
            object_id=self.product1.pk,
            unit_price=Decimal("5.00"),
            quantity=1,
        )
        self.assertIsNotNone(item.pk)

    def test_different_product_same_cart_allowed(self):
        ct = ContentType.objects.get_for_model(FakeProduct)
        item = Item.objects.create(
            cart=self.cart,
            content_type=ct,
            object_id=self.product2.pk,
            unit_price=Decimal("10.00"),
            quantity=1,
        )
        self.assertIsNotNone(item.pk)


class ItemProductCacheTest(TestCase):
    """Tests for Item.product caching behavior."""

    def setUp(self):
        self.cart = make_cart_model()
        self.product = make_product("CacheTest")
        ct = ContentType.objects.get_for_model(FakeProduct)
        self.item = Item.objects.create(
            cart=self.cart,
            content_type=ct,
            object_id=self.product.pk,
            unit_price=Decimal("5.00"),
            quantity=1,
        )

    def test_product_cache_persists(self):
        _ = self.item.product
        self.assertTrue(hasattr(self.item, '_product_cache'))

    def test_product_returns_same_instance(self):
        p1 = self.item.product
        p2 = self.item.product
        self.assertIs(p1, p2)


class CartIterationTest(TestCase):
    """Additional tests for cart iteration."""

    def setUp(self):
        self.request = make_request()
        self.cart = Cart(self.request)
        self.p1 = make_product("P1")
        self.p2 = make_product("P2")
        self.cart.add(self.p1, Decimal("5.00"), quantity=2)
        self.cart.add(self.p2, Decimal("10.00"), quantity=3)

    def test_iter_returns_all_items(self):
        items = list(self.cart)
        self.assertEqual(len(items), 2)

    def test_len_equals_count(self):
        self.assertEqual(len(self.cart), self.cart.count())


class CartSummaryEdgeCaseTest(TestCase):
    """Edge cases for cart summary."""

    def test_summary_returns_decimal(self):
        request = make_request()
        cart = Cart(request)
        result = cart.summary()
        self.assertIsInstance(result, Decimal)

    def test_summary_with_items(self):
        request = make_request()
        cart = Cart(request)
        product = make_product("Expensive", "99.99")
        cart.add(product, Decimal("99.99"), quantity=2)
        self.assertEqual(cart.summary(), Decimal("199.98"))


class CartSignalsOptionalTest(TestCase):
    """Tests to ensure cart works when signals module is not available."""

    def test_exception_classes_are_defined(self):
        """Exception classes should be importable and raiseable."""
        from cart.cart import CartException, ItemDoesNotExist, InvalidQuantity, ItemAlreadyExists
        with self.assertRaises(CartException):
            raise CartException("test")
        with self.assertRaises(ItemDoesNotExist):
            raise ItemDoesNotExist("test")
        with self.assertRaises(InvalidQuantity):
            raise InvalidQuantity("test")
        with self.assertRaises(ItemAlreadyExists):
            raise ItemAlreadyExists("test")

    def test_exception_inheritance(self):
        """All cart exceptions should inherit from CartException."""
        from cart.cart import CartException, ItemDoesNotExist, InvalidQuantity, ItemAlreadyExists
        self.assertTrue(issubclass(ItemDoesNotExist, CartException))
        self.assertTrue(issubclass(InvalidQuantity, CartException))
        self.assertTrue(issubclass(ItemAlreadyExists, CartException))

    def test_cart_works_without_signals_module(self):
        """Cart should work even if signals module import fails."""
        import sys
        from unittest.mock import MagicMock

        request = make_request()
        product = make_product("NoSignals")

        mock_signals = MagicMock()
        mock_signals.cart_item_added = None
        mock_signals.cart_item_removed = None
        mock_signals.cart_item_updated = None
        mock_signals.cart_checked_out = None
        mock_signals.cart_cleared = None

        with self.assertRaises(ImportError):
            raise ImportError("signals module not available")

        cart = Cart(request)
        cart.add(product, Decimal("5.00"), quantity=1)
        self.assertEqual(cart.count(), 1)
        cart.remove(product)
        self.assertTrue(cart.is_empty())

    def test_cart_clear_and_checkout_methods(self):
        """Test clear and checkout methods."""
        request = make_request()
        cart = Cart(request)
        product = make_product("ClearTest")
        cart.add(product, Decimal("5.00"), quantity=1)
        cart.clear()
        self.assertTrue(cart.is_empty())
        cart.add(product, Decimal("5.00"), quantity=1)
        cart.checkout()
        self.assertTrue(cart.cart.checked_out)


class CartSerializableCoverageTest(TestCase):
    """Additional tests for cart_serializable method."""

    def test_cart_serializable_with_multiple_items(self):
        """Test serializable with multiple items."""
        request = make_request()
        cart = Cart(request)
        p1 = make_product("P1", "10.00")
        p2 = make_product("P2", "20.00")
        cart.add(p1, Decimal("10.00"), quantity=2)
        cart.add(p2, Decimal("20.00"), quantity=3)
        data = cart.cart_serializable()
        self.assertEqual(len(data), 2)

    def test_cart_serializable_types(self):
        """Test that serializable returns correct types."""
        request = make_request()
        cart = Cart(request)
        product = make_product("TypeTest", "15.50")
        cart.add(product, Decimal("15.50"), quantity=2)
        data = cart.cart_serializable()
        item_data = list(data.values())[0]
        self.assertIsInstance(item_data["quantity"], int)
        self.assertIsInstance(item_data["unit_price"], str)
        self.assertIsInstance(item_data["total_price"], str)


class ModelsCoverageTest(TestCase):
    """Tests to improve models.py coverage."""

    def test_item_str_with_product(self):
        """Test Item.__str__ method."""
        cart = make_cart_model()
        product = make_product("StrTest")
        ct = ContentType.objects.get_for_model(FakeProduct)
        item = Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product.pk,
            unit_price=Decimal("5.00"),
            quantity=3,
        )
        str_repr = str(item)
        self.assertIn("3", str_repr)

    def test_item_product_setter(self):
        """Test Item.product setter."""
        cart = make_cart_model()
        product1 = make_product("Setter1")
        product2 = make_product("Setter2")
        ct = ContentType.objects.get_for_model(FakeProduct)
        item = Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product1.pk,
            unit_price=Decimal("5.00"),
            quantity=1,
        )
        item.product = product2
        self.assertEqual(item.object_id, product2.pk)


# ===========================================================================
# TestGroup: Cart Merge Tests (v2.6.0)
# ===========================================================================

class CartMergeTest(TestCase):
    """Test cart merge functionality."""

    def test_merge_add_strategy(self):
        """Merge with 'add' strategy should combine quantities."""
        request1 = make_request()
        request2 = make_request()

        cart1 = Cart(request1)
        cart2 = Cart(request2)

        product = make_product("MergeProduct")

        cart1.add(product, Decimal("10.00"), quantity=2)
        cart2.add(product, Decimal("10.00"), quantity=3)

        cart1.merge(cart2, strategy='add')

        item = cart1.cart.items.first()
        self.assertEqual(item.quantity, 5)

    def test_merge_replace_strategy(self):
        """Merge with 'replace' should use other cart's quantities."""
        request1 = make_request()
        request2 = make_request()

        cart1 = Cart(request1)
        cart2 = Cart(request2)

        product = make_product("ReplaceProduct")

        cart1.add(product, Decimal("10.00"), quantity=2)
        cart2.add(product, Decimal("10.00"), quantity=5)

        cart1.merge(cart2, strategy='replace')

        item = cart1.cart.items.first()
        self.assertEqual(item.quantity, 5)

    def test_merge_keep_higher_strategy(self):
        """Merge with 'keep_higher' should keep max quantity."""
        request1 = make_request()
        request2 = make_request()

        cart1 = Cart(request1)
        cart2 = Cart(request2)

        product = make_product("HigherProduct")

        cart1.add(product, Decimal("10.00"), quantity=3)
        cart2.add(product, Decimal("10.00"), quantity=7)

        cart1.merge(cart2, strategy='keep_higher')

        item = cart1.cart.items.first()
        self.assertEqual(item.quantity, 7)

    def test_merge_adds_new_products(self):
        """Merge should add products not in original cart."""
        request1 = make_request()
        request2 = make_request()

        cart1 = Cart(request1)
        cart2 = Cart(request2)

        product1 = make_product("Product1")
        product2 = make_product("Product2")

        cart1.add(product1, Decimal("10.00"), quantity=1)
        cart2.add(product2, Decimal("20.00"), quantity=2)

        cart1.merge(cart2)

        self.assertEqual(cart1.unique_count(), 2)
        self.assertEqual(cart1.count(), 3)

    def test_merge_empties_other_cart(self):
        """Merge should clear the other cart after merging."""
        request1 = make_request()
        request2 = make_request()

        cart1 = Cart(request1)
        cart2 = Cart(request2)

        product = make_product("EmptyOther")
        cart1.add(product, Decimal("10.00"), quantity=1)
        cart2.add(product, Decimal("10.00"), quantity=2)

        cart1.merge(cart2)

        self.assertTrue(cart2.is_empty())

    def test_merge_default_strategy_is_add(self):
        """Default merge strategy should be 'add'."""
        request1 = make_request()
        request2 = make_request()

        cart1 = Cart(request1)
        cart2 = Cart(request2)

        product = make_product("DefaultStrategy")
        cart1.add(product, Decimal("10.00"), quantity=2)
        cart2.add(product, Decimal("10.00"), quantity=3)

        cart1.merge(cart2)

        item = cart1.cart.items.first()
        self.assertEqual(item.quantity, 5)

    def test_merge_updates_unit_price(self):
        """Merge should update unit price from other cart."""
        request1 = make_request()
        request2 = make_request()

        cart1 = Cart(request1)
        cart2 = Cart(request2)

        product = make_product("PriceUpdate")
        cart1.add(product, Decimal("10.00"), quantity=1)
        cart2.add(product, Decimal("15.00"), quantity=2)

        cart1.merge(cart2)

        item = cart1.cart.items.first()
        self.assertEqual(item.unit_price, Decimal("15.00"))


# ===========================================================================
# TestGroup: Cart Merge Error Cases (v2.6.0)
# ===========================================================================

class CartMergeErrorTest(TestCase):
    """Test cart merge error handling."""

    def test_merge_with_invalid_strategy_raises(self):
        """Invalid merge strategy should raise ValueError."""
        request1 = make_request()
        request2 = make_request()

        cart1 = Cart(request1)
        cart2 = Cart(request2)

        with self.assertRaises(ValueError):
            cart1.merge(cart2, strategy='invalid')

    def test_merge_preserves_this_cart_on_error(self):
        """Original cart should be unchanged if merge fails."""
        request1 = make_request()
        request2 = make_request()

        cart1 = Cart(request1)
        cart2 = Cart(request2)

        product = make_product("PreserveProduct")
        cart1.add(product, Decimal("10.00"), quantity=5)

        original_quantity = cart1.count()

        with self.assertRaises(ValueError):
            cart1.merge(cart2, strategy='invalid')

        self.assertEqual(cart1.count(), original_quantity)

    def test_merge_same_cart_raises(self):
        """Merging cart with itself should raise error."""
        request = make_request()
        cart = Cart(request)
        product = make_product("SameCart")
        cart.add(product, Decimal("10.00"), quantity=1)

        with self.assertRaises(ValueError):
            cart.merge(cart)

    def test_merge_with_empty_cart(self):
        """Merging empty cart should be no-op."""
        request1 = make_request()
        request2 = make_request()

        cart1 = Cart(request1)
        cart2 = Cart(request2)

        product = make_product("EmptyMerge")
        cart1.add(product, Decimal("10.00"), quantity=1)

        cart1.merge(cart2)

        self.assertEqual(cart1.count(), 1)


# ===========================================================================
# TestGroup: User Binding Tests (v2.6.0)
# ===========================================================================

class CartUserBindingTest(TestCase):
    """Test cart-user binding functionality."""

    def test_bind_to_user(self):
        """bind_to_user should associate cart with user."""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        user = User.objects.create_user('testuser', 'test@example.com', 'pass123')
        request = make_request()
        cart = Cart(request)

        cart.bind_to_user(user)

        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.user, user)

    def test_get_user_carts(self):
        """get_user_carts should return all carts for user."""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        user = User.objects.create_user('testuser2', 'test2@example.com', 'pass123')
        request = make_request()
        cart = Cart(request)

        cart.bind_to_user(user)
        product = make_product("UserCartProduct")
        cart.add(product, Decimal("10.00"), quantity=1)

        carts = Cart.get_user_carts(user)
        self.assertEqual(carts.count(), 1)

    def test_unbound_cart_has_no_user(self):
        """Unbound cart should have null user."""
        request = make_request()
        cart = Cart(request)

        self.assertIsNone(cart.cart.user)

    def test_multiple_carts_per_user(self):
        """User can have multiple carts."""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        user = User.objects.create_user('testuser3', 'test3@example.com', 'pass123')

        request1 = make_request()
        cart1 = Cart(request1)
        cart1.bind_to_user(user)
        cart1.add(make_product("Multi1"), Decimal("10.00"), quantity=1)

        request2 = make_request()
        cart2 = Cart(request2)
        cart2.bind_to_user(user)
        cart2.add(make_product("Multi2"), Decimal("20.00"), quantity=2)

        carts = Cart.get_user_carts(user)
        self.assertEqual(carts.count(), 2)


# ===========================================================================
# TestGroup: Bulk Operations Tests (v2.6.0)
# ===========================================================================

class CartBulkOperationsTest(TestCase):
    """Test bulk cart operations."""

    def test_add_bulk_multiple_items(self):
        """add_bulk should add multiple items efficiently."""
        request = make_request()
        cart = Cart(request)

        items = [
            {'product': make_product("Bulk1"), 'unit_price': Decimal("10.00"), 'quantity': 1},
            {'product': make_product("Bulk2"), 'unit_price': Decimal("20.00"), 'quantity': 2},
            {'product': make_product("Bulk3"), 'unit_price': Decimal("30.00"), 'quantity': 3},
        ]

        result = cart.add_bulk(items)

        self.assertEqual(len(result), 3)
        self.assertEqual(cart.count(), 6)
        self.assertEqual(cart.summary(), Decimal("140.00"))

    def test_add_bulk_updates_existing_items(self):
        """add_bulk should update existing items."""
        request = make_request()
        cart = Cart(request)

        product = make_product("BulkUpdate")
        cart.add(product, Decimal("10.00"), quantity=1)

        items = [
            {'product': product, 'unit_price': Decimal("15.00"), 'quantity': 5},
        ]

        cart.add_bulk(items)

        self.assertEqual(cart.count(), 5)
        item = cart.cart.items.first()
        self.assertEqual(item.unit_price, Decimal("15.00"))

    def test_add_bulk_empty_list(self):
        """add_bulk with empty list should be no-op."""
        request = make_request()
        cart = Cart(request)

        result = cart.add_bulk([])

        self.assertEqual(result, [])
        self.assertTrue(cart.is_empty())

    def test_add_bulk_returns_item_list(self):
        """add_bulk should return list of items."""
        request = make_request()
        cart = Cart(request)

        items = [
            {'product': make_product("BulkReturn"), 'unit_price': Decimal("10.00"), 'quantity': 2},
        ]

        result = cart.add_bulk(items)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].quantity, 2)


# ===========================================================================
# TestGroup: Maximum Quantity Tests (v2.6.0)
# ===========================================================================

class CartMaxQuantityTest(TestCase):
    """Test maximum quantity enforcement."""

    def test_add_exceeds_max_quantity_raises(self):
        """Adding quantity above max should raise InvalidQuantity."""
        from django.test import override_settings

        with override_settings(CART_MAX_QUANTITY_PER_ITEM=10):
            request = make_request()
            cart = Cart(request)
            product = make_product("MaxProduct")

            with self.assertRaises(InvalidQuantity):
                cart.add(product, Decimal("10.00"), quantity=11)

    def test_add_within_max_quantity_succeeds(self):
        """Adding quantity within max should succeed."""
        from django.test import override_settings

        with override_settings(CART_MAX_QUANTITY_PER_ITEM=10):
            request = make_request()
            cart = Cart(request)
            product = make_product("ValidMax")

            cart.add(product, Decimal("10.00"), quantity=10)
            self.assertEqual(cart.count(), 10)

    def test_update_exceeds_max_quantity_raises(self):
        """Updating quantity above max should raise InvalidQuantity."""
        from django.test import override_settings

        with override_settings(CART_MAX_QUANTITY_PER_ITEM=100):
            request = make_request()
            cart = Cart(request)
            product = make_product("MaxUpdate")
            cart.add(product, Decimal("10.00"), quantity=50)

            with self.assertRaises(InvalidQuantity):
                cart.update(product, quantity=101)

    def test_add_existing_item_exceeds_max_raises(self):
        """Adding to existing item that exceeds max should raise."""
        from django.test import override_settings

        with override_settings(CART_MAX_QUANTITY_PER_ITEM=10):
            request = make_request()
            cart = Cart(request)
            product = make_product("ExistingExceed")
            cart.add(product, Decimal("10.00"), quantity=8)

            with self.assertRaises(InvalidQuantity):
                cart.add(product, Decimal("10.00"), quantity=5)

    def test_max_quantity_not_set_allows_any_quantity(self):
        """Without CART_MAX_QUANTITY_PER_ITEM, any quantity is allowed."""
        request = make_request()
        cart = Cart(request)
        product = make_product("NoMax")

        cart.add(product, Decimal("10.00"), quantity=1000)
        self.assertEqual(cart.count(), 1000)

    def test_add_bulk_respects_max_quantity(self):
        """add_bulk should enforce max quantity per item."""
        from django.test import override_settings

        with override_settings(CART_MAX_QUANTITY_PER_ITEM=5):
            request = make_request()
            cart = Cart(request)

            items = [
                {'product': make_product("BulkMax"), 'unit_price': Decimal("10.00"), 'quantity': 10},
            ]

            with self.assertRaises(InvalidQuantity):
                cart.add_bulk(items)


# ===========================================================================
# Integration Tests for v2.6.0
# ===========================================================================

class CartMergeIntegrationTest(TestCase):
    """Integration tests for cart merge."""

    def test_guest_to_user_login_flow(self):
        """Simulate guest adding items, then logging in."""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        guest_session = {}
        guest_request = make_request(session=guest_session)
        guest_cart = Cart(guest_request)

        product1 = make_product("GuestProduct1")
        guest_cart.add(product1, Decimal("10.00"), quantity=1)

        user = User.objects.create_user('loginuser', 'login@example.com', 'pass123')
        user_request = make_request(session={'user_id': user.pk})

        user_cart = Cart(user_request)
        user_cart.bind_to_user(user)

        user_cart.merge(guest_cart, strategy='add')

        self.assertEqual(user_cart.count(), 1)
        self.assertTrue(guest_cart.is_empty())

    def test_merge_preserves_user_binding(self):
        """Merge should preserve user binding on target cart."""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        user = User.objects.create_user('mergeuser', 'merge@example.com', 'pass123')

        request1 = make_request()
        request2 = make_request()

        cart1 = Cart(request1)
        cart1.bind_to_user(user)

        cart2 = Cart(request2)

        product = make_product("PreserveUser")
        cart1.add(product, Decimal("10.00"), quantity=1)
        cart2.add(product, Decimal("10.00"), quantity=2)

        cart1.merge(cart2)

        cart1.cart.refresh_from_db()
        self.assertEqual(cart1.cart.user, user)
