from decimal import Decimal

from django import template
from django.conf import settings
from django.db.models import F, Sum
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html

from ..cart import CART_ID
from ..models import Item

register = template.Library()


def _session_cart_id(request) -> int | None:
    """Read CART-ID from the request session without touching the ORM.

    Read-only template tags share this helper so a render on a fresh
    visitor (no CART-ID yet) is a zero-query zero-mutation path —
    crucially, it does not call ``Cart(request)`` and therefore does
    not materialise a :class:`cart.models.Cart` row (P1-C, v3.0.13).
    """
    if request is None:
        return None
    session = getattr(request, "session", None)
    if session is None:
        return None
    return session.get(CART_ID)


@register.simple_tag(takes_context=True)
def cart_item_count(context) -> int:
    """
    Return the total number of items in the cart.

    Usage::

        {% load cart_tags %}
        {% cart_item_count %}
    """
    cart_id = _session_cart_id(context.get("request"))
    if not cart_id:
        return 0
    total = Item.objects.filter(
        cart_id=cart_id,
        cart__checked_out=False,
    ).aggregate(
        total=Sum("quantity")
    )["total"]
    return total or 0


@register.simple_tag(takes_context=True)
def cart_summary(context) -> str:
    """
    Return a formatted string with the cart total.

    Usage::

        {% load cart_tags %}
        {% cart_summary %}
    """
    cart_id = _session_cart_id(context.get("request"))
    if not cart_id:
        return "$0.00"
    total = Item.objects.filter(
        cart_id=cart_id,
        cart__checked_out=False,
    ).aggregate(
        total=Sum(F("quantity") * F("unit_price"))
    )["total"]
    return f"${total or Decimal('0.00'):.2f}"


@register.simple_tag(takes_context=True)
def cart_is_empty(context) -> bool:
    """
    Return True if the cart is empty.

    Usage::

        {% load cart_tags %}
        {% cart_is_empty %}
    """
    cart_id = _session_cart_id(context.get("request"))
    if not cart_id:
        return True
    return not Item.objects.filter(
        cart_id=cart_id,
        cart__checked_out=False,
    ).exists()


@register.simple_tag(takes_context=True)
def cart_link(context, text: str = "View Cart", css_class: str = "") -> str:
    """
    Return an HTML link to the cart page.

    When ``CART_DETAIL_URL_NAME`` is defined in settings, the URL is
    resolved via :func:`django.urls.reverse`. Otherwise (and on a
    ``NoReverseMatch``), the tag falls back to the static ``"/cart/"``
    default so a misconfigured URL name doesn't break the surrounding
    template render.

    The cart's primary key is never embedded in the URL — pre-v3.0.13
    the tag emitted ``/cart/{id}/`` and leaked sequential ids to
    referrers, analytics, and third-party scripts (P1-C).

    Usage::

        {% load cart_tags %}
        {% cart_link "Go to Cart" "btn btn-primary" %}
    """
    url_name = getattr(settings, "CART_DETAIL_URL_NAME", None)
    cart_url = "/cart/"
    if url_name:
        try:
            cart_url = reverse(url_name)
        except NoReverseMatch:
            pass

    if css_class:
        return format_html('<a href="{}" class="{}">{}</a>', cart_url, css_class, text)
    return format_html('<a href="{}">{}</a>', cart_url, text)
