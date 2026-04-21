from django.contrib import admin
from django.http import HttpResponse
from django.urls import path

from tests.test_app import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cart/", views.cart_detail, name="cart_detail"),
    path("cart/add/<int:product_id>/", views.cart_add, name="cart_add"),
    path("cart/remove/<int:product_id>/", views.cart_remove, name="cart_remove"),
    path("cart/update/<int:product_id>/", views.cart_update, name="cart_update"),
    path("cart/checkout/", views.cart_checkout, name="cart_checkout"),
]


def _bare_404(request, exception=None):
    # Django's default page_not_found view renders a template, which
    # fires the template_rendered signal. The test client's
    # store_rendered_templates handler copies the template Context via
    # Context.__copy__ — which on Python 3.14 + Django <6.0 raises
    # AttributeError because Django assigns to a super() proxy that
    # Py3.14 no longer permits. Returning a bare response here skips
    # template rendering entirely, dodging the bug. Not a django-cart
    # issue; fixed in Django 6.0. Safe for our test suite because no
    # existing test asserts on default 404 HTML output.
    return HttpResponse(status=404)


handler404 = _bare_404
