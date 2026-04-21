![CI](https://img.shields.io/github/actions/workflow/status/bmentges/django-cart/ci.yml?branch=master&style=for-the-badge&logo=github&logoColor=white&label=CI)
![PyPI](https://img.shields.io/pypi/v/django-cart?style=for-the-badge&logo=pypi&logoColor=white&label=PyPI)
![Python](https://img.shields.io/badge/Python-3.10%2B-informational?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-4.2%2B-0C4B33?style=for-the-badge&logo=django&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

# django-cart

A lightweight, session-backed shopping cart for Django. One thin
`Cart` facade over one database row, extended through explicit
pluggable subsystems for tax, shipping, inventory, and session
storage.

> [!tip] Why reach for django-cart
> - **Prototype-fast.** A working cart in three lines of view code
>   and a `pip install`. No schema changes to your product models.
> - **Small-store friendly.** Discounts, tax, and shipping ship
>   in-box and plug in through one setting each. Scale out later by
>   swapping the session adapter.
> - **Agent-ready.** The public API fits in one context window.
>   Coding agents (Claude, Cursor, Copilot) can generate correct
>   extensions on the first pass — see
>   [`docs/AGENTS.md`](docs/AGENTS.md).

```mermaid
graph TB
    classDef facade fill:#1f2937,stroke:#60a5fa,color:#f9fafb,stroke-width:2px
    classDef plug fill:#0f172a,stroke:#a78bfa,color:#e2e8f0,stroke-dasharray:4 2
    classDef store fill:#0b1220,stroke:#34d399,color:#d1fae5
    classDef opt fill:#0b1220,stroke:#f59e0b,color:#fef3c7,stroke-dasharray:2 2

    View["Django view<br>or DRF endpoint"]
    Cart["Cart facade<br>cart.cart.Cart"]:::facade
    Session["Session Adapter<br>CARTS_SESSION_ADAPTER_CLASS"]:::store
    DB[("Cart, Item, Discount<br>database rows")]:::store

    Tax["Tax Calculator<br>CART_TAX_CALCULATOR"]:::plug
    Ship["Shipping Calculator<br>CART_SHIPPING_CALCULATOR"]:::plug
    Inv["Inventory Checker<br>CART_INVENTORY_CHECKER"]:::plug

    Signals["Django signals<br>cart_item_added, ..."]:::opt
    Tags["Template tags<br>cart_item_count, ..."]:::opt

    View --> Cart
    Cart --> Session
    Cart --> DB
    Cart -.->|plug| Tax
    Cart -.->|plug| Ship
    Cart -.->|plug| Inv
    Cart -.->|emit| Signals
    View -.->|render| Tags
```

---

## Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Using the Cart](#using-the-cart)
- [Discounts](#discounts)
- [Pluggable Subsystems](#pluggable-subsystems)
- [Session Storage](#session-storage)
- [Signals](#signals)
- [Template Tags](#template-tags)
- [Settings Reference](#settings-reference)
- [Admin Integration](#admin-integration)
- [Operations](#operations)
- [Agent-Ready](#agent-ready)
- [Data Model](#data-model)
- [Testing](#testing-django-cart)
- [Requirements](#requirements)
- [Changelog, Roadmap, License](#changelog-roadmap-license)

---

## Installation

```bash
pip install django-cart
```

Add to `INSTALLED_APPS` and run migrations. The library ships five
migrations; no product-model changes are required.

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "django.contrib.contenttypes",  # already default in Django
    "cart",
]
```

```bash
python manage.py migrate cart
```

> [!note] About `uv`
> The maintainer uses [`uv`](https://docs.astral.sh/uv/) for local
> development of this library. Downstream projects can use any
> installer (`pip`, `poetry`, `pipenv`, `uv`, `rye`). The public API
> is installer-agnostic.

---

## Quick Start

A complete add-to-cart flow is three view functions and a template.

```python
# views.py
from decimal import Decimal
from django.shortcuts import get_object_or_404, redirect, render
from cart.cart import Cart
from shop.models import Product


def cart_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    Cart(request).add(product, unit_price=product.price, quantity=1)
    return redirect("cart_detail")


def cart_remove(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    Cart(request).remove(product)
    return redirect("cart_detail")


def cart_detail(request):
    return render(request, "cart/detail.html", {"cart": Cart(request)})
```

```html
{# cart/detail.html #}
{% load cart_tags %}
{% if cart.is_empty %}
    <p>Your cart is empty.</p>
{% else %}
    <ul>
      {% for item in cart %}
        <li>{{ item.quantity }} × {{ item.product }} —
            {{ item.total_price }}</li>
      {% endfor %}
    </ul>
    <p><strong>Total: {{ cart.summary }}</strong></p>
{% endif %}
```

What just happened:

1. `Cart(request)` looked up `CART-ID` in the current session. It
   did not find one, so it created a new `cart.models.Cart` row and
   wrote the row id back into the session.
2. `.add(...)` created a `cart.models.Item` bound to the cart, with
   a generic foreign key to your `Product` — no changes required to
   the `Product` model itself.
3. In the template, iterating `cart` walks items with products
   prefetched; `cart.summary` returns a `Decimal` sum of all
   `quantity × unit_price`.

---

## Core Concepts

### The `Cart` facade

`cart.cart.Cart` is a thin wrapper around a single
`cart.models.Cart` row associated with the current session. The
class holds two pieces of state:

- `self.cart` — the DB row.
- `self._cache` — an in-memory cache for `count()` and `summary()`,
  invalidated on every mutation.

No hidden threads, no background work, no module-level registry.

### Items and generic foreign keys

Each `Item` references its product through
`(content_type, object_id)` — Django's
[contenttypes framework](https://docs.djangoproject.com/en/stable/ref/contrib/contenttypes/).
This is what lets `django-cart` work with **any** product model
without schema changes.

```python
cart.add(coffee_bean, Decimal("12.00"))        # Coffee model
cart.add(digital_course, Decimal("99.00"))     # Course model
# Same cart, different product classes.
```

### Session-backed lifecycle

```mermaid
flowchart LR
    classDef state fill:#0b1220,stroke:#60a5fa,color:#e2e8f0
    classDef money fill:#0b1220,stroke:#34d399,color:#d1fae5
    classDef final fill:#1f2937,stroke:#a78bfa,color:#f9fafb,stroke-width:2px

    Empty["Cart(request)<br>empty"]:::state
    Add["add(product, price)"]:::state
    Inspect["summary / count /<br>is_empty / iteration"]:::state
    Discount["apply_discount(code)"]:::money
    Math["tax() + shipping() −<br>discount_amount() → total()"]:::money
    Checkout["checkout()<br>atomic, idempotent"]:::final

    Empty --> Add
    Add --> Inspect
    Inspect --> Discount
    Discount --> Math
    Math --> Checkout
```

The only thing that lives in the HTTP session is the integer cart
id. Everything else is a database row. A cart survives page loads
but does not become an order — that is your checkout flow's
responsibility. `checkout()` simply marks the cart
`checked_out=True` and (if a discount was applied) bumps its usage
counter atomically.

---

## Using the Cart

### Adding, updating, removing

```python
from cart.cart import Cart, InvalidQuantity, ItemDoesNotExist

cart = Cart(request)

item = cart.add(product, unit_price=Decimal("12.00"), quantity=2)
cart.update(product, quantity=5)          # new quantity (0 removes)
cart.update(product, quantity=3, unit_price=Decimal("9.99"))
cart.remove(product)                      # raises ItemDoesNotExist
cart.clear()                              # empties everything
```

All mutations wrap the DB work in `transaction.atomic()` and
invalidate the internal summary cache on success.

> [!warning] Concurrency
> `add()` / `update()` / `merge()` are transactional but do **not**
> hold row locks during their read phase. Under concurrent requests
> on Postgres or MySQL, two workers reading `quantity=N` can both
> write `N+q`, clobbering one of the adds. For code paths that must
> be concurrent-safe, wrap the mutation in your own
> `select_for_update()` block or serialise upstream (idempotency
> keys, queue-per-cart, etc.). `checkout()` already locks the `Cart`
> row and (when a discount is applied) the `Discount` row via
> `select_for_update()` — use it as a template.

### Bulk operations

Add or update many items at once, inside a single transaction:

```python
cart.add_bulk([
    {"product": p1, "unit_price": Decimal("10.00"), "quantity": 2},
    {"product": p2, "unit_price": Decimal("20.00"), "quantity": 1},
])
```

### Iteration and introspection

```python
len(cart)                 # int — total units (alias of cart.count())
cart.count()              # int — same as len(cart)
cart.unique_count()       # int — number of distinct products
cart.is_empty()           # bool
product in cart           # bool — uses __contains__
for item in cart: ...     # iterates items, content_type preloaded
```

Each `item` exposes `.product`, `.quantity`, `.unit_price`,
`.total_price` (a `Decimal` property).

### Money math

```python
cart.summary()            # Decimal — Σ quantity × unit_price
cart.tax()                # Decimal — uses configured TaxCalculator
cart.shipping()           # Decimal — uses configured ShippingCalculator
cart.discount_amount()    # Decimal — 0.00 if no discount applied
cart.total()              # Decimal — summary − discount + tax + shipping
```

`summary()` and `count()` are cached on the `Cart` instance and
invalidated on every mutation. `tax()` / `shipping()` call out to
the configured calculators on each call — if they are expensive,
memoise on the calculator side.

### User binding and merging

Bind a guest cart to a user on login, and merge the guest cart into
any pre-existing user cart:

```python
from cart.cart import Cart

def on_login(request):
    guest = Cart(request)                 # the current session cart
    prior = Cart.get_user_carts(request.user).filter(
        checked_out=False,
    ).first()

    if prior is None:
        guest.bind_to_user(request.user)
        return

    user_cart = Cart(request)
    user_cart.cart = prior
    user_cart.merge(guest, strategy="add")   # or "replace" / "keep_higher"
```

Available merge strategies:

| Strategy | Result per product |
|----------|--------------------|
| `add` (default) | `quantity = old + new` |
| `replace` | `quantity = new` |
| `keep_higher` | `quantity = max(old, new)` |

### Serialisation

Freeze a cart to a JSON-safe dict and restore it later — useful for
cross-device sync or for passing through an API:

```python
payload = cart.cart_serializable()
# {"42": {"content_type_id": 7, "quantity": 2,
#         "unit_price": "9.99", "total_price": "19.98"}, ...}

# ...later, possibly in a different request or worker...
restored = Cart.from_serializable(new_request, payload)
```

> [!important] `content_type_id` is required to restore into a fresh cart
> The payload emitted by `cart_serializable()` includes
> `content_type_id` per item (added in v3.0.11). This lets
> `from_serializable()` create items in a brand-new cart. Legacy
> payloads without the field can still **update** items already
> present in the target cart, but attempting to create new items
> from them raises `ValueError` with a clear message — never a
> silent no-op.

### Checkout

```python
can, message = cart.can_checkout()
if not can:
    return render(request, "cart/detail.html", {"cart": cart, "error": message})

try:
    cart.checkout()
except InvalidDiscountError as e:
    # A discount was applied earlier but is no longer valid
    # (expired, deactivated, or max_uses reached between apply
    # and checkout). The whole operation rolled back — the cart
    # is still open, the user can remove the discount and retry.
    ...
```

`checkout()` is:

- **Atomic.** Marks the cart checked-out and (if a discount is
  applied) increments `Discount.current_uses` in the same
  transaction.
- **Race-safe.** Takes a `SELECT … FOR UPDATE` on the `Cart` row
  first, then (when a discount is applied) on the `Discount` row.
  Two concurrent checkouts of the same cart produce exactly one
  counter increment; two concurrent checkouts of the last remaining
  use of a discount code result in one success and one
  `InvalidDiscountError`.
- **Idempotent across facades.** Calling `checkout()` twice on the
  same cart — even from separate `Cart(request)` instances or
  workers with stale in-memory state — is a no-op on the second
  call. No second counter bump, no duplicate `cart_checked_out`
  signal.

> [!note] `checkout()` does not reserve inventory
> Stock reservation is the consuming project's responsibility. The
> `InventoryChecker` interface has a `reserve()` method you can call
> from your own checkout flow; the library's built-in `checkout()`
> does not call it. This is deliberate — reservation semantics
> (timeout, release on failed payment, retry) vary too much per
> project to bake a default.

### Exceptions

All cart exceptions subclass `cart.cart.CartException`.

| Exception | Raised when |
|-----------|-------------|
| `InvalidQuantity` | quantity < 1 on `add`, < 0 on `update`, or > `CART_MAX_QUANTITY_PER_ITEM` |
| `ItemDoesNotExist` | `remove()` / `update()` called for a product not in the cart |
| `PriceMismatchError` | `validate_price=True` and `unit_price != product.price` |
| `InsufficientStock` | `check_inventory=True` and the configured `InventoryChecker.check()` returns `False` |
| `InvalidDiscountError` | bad code, already-applied discount, failed validity check, revalidation failure at checkout |
| `MinimumOrderNotMet` | defined but not raised by the library itself; surfaced via `can_checkout()` as `(False, message)` |

---

## Discounts

Discount codes are first-class. The `Discount` model supports
percentage and fixed-amount discounts, validity windows, usage caps,
and minimum cart values.

```python
from decimal import Decimal
from cart.models import Discount, DiscountType

Discount.objects.create(
    code="SUMMER25",
    discount_type=DiscountType.PERCENT,
    value=Decimal("25.00"),
    min_cart_value=Decimal("50.00"),
    max_uses=500,
    valid_from=start_date,
    valid_until=end_date,
)
```

Apply, inspect, remove:

```python
from cart.cart import InvalidDiscountError

try:
    cart.apply_discount("SUMMER25")
except InvalidDiscountError as e:
    print(f"Cannot apply: {e}")

cart.discount_code()       # "SUMMER25"
cart.discount_amount()     # Decimal — computed against cart.summary()
cart.remove_discount()
```

### How usage caps are enforced

```mermaid
sequenceDiagram
    participant V as View
    participant C as Cart
    participant DB as Database

    V->>C: apply_discount("SUMMER25")
    C->>DB: Discount.objects.get(code=...)
    C->>C: discount.is_valid_for_cart(self)
    C->>DB: cart.discount = discount

    Note over V,DB: Some time passes — user browses, adds items,<br>another user may also be checking out the last use.

    V->>C: checkout()
    C->>DB: BEGIN
    C->>DB: SELECT ... FROM Cart WHERE pk=? FOR UPDATE

    alt cart already checked_out<br>(another facade won the race)
        C->>DB: COMMIT
        C-->>V: ok (no-op)
    else proceed
        C->>DB: SELECT ... FROM Discount WHERE pk=? FOR UPDATE
        C->>C: discount.is_valid_for_cart(self)

        alt still valid
            C->>DB: UPDATE Discount SET current_uses = current_uses + 1
            C->>DB: UPDATE Cart SET checked_out = true
            C->>DB: COMMIT
            C-->>V: ok
        else no longer valid<br>(expired, deactivated, cap reached)
            C->>DB: ROLLBACK
            C-->>V: raises InvalidDiscountError
        end
    end
```

Two concurrent checkouts of the last remaining use of a discount
code result in exactly one success and exactly one
`InvalidDiscountError`. The counter is never exceeded.

---

## Pluggable Subsystems

Tax, shipping, and inventory checking each follow the same shape:
an abstract base class, a no-op default, and a factory that reads a
dotted path from settings.

```
cart/<subsystem>.py:
    class <Subsystem>Base(ABC):              # your subclass inherits from this
    class Default<Subsystem>(Base):          # safe no-op default
    def get_<subsystem>() -> Base:           # factory, reads settings
```

> [!warning] Silent fallback on misconfiguration
> The three subsystem factories swallow `ImportError` /
> `AttributeError` and fall back to the default implementation. A
> typo in `CART_TAX_CALCULATOR` yields "tax is always 0.00" at
> runtime — no exception, no warning. Validate your dotted paths
> in a startup check. The session adapter factory is the exception;
> it raises loudly.

### Tax

```python
# settings.py
CART_TAX_CALCULATOR = "myapp.tax.FlatRateTax"
```

```python
# myapp/tax.py
from decimal import Decimal
from cart.tax import TaxCalculator
from cart.cart import Cart


class FlatRateTax(TaxCalculator):
    def calculate(self, cart: Cart) -> Decimal:
        return cart.summary() * Decimal("0.08")
```

Usage:

```python
cart.tax()   # → Decimal
```

The default (`DefaultTaxCalculator`) always returns
`Decimal("0.00")`.

### Shipping

`ShippingCalculator` has two methods: `calculate(cart)` for the
total cost, and `get_options(cart)` for the UI to show the user a
list of choices.

```python
# settings.py
CART_SHIPPING_CALCULATOR = "myapp.shipping.FlatRateShipping"
```

```python
# myapp/shipping.py
from decimal import Decimal
from cart.shipping import ShippingCalculator, ShippingOption
from cart.cart import Cart


class FlatRateShipping(ShippingCalculator):
    def calculate(self, cart: Cart) -> Decimal:
        return Decimal("0.00") if cart.summary() >= 100 else Decimal("9.99")

    def get_options(self, cart: Cart) -> list[ShippingOption]:
        return [
            ShippingOption(id="standard", name="Standard (3–5 days)",
                           price=str(self.calculate(cart))),
            ShippingOption(id="express", name="Express (next-day)",
                           price="19.99"),
        ]
```

```python
cart.shipping()          # → Decimal
cart.shipping_options()  # → list[dict]
```

### Inventory

Opt-in per-call with `check_inventory=True`:

```python
# settings.py
CART_INVENTORY_CHECKER = "myapp.inventory.StockChecker"
```

```python
# myapp/inventory.py
from cart.inventory import InventoryChecker


class StockChecker(InventoryChecker):
    def check(self, product, quantity: int) -> bool:
        return product.stock >= quantity

    def reserve(self, product, quantity: int) -> bool:
        # Atomic decrement; use F() in real code.
        if product.stock < quantity:
            return False
        product.stock -= quantity
        product.save(update_fields=["stock"])
        return True
```

```python
from cart.cart import InsufficientStock

try:
    cart.add(product, unit_price=p.price, quantity=5, check_inventory=True)
except InsufficientStock:
    return HttpResponseBadRequest("Not enough stock")
```

The default (`DefaultInventoryChecker`) always returns `True`.
`reserve()` is a method you call from your own checkout flow; the
library's `checkout()` does not call it — see the [Checkout
note](#checkout) above.

---

## Session Storage

The only state the library puts in the HTTP session is the integer
`CART-ID`. Everything else is a database row. Which backend holds
that integer is configurable via a single setting.

```mermaid
flowchart LR
    classDef q fill:#0b1220,stroke:#f59e0b,color:#fef3c7
    classDef a fill:#1f2937,stroke:#60a5fa,color:#f9fafb

    Q1{"Using Django's<br>session framework?"}:::q
    Q2{"Fully stateless<br>(no server session)?"}:::q
    Q3{"Distributed cache<br>or JWT required?"}:::q

    D["DjangoSessionAdapter<br>(default)"]:::a
    C["CookieSessionAdapter"]:::a
    X["Custom adapter<br>(Redis, JWT, Dynamo, ...)"]:::a

    Q1 -->|Yes| D
    Q1 -->|No| Q2
    Q2 -->|Yes| C
    Q2 -->|No| Q3
    Q3 -->|Yes| X
    Q3 -->|No| D
```

### Built-in adapters

| Adapter | Use case |
|---------|----------|
| `DjangoSessionAdapter` (default) | Standard Django sessions (DB, cache, signed cookies — any `SESSION_ENGINE`). |
| `CookieSessionAdapter` | Fully stateless: stores the cart id in an HTTP cookie, reads it back on the next request. |

### Selecting an adapter

```python
# settings.py — dotted string
CARTS_SESSION_ADAPTER_CLASS = "cart.session.CookieSessionAdapter"

# or — class object
from cart.session import CookieSessionAdapter
CARTS_SESSION_ADAPTER_CLASS = CookieSessionAdapter
```

Both forms work. A typo in the dotted path raises `ImportError`
loudly — this is the one subsystem factory that does **not** fall
back silently.

> [!important]
> `CookieSessionAdapter` (and any custom cookie-backed adapter) also
> requires `CartCookieMiddleware` in `MIDDLEWARE` so pending cookies
> are written to the response. `DjangoSessionAdapter` (the default)
> does not need this — Django's `SessionMiddleware` handles it.
>
> ```python
> MIDDLEWARE = [
>     # ... existing middleware ...
>     "cart.middleware.CartCookieMiddleware",
> ]
> ```

### Custom adapter

Subclass `CartSessionAdapter` and implement its five abstract
methods. The real interface is `get` / `set` / `delete` /
`get_or_create_cart_id` / `set_cart_id` — each documented on the
base class.

```python
# myapp/session.py
from typing import Any
from cart.session import CartSessionAdapter
from cart.cart import CART_ID


class RedisSessionAdapter(CartSessionAdapter):
    def __init__(self, request):
        import redis
        self._r = redis.StrictRedis(host="localhost", port=6379, db=0)
        self._key = f"cart:{request.session.session_key}"

    def get(self, key: str, default: Any = None) -> Any:
        value = self._r.hget(self._key, key)
        return value.decode() if value else default

    def set(self, key: str, value: Any) -> None:
        self._r.hset(self._key, key, str(value))

    def delete(self, key: str) -> None:
        self._r.hdel(self._key, key)

    def get_or_create_cart_id(self) -> int | None:
        value = self.get(CART_ID)
        try:
            return int(value) if value else None
        except (ValueError, TypeError):
            return None

    def set_cart_id(self, cart_id: int) -> None:
        self.set(CART_ID, cart_id)
```

```python
# settings.py
CARTS_SESSION_ADAPTER_CLASS = "myapp.session.RedisSessionAdapter"
```

See [`docs/AGENTS.md`](docs/AGENTS.md) for a prompt-ready version
of this pattern.

---

## Signals

Five optional signals let you observe cart events without
monkey-patching. Importing `cart.signals` is not required — if the
module is missing at import time, the cart still works and no
signals fire.

| Signal | Payload (`kwargs`) | Fired by |
|--------|---------------------|----------|
| `cart_item_added` | `cart`, `item` | `Cart.add()` on success |
| `cart_item_removed` | `cart`, `product` | `Cart.remove()` on success |
| `cart_item_updated` | `cart`, `item`, `deleted` (bool) | `Cart.update()` on success |
| `cart_checked_out` | `cart` | `Cart.checkout()` — only once per cart |
| `cart_cleared` | `cart` | `Cart.clear()` on success |

Wire handlers in your app's `ready()`:

```python
# myapp/apps.py
from django.apps import AppConfig


class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self):
        import myapp.signals  # noqa: F401
```

```python
# myapp/signals.py
from django.dispatch import receiver
from cart.signals import cart_item_added, cart_checked_out


@receiver(cart_item_added)
def record_add(sender, cart, item, **kwargs):
    # Analytics, audit log, inventory decrement, etc.
    ...


@receiver(cart_checked_out)
def send_confirmation(sender, cart, **kwargs):
    ...
```

---

## Template Tags

Load once per template, then use in any context that has `request`
(the default Django context processor makes this automatic if
`django.template.context_processors.request` is in `TEMPLATES →
OPTIONS → context_processors`).

```django
{% load cart_tags %}
```

| Tag | Signature | Returns |
|-----|-----------|---------|
| `{% cart_item_count %}` | no arguments | integer |
| `{% cart_summary %}` | no arguments | formatted string, e.g. `$19.98` |
| `{% cart_is_empty %}` | no arguments | boolean |
| `{% cart_link "Label" "css-class" %}` | `text`, `css_class` — both optional | HTML `<a>` tag |

All four tags declare `takes_context=True` and read `request` from
the template context. Do not pass `request` positionally.

> [!note] Tags do not create abandoned cart rows
> The three read-only tags (`cart_item_count`, `cart_summary`,
> `cart_is_empty`) query the cart directly from the DB when the
> session already carries a `CART-ID`, and return defaults otherwise.
> `cart_link` never queries the cart at all. Loading any of these in
> a site-wide header is safe to serve to crawlers, bots, and
> pre-login visitors — none of them will materialise a DB row.

> [!tip] Route `cart_link` through your own URL conf
> Set `CART_DETAIL_URL_NAME` to a URL name you've defined, and
> `cart_link` will resolve the anchor via `reverse()`:
>
> ```python
> # settings.py
> CART_DETAIL_URL_NAME = "cart_detail"
> ```
>
> With the setting absent — or the URL name unresolvable — the tag
> falls back to a static `/cart/`. The cart's integer primary key is
> never embedded in the URL.

Example header snippet:

```django
{% load cart_tags %}

<header>
  <nav>
    <a href="/">Shop</a>
    {% cart_link "Cart" "nav-btn" %}
    <span class="badge">{% cart_item_count %}</span>
    <span class="total">{% cart_summary %}</span>
  </nav>
</header>
```

Capture a tag's return value with `as`:

```django
{% cart_item_count as count %}
{% if count %}
  <span class="badge">{{ count }}</span>
{% endif %}
```

---

## Settings Reference

All settings are optional. Defaults apply when a setting is absent
or `None`.

| Setting | Type | Default | Purpose |
|---------|------|---------|---------|
| `CART_TAX_CALCULATOR` | dotted path or class | `DefaultTaxCalculator` → `Decimal("0.00")` | Tax calculator class. See [Tax](#tax). |
| `CART_SHIPPING_CALCULATOR` | dotted path or class | `DefaultShippingCalculator` → `Decimal("0.00")`, one "free" option | Shipping calculator class. See [Shipping](#shipping). |
| `CART_INVENTORY_CHECKER` | dotted path or class | `DefaultInventoryChecker` → always `True` | Inventory checker class. See [Inventory](#inventory). |
| `CARTS_SESSION_ADAPTER_CLASS` | dotted path or class | `DjangoSessionAdapter` | Where the integer cart id is stored. See [Session Storage](#session-storage). |
| `CART_MAX_QUANTITY_PER_ITEM` | int or `None` | `None` (unlimited) | Cap on `item.quantity`. Exceeding raises `InvalidQuantity`. |
| `CART_MIN_ORDER_AMOUNT` | `Decimal` or `None` | `None` (no minimum) | Minimum `cart.summary()` required for `can_checkout()` to return `True`. |
| `CART_DETAIL_URL_NAME` | str or `None` | `None` | URL name passed to `reverse()` by the `{% cart_link %}` template tag. Falls back to a static `/cart/` when unset or unresolvable. See [Template Tags](#template-tags). |

---

## Admin Integration

`cart/admin.py` registers `Cart` with an inline `Item` editor.
`Item` is visible through the cart edit page — not as a top-level
model — which matches how you typically want to inspect a cart.

> [!note] `Discount` is not registered
> The `Discount` model is intentionally not registered in the
> library's admin, because a storefront often wants custom admin
> views (bulk CSV import, per-campaign grouping, voucher
> generators). Register it yourself:
>
> ```python
> # myapp/admin.py
> from django.contrib import admin
> from cart.models import Discount
>
>
> @admin.register(Discount)
> class DiscountAdmin(admin.ModelAdmin):
>     list_display = ("code", "discount_type", "value",
>                     "current_uses", "max_uses", "active",
>                     "valid_until")
>     list_filter = ("active", "discount_type")
>     search_fields = ("code",)
>     readonly_fields = ("current_uses",)
> ```

---

## Operations

### Pruning abandoned carts

Abandoned carts accumulate. The `clean_carts` management command
removes them:

```bash
python manage.py clean_carts                    # default: unchecked-out, >90 days old
python manage.py clean_carts --days 30          # custom retention
python manage.py clean_carts --days 30 --dry-run
python manage.py clean_carts --days 60 --include-checked-out
```

Schedule with cron:

```cron
# Nightly at 02:00
0 2 * * * /path/to/venv/bin/python /path/to/project/manage.py clean_carts --days 30
```

Or Celery:

```python
# myapp/tasks.py
from celery import shared_task
from django.core.management import call_command


@shared_task
def prune_abandoned_carts():
    call_command("clean_carts", days=30)
```

---

## Agent-Ready

`django-cart` is designed to be **extended by coding agents on the
first pass**. Three properties make that possible:

1. **Small surface.** The public API is under 1000 lines across
   four files and fits entirely in a single agent context window.
2. **Explicit extension points.** Every subsystem is a settings
   dotted-path pointing at a subclass of a clearly-typed abstract
   base. No registries, no decorators, no magic.
3. **Stable contracts.** Public names are preserved across patch
   and minor releases. The same prompt that works today works on
   the next minor.

A minimum working example — generating a custom tax calculator with
Claude:

```text
Prompt:

  In my Django project I use django-cart. Generate a TaxCalculator
  subclass that applies 7.25% tax if the cart's `summary()` is
  above $100 and 5% otherwise. Wire it in through settings and
  write a pytest that asserts both branches.

Expected output:
  - myapp/tax.py with `class Tiered(TaxCalculator)` returning Decimal
  - settings.py with CART_TAX_CALCULATOR set to its dotted path
  - tests/test_tax.py with two test functions exercising both branches
```

For the full agentic extension guide — prompt templates, review
checklist, sharp edges, verification steps — see
**[`docs/AGENTS.md`](docs/AGENTS.md)**.

---

## Data Model

Three models, one generic FK, a handful of indexes.

```mermaid
erDiagram
    Cart ||--o{ Item : "has many"
    Cart }o--|| Discount : "optional FK (nullable)"
    Item }o..|| PRODUCT : "GenericFK<br>content_type + object_id"

    Cart {
        int id PK
        datetime creation_date
        bool checked_out
        int user_id FK "nullable"
        int discount_id FK "nullable"
    }

    Item {
        int id PK
        int cart_id FK
        int content_type_id FK
        int object_id
        int quantity "PositiveInteger"
        decimal unit_price "max_digits=18, dp=2"
    }

    Discount {
        int id PK
        string code UK
        string discount_type "percent or fixed"
        decimal value
        decimal min_cart_value "nullable"
        int max_uses "nullable"
        int current_uses
        bool active
        datetime valid_from "nullable"
        datetime valid_until "nullable"
    }

    PRODUCT {
        any_model your_existing_product "no changes required"
    }
```

`Item` has `unique_together` on `(cart, content_type, object_id)`
and a composite index on the same triple — so `cart.add(p)` is
always one primary-key lookup.

---

## Testing django-cart

> [!note] Contributors only
> This section is for working **on** the library. Application code
> consuming `django-cart` does not need any of this.

`django-cart` uses `pytest` + `pytest-django` exclusively — there
is no `unittest.TestCase` subclassing, no `runtests.py`. Fixtures
live in `tests/conftest.py`; helpers are never defined inside test
files.

```bash
uv venv
uv pip install -e ".[dev]"
uv run pytest
```

Run a single file or test:

```bash
uv run pytest tests/test_cart_add.py
uv run pytest tests/test_cart_add.py::test_add_new_product_stores_the_quantity
```

Coverage:

```bash
uv run coverage run -m pytest
uv run coverage report            # advisory floor: 90% (local only)
uv run coverage html               # → htmlcov/
```

See [`tests/README.md`](tests/README.md) for the full test pattern,
fixture catalogue, and guidance on writing behavioural (not
reflection) tests.

---

## Requirements

**Python 3.10+, Django 4.2+.**

### Compatibility matrix

|              | Django 4.2 | Django 5.0 | Django 5.1 | Django 6.0 |
|--------------|:----------:|:----------:|:----------:|:----------:|
| Python 3.10  |     ✅     |     ✅     |     ✅     |      —     |
| Python 3.11  |     ✅     |     ✅     |     ✅     |      —     |
| Python 3.12  |     ✅     |     ✅     |     ✅     |     ✅     |
| Python 3.13  |     ✅     |     ✅     |     ✅     |     ✅     |
| Python 3.14  |     ❌     |     ❌     |     ❌     |     ✅     |

- ✅ exercised in CI.
- ❌ unsupported — see the callout below.
- — this Python version is outside the upstream Django release's
  supported Python range.

> [!warning] **Python 3.14 requires Django 6.0+**
> `django-cart` does **not** support Python 3.14 paired with Django
> 4.2, 5.0, or 5.1 — and will not. The incompatibility is upstream in
> Django itself.
>
> **Why it breaks.** Django's `django.template.Context.__copy__`
> (pre-6.0) assigns `duplicate.dicts = self.dicts[:]` onto a value
> returned by `copy(super())`, i.e. a `super()` proxy. Python 3.14
> no longer permits attribute assignment on `super()` proxies, so any
> template render under Py3.14 + Django<6 raises
> `AttributeError: 'super' object has no attribute 'dicts' and no
> __dict__ for setting new attributes`.
>
> Django fixed `Context.__copy__` in 6.0. There is nothing
> `django-cart` can patch on its side — the break is in Django's
> template engine, not in this library.
>
> **What to do.** On Python 3.14, upgrade to Django 6.0+. On earlier
> Django, stay on Python 3.13 or below.

---

## What's Next

> [!tip] Near-future roadmap item — high-precision decimal representation
> A roadmap slot is reserved for cryptocurrency-style fractional
> quantities — representing tiny fractions of a product (e.g. a
> `Coin` model) denominated in long decimals with satoshi- or
> wei-level precision. The cart stays a collection of `(product,
> quantity, unit_price)` triples; only the numeric precision
> changes. Design doc required before implementation. Broader
> prioritisation lives in
> [`docs/ANALYSIS.md`](docs/ANALYSIS.md).
>
> *This is a scope marker, not a commitment.*

---

## Changelog, Roadmap, License

- **Changelog:** [`CHANGELOG.md`](CHANGELOG.md) — Keep-a-Changelog
  format.
- **Analysis & remediation plan:** [`docs/ANALYSIS.md`](docs/ANALYSIS.md)
  — bug-by-bug priorities, design gaps, and the suggested per-release
  scope.
- **License:** MIT. See [`LICENSE`](LICENSE). (Relicensed from
  LGPL-3.0 in v3.0.11 — see `CHANGELOG.md`.)

Contributions welcome. The library is small on purpose — if a
feature fits the "session-backed cart" mission, open an issue or
PR. For experimental / speculative work, prefer a downstream
package that extends `django-cart` via its public API rather than
forking.
