from django.contrib import admin
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
