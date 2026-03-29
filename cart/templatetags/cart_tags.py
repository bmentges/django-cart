from decimal import Decimal

from django import template
from django.utils.html import format_html

from ..cart import Cart

register = template.Library()


@register.simple_tag(takes_context=True)
def cart_item_count(context) -> int:
    """
    Return the total number of items in the cart.

    Usage::

        {% load cart_tags %}
        {{ cart_item_count }}
    """
    request = context.get("request")
    if request is None:
        return 0
    cart = Cart(request)
    return cart.count()


@register.simple_tag(takes_context=True)
def cart_summary(context) -> str:
    """
    Return a formatted string with the cart total.

    Usage::

        {% load cart_tags %}
        {{ cart_summary }}
    """
    request = context.get("request")
    if request is None:
        return "$0.00"
    cart = Cart(request)
    return f"${cart.summary():.2f}"


@register.simple_tag(takes_context=True)
def cart_is_empty(context) -> bool:
    """
    Return True if the cart is empty.

    Usage::

        {% load cart_tags %}
        {% if cart_is_empty %}
            <p>Your cart is empty</p>
        {% endif %}
    """
    request = context.get("request")
    if request is None:
        return True
    cart = Cart(request)
    return cart.is_empty()


@register.simple_tag(takes_context=True)
def cart_link(context, text: str = "View Cart", css_class: str = "") -> str:
    """
    Return an HTML link to the cart page.

    Usage::

        {% load cart_tags %}
        {{ cart_link "Go to Cart" "btn btn-primary" }}
    """
    request = context.get("request")
    if request is None:
        cart_url = "/cart/"
    else:
        cart = Cart(request)
        cart_id = request.session.get("CART-ID", "")
        cart_url = f"/cart/{cart_id}/" if cart_id else "/cart/"

    if css_class:
        return format_html('<a href="{}" class="{}">{}</a>', cart_url, css_class, text)
    return format_html('<a href="{}">{}</a>', cart_url, text)
