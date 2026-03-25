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
from django.db import models as django_models
from django.test import TestCase
from django.utils import timezone

from cart.models import Cart as CartModel, Item
from cart.cart import (
    Cart,
    ItemDoesNotExist,
    InvalidQuantity,
    CART_ID,
)
from cart.management.commands.clean_carts import Command as CleanCartsCommand  # noqa: F401


# ---------------------------------------------------------------------------
# Concrete product model used as a generic FK target in tests.
# Registered in INSTALLED_APPS via app_label = "cart" so it gets a real
# ContentType row and a real DB table in the test database.
# ---------------------------------------------------------------------------

class FakeProduct(django_models.Model):
    """Lightweight product model used only in tests."""
    name = django_models.CharField(max_length=100)
    price = django_models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        app_label = "cart"

    def __str__(self):
        return self.name


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
        self.assertIn(str(cart.creation_date), str(cart))

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
        