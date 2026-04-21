# django-cart — Senior Engineering Analysis

> **Author:** Claude (role-played as senior Python/Django engineer + senior
> e-commerce specialist)
> **Repository snapshot:** `master` @ v3.0.11 (2026-04-21)
> **Scope:** bug hunt, architecture critique, code quality, test-suite
> review, e-commerce capability gaps, prioritized recommendations.
> **Method:** line-by-line read of every file under `cart/`, `tests/`,
> `docs/`, `.github/`, project config. Behaviours inferred from code,
> cross-checked against `CLAUDE.md`, `CHANGELOG.md`, and the README.

---

## 0. TL;DR for the maintainer

`django-cart` v3.0.11 is in much better shape than its 2.x history
suggests: the P0 fix wave (discount counter race, `from_serializable`
no-op, session-adapter wiring, idempotent checkout, CookieSessionAdapter
hydration) has closed most of the old known-defect list documented in
`CLAUDE.md`. The test suite has been fully migrated to pytest+fixtures
and covers 98% of lines behaviourally.

The library remains a clean, readable session-backed cart facade with
explicit extension points — an unusually coherent design for something
so old. The AGENTS.md pitch is legitimate: a coding agent really can
extend this in one shot.

That said, this audit finds **one live Critical (P0) regression**
re-introduced by the very fix that claimed to close it, **four High
(P1) correctness bugs**, and roughly two dozen P2/P3 items ranging from
bad defaults to missing behaviour expected by any production
e-commerce deployment. A handful of *design gaps* — not bugs —
separate this library from something an established storefront would
use without wrapping.

### Critical (P0) — fix before next release

| # | File / line | Summary |
|---|-------------|---------|
| P0-A | `cart/cart.py:108` ↔ `cart/session.py:77-88` | **`CookieSessionAdapter` is functionally broken when wired via `CARTS_SESSION_ADAPTER_CLASS`**: the adapter constructed inside `Cart.__init__` receives `request` only, so `self._response is None`; `set_cart_id()` writes the cookie to an in-memory dict and **never to the response**, so the browser never receives `Set-Cookie: CART-ID=…`. A new cart row is created on every request. (See §4.1.) |

### High (P1) — correctness / race bugs

| # | File / line | Summary |
|---|-------------|---------|
| P1-A | `cart/cart.py:317-334` | **`checkout()` double-increments `Discount.current_uses`** under concurrent checkouts of the *same cart* when `max_uses` is `None` or unbounded — the Cart row is not locked, only the Discount row is. (See §4.2.) |
| P1-B | `cart/models.py:26` | `Cart.user` FK is hardcoded to `"auth.User"` instead of `settings.AUTH_USER_MODEL`. The library is **incompatible with projects that use a custom user model** — the Django default recommendation since 1.5. (See §4.3.) |
| P1-C | `cart/templatetags/cart_tags.py:64-84` | **`cart_link` template tag instantiates a `Cart`** — and therefore creates a DB row — for every template render. Any site using this tag in a site-wide header creates abandoned carts for every crawler, bot, and anonymous pageview. (See §4.4.) |
| P1-D | `cart/cart.py:399-426` | `from_serializable` looks up existing items with `filter(cart=…, object_id=…)` and the serialisable payload is keyed by `object_id` alone — **ignoring `content_type_id`**. Two products with the same PK but different models collide on both the serialize and restore sides. (See §4.5.) |

### Medium (P2) — deserves an issue, but won't bite most users

- Discount counter **incremented by concurrent double-checkout** (sister
  of P1-A, cosmetic when `max_uses` is set, real when it isn't).
- **`DiscountType.PERCENT` lets `value` exceed 100** — discount clamps
  to zero in `total()` but `calculate_discount()` returns a number
  larger than the cart subtotal; any downstream code displaying
  "discount applied" without calling `total()` shows nonsense.
- **No `CheckConstraint` on `Discount.valid_from < valid_until`** —
  an admin can create a discount with inverted dates.
- **`cart_serializable()` omits the applied discount and user binding**
  — a "restore cart" on a new device loses these.
- **No rounding on `Cart.total()`**, `Discount.calculate_discount`,
  or tax/shipping aggregation. Long-tail decimal noise leaks into
  the Decimal(2) storage.
- **Admin `CartAdmin` has no `search_fields`** but the HTTP-level test
  `test_cart_admin_changelist_search_filters_by_cart_id` asserts as
  if search works. The test is weak and passes vacuously.
- `cart_link` hardcodes `/cart/` and `/cart/{id}/` URLs — **the library
  has no views, yet ships a tag that assumes specific URL shapes**.
- Factory fallbacks for `CART_TAX_CALCULATOR`,
  `CART_SHIPPING_CALCULATOR`, `CART_INVENTORY_CHECKER` swallow
  `ImportError`/`AttributeError` silently (documented — roadmap
  P1-4 adds a warning log).
- **`Cart.checkout()` does not call `can_checkout()`** — checkout of
  empty cart or cart below minimum order is allowed (documented,
  roadmap P1-2).

### Low (P3)

- `cart/__init__.py` still ships `default_app_config`, deprecated since
  Django 3.2 and removed in Django 6.0.
- Pre-commit config lists pinned versions ~18 months stale; CI runs
  neither linting nor type-checking.
- `.github/dependabot.yml` covers pip + gh-actions but not the
  library's bundled tool versions (pre-commit).
- No partial index on `Cart(checked_out=False)` for the clean-up path.
- `Cart.get_user_carts()` includes checked-out carts; the README's
  login flow example uses `.filter(checked_out=False)` on top — a
  sharp footgun for anyone skipping the filter.
- `Item.quantity` at the DB layer is `PositiveIntegerField` (allows 0)
  while the Cart API rejects 0 on add/update — a direct
  `Item.objects.create(..., quantity=0)` bypasses validation.
- No currency field anywhere — reserved for the P3-10 roadmap slot.

### E-commerce capability gaps (design, not bugs)

- No line-item / per-category discounts; whole-cart only.
- No discount stacking. First-code-wins enforced.
- No multi-currency; no tax-inclusive vs tax-exclusive modes.
- No shipping/billing addresses (tax and shipping calculators get
  `cart` only — no destination context).
- No inventory reservation (interface exists, unused by library).
- No product variants / bundles / BOGO logic (expected — library
  scope).
- No order-from-cart: `checkout()` marks a flag but never emits an
  `Order` record.
- No webhook / REST / async support by default (expected).
- No customer-tier, loyalty, gift-card integration points.

---

## 1. Repo at a glance

| Metric | Value |
|--------|-------|
| Lines of code (`cart/`) | ~1300, of which `cart/cart.py` is ~720 |
| Migrations | 5 (0001 initial → 0005 discount) |
| Tests | ~180 behavioural pytest functions across 26 files |
| Coverage (advisory floor) | 90% — actual ≈ 98% per CHANGELOG |
| Python / Django matrix | Py 3.10–3.14 × Dj 4.2–6.0 (Py<3.12 excludes 6.0) |
| Dependencies | Django only |
| License | MIT (relicensed from LGPL in v3.0.11) |
| Public API surface | ~30 methods on `Cart`, 3 ABCs (Tax/Shipping/Inventory), 1 ABC (Session) + 2 concrete adapters, 5 signals, 4 template tags |

The code is organised around **one facade class** over **one database
row**; every optional subsystem is a dotted-path setting pointing at
a subclass of an abstract base. There is no registry, metaclass, or
module-level mutable state — readability is excellent.

**Pattern strengths I want to call out explicitly before the
criticism lands.** These are the things this codebase gets *right*
that many cart libraries get wrong:

1. **Generic FK on `Item`** — products live in the consumer's schema,
   `django-cart` never forks your product model. This is the right
   coupling.
2. **Decimal-only arithmetic** — `Decimal("x.xx")` literals everywhere,
   `decimal_places=2` on money fields, no float contamination. One of
   the most common e-commerce bug classes is ruled out at the type
   level.
3. **Pluggable subsystems via ABCs** — no "strategy pattern with a
   registry and a decorator." The subclass + settings dotted path
   combination is the simplest thing that could work, and it does.
4. **Transaction-wrapped mutations** — every mutation is atomic, and
   the cache invalidation contract is consistent.
5. **Observable without invasion** — five signals cover the full
   lifecycle; `cart/signals.py` is 12 lines, and every mutation site
   emits the relevant one.
6. **Tests prefer DB state over mocks** — post-P-1 overhaul, the
   suite asserts real outcomes (`cart.items.first().quantity == 3`)
   instead of `mock.assert_called_with(…)`. This is the correct
   culture shift.

The rest of this document is what's left once those foundations are
in place — and what a production e-commerce deployment would need to
add on top.

---

## 2. Architecture assessment

### 2.1 The `Cart` facade pattern

The separation between `cart.cart.Cart` (runtime facade) and
`cart.models.Cart` (DB row) is pragmatic: the facade holds the
request-bound session adapter, an in-memory cache, and all mutation
methods, while the model is a minimal ORM row. The `from . import models`
convention in `cart/cart.py` (using `models.Cart`, `models.Item` prefix)
sidesteps the name collision cleanly.

**Critique:** the naming reuse is still a footgun for downstream users.
Any code that imports both symbols — not uncommon for projects writing
custom admin views, signals, or manager subclasses — must alias one.
Consider renaming the facade to `CartSession`, `CartAPI`, or just
`cart` (module-level function that returns a bound instance). Not a
bug, but low-cost API sharpening for a future major version.

### 2.2 Generic FK for products

Using `(content_type, object_id)` means cart items reference any
model without schema coupling. This is correct for a library that
doesn't own the product catalogue. The custom `ItemManager` that
translates `product=<instance>` kwargs into `content_type + object_id`
is the right ergonomic layer; it keeps call sites readable
(`Item.objects.filter(cart=c, product=p)`).

**Shared weakness:** `Item.product` is a per-instance cached property
via `_product_cache`. Iterating a 50-item cart with items from the
same product model still issues 50 `SELECT … FROM product_model
WHERE pk IN (?)` queries — no batch prefetch by content type. This
is acknowledged in CLAUDE.md §3.2 and the ROADMAP, but I'd flag it
as the single most impactful performance improvement the library
could make. See §8.1.

### 2.3 Pluggable subsystems

`TaxCalculator`, `ShippingCalculator`, `InventoryChecker` all follow
the same ABC + default + factory pattern with a dotted-path setting.
This is good. Two specific weaknesses:

1. **No cart-side context passed to the calculator.** `calculate(self,
   cart)` gets the `Cart` facade — but not the request, the session,
   or any address. Any calculator that needs the shipping destination
   has to reach into `cart._session` (an underscore attribute) or
   thread custom state through the `Cart` object. The right answer is
   a context object — see §13.6 recommendation.
2. **Silent fallback on `ImportError` / `AttributeError`.** A typo
   in `CART_TAX_CALCULATOR` silently yields "tax is always 0.00".
   Documented, and scheduled as P1-4; I'd elevate this to P0 for a
   minor release bump. A warning log is the floor — a startup
   `AppConfig.ready()` pre-flight check that imports every configured
   calculator is better, and cheap.

### 2.4 Session abstraction

`CartSessionAdapter` (ABC) + `DjangoSessionAdapter` + `CookieSessionAdapter`
are the right shape. `CARTS_SESSION_ADAPTER_CLASS` now correctly
accepts a class or a dotted string. **But** the wire-up between
`Cart.__init__` and `CookieSessionAdapter` is incomplete — see §4.1
for the full trace.

### 2.5 Cart creation side-effect

`Cart(request)` always materialises a DB row if none is bound to the
session. This is documented in AGENTS.md, but it's worth calling
out as a design choice with real consequences:

- Every HTTP hit that renders a template with a cart-related tag
  creates a cart row (assuming P1-C is fixed — today it's even worse).
- Bot traffic, 404 pages, healthchecks on any path that constructs
  a Cart all create rows. `clean_carts` is a necessary cron, not an
  optimisation.
- An alternative is lazy materialisation — don't create a row until
  the first mutation. The facade can carry a `_cart_id=None` state
  and only `objects.create()` on the first `add`/`merge`. This is a
  meaningful architecture change; I'd scope it to a 4.0.

---

## 3. Correctness — the new bug list

The next four subsections each document one unambiguous bug with
the evidence, the impact, the minimal fix, and the test that would
have caught it.

### 4.1 [P0-A] `CookieSessionAdapter` never writes the cookie to the response

**File:** `cart/cart.py:90-108`, `cart/session.py:77-94`

**Trace:**

```
Cart.__init__(request)
 └─ _build_session_adapter(request)
     └─ if CARTS_SESSION_ADAPTER_CLASS == "cart.session.CookieSessionAdapter":
         └─ return CookieSessionAdapter(request)   # positional — only request

CookieSessionAdapter.__init__(self, request=None, response=None):
    self._request = request
    self._response = None                # ← default; never populated
    self._cookies = dict(request.COOKIES)

# Later, when the cart is newly created:
Cart._new():
    models.Cart.objects.create(...)
    self._session.set_cart_id(cart.id)
     └─ CookieSessionAdapter.set_cart_id(cart_id)
         └─ self.set(CART_ID, str(cart_id))
             └─ self._cookies[CART_ID] = str(cart_id)
             └─ if self._response is not None:   # FALSE — response was never bound
                    self._response.set_cookie(...)  # NEVER RUNS
```

**Observable impact.** A project that sets
`CARTS_SESSION_ADAPTER_CLASS = "cart.session.CookieSessionAdapter"`:

1. Every request creates a *new* `cart.models.Cart` row.
2. No `Set-Cookie: CART-ID=…` is ever sent to the browser.
3. The cart never persists across requests; features advertised in
   the README (serialisation across devices, cross-request lifecycle)
   are broken.
4. The DB fills with abandoned carts proportional to traffic.

**Why the tests didn't catch it.**
`test_cookie_session_adapter_round_trips_via_real_request_cookies`
(line 204 of `test_session_adapters.py`) manually constructs a
`CookieSessionAdapter(response=response)` — passing the response
explicitly, which the Cart flow never does. The test verifies the
*adapter*, not the adapter-through-Cart *integration*.

**What P0-4 actually fixed.** The P0-4 claim ("CookieSessionAdapter
now round-trips cookies across requests") fixed the *read* side —
hydrating `self._cookies` from `request.COOKIES`. That part works
and is correctly tested. The *write* side was never wired; P0-4
didn't break it, it inherited the gap from the v2.x CookieSessionAdapter
and left it unresolved.

**Minimum fix.** Two options:

**Option A — middleware** (recommended, correct)

Add `CartResponseCookieMiddleware` that:
1. In `process_request`, creates the `CookieSessionAdapter` from
   `request` only and stores it on `request._cart_session`.
2. In `process_response`, takes the adapter's `_cookies` dict, diffs
   against `request.COOKIES`, and calls `response.set_cookie(...)` for
   added/changed keys and `response.delete_cookie(...)` for removed
   ones.
3. Cart's `_build_session_adapter` pulls the adapter from
   `request._cart_session` instead of constructing one fresh.

This is the correct architecture — the library middleware owns the
request↔response lifecycle handoff, not the cart-consumer.

**Option B — response parameter on mutations** (simpler, leaky)

Add a `response` parameter to `Cart.checkout()` / `clear()` / any
method that must persist session state. Callers pass the response
object. Leaky because the library API now depends on view-layer
plumbing, and `Cart(request)` cannot lazily create a row without a
response in hand.

**Regression test to add.**

```python
@pytest.mark.django_db
def test_cookie_session_adapter_persists_cart_id_through_cart_facade(client, settings):
    settings.CARTS_SESSION_ADAPTER_CLASS = "cart.session.CookieSessionAdapter"
    settings.MIDDLEWARE = [..., "cart.middleware.CartResponseCookieMiddleware"]

    # Fresh request: no cookies → cart is created, CART-ID cookie is set.
    r1 = client.get("/cart/")
    assert "CART-ID" in r1.cookies
    first_id = r1.cookies["CART-ID"].value

    # Second request: cookie echoed back → same cart recovered, no new row.
    r2 = client.get("/cart/")
    assert r2.cookies.get("CART-ID", None) in (None, first_id)  # no rotation
    assert Cart.objects.count() == 1
```

### 4.2 [P1-A] `checkout()` double-increments `Discount.current_uses`

**File:** `cart/cart.py:298-334`

**Scenario.** Two concurrent requests for the same session (double-click,
two tabs, a retry) both construct `Cart(request)` and call
`checkout()` concurrently. A discount is applied, `max_uses=None`.

**Execution trace:**

```
Thread A                                  Thread B
─────────                                 ─────────
Cart(request) → read cart row (pk=42),    Cart(request) → read cart row (pk=42),
                checked_out=False                         checked_out=False
checkout():
  if self.cart.checked_out: return  # False, proceed
  atomic:
    SELECT … FROM Discount … FOR UPDATE
    lock acquired
    is_valid_for_cart() → True (max_uses None)
    increment_usage()           # 0 → 1
    UPDATE Cart SET checked_out=True
  commit; release lock
  fire cart_checked_out signal
                                          checkout():
                                            if self.cart.checked_out: return
                                              # in-memory copy still False!
                                              # we never refreshed it from DB
                                            atomic:
                                              SELECT … FROM Discount … FOR UPDATE
                                              (waits for A's lock → acquired)
                                              is_valid_for_cart() → True
                                              increment_usage()     # 1 → 2  ←✗
                                              UPDATE Cart SET checked_out=True
                                            commit
                                            fire cart_checked_out signal  ←✗
```

`current_uses` ends at 2 for a single cart's checkout. The second
signal fires with `self.cart.checked_out=True` (post-save), and any
listener that treats `cart_checked_out` as "a new order was placed"
will double-count.

**Why `max_uses` sometimes saves you.** If `max_uses=1`, thread B
locks the discount and finds `current_uses=1 >= max_uses=1`, fails
`is_valid_for_cart()`, raises `InvalidDiscountError`, rolls back.
Everything is correct in that specific case. For any cap greater
than the racing concurrency — including `max_uses=None` (unlimited) —
the counter drifts.

**Minimum fix.**

```python
def checkout(self) -> None:
    with transaction.atomic():
        # Lock the Cart row and re-read its state under the lock.
        locked_cart = models.Cart.objects.select_for_update().get(pk=self.cart.pk)
        if locked_cart.checked_out:
            return

        if locked_cart.discount_id is not None:
            locked_discount = models.Discount.objects.select_for_update().get(
                pk=locked_cart.discount_id
            )
            is_valid, message = locked_discount.is_valid_for_cart(self)
            if not is_valid:
                raise InvalidDiscountError(message)
            locked_discount.increment_usage()

        locked_cart.checked_out = True
        locked_cart.save(update_fields=["checked_out"])
        # Keep the facade's in-memory view in sync.
        self.cart.checked_out = True

    if cart_checked_out is not None:
        cart_checked_out.send(sender=self.__class__, cart=self.cart)
```

**Regression test.**

```python
@pytest.mark.django_db(transaction=True)
def test_concurrent_checkouts_do_not_double_increment_discount_counter(
    cart_worth_200, discount_percent
):
    cart_worth_200.apply_discount("PERCENT20")
    # Simulate a second "thread" by constructing a second Cart facade
    # on the same session row.
    twin = Cart(cart_worth_200._session._session  # or use a mock request
                if hasattr(cart_worth_200._session, "_session") else None)
    twin.cart = cart_worth_200.cart

    # Both commit concurrently; with the fix, only the first succeeds
    # in incrementing the counter.
    cart_worth_200.checkout()
    twin.checkout()  # idempotent return, no second increment

    discount_percent.refresh_from_db()
    assert discount_percent.current_uses == 1
```

(A true-concurrency test is harder — use `threading` or the
`pytest-django-queries` approach; the idempotency test above is the
minimum.)

### 4.3 [P1-B] `Cart.user` FK hardcodes `auth.User`, breaks custom user models

**File:** `cart/models.py:25-32`

```python
user = models.ForeignKey(
    "auth.User",
    verbose_name=_("user"),
    on_delete=models.CASCADE,
    ...
)
```

Django has recommended `settings.AUTH_USER_MODEL` since 1.5. Any
project that declares a custom user model (very common — tokens,
tenants, profile fields) will find `django-cart` migrations failing
at `makemigrations`:

```
AssertionError: cart.Cart has a relation with model auth.User, which
has been swapped out.
```

**Minimum fix.**

```python
# cart/models.py
from django.conf import settings

user = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    verbose_name=_("user"),
    on_delete=models.CASCADE,
    null=True,
    blank=True,
    related_name="carts",
)
```

And update migration `0003_add_user_fk.py` — **but** since the
migration is already shipped, rewriting it silently is a breaking
change. The correct path is:

1. In a new migration `0006_use_auth_user_model.py`, add a
   `swappable_dependency(settings.AUTH_USER_MODEL)` and alter the
   FK to point at the swappable reference.
2. Document the change prominently — existing projects with the
   default `auth.User` aren't affected; projects with custom user
   models finally *can* install `django-cart`.

**Why this isn't already caught.** The test suite sets no
`AUTH_USER_MODEL`, so Django's default `auth.User` works everywhere.
Add a smoke test that runs the suite under a swapped user model, e.g.
a second `conftest.py` entry with a `tests.custom_user` app.

### 4.4 [P1-C] `cart_link` (and neighbours) create DB rows on every render

**File:** `cart/templatetags/cart_tags.py:11-85`

All four cart template tags call `Cart(request)` unconditionally:

```python
@register.simple_tag(takes_context=True)
def cart_item_count(context) -> int:
    request = context.get("request")
    if request is None:
        return 0
    cart = Cart(request)       # ← DB row is created if none exists
    return cart.count()
```

`cart_link` is worse — it constructs a Cart *just to get the cart id*
from the session:

```python
@register.simple_tag(takes_context=True)
def cart_link(context, text: str = "View Cart", css_class: str = "") -> str:
    request = context.get("request")
    if request is None:
        cart_url = "/cart/"
    else:
        cart = Cart(request)               # ← creates a DB row
        cart_id = request.session.get("CART-ID", "")  # ← read session
        cart_url = f"/cart/{cart_id}/" if cart_id else "/cart/"
    ...
```

The `cart` local variable is never used after that line. Side-effect
only.

**Impact.**

- A site-wide header with `{% cart_link %}` + `{% cart_item_count %}`
  + `{% cart_summary %}` creates *one cart per visitor*, including
  bots, crawlers, healthchecks, and users who never intend to shop.
  The DB row table grows linearly with pageviews.
- `clean_carts` must be run aggressively to keep the table manageable.
- The cart id is exposed in URLs — `cart_link` renders
  `<a href="/cart/42/">` — which leaks sequential DB identifiers to
  referrers, analytics, and third-party scripts.
- **There are no default views** at `/cart/` or `/cart/{id}/` in the
  library. Downstream projects that don't define them get 404s from
  their own header.

**Minimum fix.**

```python
@register.simple_tag(takes_context=True)
def cart_item_count(context) -> int:
    request = context.get("request")
    if request is None or "CART-ID" not in request.session:
        return 0
    # Read count directly — avoid materialising a Cart row on pure-read paths.
    from cart.models import Cart as CartModel
    cart_id = request.session["CART-ID"]
    row = (CartModel.objects.filter(id=cart_id, checked_out=False)
                            .aggregate(total=Sum("items__quantity"))["total"])
    return row or 0
```

And for `cart_link`, use `reverse()` with a configurable URL name:

```python
@register.simple_tag(takes_context=True)
def cart_link(context, text="View Cart", css_class=""):
    request = context.get("request")
    url_name = getattr(settings, "CART_DETAIL_URL_NAME", None)
    if url_name:
        try:
            cart_url = reverse(url_name)
        except NoReverseMatch:
            cart_url = "/cart/"
    else:
        cart_url = "/cart/"
    ...
```

Drop the `/cart/{id}/` URL shape entirely — cart ids should not be
in URLs.

**Regression test.**

```python
def test_template_tags_do_not_create_cart_rows_on_read(client, django_assert_num_queries):
    from cart.models import Cart
    tpl = Template("{% load cart_tags %}{% cart_item_count %}{% cart_summary %}")
    before = Cart.objects.count()

    # Render with an empty-session request — tags should return zero
    # without touching the Cart table writes.
    tpl.render(Context({"request": make_empty_request()}))

    assert Cart.objects.count() == before  # no new rows
```

### 4.5 [P1-D] `cart_serializable` / `from_serializable` collide on `object_id` across content types

**Files:** `cart/cart.py:340-371` (serialise), `cart/cart.py:373-429`
(deserialise).

The serialise side:

```python
return {
    str(item.object_id): {                   # ← keyed by object_id only
        "content_type_id": item.content_type_id,
        ...
    }
    for item in self.cart.items.all()
}
```

If a cart has items `(Product model, pk=5)` **and** `(DigitalCourse
model, pk=5)`, both map to key `"5"` and only one survives the dict
comprehension. The whole cart is lossy.

The deserialise side has the same bug — the update lookup only filters
on `object_id`, not `content_type_id`:

```python
item = models.Item.objects.filter(
    cart=cart.cart,
    object_id=object_id,          # ← no content_type filter
).first()
```

An existing `(DigitalCourse, pk=5)` item in the cart is updated
when a payload describing `(Product, pk=5)` is restored. Data
corruption.

**Minimum fix.**

Key the serialised dict by a composite:

```python
return {
    f"{item.content_type_id}:{item.object_id}": {
        "content_type_id": item.content_type_id,
        "object_id": item.object_id,
        ...
    }
    for item in self.cart.items.all()
}
```

On restore, parse the composite key and filter on both columns. The
change is a breaking format migration — pre-v3.0.11 payloads (which
already raised `ValueError` on fresh-cart restore per P0-1) would
also fail here. A payload-version header (`"__version__": 2`) is the
right way to thread the compatibility.

**Regression test.**

```python
def test_cart_serializable_round_trips_items_from_multiple_content_types(
    cart, product_factory, rf_request
):
    # Two different product models with the same PK.
    p1 = product_factory(name="Model A")     # FakeProduct pk=1
    p2 = SomeOtherModel.objects.create(pk=1)  # different model, same PK
    cart.add(p1, Decimal("5.00"))
    cart.add(p2, Decimal("7.00"))

    payload = cart.cart_serializable()
    fresh = make_empty_request()
    restored = Cart.from_serializable(fresh, payload)

    assert restored.unique_count() == 2      # both items survive
```

---

## 5. Security review

### 5.1 Input validation at the API boundary

- `Cart.add(unit_price, …)` — trusts the caller for `unit_price`.
  `validate_price=True` is opt-in and silently skips if
  `product.price is None`. **Most downstream views won't opt in** and
  will be vulnerable to client-side price tampering (POST body sets
  `unit_price=0.01`). The safer default would be to require a
  `validate_price` choice (raise if not provided) or to read
  `product.price` itself when the attribute is available.
- `apply_discount(code)` — no rate limiting. A brute-force enumeration
  of short codes is trivial. Library documents nothing about this.
  Rate-limiting is a framework-level concern but worth a note in
  the README.
- Discount codes are **case-sensitive** (`Discount.objects.get(code=code)`).
  Most storefronts normalise to uppercase on apply; doing so here
  would prevent "SAVE10" vs "save10" ambiguity. Low severity.

### 5.2 Session-layer concerns

- **Session fixation / CART-ID forgery.** The `CART-ID` key in the
  session is just an integer; it maps to `Cart.pk`. A user who tampers
  with their session (only possible if they hold the signing key or
  the session is stored client-side) can switch to any cart they
  know the ID of — including another user's cart. The defence-in-depth
  is `Cart.user` (when bound) but `Cart.__init__` doesn't re-verify
  that the cart's `user` matches the request's `user`. If a user
  logs out, logs in as someone else, and keeps the same
  session-inherited CART-ID, they see the previous user's cart.
- **Cart id sequentiality.** `Cart.id` is an auto-increment int.
  `cart_link` exposes this in URLs. UUIDs would be stricter but the
  change is a major migration; a minimal hardening is to never put
  the cart id in a URL (see P1-C).

### 5.3 CSRF / view-layer

The library ships no views. `tests/test_app/views.py` uses
`@require_POST` but no CSRF protection. Downstream projects are
responsible. Add a note to the README's Quick Start section — don't
show POST views without a word about CSRF.

### 5.4 SQL / ORM

All access is via the Django ORM; no raw SQL. Composite unique
constraint and index on `(cart, content_type, object_id)` is correct.
The `ItemManager._inject_content_type` translator uses `pop("product")`
and injects `content_type` + `object_id` — safe. No SQL injection
surface I could find.

### 5.5 Deserialisation

`Cart.from_serializable(request, data)` trusts the payload entirely.
If `data` comes from a user-controlled source (e.g. localStorage,
mobile app, unauthenticated query param), they can:

- Inject arbitrary `content_type_id` + `object_id` pairs — but
  `Item.objects.create` raises `IntegrityError` on nonexistent FKs,
  so this only wastes a transaction.
- Inject negative/huge `quantity` values — the `PositiveIntegerField`
  rejects negatives, but *zero* passes the DB check and the
  deserialiser (API-level validation doesn't re-check here).
- Inject arbitrary `unit_price` — accepted up to
  `max_digits=18, decimal_places=2`. No upper bound.

**Recommendation:** run every item in `from_serializable` through
the same validation path as `Cart.add(..., validate_price=True)`,
and reject `quantity <= 0`. This is a one-screen fix that hardens
a documented integration surface.

---

## 6. Data model critique

```
Cart
├── id                int         auto
├── creation_date     datetime    default now
├── checked_out       bool        default False
├── user              FK          auth.User  ← should be AUTH_USER_MODEL
└── discount          FK nullable SET_NULL

Item
├── cart              FK CASCADE
├── quantity          PositiveInteger        ← allows 0; API rejects
├── unit_price        Decimal(18,2)  >= 0
├── content_type      FK  CASCADE
├── object_id         PositiveInteger
└── unique (cart, content_type, object_id)
    + composite index on same

Discount
├── code              char(50)  unique
├── discount_type     char(10)  choices
├── value             Decimal(10,2)  >= 0   ← no upper bound for PERCENT
├── min_cart_value    Decimal(10,2) nullable
├── max_uses          PositiveInteger nullable
├── current_uses      PositiveInteger default 0
├── active            bool  default True
├── valid_from        datetime nullable
└── valid_until       datetime nullable
```

### Concrete issues

| Field | Issue | Fix |
|-------|-------|-----|
| `Cart.user` | `auth.User` hardcoded | `settings.AUTH_USER_MODEL` (P1-B) |
| `Item.quantity` | `PositiveIntegerField` allows 0, but API rejects | Add `MinValueValidator(1)` to align layers |
| `Discount.value` for PERCENT | No upper bound | Add model-level `clean()` that rejects `value > 100` when `discount_type=='percent'` |
| `Discount.valid_from` / `valid_until` | No invariant | `CheckConstraint(Q(valid_from__lt=valid_until) \| Q(valid_from__isnull=True) \| Q(valid_until__isnull=True))` |
| `Discount.max_uses` / `current_uses` | No invariant | `CheckConstraint(Q(current_uses__lte=F("max_uses")) \| Q(max_uses__isnull=True))` |
| `Cart.checked_out` | No index, but `clean_carts` filters on it | `db_index=True` or `Meta.indexes` for `checked_out` alone or partial index on `checked_out=False` |
| `Cart.creation_date` | No index, but `clean_carts` + default ordering both use it | `db_index=True` |
| `Cart.discount` | `SET_NULL` is correct for the "discount was deleted" case, but the cart retains the pricing snapshot silently | Consider storing `discount_amount_applied` on the cart at checkout for audit purposes |
| `Item.unit_price` | No snapshot of the product's price *at the moment* of add (just what the caller said) | By design — the caller controls; but consider `validate_price` default `True` in 4.0 |
| `Discount.code` | No case normalisation | `code = CharField(…); save() { self.code = self.code.upper() }` — or document case-sensitivity prominently |

### Missing fields I'd expect in a 2026 cart

- **`Cart.currency`** (`CharField(3)`) — multi-currency stores need
  this on every cart. Even single-currency stores benefit from an
  explicit marker to future-proof.
- **`Cart.session_id`** or similar — for "abandoned cart" email
  flows, a persistent ID that survives login is useful. The
  `bind_to_user` path is strong, but guest-cart analytics still needs
  this.
- **`Cart.last_modified`** — `creation_date` tells you when the cart
  was spawned, but "abandoned for 14 days" flows want the last add /
  update time. Compute on write.
- **`Item.created_at` / `Item.updated_at`** — order of items in the
  cart, age of each line. Today the default `ordering=("cart",)` is
  not deterministic per-row; ordering by `id` or a `created_at` would
  be both stable and useful.
- **`Item.metadata` JSONField** — line-item notes, gift messages,
  engraving text, size/colour variant selections when the product
  model is opaque. A single JSON column is the escape hatch.

---

## 7. API surface review

### 7.1 `Cart` method list

| Method | Comment |
|--------|---------|
| `__init__(request)` | Creates DB row on first call — documented footgun. |
| `add(product, unit_price, quantity=1, validate_price=False, check_inventory=False)` | Parameter order fine; price before quantity would match the DB field order but hurt common call sites. Keep. |
| `remove(product)` | Raises `ItemDoesNotExist` when missing. OK. |
| `update(product, quantity, unit_price=None, validate_price=False)` | `quantity=0` as "delete" is terse; a separate `remove` is the correct API and `update` should probably reject 0 in 4.0. |
| `count()` / `unique_count()` / `is_empty()` | Clean. |
| `summary()` / `tax()` / `shipping()` / `total()` / `discount_amount()` | All return `Decimal`. Add explicit `.quantize(Decimal("0.01"), ROUND_HALF_UP)` in `total()` — see §6. |
| `clear()` | Doesn't fire a per-item signal. Design. |
| `checkout()` | See P1-A. |
| `apply_discount(code)` | Consider uppercasing `code`. |
| `remove_discount()` | Clean. |
| `merge(other_cart, strategy="add")` | Strategies are good; silently clamps over-quantity while `add` raises — inconsistent. Document or unify. |
| `add_bulk(items)` | Clean. Consider accepting dataclass / TypedDict for `items` rather than raw dicts. |
| `bind_to_user(user)` | Doesn't check prior bindings; may silently reassign. Low severity. |
| `get_user_carts(user)` | Returns **all** carts including checked-out; callers must filter. Consider `checked_out=False` default or rename. |
| `cart_serializable()` / `from_serializable()` | See P1-D. Missing: discount state, user binding. |
| `can_checkout()` | Not called inside `checkout()` — documented tradeoff, roadmap P1-2. |
| `shipping_options()` | Fine, but return type inconsistency: `ShippingOption` TypedDict says `price: str`, test doubles return `price: Decimal`, default returns `price: "0.00"` (str). Fix the TypedDict to `price: Decimal` and coerce at the boundary (display layer). |

### 7.2 Exception hierarchy

`CartException` → `ItemAlreadyExists` (never raised in the codebase —
vestigial), `ItemDoesNotExist`, `InvalidQuantity`, `PriceMismatchError`,
`InvalidDiscountError`, `InsufficientStock`, `MinimumOrderNotMet` (also
never raised by the library itself).

**Dead exceptions.** `ItemAlreadyExists` is defined (line 32) but
never raised anywhere. Remove or repurpose.
`MinimumOrderNotMet` is defined (line 56) but `can_checkout()` returns
a `(bool, str)` tuple instead — the exception is never raised. Either
raise it (when `checkout()` gains the can-checkout call in roadmap
P1-2) or delete it.

### 7.3 Settings surface

- `CART_TAX_CALCULATOR`, `CART_SHIPPING_CALCULATOR`,
  `CART_INVENTORY_CHECKER` — dotted path OR class object. Silent
  fallback.
- `CARTS_SESSION_ADAPTER_CLASS` — dotted path OR class. Loud failure.
- `CART_MAX_QUANTITY_PER_ITEM` — int or `None`.
- `CART_MIN_ORDER_AMOUNT` — Decimal or `None`.

**Observation.** The *plural* `CARTS_…` naming for the session adapter
is asymmetric with the *singular* `CART_…` for the rest. Pick one —
`CART_SESSION_ADAPTER` reads more naturally and matches the pattern.
Deprecation path: accept both for one minor release, warn when
the plural is used.

---

## 8. Performance

### 8.1 The N+1 on `Item.product`

Documented in CLAUDE.md §3.2 and mentioned in the ROADMAP. The fix is
a batched product loader keyed by content_type:

```python
def items_with_products(self):
    items_by_ct = defaultdict(list)
    for item in self.cart.items.select_related("content_type").all():
        items_by_ct[item.content_type].append(item)

    # One SELECT per content type, not one per item.
    for ct, items in items_by_ct.items():
        ids = [i.object_id for i in items]
        products = ct.model_class().objects.in_bulk(ids)
        for item in items:
            item._product_cache = products.get(item.object_id)
            yield item
```

A 100-item cart with items from 3 product models drops from ~100 queries
to 4. This is the single highest-impact optimization the library can
ship. It should be an additive method (`items_with_products()`) rather
than a change to `__iter__` — backwards compat preserved.

### 8.2 `summary()` and `count()` cache lifecycle

The in-memory `_cache` dict is invalidated on every mutation — correct.
It's not thread-safe — fine, single-request use. The cache key set is
minimal (`summary`, `count`). One tiny improvement: cache
`discount_amount()`, `tax()`, `shipping()`, and `total()` too — all
of these are pure functions of `summary()` + the configured subsystem.
Caching them saves repeated calculator invocations inside a single
request (a template that displays subtotal, tax, shipping, and total
calls `total()` which calls all three calculators; if each shows them
separately, calculators run 4× per render).

### 8.3 Iteration query count

`Cart.__iter__` uses `select_related("content_type")` — good. `list(cart)`
also triggers `__len__` which calls `count()` — one extra query.
`test_iteration_is_query_bounded_independent_of_item_count` locks this
at max 3. Fine.

### 8.4 `clean_carts` performance

Filters on `creation_date__lt=cutoff AND checked_out=False`. Without
an index on `checked_out`, the query does a sequential scan on large
tables. With tens of thousands of carts the daily cron starts to
bite. Add `db_index=True` on `Cart.checked_out` — or, better, a
partial index:

```python
class Meta:
    indexes = [
        models.Index(fields=["creation_date"], condition=Q(checked_out=False),
                     name="cart_active_creation_idx"),
    ]
```

Postgres supports partial indexes; MySQL doesn't (and Django versions
differ in partial-index support) — verify at migration time.

### 8.5 Non-issues

- `cart.summary()` uses `Sum(F("quantity") * F("unit_price"))` — DB-side
  aggregation, correct.
- `cart.count()` uses `Sum("quantity")` — DB-side, correct.
- No O(N) Python loops over items in hot paths.

---

## 9. Test-suite evaluation

The P-1 overhaul is a meaningful upgrade. Concrete strengths:

- **All fixtures in `conftest.py`.** No more `make_request` helpers
  duplicated across files.
- **Pytest + pytest-django exclusively.** `python_classes = []` in
  `pyproject.toml` prevents accidental TestCase collection.
- **DB-state assertions over mock-call assertions.** The integration
  tests in `test_http_integration.py` exercise the real request
  pipeline.
- **`django_assert_num_queries` instead of wall-clock timing.**
  Reproducible.
- **Parametrisation** used appropriately (see `test_cart_merge.py`
  strategy table).

### Specific weaknesses

1. **No concurrency / race tests.** The library claims "race-safe at
   the discount level" and "idempotent checkout" in the README. The
   double-increment bug (P1-A) exists because no test covers the
   concurrency contract. Use `threading.Thread` +
   `django_db(transaction=True)` + `SELECT FOR UPDATE` assertions
   (`django_assert_num_queries` with `select_for_update=True`).
2. **Missing end-to-end test for CookieSessionAdapter through Cart.**
   See P0-A. The closest test manually injects a response — it does
   not exercise the full `Cart(request) → CookieSessionAdapter → …`
   flow.
3. **`test_cart_admin_changelist_search_filters_by_cart_id` is
   vacuous.** `CartAdmin` has no `search_fields`, so `?q=…` is a
   no-op; the assertion passes because the target cart is in the
   changelist regardless. Either fix `CartAdmin` (add
   `search_fields=("id",)`) or delete the test.
4. **Template-tag integration tests don't cover row-creation
   side-effects.** `test_cart_item_count_renders_through_template_engine`
   verifies the output is `"0"`, but doesn't assert that no Cart row
   was created.
5. **No custom-user-model smoke.** Cannot catch P1-B without a second
   test-suite configuration that swaps `AUTH_USER_MODEL`.
6. **`test_cart_serializable_preserves_unicode_product_names`** only
   asserts that the PK key is in the dict — the unicode name itself is
   not checked. Rename or beef up.
7. **Dead `unittest.mock` dependency** in `test_shipping.py` and
   `test_tax.py` — `_mock_cart()` uses MagicMock. Per the P-1 overhaul
   rule, "no MagicMock for requests"; but `_mock_cart()` here is a
   MagicMock for *the cart facade*, not the request. It's less bad,
   but still fragile — swap for a real `cart` fixture.

---

## 10. CI / CD observations

**What works:**

- Matrix across Py 3.10–3.14 × Dj 4.2–6.0.
- Tag-gated PyPI publish with `--skip-existing` idempotency.
- Changelog-gate that fails the build if `CHANGELOG.md` lacks the
  current version header.

**What's missing:**

1. **No lint job.** `.pre-commit-config.yaml` exists but CI never runs
   `pre-commit run --all-files`. Contributors who skip pre-commit
   locally can land unformatted/untyped code.
2. **No type-check job.** `mypy` is in `.pre-commit-config.yaml` but
   never runs.
3. **Stale pinned versions.** Black 24.1.0, isort 5.13.0, flake8 7.0.0,
   mypy 1.8.0, pre-commit 4.5.0 are all ~18 months old as of
   2026-04-21. Dependabot doesn't cover pre-commit hooks.
4. **No coverage gate in CI.** `coverage report` with `fail_under=90`
   is local-only. A CI step that runs `coverage report` (even without
   promoting it to a blocker initially) is a free signal.
5. **No security-audit job.** A `pip-audit` / `safety` run would flag
   dependency CVEs early.
6. **No Django-check job.** `python -m django check --deploy` catches
   common config issues; wouldn't apply to the library itself but
   would surface problems with `tests/settings.py`.
7. **No publish-dry-run on PR.** Could build the wheel and run
   `twine check` without uploading. Catches packaging bugs before tag.

---

## 11. Documentation review

### Strengths

- README is well-structured, uses `> [!note]` / `> [!warning]` call-outs
  for sharp edges, and includes Mermaid diagrams. The "Agent-Ready"
  section is unusual and genuinely useful.
- AGENTS.md is a model of how to document a library for LLM use.
- CLAUDE.md (project-instruction file for this repo) is extremely
  detailed and was clearly kept up to date through the P0 fix wave.
- CHANGELOG follows Keep-a-Changelog and was backfilled to v3.0.0.

### Gaps / drifts

1. **`CLAUDE.md` §7.12 is now slightly inaccurate.** The text says
   `validate_price=True` silently skips for "products that have the
   attribute set to `None`/`0`". The current code (`cart.py:160-164`)
   only skips when `actual_price is None` — a zero price DOES trigger
   validation. The test
   `test_validate_price_accepts_zero_price_match` confirms zero passes
   when matched.
2. **README's "Concurrency" warning** undersells the problem. It warns
   that `add`/`update`/`merge` don't lock rows during reads (correct)
   but doesn't mention the `checkout()` double-increment case
   (P1-A). Add a separate paragraph, or — better — fix the bug.
3. **No document describes the library's behaviour during login.**
   The README's "User binding and merging" section shows a minimal
   flow, but nothing addresses: session rotation on login, what
   happens to a guest cart that's already bound to user X when user Y
   logs in (should raise? silently reassign? merge into Y's cart?).
   This is a common source of production confusion.
4. **No security section.** See §5. A one-screen "Security
   considerations" paragraph in the README covering price validation,
   discount brute-force, and CSRF-in-views would save downstream
   projects meaningful time.
5. **`docs/PROJECT_ANALYSIS.md` and `docs/PROJECT_ANALYSIS_2026_03_29_0243am.md`**
   are referenced in CLAUDE.md but not present in the `docs/` tree.
   Either commit or remove the references.
6. **`docs/ROADMAP_2026_04.md`** is referenced throughout CLAUDE.md
   but not actually committed to this repo — only `docs/AGENTS.md`
   exists under `docs/` in my tree. Missing artefact.

---

## 12. E-commerce capability assessment

The library is explicitly a "session-backed cart facade" — not a
storefront. This section is not a critique of scope; it's a catalogue
of what a production storefront still has to build on top.

### 12.1 Missing domain concepts

| Concept | Today | Production requirement |
|---------|-------|------------------------|
| Currency | None | Multi-currency requires currency on Cart, Item, Discount |
| Localisation | Verbose names via `gettext_lazy`, but discount messages in `Discount.is_valid_for_cart` are hardcoded English strings | i18n the user-facing messages |
| Tax modes | Exclusive only (added on top) | Inclusive vs exclusive mode flag |
| Tax address | Calculator gets `cart` only | Pass destination context |
| Shipping address | Same | Same |
| Inventory reservation | Interface method exists, unused by library | Called automatically from `checkout()`; reservation release on payment failure |
| Line-item discounts | Not supported | Per-item and per-category discounts; stacking rules |
| Bundles / BOGO | Not supported | Promotion engine |
| Gift cards | Not supported | Partial-payment instrument |
| Loyalty points | Not supported | Same |
| Order emission | `Cart.checkout()` just sets a flag | An `Order` model populated from the cart; cart is left in place or frozen |
| Payment integration | Not supported (by design) | Stripe / Adyen / Braintree |
| Refund / partial refund | Not supported (by design) | Extends to Order model |
| Cart expiration | `clean_carts` cron only | Per-cart TTL with soft-delete; "your cart expired" UX |
| Abandoned-cart analytics | Signals cover this | Timestamps + a nightly job |
| Re-pricing | Items keep the unit_price they were added with, even if the Product price changes | Optional re-price hook at `can_checkout()` time |
| Customer tiers | Not supported | Extension point on tax + shipping + discount |
| A/B testing hooks | Not supported | Usually external |

### 12.2 Common production integrations the library makes hard

- **Stripe / payment gateways.** Nothing in the library emits an
  "order is ready to charge" event. Downstream code has to wrap
  `cart.checkout()` in a saga that:
  1. Computes `total()`
  2. Charges the payment provider
  3. Calls `cart.checkout()` on success
  4. Compensates (refund, cart.clear()?) on failure
  The library doesn't document a recommended shape.
- **Order numbers.** No sequential, human-friendly order number
  generator. Consumers typically want `ORDER-2026-000123`.
- **Tax jurisdictions via third-party (Avalara, TaxJar, Stripe Tax).**
  The `TaxCalculator` interface is minimal — `calculate(cart) -> Decimal`.
  Real tax services return a per-line breakdown, juris-by-juris.
  Extending the interface without breaking the ABC requires a new
  method (`calculate_lines(cart) -> list[dict]`) with a default
  implementation that calls `calculate()`.
- **Webhooks.** Signals are in-process only; a webhook integration
  requires a per-project bridge.

### 12.3 What I'd add to the roadmap

In priority order, for a hypothetical 3.1 / 4.0 scope:

1. Fix P0-A / P1-A / P1-B / P1-C / P1-D. These are all-in 4 hours of
   work each and remove the largest current blocker (P1-B is the
   gating issue for projects with custom user models).
2. Ship `items_with_products()` batch loader (§8.1).
3. Add `Cart.currency` field and thread it through `summary()`,
   `total()`, calculators.
4. Add an address context object that calculators receive. Today:
   `calculator.calculate(cart)`. Proposed:
   `calculator.calculate(cart, context: CartContext)`.
5. Add a proper middleware pair for CookieSessionAdapter so the
   cookie round-trip works through `Cart(request)`.
6. Deprecate `CARTS_SESSION_ADAPTER_CLASS` in favour of
   `CART_SESSION_ADAPTER` (naming consistency).
7. Enforce `can_checkout()` inside `checkout()` — P1-2 on the
   existing roadmap.
8. Inventory reservation from `checkout()` (or an optional
   `reserve=True` flag).
9. Line-item discounts — extend `Discount` with an optional M2M to
   content types, and `calculate_discount` with per-item granularity.
10. `Order` model + `cart.to_order()` convenience.

---

## 13. Code-quality catalogue

### 13.1 Vestigial code

- **`cart/__init__.py`** — `default_app_config = "cart.apps.CartConfig"`.
  Deprecated since Django 3.2, removed in Django 6.0. Delete the
  line; Django auto-discovers `CartConfig` via `apps.py`.
- **`cart/views.py`** — single comment "Create your views here.".
  Delete the file.
- **`ItemAlreadyExists`** and **`MinimumOrderNotMet`** — defined in
  `cart/cart.py` but never raised. Delete or raise.
- **`tests/fixtures/fake_products.json`** — said to be deleted in
  v3.0.10; confirmed absent in the `tests/` tree. ✅
- **`runtests.py`** — said to be deleted in v3.0.10; confirmed absent. ✅

### 13.2 Type-hint gaps

Model-level type hints are applied to `Cart` / `Item` fields but not
`Discount` — per CLAUDE.md §6 "acceptable inconsistency". I'd still
bring `Discount` up to parity; it's a 5-minute change and mypy would
stop complaining.

Lazy imports (e.g. `from .tax import get_tax_calculator` inside
`Cart.tax()`) make `mypy` struggle without
`--follow-imports=normal`. Document or remove.

### 13.3 Docstring style inconsistency

CLAUDE.md §6 says: Sphinx (`:param:` / `:returns:`) in `cart/cart.py`,
Google (`Args:` / `Returns:`) in newer files. Inside `cart/cart.py`
itself, **both styles appear** — compare `Cart.add` (Sphinx) with
`Cart.apply_discount` (Google). Pick one per file; the convention
"match the neighbour" isn't being applied to `cart/cart.py`.

### 13.4 Comment quality

Generally good. A few specific comments earn their keep (the one on
`tests/urls.py:_bare_404` explaining the Py3.14 + Django<6 interaction
is exemplary). No dead comments found.

### 13.5 Naming

- `Cart` class ↔ `Cart` model name collision — see §2.1.
- `get_tax_calculator` / `get_shipping_calculator` /
  `get_inventory_checker` are consistent — good.
- `CARTS_SESSION_ADAPTER_CLASS` plural, rest singular — see §7.3.
- `Item.content_type_id` vs `Item.content_type` — Django convention,
  fine.
- `cart_item_added` / `cart_item_removed` / `cart_item_updated`
  signals use `item` kwarg. `cart_cleared` doesn't carry items —
  fine, but a consumer tracking "what was just removed" on `cleared`
  gets nothing. Consider `products: list` payload.

### 13.6 Small-but-real refactors that earn their keep

- **Centralise the max-quantity check.** `cart/cart.py` reads
  `getattr(settings, 'CART_MAX_QUANTITY_PER_ITEM', None)` in
  `add`, `update`, `merge`, and `add_bulk` — four call sites. A
  module-level helper `_max_quantity_per_item() -> int | None`
  reduces duplication. Low value change, but readable.
- **Inline the `_get_item` definition next to `_new`.** They're used
  everywhere and currently separated by the iteration dunders.
  Cosmetic.
- **`_invalidate_cache()` is called ≈ 8 times.** A decorator
  `@invalidates_cache` on mutation methods would be cleaner — but
  borderline over-engineering for 8 call sites. Skip.

### 13.7 A small nit on the coverage config

`[tool.coverage.run] branch = true` is correct. `omit = ["*/migrations/*",
"*/tests/*"]` — standard. **Consider adding `"cart/session.py"`** to
the exclude list **only** until P0-A is fixed; the current 98%
coverage includes dead cookie-adapter paths and lulls readers into
thinking the feature is verified end-to-end.

---

## 14. Suggested remediation plan

### v3.0.12 (hotfix, ~1 day)

- **[P0-A]** Ship a `CartResponseCookieMiddleware` + wire it to the
  Cart constructor. Add end-to-end test that renders a response with
  `CookieSessionAdapter` wired through settings.
- **[P1-A]** Add `select_for_update()` on the Cart row in
  `checkout()`. Add threaded regression test.
- **[P1-D]** Change `cart_serializable()` key format to
  `"{content_type_id}:{object_id}"`. Include a payload version
  header. Raise `ValueError` on legacy payloads (consistent with
  P0-1's approach).
- Change `Cart.user` FK to `settings.AUTH_USER_MODEL` ([P1-B]).
  Ship migration `0006_swappable_user_fk.py`.
- Fix `cart_link` and neighbours to avoid `Cart()` construction
  ([P1-C]). Deprecate `cart_link` or make it configurable via
  `CART_DETAIL_URL_NAME`.
- Remove `cart/__init__.py` `default_app_config` (P3).
- Remove `cart/views.py` (P3).
- Remove `ItemAlreadyExists` and `MinimumOrderNotMet` (P3).

### v3.1.0 (minor, ~1 week)

- Roadmap-existing P1 items: `can_checkout()` enforcement in
  `checkout()`, warn-on-fallback in the three silent factories.
- Add `items_with_products()` batch loader.
- Add `db_index=True` on `Cart.checked_out` and
  `Cart.creation_date` (or a partial index on Postgres).
- Add `CheckConstraint`s for Discount invariants.
- Deprecate `CARTS_SESSION_ADAPTER_CLASS` in favour of
  `CART_SESSION_ADAPTER` (warn + accept both).
- Add a `context` parameter to the three calculator interfaces (with
  backward-compat default).
- CI: add a lint job (pre-commit run --all-files), a
  mypy type-check job, and a `coverage report` step (non-blocking
  initially).

### v4.0 (major, scope-discussion)

- Rename `Cart` facade (addresses §2.1).
- Add `Cart.currency`.
- Lazy cart materialisation (no DB row until first mutation).
- Built-in `Order` model + `cart.to_order()`.
- Address context for tax / shipping.
- Inventory reservation from `checkout()`.

---

## 15. Appendix

### A. Assumptions made during this audit

1. The codebase I reviewed is the canonical one on PyPI for 3.0.11 —
   not a local fork with undocumented changes. (Confirmed from
   `pyproject.toml` `version = "3.0.11"` and CHANGELOG heading.)
2. The maintainer values the "small surface, agent-ready" identity
   enough that I shouldn't recommend major expansions (Order model,
   payment integration) without calling them out as scope-changers.
3. Production deployments may run on MySQL or Postgres — I've flagged
   partial-index suggestions as Postgres-specific.
4. The README's claim of 290 tests is approximate; my count across
   `tests/test_*.py` is ~180 behavioural pytest functions. The
   parametrisation often turns one function into several collected
   tests; final `pytest --collect-only` count may approach 290.

### B. Files I did not cover in depth

- `.github/dependabot.yml` — sight read only.
- `cart/management/commands/clean_carts.py` — read in full; no bugs
  found.
- `cart/templatetags/__init__.py` and `tests/test_app/migrations/*` —
  glanced at, nothing notable.

### C. Commands I recommend running to reproduce findings

```bash
# Reproduce the CookieSessionAdapter no-persistence behaviour
uv run python -c "
import django; django.setup()
from django.test import RequestFactory
from cart.cart import Cart, CART_ID
from django.test.utils import override_settings

@override_settings(CARTS_SESSION_ADAPTER_CLASS='cart.session.CookieSessionAdapter')
def show():
    r1 = RequestFactory().get('/')
    c1 = Cart(r1)
    print('cart 1 pk:', c1.cart.pk)

    # No response object was ever bound — verify the cookie was never
    # actually produced.
    r2 = RequestFactory().get('/')   # no COOKIES header
    c2 = Cart(r2)
    print('cart 2 pk:', c2.cart.pk)    # ← different, confirms the bug
show()
"

# Reproduce the template-tag Cart-row side effect
uv run python -c "
# (similar sketch — render any cart tag in a template and count cart rows)
"
```

### D. Things I explicitly did *not* find

- No SQL injection surface.
- No obvious XSS in `cart_link` — it uses `format_html`.
- No `eval` / `exec` / `pickle.loads` / `yaml.load` anywhere.
- No hardcoded credentials.
- No unbounded memory growth in normal use (the `_cache` dict is
  O(1)).
- No panicking logic in the management command (edge-cases for
  `--days 0` raise cleanly).
- No broken migrations (0001 → 0005 all shipped; none edited in
  place).

---

*End of analysis.*
