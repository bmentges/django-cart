"""Performance invariants for cart operations.

These tests assert query-count bounds, not wall-clock timings. Query
counts are reproducible across hardware, machine load, and Python
versions; wall clock is not. If a change regresses the query profile
(introduces an N+1, drops ``select_related``, caches badly) the test
fails loudly with a bounded number.

The bounds are upper bounds — passing with fewer queries is fine. If a
future change lowers the steady-state count (e.g. a batch product
loader for ``Cart.__iter__``), tighten the bound in the same PR.
"""
from __future__ import annotations

from decimal import Decimal

import pytest


def test_add_is_query_bounded_per_item(
    cart, product_factory, django_assert_max_num_queries
):
    """50 sequential ``cart.add()`` calls must stay linear in queries.

    Current profile (v3.0.4) per add: ``_get_item`` SELECT, ``Item``
    INSERT, plus two SAVEPOINT statements from the ``transaction.atomic``
    block. Upper bound of 250 leaves ~5 queries per add of headroom —
    tight enough to catch a regression that (say) drops the atomic block
    in favour of multiple transactions, or adds a ``ContentType.get``
    per call. 250 / 50 = 5 queries/add average ceiling.
    """
    products = [product_factory(name=f"PerfAdd{i}") for i in range(50)]

    with django_assert_max_num_queries(250):
        for p in products:
            cart.add(p, Decimal("10.00"), quantity=1)

    assert cart.count() == 50


def test_summary_is_a_single_aggregate_query(
    cart, product_factory, django_assert_num_queries
):
    """``cart.summary()`` on N items must issue exactly one aggregate query.

    Regressions this test catches: computing the total in Python instead
    of via ``Sum(F(...) * F(...))``, fetching every item row to total it
    up, removing the cache (which would turn a second call into another
    query but wouldn't break this test — see the cache-specific tests
    for that).
    """
    for i in range(100):
        cart.add(product_factory(name=f"PerfSum{i}"), Decimal("10.00"))

    cart._invalidate_cache()

    with django_assert_num_queries(1):
        summary = cart.summary()

    assert summary == Decimal("1000.00")


def test_iteration_is_query_bounded_independent_of_item_count(
    cart, product_factory, django_assert_max_num_queries
):
    """Iterating over all items must be O(1) queries, not O(N).

    Current profile (v3.0.4): ``Cart.__iter__`` issues a single
    ``select_related('content_type')`` SELECT for the full item set.
    ``list(cart)`` additionally triggers ``Cart.__len__`` (CPython asks
    ``__len__`` for a pre-allocation hint), which invokes ``count()`` —
    one aggregate query. So ``list(cart)`` = 2 queries regardless of
    item count.

    The upper bound of 3 catches any N+1 regression (e.g. dropping
    ``select_related`` on ``__iter__``, or someone adding a per-item
    ``Item.product`` fetch inside the iteration path). If a future
    batch-loader lowers the count, tighten this bound in the same PR.
    """
    for i in range(50):
        cart.add(product_factory(name=f"PerfIter{i}"), Decimal("10.00"))

    with django_assert_max_num_queries(3):
        items = list(cart)

    assert len(items) == 50
