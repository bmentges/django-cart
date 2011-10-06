# Introduction

django-cart is a very simple application that just let you add and remove items from a session based cart. django-cart uses the power of the Django content type framework to enable you to have your own Product model and associate with the cart without having to change anything. Please refer to the tests to see how it's done.

# Prerequisites

- Django 1.1+
- django content type framework in your INSTALLED_APPS

# Installation

Add 'cart' to your installed apps

# Usage

A basic usage of django-cart could be (example):

```python
# views.py
from cart import Cart
from myproducts.models import Product

def add_to_cart(request, product_id, quantity):
    product = Product.objects.get(id=product_id)
    cart = Cart(request)
    cart.add(product, product.unit_price, quantity)

def remove_from_cart(request, product_id):
    product = Product.objects.get(id=product_id)
    cart = Cart(request)
    cart.remove(product)

def get_cart(request):
    return render_to_response('cart.html', dict(cart=Cart(request)))
```

```django
# templates/cart.html
{% extends 'base.html' %}

{% block body %}
    <table>
        <tr>
            <th>Product</th>
            <th>Quantity</th>
            <th>Total Price</th>
        </tr>
        {% for item in cart %}
        <tr>
            <td>{{ item.product.name }}</td>
            <td>{{ item.quantity }}</td>
            <td>{{ item.total_price }}</td>
        </tr>
        {% endfor %}
    </table>
{% endblock %}
```

# Some Info

This project was abandoned and I got it and added tests and South migrations, and I will be maintaining it from now on. 

# Known Problems

Right now the main problem is that it adds a database record for each cart it creates. I'm in the process of studying this and will soon implement something to handle it.

- Bruno Carvalho
