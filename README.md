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
- [Django Signals](#django-signals)
- [Template Tags](#template-tags)
- [Session Adapters](#session-adapters)
- [Cleaning Old Carts](#cleaning-old-carts)
- [Scheduling with Cron](#scheduling-with-cron)
- [Running the Tests](#running-the-tests)

---

## Features

- Session-linked cart backed by a lightweight DB record
- Works with any product model via Django's generic foreign keys
- `add`, `remove`, `update`, `clear`, `checkout` operations
- `count`, `summary`, `is_empty`, `cart_serializable` helpers
- **Django signals** for extensibility (item added, removed, updated, cart checked out, cart cleared)
- **Template tags** for easy cart display in templates (item count, summary, is_empty, cart link)
- **Session adapters** for flexible session storage (Django sessions, cookies)
- **Cart merge** with configurable strategies (add, replace, keep_higher)
- **User binding** to persist carts to user accounts
- **Bulk operations** for efficient multiple item management
- **Maximum quantity limits** per item via settings
- Management command `clean_carts` with configurable retention window
- Full test suite (209 tests) covering success, error, integration, and performance cases
- Type hints for full IDE and static analysis support
- Product caching to avoid N+1 queries when iterating
- Pre-commit hooks for code quality (black, isort, flake8, mypy)
- Automated dependency updates via Dependabot

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
| `cart.merge(other_cart, strategy)` | Merge another cart into this one. |
| `cart.bind_to_user(user)` | Bind cart to a user account. |
| `cart.add_bulk(items)` | Add multiple items efficiently. |
| `Cart.get_user_carts(user)` | Get all carts for a user. |
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

## Django Signals

django-cart emits Django signals at key cart events, enabling easy integration with analytics, notifications, and custom logic.

### Available Signals

| Signal | Description |
|---|---|
| `cart_item_added` | Emitted when an item is added to the cart |
| `cart_item_removed` | Emitted when an item is removed from the cart |
| `cart_item_updated` | Emitted when an item quantity is updated |
| `cart_checked_out` | Emitted when checkout is completed |
| `cart_cleared` | Emitted when the cart is cleared |

### Signal Payloads

All signals provide the same sender (`Cart` instance) and keyword arguments:
- `cart`: The cart instance
- `product`: The product instance
- `quantity`: The quantity involved
- `unit_price`: The unit price
- `total_price`: The total price for the item

### Example: Connect a Signal Handler

```python
# signals.py
from django.dispatch import receiver
from cart.signals import cart_item_added, cart_item_removed, cart_checked_out


@receiver(cart_item_added)
def log_cart_addition(sender, cart, product, quantity, unit_price, total_price, **kwargs):
    print(f"Added {quantity}x {product} to cart (total: {total_price})")
    # Track analytics, send notifications, etc.


@receiver(cart_item_removed)
def log_cart_removal(sender, cart, product, **kwargs):
    print(f"Removed {product} from cart")


@receiver(cart_checked_out)
def handle_checkout(sender, cart, **kwargs):
    print(f"Cart {cart.id} checked out with total: {cart.summary}")
    # Trigger order processing, send confirmation email, etc.
```

### Connecting Signals

In your Django app's `ready` method:

```python
# myapp/apps.py
from django.apps import AppConfig


class MyAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "myapp"

    def ready(self):
        import myapp.signals  # noqa: F401
```

### Signals Are Optional

The cart works perfectly fine without signals. If the signals module is not available, cart operations continue without errors.

---

## Template Tags

django-cart provides template tags for easy cart display in your templates.

### Loading Template Tags

```html
{% load cart_tags %}
```

### Available Tags

#### `cart_item_count`

Returns the total number of items in the cart:

```html
<p>Items in cart: {% cart_item_count request %}</p>
```

#### `cart_summary`

Returns the grand total of the cart:

```html
<p>Total: {% cart_summary request %}</p>
```

#### `cart_is_empty`

Returns `True` if the cart is empty:

```html
{% if cart_is_empty request %}
    <p>Your cart is empty</p>
{% else %}
    <a href="{% url 'cart_detail' %}">View Cart</a>
{% endif %}
```

#### `cart_link`

Renders a link to the cart with optional CSS class and text:

```html
{# Basic usage #}
{% cart_link request %}

{# With CSS class #}
{% cart_link request "btn btn-primary" %}

{# With custom text and CSS class #}
{% cart_link request "btn" "View Shopping Cart" %}
```

---

## Session Adapters

django-cart uses session adapters to store the cart ID in the session. You can use the built-in adapters or create custom ones.

### Available Adapters

| Adapter | Description |
|---|---|
| `DjangoSessionAdapter` | Stores cart ID in Django's default session backend |
| `CookieSessionAdapter` | Stores cart ID in a signed cookie (no server-side session required) |

### Using CookieSessionAdapter

```python
# settings.py
from cart.session import CookieSessionAdapter

CARTS_SESSION_ADAPTER_CLASS = CookieSessionAdapter
```

### Custom Session Adapter

Create your own adapter by subclassing `CartSessionAdapter`:

```python
# myapp/session.py
from cart.session import CartSessionAdapter


class RedisSessionAdapter(CartSessionAdapter):
    """Store cart ID in Redis instead of Django sessions."""

    def __init__(self, request):
        super().__init__(request)
        import redis
        self.redis = redis.Redis(host="localhost", port=6379)

    def _get_session_key(self):
        return f"cart:{self.request.session.session_key}"

    def _set_session_key(self, value):
        self.redis.set(self._get_session_key(), value)

    def _del_session_key(self):
        self.redis.delete(self._get_session_key())
```

Then configure it in settings:

```python
# settings.py
CARTS_SESSION_ADAPTER_CLASS = "myapp.session.RedisSessionAdapter"
```

### CartSessionAdapter API

All adapters must implement these methods:

| Method | Description |
|---|---|
| `get()` | Get the cart ID from storage |
| `set(cart_id)` | Store the cart ID |
| `delete()` | Remove the cart ID |
| `get_or_create_cart_id()` | Get existing or create new cart ID |
| `cart_id` (property) | Get or set cart ID via property |

---

## Cart Merge

django-cart supports merging guest carts with user carts when a user logs in.

### Merge Strategies

| Strategy | Description |
|---|---|
| `add` | Add quantities together (default) |
| `replace` | Use the other cart's quantities |
| `keep_higher` | Keep the higher quantity for duplicates |

### Example: Guest to User Login Flow

```python
# When a user logs in, merge their guest cart into their user cart
def login_view(request):
    user = authenticate(request)
    if user:
        login(request, user)
        
        # Get guest cart from session
        guest_cart = Cart(request)
        
        # Get or create user cart
        user_carts = Cart.get_user_carts(user)
        if user_carts.exists():
            user_cart = Cart(request)
            user_cart.cart = user_carts.first()
        else:
            user_cart = Cart(request)
            user_cart.bind_to_user(user)
        
        # Merge guest cart into user cart
        user_cart.merge(guest_cart, strategy='add')
        
        return redirect('dashboard')
```

### Merge API

```python
cart = Cart(request)
other_cart = Cart(other_request)

# Add quantities together (default)
cart.merge(other_cart)

# Replace with other cart's quantities
cart.merge(other_cart, strategy='replace')

# Keep higher quantity for duplicates
cart.merge(other_cart, strategy='keep_higher')
```

---

## User Binding

Persist carts to user accounts so they are available across sessions.

### Binding a Cart to a User

```python
cart = Cart(request)
user = request.user
cart.bind_to_user(user)
```

### Retrieving User Carts

```python
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.get(username='john')

# Get all carts for a user
user_carts = Cart.get_user_carts(user)
for cart in user_carts:
    print(f"Cart {cart.id}: {cart.items.count()} items")
```

### Guest to User Migration

```python
def on_user_login(request, user):
    # Get guest cart
    guest_cart = Cart(request)
    
    if not guest_cart.is_empty():
        # Get user's most recent cart or create new one
        user_carts = Cart.get_user_carts(user)
        if user_carts.exists():
            user_cart = Cart(request)
            user_cart.cart = user_carts.first()
        else:
            user_cart = Cart(request)
            user_cart.bind_to_user(user)
        
        # Merge guest cart into user cart
        user_cart.merge(guest_cart)
```

---

## Bulk Operations

Add or update multiple items efficiently with `add_bulk()`.

### Example

```python
cart = Cart(request)

items = [
    {'product': product1, 'unit_price': Decimal("10.00"), 'quantity': 2},
    {'product': product2, 'unit_price': Decimal("20.00"), 'quantity': 1},
    {'product': product3, 'unit_price': Decimal("30.00"), 'quantity': 3},
]

result = cart.add_bulk(items)
# Returns list of Item instances

print(f"Added {len(result)} items")
print(f"Total: {cart.summary()}")
```

### Bulk Update

`add_bulk()` also updates existing items:

```python
product = Product.objects.get(pk=1)

# If product already in cart, it will be updated
items = [
    {'product': product, 'unit_price': Decimal("15.00"), 'quantity': 5},
]

cart.add_bulk(items)
```

---

## Maximum Quantity Configuration

Limit the maximum quantity allowed per item using the `CART_MAX_QUANTITY_PER_ITEM` setting.

### Configuration

```python
# settings.py
CART_MAX_QUANTITY_PER_ITEM = 100  # Max 100 units per item
```

### Behavior

- Adding an item with quantity exceeding the limit raises `InvalidQuantity`
- Updating an item quantity above the limit raises `InvalidQuantity`
- If not set, any quantity is allowed (default behavior)

### Example

```python
# settings.py
CART_MAX_QUANTITY_PER_ITEM = 10

# In views
cart = Cart(request)
cart.add(product, Decimal("9.99"), quantity=5)  # OK

try:
    cart.add(product, Decimal("9.99"), quantity=15)  # Raises InvalidQuantity
except InvalidQuantity as e:
    print(e)  # "Quantity cannot exceed 10."
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
- `Item` model — `total_price`, `unique_together` constraint, unit price validation
- `Cart` class — all public methods (success, error, and edge cases)
- `Cart` class — atomic operations, session persistence, serialization
- `clean_carts` command — deletion, dry-run, boundary conditions, cascade behaviour
- Integration tests — session handling, cart operations, serialization
- Performance benchmarks — add, summary, and iteration timing
- Admin operations — changelist, search, and filtering
- Signals — cart_item_added, cart_item_removed, cart_item_updated, cart_checked_out, cart_cleared
- Template tags — cart_item_count, cart_summary, cart_is_empty, cart_link
- Session adapters — DjangoSessionAdapter, CookieSessionAdapter

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

## Developer Setup

### Pre-commit Hooks

This project uses pre-commit hooks to maintain code quality. Install them with:

```bash
pip install pre-commit
pre-commit install
```

The hooks include:
- **black** — Code formatting
- **isort** — Import sorting
- **flake8** — Linting
- **mypy** — Type checking

### Automated Dependencies

This project uses [Dependabot](.github/dependabot.yml) for automated dependency updates:
- Python packages (weekly schedule)
- GitHub Actions (weekly schedule)

### Performance Considerations

The cart uses product caching to avoid N+1 queries when iterating over items. The `Item.product` property caches the product instance on first access.

```python
# Efficient - single query per item, then cached
for item in cart:
    print(item.product.name)  # Cached after first access
```

### Serialization

The `cart_serializable()` method returns a JSON-safe dictionary for API responses:

```python
cart = Cart(request)
data = cart.cart_serializable()
# Returns: {'123': {'quantity': 2, 'unit_price': '9.99', 'total_price': '19.98'}, ...}
```


