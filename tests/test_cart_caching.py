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
