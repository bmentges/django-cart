"""Cart class initialisation and session wiring."""
from __future__ import annotations

import pytest
from django.test import RequestFactory

from cart.cart import CART_ID, Cart


pytestmark = pytest.mark.django_db


def test_new_cart_is_created_when_session_has_no_cart_id(rf_request):
    cart = Cart(rf_request)

    assert cart.cart.pk is not None
    assert rf_request.session[CART_ID] == cart.cart.pk


def test_cart_is_reused_across_two_cart_instances_on_same_session(rf_request):
    cart1 = Cart(rf_request)
    cart2 = Cart(rf_request)

    assert cart1.cart.pk == cart2.cart.pk


def test_new_cart_is_created_when_session_points_to_nonexistent_id():
    request = RequestFactory().get("/")
    request.session = {CART_ID: 99999}

    cart = Cart(request)

    assert cart.cart.pk != 99999


def test_new_cart_is_created_when_existing_cart_is_checked_out(rf_request):
    first = Cart(rf_request)
    first.cart.checked_out = True
    first.cart.save()

    second = Cart(rf_request)

    assert second.cart.pk != first.cart.pk


def test_session_id_is_written_back_on_cart_creation(rf_request):
    cart = Cart(rf_request)

    assert CART_ID in rf_request.session
    assert rf_request.session[CART_ID] == cart.cart.pk


def test_shared_session_yields_same_cart_across_requests():
    session = {}
    r1 = RequestFactory().get("/")
    r1.session = session
    r2 = RequestFactory().get("/")
    r2.session = session

    c1 = Cart(r1)
    c2 = Cart(r2)

    assert c1.cart.pk == c2.cart.pk
