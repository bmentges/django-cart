"""Template tags declared in cart.templatetags.cart_tags.

Covers the four tags: cart_item_count, cart_summary, cart_is_empty,
cart_link.

NOTE: these tests invoke the tag callables directly rather than rendering
real templates via ``Template(...).render(...)``. The direct-call path
exercises the function body but skips template-engine concerns (``{% load
%}`` resolution, ``takes_context=True`` wiring, parse-time argument
handling). End-to-end template-render coverage is owned by P0-5 (README
template-tag examples wrong) and will be added in v3.0.16 alongside the
README fix — see docs/ROADMAP_2026_04.md.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.template import Context

from cart.templatetags.cart_tags import (
    cart_is_empty,
    cart_item_count,
    cart_link,
    cart_summary,
)


@pytest.fixture
def context_with_request(rf_request):
    """Template context with ``rf_request`` attached — what ``takes_context=True`` sees."""
    return Context({"request": rf_request})


@pytest.fixture
def context_without_request():
    """Template context with no request — simulates tag use outside a request cycle."""
    return Context({})


# --------------------------------------------------------------------------- #
# cart_item_count
# --------------------------------------------------------------------------- #

def test_cart_item_count_returns_zero_for_empty_cart(db, context_with_request):
    assert cart_item_count(context_with_request) == 0


def test_cart_item_count_returns_actual_count(cart, product, context_with_request):
    cart.add(product, unit_price=Decimal("9.99"), quantity=3)

    assert cart_item_count(context_with_request) == 3


def test_cart_item_count_returns_zero_when_context_has_no_request(context_without_request):
    assert cart_item_count(context_without_request) == 0


# --------------------------------------------------------------------------- #
# cart_summary
# --------------------------------------------------------------------------- #

def test_cart_summary_returns_zero_dollars_for_empty_cart(db, context_with_request):
    assert cart_summary(context_with_request) == "$0.00"


def test_cart_summary_returns_formatted_total(cart, product, context_with_request):
    cart.add(product, unit_price=Decimal("9.99"), quantity=2)

    assert cart_summary(context_with_request) == "$19.98"


def test_cart_summary_returns_zero_dollars_when_context_has_no_request(
    context_without_request,
):
    assert cart_summary(context_without_request) == "$0.00"


# --------------------------------------------------------------------------- #
# cart_is_empty
# --------------------------------------------------------------------------- #

def test_cart_is_empty_returns_true_for_empty_cart(db, context_with_request):
    assert cart_is_empty(context_with_request) is True


def test_cart_is_empty_returns_false_for_nonempty_cart(cart, product, context_with_request):
    cart.add(product, unit_price=Decimal("9.99"), quantity=1)

    assert cart_is_empty(context_with_request) is False


def test_cart_is_empty_returns_true_when_context_has_no_request(context_without_request):
    assert cart_is_empty(context_without_request) is True


# --------------------------------------------------------------------------- #
# cart_link
# --------------------------------------------------------------------------- #

def test_cart_link_returns_default_anchor(db, context_with_request):
    result = cart_link(context_with_request)

    assert '<a href="/cart/' in result
    assert '>View Cart</a>' in result


def test_cart_link_accepts_custom_text(db, context_with_request):
    result = cart_link(context_with_request, text="Go to Cart")

    assert '>Go to Cart</a>' in result


def test_cart_link_accepts_css_class(db, context_with_request):
    result = cart_link(context_with_request, text="Cart", css_class="btn btn-primary")

    assert 'class="btn btn-primary"' in result


def test_cart_link_falls_back_to_root_when_context_has_no_request(context_without_request):
    result = cart_link(context_without_request)

    assert '<a href="/cart/">View Cart</a>' in result
