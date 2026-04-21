"""Django admin integration for Cart — HTTP-level behavioural tests.

Replaces the legacy CartAdminTest / ItemInlineTest / CartAdminOperationsTest
classes which were almost entirely configuration-reflection
(``admin.list_display`` / ``admin.readonly_fields`` / ``admin.model ==
Item`` etc.) plus a handful of RequestFactory unit tests of admin
internals. Per §P-1 delete list, those are retired; this file exercises
the actual user-facing admin surface via the Django test client.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cart.models import Cart as CartModel

pytestmark = pytest.mark.django_db


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
    """Search must actually filter — pre-v3.0.14 the admin had no
    ``search_fields`` so ``?q=`` was a no-op and the changelist
    returned every cart regardless. The assertion below (noise excluded)
    would've passed vacuously on master because the changelist returned
    both carts unfiltered. Searching by the id in the target row must
    keep the target and drop the noise."""
    import re

    CartModel.objects.all().delete()
    target = CartModel.objects.create()
    noise = CartModel.objects.create()

    response = superuser_client.get("/admin/cart/cart/", {"q": str(target.pk)})

    assert response.status_code == 200
    # Django 6.0 appends ``?_changelist_filters=…`` to change-links when
    # a filter is active, so a literal-string check wouldn't match.
    # Scan for the pk segment and compare.
    change_pks = set(
        re.findall(r"/admin/cart/cart/(\d+)/change/", response.content.decode())
    )
    assert str(target.pk) in change_pks
    assert str(noise.pk) not in change_pks


def test_cart_admin_changelist_filters_by_checked_out(superuser_client):
    CartModel.objects.all().delete()
    CartModel.objects.create(checked_out=False)
    checked = CartModel.objects.create(checked_out=True)

    response = superuser_client.get("/admin/cart/cart/", {"checked_out__exact": "1"})

    assert response.status_code == 200
    assert str(checked.pk).encode() in response.content
