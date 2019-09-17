# Introduction

[![Build Status](https://travis-ci.com/bmentges/django-cart.svg?branch=master)](https://travis-ci.com/bmentges/django-cart)

django-cart is a very simple application that just let you add and remove items from a session based cart. django-cart uses the power of the Django content type framework to enable you to have your own Product model and associate with the cart without having to change anything. Please refer to the tests to see how it's done.

## Prerequisites

- Django 1.1+
- django content type framework in your INSTALLED_APPS
- south for migrations (optional)

## Installation

To install this just type:

```
python setup.py install
```

or

```
pip install django-cart
```

After installation is complete:

1. add 'cart' to your INSTALLED_APPS directive and
2. If you have South migrations type: `./manage.py migrate cart`
3. or if you don't: `./manage.py makemigrations cart`

## Usage

A basic usage of django-cart could be (example):

```python
# views.py
from cart.cart import Cart
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
    return render(request, 'cart.html', {'cart': Cart(request)})
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

## Some Info

This project was abandoned and I got it and added tests and South migrations, and I will be maintaining it from now on.

## Known Problems

Right now the main problem is that it adds a database record for each cart it creates. I'm in the process of studying this and will soon implement something to handle it.


## A note on the authors of this project

This project is a fork of [django-cart](http://code.google.com/p/django-cart/ "django-cart") on Google Code. It was originally started by Eric Woudenberg and followed up by Marc Garcia <http://vaig.be>. The last change ocurred in March 25 2009, without any tests. My goal is to push this project a little further by adding tests to guarantee it's functionality and to fix the main issues. I intend to keep it as simple as it is.

- Bruno Carvalho
