"""In-memory cache for count() and summary(): invalidation on every mutation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cart.cart import Cart

pytestmark = pytest.mark.django_db


def test_summary_is_cached_across_calls_on_the_same_instance(cart, product):
    cart.add(product, Decimal("10.00"), quantity=2)

    first = cart.summary()
    # Bypass the Cart API so the DB diverges from the cache.
    cart.cart.items.update(quantity=5)
    second = cart.summary()

    assert first == second == Decimal("20.00")


def test_count_is_cached_across_calls_on_the_same_instance(cart, product):
    cart.add(product, Decimal("10.00"), quantity=2)

    first = cart.count()
    cart.cart.items.update(quantity=5)
    second = cart.count()

    assert first == second == 2


def test_add_invalidates_the_cache(cart, product):
    assert cart.summary() == Decimal("0.00")

    cart.add(product, Decimal("10.00"), quantity=1)

    assert cart.summary() == Decimal("10.00")
    assert cart.count() == 1


def test_remove_invalidates_the_cache(cart, product):
    cart.add(product, Decimal("10.00"), quantity=1)
    assert cart.summary() == Decimal("10.00")

    cart.remove(product)

    assert cart.summary() == Decimal("0.00")
    assert cart.count() == 0


def test_update_invalidates_the_cache(cart, product):
    cart.add(product, Decimal("10.00"), quantity=1)
    assert cart.summary() == Decimal("10.00")

    cart.update(product, quantity=5)

    assert cart.summary() == Decimal("50.00")
    assert cart.count() == 5


def test_clear_invalidates_the_cache(cart, product):
    cart.add(product, Decimal("10.00"), quantity=3)
    assert cart.summary() == Decimal("30.00")

    cart.clear()

    assert cart.summary() == Decimal("0.00")
    assert cart.count() == 0


def test_cache_is_isolated_per_cart_instance(rf_request, product_factory):
    from django.test import RequestFactory

    r1 = rf_request
    r2 = RequestFactory().get("/")
    r2.session = {}

    p1 = product_factory(name="Cache1")
    p2 = product_factory(name="Cache2")
    c1 = Cart(r1)
    c2 = Cart(r2)

    c1.add(p1, Decimal("10.00"), quantity=1)
    c2.add(p2, Decimal("20.00"), quantity=1)

    assert c1.summary() == Decimal("10.00")
    assert c2.summary() == Decimal("20.00")


def test_cache_holds_up_under_many_summary_calls_on_large_cart(
    cart, product_factory, django_assert_max_num_queries
):
    for i in range(100):
        cart.add(product_factory(name=f"LargeCache{i}"), Decimal("10.00"), quantity=1)

    # First call runs the aggregate (1 query); next nine should all hit
    # the in-memory cache (0 queries each). Upper bound 1 catches any
    # regression that drops caching.
    with django_assert_max_num_queries(1):
        for _ in range(10):
            cart.summary()


# --------------------------------------------------------------------------- #
# Calculator-value caching — tax / shipping / discount_amount / total
#
# ANALYSIS §8.2: a template that displays subtotal, tax, shipping, and
# total invokes three calculators (and the discount computation) per
# render of total() plus one each for the individual tax()/shipping()
# calls. Caching them on ``_cache`` means each calculator runs exactly
# once per Cart instance, with ``_invalidate_cache()`` (called from
# every mutation) resetting the lot.
# --------------------------------------------------------------------------- #

from cart.shipping import ShippingCalculator  # noqa: E402
from cart.tax import TaxCalculator  # noqa: E402


class _CountingTaxCalculator(TaxCalculator):
    """Flat-rate tax calculator that counts how often ``calculate()`` runs."""

    call_count = 0

    def calculate(self, cart):
        _CountingTaxCalculator.call_count += 1
        return cart.summary() * Decimal("0.10")


class _CountingShippingCalculator(ShippingCalculator):
    """Flat-rate shipping calculator that counts how often ``calculate()`` runs."""

    call_count = 0

    def calculate(self, cart):
        _CountingShippingCalculator.call_count += 1
        return Decimal("9.99")

    def get_options(self, cart):
        return [{"id": "flat", "name": "Flat", "price": Decimal("9.99")}]


def test_tax_is_cached_across_calls(cart, product, settings):
    """Repeated ``cart.tax()`` calls must hit the cache after the first.
    Tax calculators can be expensive in the wild (external APIs — Stripe
    Tax, Avalara, TaxJar) so recomputing per call is a real cost."""
    settings.CART_TAX_CALCULATOR = "tests.test_cart_caching._CountingTaxCalculator"
    _CountingTaxCalculator.call_count = 0
    cart.add(product, Decimal("100.00"), quantity=1)

    for _ in range(5):
        cart.tax()

    assert _CountingTaxCalculator.call_count == 1


def test_shipping_is_cached_across_calls(cart, product, settings):
    settings.CART_SHIPPING_CALCULATOR = (
        "tests.test_cart_caching._CountingShippingCalculator"
    )
    _CountingShippingCalculator.call_count = 0
    cart.add(product, Decimal("50.00"), quantity=1)

    for _ in range(5):
        cart.shipping()

    assert _CountingShippingCalculator.call_count == 1


def test_total_does_not_reinvoke_calculators_on_repeat_calls(cart, product, settings):
    """``cart.total()`` combines summary / discount / tax / shipping.
    Callers that render subtotal + tax + shipping + total shouldn't
    pay for four calculator runs per field."""
    settings.CART_TAX_CALCULATOR = "tests.test_cart_caching._CountingTaxCalculator"
    settings.CART_SHIPPING_CALCULATOR = (
        "tests.test_cart_caching._CountingShippingCalculator"
    )
    _CountingTaxCalculator.call_count = 0
    _CountingShippingCalculator.call_count = 0
    cart.add(product, Decimal("100.00"), quantity=2)

    for _ in range(4):
        cart.total()

    assert _CountingTaxCalculator.call_count == 1
    assert _CountingShippingCalculator.call_count == 1


def test_add_invalidates_tax_and_shipping_caches(cart, product, settings):
    """A mutation must reset the tax / shipping cache — otherwise the
    template's subtotal updates but the tax line stays stale."""
    settings.CART_TAX_CALCULATOR = "tests.test_cart_caching._CountingTaxCalculator"
    settings.CART_SHIPPING_CALCULATOR = (
        "tests.test_cart_caching._CountingShippingCalculator"
    )
    _CountingTaxCalculator.call_count = 0
    _CountingShippingCalculator.call_count = 0
    cart.add(product, Decimal("10.00"), quantity=1)
    cart.tax()
    cart.shipping()

    cart.add(product, Decimal("10.00"), quantity=1)

    cart.tax()
    cart.shipping()
    assert _CountingTaxCalculator.call_count == 2
    assert _CountingShippingCalculator.call_count == 2


def test_discount_amount_is_cached_across_calls(cart, product):
    """Cheap to compute (one Decimal multiplication) but still worth
    caching: it runs inside ``total()`` and a template rendering
    'you saved $X' alongside total shouldn't re-multiply per field."""
    from cart.models import Discount, DiscountType

    Discount.objects.create(
        code="CACHE20",
        discount_type=DiscountType.PERCENT,
        value=Decimal("20.00"),
    )
    cart.add(product, Decimal("100.00"), quantity=2)
    cart.apply_discount("CACHE20")

    # Patch calculate_discount to count calls.
    original = Discount.calculate_discount
    Discount.calculate_discount.call_count = 0  # type: ignore[attr-defined]

    def counting_calculate_discount(self, c):
        counting_calculate_discount.call_count += 1  # type: ignore[attr-defined]
        return original(self, c)

    counting_calculate_discount.call_count = 0  # type: ignore[attr-defined]
    Discount.calculate_discount = counting_calculate_discount  # type: ignore[method-assign]
    try:
        for _ in range(5):
            cart.discount_amount()
        assert counting_calculate_discount.call_count == 1  # type: ignore[attr-defined]
    finally:
        Discount.calculate_discount = original  # type: ignore[method-assign]
