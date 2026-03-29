![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/bmentges/django-cart/ci.yml?style=for-the-badge&logo=github&logoColor=white&logoSize=auto&label=CI%2FCD%20Build%3A)  ![PyPI - Version](https://img.shields.io/pypi/v/django-cart?style=for-the-badge&logo=pypi&logoColor=white&logoSize=auto&label=PYPI%20Latest%20Version%3A)

# django-cart

A simple, session-backed shopping cart for **modern Django (4.2+)** and **Python 3.10+**.

django-cart uses Django's [content-type framework](https://docs.djangoproject.com/en/stable/ref/contrib/contenttypes/) so you can use **any** model as a product — no changes required to your existing code.

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Cart API Reference](#cart-api-reference)
- [Template Example](#template-example)
- [Cleaning Old Carts](#cleaning-old-carts)
- [Scheduling with Cron](#scheduling-with-cron)
- [Running the Tests](#running-the-tests)
- [Changelog](#changelog)

---

## Features

- Session-linked cart backed by a lightweight DB record
- Works with any product model via Django's generic foreign keys
- `add`, `remove`, `update`, `clear`, `checkout` operations
- `count`, `summary`, `is_empty`, `cart_serializable` helpers
- Management command `clean_carts` with configurable retention window
- Full test suite covering success, error, and edge cases

---

## Requirements

| Dependency | Version |
|---|---|
| Python | 3.10+ |
| Django | 4.2+ |

The `django.contrib.contenttypes` app must be in `INSTALLED_APPS` (it is by default).

---

## Installation

```bash
pip install django-cart
```

Then add `cart` to `INSTALLED_APPS` in your `settings.py`:

```python
INSTALLED_APPS = [
    ...
    "django.contrib.contenttypes",  # must be present
    "cart",
]
```

Run the migrations:

```bash
python manage.py migrate cart
```

---

## Quick Start

### 1. Add to your views

```python
# views.py
from decimal import Decimal
from django.shortcuts import get_object_or_404, redirect, render

from cart.cart import Cart, ItemDoesNotExist, InvalidQuantity
from shop.models import Product  # your own product model


def cart_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    quantity = int(request.POST.get("quantity", 1))
    cart = Cart(request)
    cart.add(product, unit_price=product.price, quantity=quantity)
    return redirect("cart_detail")


def cart_remove(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    cart = Cart(request)
    try:
        cart.remove(product)
    except ItemDoesNotExist:
        pass  # already gone — not an error in most UX flows
    return redirect("cart_detail")


def cart_update(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    quantity = int(request.POST.get("quantity", 1))
    cart = Cart(request)
    try:
        cart.update(product, quantity=quantity)
    except InvalidQuantity:
        pass
    return redirect("cart_detail")


def cart_detail(request):
    cart = Cart(request)
    return render(request, "cart/detail.html", {"cart": cart})


def cart_checkout(request):
    cart = Cart(request)
    # … process payment …
    cart.checkout()
    return redirect("order_complete")
```

### 2. URL configuration

```python
# urls.py
from django.urls import path
from shop import views

urlpatterns = [
    path("cart/", views.cart_detail, name="cart_detail"),
    path("cart/add/<int:product_id>/", views.cart_add, name="cart_add"),
    path("cart/remove/<int:product_id>/", views.cart_remove, name="cart_remove"),
    path("cart/update/<int:product_id>/", views.cart_update, name="cart_update"),
    path("cart/checkout/", views.cart_checkout, name="cart_checkout"),
]
```

---

## Cart API Reference

```python
from cart.cart import Cart, ItemDoesNotExist, InvalidQuantity

cart = Cart(request)
```

| Method / Property | Description |
|---|---|
| `cart.add(product, unit_price, quantity=1)` | Add a product. If already present, increments quantity and updates price. Raises `InvalidQuantity` if quantity < 1. |
| `cart.remove(product)` | Remove a product entirely. Raises `ItemDoesNotExist` if not in cart. |
| `cart.update(product, quantity, unit_price=None)` | Set exact quantity (0 removes the item). Raises `ItemDoesNotExist` or `InvalidQuantity`. |
| `cart.count()` | Total number of **units** across all items. |
| `cart.unique_count()` | Number of distinct products. |
| `cart.summary()` | Grand total as `Decimal`. |
| `cart.is_empty()` | `True` if the cart has no items. |
| `cart.clear()` | Delete all items (keeps the cart record). |
| `cart.checkout()` | Mark the cart as checked out. |
| `cart.cart_serializable()` | Returns a JSON-safe `dict` keyed by `object_id`. |
| `product in cart` | `True` if the product is in the cart (`__contains__`). |
| `len(cart)` | Equivalent to `cart.count()`. |
| `for item in cart` | Iterate over `Item` instances. |

Each `Item` exposes:

```python
item.product        # the product instance (via generic FK)
item.quantity       # int
item.unit_price     # Decimal
item.total_price    # Decimal  (quantity × unit_price)
```

---

## Template Example

```html
{# templates/cart/detail.html #}
{% extends "base.html" %}

{% block content %}
<h1>Your Cart</h1>

{% if cart.is_empty %}
  <p>Your cart is empty.</p>
{% else %}
  <table>
    <thead>
      <tr>
        <th>Product</th>
        <th>Unit Price</th>
        <th>Qty</th>
        <th>Total</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      {% for item in cart %}
      <tr>
        <td>{{ item.product.name }}</td>
        <td>{{ item.unit_price }}</td>
        <td>{{ item.quantity }}</td>
        <td>{{ item.total_price }}</td>
        <td>
          <a href="{% url 'cart_remove' item.product.pk %}">Remove</a>
        </td>
      </tr>
      {% endfor %}
    </tbody>
    <tfoot>
      <tr>
        <td colspan="3"><strong>Total</strong></td>
        <td colspan="2"><strong>{{ cart.summary }}</strong></td>
      </tr>
    </tfoot>
  </table>

  <a href="{% url 'cart_checkout' %}">Proceed to Checkout</a>
{% endif %}
{% endblock %}
```

---

## Cleaning Old Carts

Over time, abandoned sessions leave orphaned `Cart` rows in your database. The `clean_carts` management command removes them.

### Basic usage

Delete all **unchecked-out** carts older than 90 days (the default):

```bash
python manage.py clean_carts
```

### Custom retention window

Delete abandoned carts older than 30 days:

```bash
python manage.py clean_carts --days 30
```

### Include checked-out carts

Remove *all* carts older than 60 days, including those that were checked out:

```bash
python manage.py clean_carts --days 60 --include-checked-out
```

### Dry run

Preview what would be deleted without actually deleting anything:

```bash
python manage.py clean_carts --days 30 --dry-run
# [DRY RUN] Would delete 142 cart(s) older than 30 day(s).
```

### All options

| Flag | Default | Description |
|---|---|---|
| `--days N` | `90` | Delete carts older than N days |
| `--include-checked-out` | off | Also delete checked-out carts |
| `--dry-run` | off | Preview only — no deletions |

---

## Scheduling with Cron

Run `clean_carts` automatically so your database stays clean without manual intervention.

### Standard crontab

Open your crontab:

```bash
crontab -e
```

Add a line. For example, to run every day at 2:00 AM and delete carts older than 30 days:

```cron
0 2 * * * /path/to/venv/bin/python /path/to/project/manage.py clean_carts --days 30 >> /var/log/clean_carts.log 2>&1
```

Replace `/path/to/venv` and `/path/to/project` with the actual paths on your server.

### With environment variables

If your Django project needs environment variables (e.g. `DATABASE_URL`), load them before calling the command:

```cron
0 2 * * * /bin/bash -c 'source /etc/environment && /path/to/venv/bin/python /path/to/project/manage.py clean_carts --days 30' >> /var/log/clean_carts.log 2>&1
```

### Using a Makefile target (optional convenience)

```makefile
.PHONY: clean-carts
clean-carts:
    python manage.py clean_carts --days 30
```

### Django management commands from Celery (alternative)

If you already use [Celery Beat](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html) for periodic tasks you can call the command from a task instead:

```python
# tasks.py
from celery import shared_task
from django.core.management import call_command

@shared_task
def clean_old_carts():
    call_command("clean_carts", days=30)
```

---

## Running the Tests

Install the development dependencies:

```bash
pip install django
```

Run all tests with the standalone runner:

```bash
python runtests.py
```

Run a specific test class:

```bash
python runtests.py tests.test_cart.CartAddTest
```

The test suite covers:

- `CartModel` — creation, ordering, defaults
- `ItemManager` — filter/get by product instance
- `Item` model — `total_price`, `unique_together` constraint
- `Cart` class — all public methods (success, error, and edge cases)
- `clean_carts` command — deletion, dry-run, boundary conditions, cascade behaviour

---

## Running Code Coverage

Install coverage tool:

```bash
pip install coverage
```

Run tests with coverage:

```bash
coverage run runtests.py
```

Generate a coverage report in the terminal:

```bash
coverage report
```

Generate an HTML coverage report (results saved to `htmlcov/`):

```bash
coverage html
```

Open the HTML report in your browser:

```bash
open htmlcov/index.html  # macOS
# or
xdg-open htmlcov/index.html  # Linux
# or
start htmlcov/index.html  # Windows
```

---

## Changelog

### v2.2.12

- Update Changelog section in README.md with all tags from v2.0.0 to v2.2.11

### v2.2.11

- Fix SonarCloud coverage path issue - add step to replace GitHub workspace paths in coverage.xml

### v2.2.10

- (tag only)

### v2.2.9

- Add sonar-project.properties for SonarCloud configuration
- Fix SonarCloud CI integration

### v2.2.8

- Fix SonarCloud action inputs in CI workflow

### v2.2.7

- Fix SonarCloud configuration in CI - pass SONAR_PROJECT_KEY and SONAR_ORGANIZATION

### v2.2.6

- Add SonarCloud integration to CI workflow

### v2.2.5

- Remove unused tests placeholder file (cart/tests.py)
- 100% code coverage achieved

### v2.2.4

- Add coverage tool to dev dependencies
- Create .coveragerc configuration
- Add README section for running code coverage
- Add 11 admin tests covering CartAdmin and ItemInline
- Add 18 new tests for edge cases
- Test count increased from 63 to 92
- Code coverage increased to 79%

### v2.2.3

- Fixing tag (version bump)

### v2.2.2

- Replace deprecated get_object_for_this_type with model_class().objects.get()
- Remove total_price from ItemInline.readonly_fields (computed property optimization)

### v2.2.1

- Fix ContentType lookup for proxy model support - use product._meta.model instead of type(product)

### v2.2.0

- Refactor test infrastructure
- Remove FakeProduct model from cart migration
- Create dedicated test_app with FakeProduct model
- Add fixture file with sample test products

### v2.1.0

- Fix race conditions in Cart.add() and Cart.update() with atomic transactions
- Add CartAtomicTest with 6 tests for atomic behavior

### v2.0.0

- Dropped Python 2 / Django < 4.2 support
- Replaced `ugettext_lazy` → `gettext_lazy`
- Replaced `__unicode__` → `__str__`
- Replaced `import models` → `from . import models` (relative import)
- `Cart.new()` → private `Cart._new()`; `creation_date` now uses `timezone.now()` instead of `datetime.datetime.now()`
- `Item.item_set` → `Item.items` (`related_name="items"`)
- Added `unique_together` constraint on `(cart, content_type, object_id)`
- Added `__contains__`, `__len__` to `Cart`
- Added `unique_count()`, `checkout()` methods
- `cart_serializable()` now includes `unit_price`
- `update()` no longer silently ignores `unit_price=None` — only updates price when explicitly provided
- Added `InvalidQuantity` exception; `add()` and `update()` now validate quantities
- Added `clean_carts` management command
- Full test suite added
