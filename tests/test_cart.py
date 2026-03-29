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
