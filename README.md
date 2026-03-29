![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/bmentges/django-cart/ci.yml?style=for-the-badge&logo=github&logoColor=white&logoSize=auto&label=CI%2FCD%20Build%3A)  ![PyPI - Version](https://img.shields.io/pypi/v/django-cart?style=for-the-badge&logo=pypi&logoColor=white&logoSize=auto&label=PYPI%20Latest%20Version%3A)

# django-cart

A lightweight, session-backed shopping cart for **Django e-commerce applications**. Built for developers who need a robust cart solution without the bloat of full e-commerce platforms.

**django-cart** uses Django's [content-type framework](https://docs.djangoproject.com/en/stable/ref/contrib/contenttypes/) to work with **any product model** — no modifications to your existing code required.

---

## Table of Contents

- [Why django-cart?](#why-django-cart)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Basic Usage](#basic-usage)
- [API Reference](#api-reference)
- [Advanced Features](#advanced-features)
  - [Discounts](#discounts)
  - [Tax Calculator](#tax-calculator)
  - [Shipping Calculator](#shipping-calculator)
  - [Inventory Checker](#inventory-checker)
  - [Cart Merge](#cart-merge)
  - [User Binding](#user-binding)
  - [Bulk Operations](#bulk-operations)
  - [Maximum Quantity Limits](#maximum-quantity-limits)
  - [Price Validation](#price-validation)
  - [Caching](#caching)
- [Template Integration](#template-integration)
- [Signals](#signals)
- [Session Adapters](#session-adapters)
- [Database Optimization](#database-optimization)
- [Maintenance](#maintenance)
- [Testing](#testing)
- [Developer Setup](#developer-setup)

---

## Why django-cart?

| Feature | Benefit |
|---------|---------|
| **Any Product Model** | Works with your existing models via generic foreign keys |
| **Session-Backed** | Lightweight storage, scales to multiple servers |
| **Atomic Operations** | Safe concurrent cart modifications |
| **Type Hints** | Full IDE support and static analysis |
| **Extensible** | Signals, hooks, and custom session adapters |
| **Production-Ready** | 290 tests, database indexes, cache support |

---

## Quick Start

```python
from cart.cart import Cart
from decimal import Decimal

# Add items to cart
cart = Cart(request)
cart.add(product, unit_price=product.price, quantity=2)

# Check cart status
cart.count()         # Total items (e.g., 5)
cart.summary()        # Total price (e.g., Decimal('99.99'))
cart.is_empty()       # Boolean

# Update quantities
cart.update(product, quantity=5)

# Remove items
cart.remove(product)

# Checkout
cart.checkout()
```

---

## Installation

```bash
pip install django-cart
```

Add to `INSTALLED_APPS` in `settings.py`:

```python
INSTALLED_APPS = [
    ...
    "django.contrib.contenttypes",  # Required (default in Django)
    "cart",
]
```

Run migrations:

```bash
python manage.py migrate cart
```

---

## Basic Usage

### Views

```python
# views.py
from django.shortcuts import get_object_or_404, redirect, render
from cart.cart import Cart, ItemDoesNotExist, InvalidQuantity
from shop.models import Product


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
        pass  # Already removed
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
    return render(request, "cart/detail.html", {"cart": Cart(request)})


def cart_checkout(request):
    cart = Cart(request)
    # Process payment...
    cart.checkout()
    return redirect("order_complete")
```

### URLs

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

## API Reference

### Cart Class

```python
from cart.cart import Cart, ItemDoesNotExist, InvalidQuantity

cart = Cart(request)
```

#### Core Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `cart.add(product, unit_price, quantity=1)` | Add product to cart | `Item` |
| `cart.remove(product)` | Remove product | `None` |
| `cart.update(product, quantity, unit_price=None)` | Update quantity (0 = remove) | `None` |
| `cart.clear()` | Remove all items | `None` |
| `cart.checkout()` | Mark cart as checked out | `None` |

#### Query Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `cart.count()` | Total units in cart | `int` |
| `cart.unique_count()` | Number of distinct products | `int` |
| `cart.summary()` | Grand total | `Decimal` |
| `cart.is_empty()` | Cart has no items | `bool` |
| `cart.contains(product)` | Product in cart | `bool` |

#### Utility Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `cart.cart_serializable()` | JSON-safe dict for APIs | `dict` |
| `cart.merge(other_cart, strategy)` | Merge two carts | `None` |
| `cart.bind_to_user(user)` | Associate with user account | `None` |
| `cart.add_bulk(items)` | Add multiple items | `list[Item]` |
| `Cart.get_user_carts(user)` | Carts for a user (class method) | `QuerySet` |

### Item Properties

Each item in the cart exposes:

```python
item.product       # Your product model instance
item.quantity      # int
item.unit_price    # Decimal
item.total_price  # Decimal (quantity × unit_price)
```

### Magic Methods

```python
len(cart)              # Same as cart.count()
for item in cart:      # Iterate over items
cart[product]          # Access item by product
product in cart        # Same as cart.contains(product)
```

### Exceptions

| Exception | When Raised |
|-----------|-------------|
| `InvalidQuantity` | Quantity < 1 or exceeds maximum |
| `ItemDoesNotExist` | Product not in cart |

---

## Advanced Features

### Discounts

Apply discount codes to carts with support for percentage and fixed amount discounts:

```python
from cart.cart import Cart, InvalidDiscountError

cart = Cart(request)

# Apply a discount code
cart.apply_discount("SAVE20")  # 20% off

# Check discount info
discount_amount = cart.discount_amount()  # Decimal("20.00")
discount_code = cart.discount_code()       # "SAVE20"

# Remove discount
cart.remove_discount()

# Validation with Discount model
discount = Discount.objects.get(code="SAVE20")
is_valid, message = discount.is_valid_for_cart(cart)
```

Create discounts with various restrictions:

```python
from cart.models import Discount, DiscountType

discount = Discount.objects.create(
    code="SUMMER2024",
    discount_type=DiscountType.PERCENT,
    value=Decimal("15.00"),        # 15% off
    min_cart_value=Decimal("50.00"),  # Minimum order
    max_uses=100,                  # Limited uses
    valid_from=start_date,
    valid_until=end_date,
)
```

### Tax Calculator

Customize tax calculation for your region:

```python
# settings.py
CART_TAX_CALCULATOR = 'myapp.tax.USStateTaxCalculator'

# myapp/tax.py
from cart.tax import TaxCalculator
from decimal import Decimal

class USStateTax(TaxCalculator):
    def calculate(self, cart):
        subtotal = cart.summary()
        return subtotal * Decimal("0.0825")  # 8.25% tax

# Usage
tax = cart.tax()  # Returns Decimal
```

### Shipping Calculator

Configure shipping options based on cart contents:

```python
# settings.py
CART_SHIPPING_CALCULATOR = 'myapp.shipping.FlatRateShipping'

# myapp/shipping.py
from cart.shipping import ShippingCalculator, ShippingOption
from decimal import Decimal

class FlatRateShipping(ShippingCalculator):
    def calculate(self, cart):
        return Decimal("9.99")
    
    def get_options(self, cart):
        return [
            {"id": "standard", "name": "Standard Shipping", "price": "9.99"},
            {"id": "express", "name": "Express Shipping", "price": "19.99"},
        ]

# Usage
shipping_cost = cart.shipping()  # Decimal
options = cart.shipping_options()  # List of shipping options
```

### Inventory Checker

Validate product availability before adding to cart:

```python
# settings.py
CART_INVENTORY_CHECKER = 'myapp.inventory.StockInventoryChecker'

# myapp/inventory.py
from cart.inventory import InventoryChecker

class StockInventoryChecker(InventoryChecker):
    def is_available(self, product, quantity):
        return product.stock >= quantity
    
    def reserve(self, product, quantity):
        product.stock -= quantity
        product.save()
    
    def release(self, product, quantity):
        product.stock += quantity
        product.save()

# Usage
from cart.cart import InsufficientStock

cart = Cart(request)
try:
    cart.add(product, price, quantity=10, check_inventory=True)
except InsufficientStock:
    print("Not enough stock available")
```

### Cart Merge

Merge guest carts into user carts upon login. Three strategies available:

| Strategy | Behavior |
|----------|----------|
| `add` | Combine quantities (default) |
| `replace` | Use other cart's quantities |
| `keep_higher` | Keep maximum quantity |

```python
# Login flow example
def login_view(request):
    user = authenticate(request)
    if user:
        login(request, user)
        
        # Get guest cart
        guest_cart = Cart(request)
        
        # Get or create user cart
        user_carts = Cart.get_user_carts(user)
        if user_carts.exists():
            user_cart = Cart(request)
            user_cart.cart = user_carts.first()
        else:
            user_cart = Cart(request)
            user_cart.bind_to_user(user)
        
        # Merge with 'add' strategy (combines quantities)
        user_cart.merge(guest_cart, strategy='add')
```

### User Binding

Persist carts to user accounts across sessions:

```python
# Bind current cart to user
cart = Cart(request)
cart.bind_to_user(request.user)

# Retrieve all carts for a user
user_carts = Cart.get_user_carts(request.user)
for cart in user_carts:
    print(f"Cart {cart.id}: {cart.summary()}")
```

### Bulk Operations

Add or update multiple items efficiently:

```python
cart = Cart(request)

items = [
    {'product': product1, 'unit_price': Decimal("10.00"), 'quantity': 2},
    {'product': product2, 'unit_price': Decimal("20.00"), 'quantity': 1},
    {'product': product3, 'unit_price': Decimal("30.00"), 'quantity': 3},
]

cart.add_bulk(items)  # Atomic operation
```

### Maximum Quantity Limits

Restrict how many units per item:

```python
# settings.py
CART_MAX_QUANTITY_PER_ITEM = 10

# Usage
cart.add(product, price, quantity=5)  # OK
cart.add(product, price, quantity=15)  # Raises InvalidQuantity
```

### Price Validation

Verify passed price matches product's actual price:

```python
from cart.cart import PriceMismatchError

# Product with price attribute
product.price = Decimal("19.99")

# validate_price=True checks price matches
cart.add(product, unit_price=Decimal("19.99"), quantity=1, validate_price=True)  # OK
cart.add(product, unit_price=Decimal("9.99"), quantity=1, validate_price=True)   # Raises PriceMismatchError
```

### Caching

Summary and count results are cached and automatically invalidated on changes:

```python
cart = Cart(request)
cart.add(product, price, quantity=2)

# First call calculates, subsequent calls use cache
total = cart.summary()  # Calculated
total = cart.summary()  # Cached

# Cache invalidates automatically on:
cart.add(product, price, quantity=1)  # Invalidates
cart.update(product, quantity=5)      # Invalidates
cart.remove(product)                  # Invalidates
cart.clear()                          # Invalidates
```

---

## Template Integration

### Cart Template

```html
{% load cart_tags %}

<h1>Your Cart</h1>

{% if cart.is_empty %}
    <p>Your cart is empty.</p>
{% else %}
    <table>
        <thead>
            <tr>
                <th>Product</th>
                <th>Price</th>
                <th>Qty</th>
                <th>Total</th>
            </tr>
        </thead>
        <tbody>
            {% for item in cart %}
            <tr>
                <td>{{ item.product.name }}</td>
                <td>{{ item.unit_price }}</td>
                <td>{{ item.quantity }}</td>
                <td>{{ item.total_price }}</td>
            </tr>
            {% endfor %}
        </tbody>
        <tfoot>
            <tr>
                <td colspan="3"><strong>Total</strong></td>
                <td><strong>{{ cart.summary }}</strong></td>
            </tr>
        </tfoot>
    </table>
{% endif %}
```

### Template Tags

```html
{% load cart_tags %}

<p>Items: {% cart_item_count request %}</p>
<p>Total: {% cart_summary request %}</p>

{% if cart_is_empty request %}
    <p>Empty!</p>
{% endif %}

{% cart_link request "btn btn-primary" "View Cart" %}
```

---

## Signals

Receive notifications on cart events for analytics, logging, or integrations:

### Available Signals

| Signal | When Fired |
|--------|------------|
| `cart_item_added` | Item added or quantity increased |
| `cart_item_removed` | Item removed from cart |
| `cart_item_updated` | Item quantity changed |
| `cart_checked_out` | Checkout completed |
| `cart_cleared` | Cart emptied |

### Example Handler

```python
# signals.py
from django.dispatch import receiver
from cart.signals import cart_item_added, cart_checked_out


@receiver(cart_item_added)
def on_item_added(sender, cart, product, quantity, **kwargs):
    print(f"{quantity}x {product} added to cart {cart.id}")


@receiver(cart_checked_out)
def on_checkout(sender, cart, **kwargs):
    print(f"Cart {cart.id} checked out: {cart.summary}")
```

Connect in your app's `ready()` method:

```python
# myapp/apps.py
class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self):
        import myapp.signals  # noqa: F401
```

---

## Session Adapters

Control where the cart ID is stored:

### Built-in Adapters

| Adapter | Use Case |
|---------|----------|
| `DjangoSessionAdapter` | Default Django sessions |
| `CookieSessionAdapter` | Cookie-based (no server sessions) |

### Using Cookie Storage

```python
# settings.py
from cart.session import CookieSessionAdapter

CARTS_SESSION_ADAPTER_CLASS = CookieSessionAdapter
```

### Custom Adapter

```python
# myapp/session.py
from cart.session import CartSessionAdapter

class RedisSessionAdapter(CartSessionAdapter):
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

```python
# settings.py
CARTS_SESSION_ADAPTER_CLASS = "myapp.session.RedisSessionAdapter"
```

---

## Database Optimization

### Indexes

Cart automatically uses database indexes for efficient queries on common patterns (cart ID, content type, object ID).

### Avoiding N+1 Queries

The `Item.product` property is cached to prevent repeated database hits:

```python
# Efficient - single query per item
for item in cart:
    print(item.product.name)  # Cached after first access
```

### Serialization for APIs

```python
# JSON-safe dictionary for API responses
data = cart.cart_serializable()
# Returns: {'123': {'quantity': 2, 'unit_price': '9.99', 'total_price': '19.98'}, ...}
```

---

## Maintenance

### Cleaning Old Carts

Remove abandoned carts from your database:

```bash
# Delete unchecked-out carts older than 90 days (default)
python manage.py clean_carts

# Custom retention period
python manage.py clean_carts --days 30

# Include checked-out carts
python manage.py clean_carts --days 60 --include-checked-out

# Preview only
python manage.py clean_carts --days 30 --dry-run
```

### Scheduling with Cron

```cron
# Run daily at 2 AM
0 2 * * * /path/to/venv/bin/python /path/to/project/manage.py clean_carts --days 30 >> /var/log/clean_carts.log 2>&1
```

### Celery Alternative

```python
# tasks.py
from celery import shared_task
from django.core.management import call_command

@shared_task
def clean_old_carts():
    call_command("clean_carts", days=30)
```

---

## Testing

### Run All Tests

```bash
python runtests.py
```

### Run Specific Tests

```bash
python runtests.py tests.test_cart.CartAddTest
```

### Test Coverage

```bash
pip install coverage
coverage run runtests.py
coverage report
coverage html  # HTML report in htmlcov/
```

### What Gets Tested

- All cart operations (add, remove, update, clear, checkout)
- Error handling (InvalidQuantity, ItemDoesNotExist)
- Edge cases (empty cart, concurrent modifications)
- Signals and template tags
- Session adapters
- Integration with Django

---

## Developer Setup

### Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install
```

Hooks: black (formatting), isort (imports), flake8 (linting), mypy (type checking)

### Dependencies

```bash
pip install -e ".[dev]"
```

### Project Structure

```
cart/
├── __init__.py
├── admin.py          # Django admin integration
├── apps.py           # App configuration
├── cart.py           # Main Cart class
├── models.py         # Cart and Item models
├── signals.py        # Cart event signals
├── session.py        # Session adapters
├── templatetags/
│   └── cart_tags.py  # Template tags
└── management/
    └── commands/
        └── clean_carts.py
```

---

## Requirements

| Dependency | Version |
|------------|---------|
| Python | 3.10+ |
| Django | 4.2+ |

---

## License

LGPL-3.0
