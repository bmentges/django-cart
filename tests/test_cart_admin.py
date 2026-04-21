"""Django admin integration for Cart — HTTP-level behavioural tests.

Replaces the legacy CartAdminTest / ItemInlineTest / CartAdminOperationsTest
classes which were almost entirely configuration-reflection
(``admin.list_display`` / ``admin.readonly_fields`` / ``admin.model ==
Item`` etc.) plus a handful of RequestFactory unit tests of admin
internals. Per §P-1 delete list, those are retired; this file exercises
the actual user-facing admin surface via the Django test client.
"""
from __future__ import annotations

import sys
from decimal import Decimal

import django
import pytest

from cart.models import Cart as CartModel


# Django <6.0 Context.__copy__ assigns to a super() proxy, which Python
# 3.14 forbids. The test client's template-capture instrumentation fires
# it on every admin page render, so we can't cover admin via the Client
# on that combo. Not a django-cart bug; Django fixed Context.__copy__
# in 6.0. Coverage still runs on every other combo (py3.10–3.13 × all
# Django, and py3.14 × Django 6.0+).
_DJANGO_CONTEXT_COPY_BROKEN_ON_PY314 = (
    sys.version_info >= (3, 14) and django.VERSION[:2] < (6, 0)
)

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        _DJANGO_CONTEXT_COPY_BROKEN_ON_PY314,
        reason=(
            "Django <6.0 Context.__copy__ incompatible with Python 3.14 "
            "test-client instrumentation (assigns to super() proxy). "
            "Fixed in Django 6.0; unrelated to django-cart."
        ),
    ),
]


@pytest.fixture
def superuser_client(client, django_user_model):
    django_user_model.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="admin-pass-123",
    )
    client.login(username="admin", password="admin-pass-123")
    return client


def test_cart_admin_changelist_renders_for_superuser(superuser_client, cart, product):
    cart.add(product, Decimal("10.00"), quantity=2)

    response = superuser_client.get("/admin/cart/cart/")

    assert response.status_code == 200


def test_cart_admin_changelist_search_filters_by_cart_id(superuser_client):
    CartModel.objects.all().delete()
    target = CartModel.objects.create()
    CartModel.objects.create()  # noise

    response = superuser_client.get("/admin/cart/cart/", {"q": str(target.pk)})

    assert response.status_code == 200
    # Target appears in the changelist, the other cart should not.
    assert str(target.pk).encode() in response.content


def test_cart_admin_changelist_filters_by_checked_out(superuser_client):
    CartModel.objects.all().delete()
    CartModel.objects.create(checked_out=False)
    checked = CartModel.objects.create(checked_out=True)

    response = superuser_client.get("/admin/cart/cart/", {"checked_out__exact": "1"})

    assert response.status_code == 200
    assert str(checked.pk).encode() in response.content
