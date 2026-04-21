"""Minimal cart views for HTTP integration testing.

These views exist solely to exercise the library through the full
Django request pipeline (URL → middleware → view → Cart) from
tests/test_http_integration.py. They mirror the shape the README
advertises for downstream implementers but return JSON instead of
rendering templates so test assertions stay trivial.

Not part of the public django-cart API; not exported from the package.
"""
from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from cart.cart import Cart, InvalidQuantity, ItemDoesNotExist
from tests.test_app.models import FakeProduct


def _payload(cart: Cart) -> dict:
    return {
        "count": cart.count(),
        "unique_count": cart.unique_count(),
        "summary": str(cart.summary()),
        "is_empty": cart.is_empty(),
        "checked_out": cart.cart.checked_out,
        "items": cart.cart_serializable(),
    }


@require_GET
def cart_detail(request):
    cart = Cart(request)
    return JsonResponse(_payload(cart))


@require_POST
def cart_add(request, product_id: int):
    product = get_object_or_404(FakeProduct, pk=product_id)
    quantity = int(request.POST.get("quantity", 1))
    cart = Cart(request)
    try:
        cart.add(product, unit_price=product.price, quantity=quantity)
    except InvalidQuantity as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(_payload(cart))


@require_POST
def cart_remove(request, product_id: int):
    product = get_object_or_404(FakeProduct, pk=product_id)
    cart = Cart(request)
    try:
        cart.remove(product)
    except ItemDoesNotExist as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    return JsonResponse(_payload(cart))


@require_POST
def cart_update(request, product_id: int):
    product = get_object_or_404(FakeProduct, pk=product_id)
    quantity = int(request.POST.get("quantity", 1))
    cart = Cart(request)
    try:
        cart.update(product, quantity=quantity)
    except ItemDoesNotExist as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except InvalidQuantity as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(_payload(cart))


@require_POST
def cart_checkout(request):
    cart = Cart(request)
    cart.checkout()
    return JsonResponse(_payload(cart))
