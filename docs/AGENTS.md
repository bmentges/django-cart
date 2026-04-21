# Using Agents with django-cart

> [!note] About this document
> This guide is for **engineers who work alongside coding agents**
> (Claude Code, Cursor, Copilot, Cline, etc.) to extend a Django
> project that uses `django-cart`. It is **not** an instruction
> file consumed by the agent runtime — those conventionally live at
> the repo root as `CLAUDE.md` / `AGENTS.md` for a given project.
>
> If you are looking for how Claude Code itself works, see
> the [Claude Code docs](https://claude.com/claude-code). This
> document describes how `django-cart`'s design makes agent-driven
> extension straightforward.

---

## TL;DR

`django-cart` is small, explicit, and stable. A coding agent can
hold the entire public surface in context, generate correct
extensions on the first pass, and verify them with the existing
test harness. The four concrete affordances the library provides
for this are:

1. **Small public API surface.** One `Cart` facade, four abstract
   base classes for pluggable subsystems, five optional signals.
2. **Type hints everywhere.** Every public method has return type
   annotations and parameter types, so an agent grounding against
   the module reads the contract directly.
3. **Explicit extension points via dotted-path settings.** No
   monkey-patching or registry magic — every subsystem is swapped
   via a single `CART_*` setting pointing at a class the agent
   writes.
4. **Stable contracts.** Public names are preserved across patch
   and minor releases (see `CHANGELOG.md`). The same prompt works
   across versions unless a major bump is called out.

---

## Why this fits agent-driven extension

### The surface is small enough to hold in context

The full public API lives in four places:

| File | What lives here |
|------|-----------------|
| `cart/cart.py` | `Cart` facade + exceptions (~700 lines) |
| `cart/models.py` | `Cart`, `Item`, `Discount` + `DiscountType` (~230 lines) |
| `cart/session.py` | `CartSessionAdapter` + two built-ins (~110 lines) |
| `cart/tax.py`, `cart/shipping.py`, `cart/inventory.py` | One base + default each (~120 lines each) |

An agent can ingest all of this in a single context window and cite
exact line numbers when suggesting changes. There is no plugin
registry, no metaclass, and no "discover at runtime" behaviour to
reason about.

### Extension points are explicit, not implicit

Every pluggable subsystem follows the same shape:

```
cart/<subsystem>.py:
    class <Subsystem>Base(ABC):          # abstract interface
    class Default<Subsystem>(Base):      # no-op default
    def get_<subsystem>() -> Base:       # factory reading a setting
```

Adding behaviour means:

1. Subclass the abstract base in your project.
2. Set `CART_<SUBSYSTEM>_CLASS = "myapp.mod.ClassName"` in Django
   settings.

That is all. An agent writing the subclass sees exactly which methods
it must implement (the `@abstractmethod` decorators), their type
signatures, and a concrete default implementation it can model
against.

### Contracts that help agents generate correct code on the first pass

- **Abstract methods raise `NotImplementedError` in the base.** An
  agent that subclasses without overriding a method gets a clear
  runtime error immediately, not subtle wrong behaviour later.
- **Decimal literals are always quoted strings.** `Decimal("0.00")`,
  never `Decimal(0)` or a float. An agent that writes
  `Decimal(0.1)` triggers the type-hint mismatch during review.
- **Public methods are annotated with their exceptions in the
  docstring.** An agent reading the signature sees which
  `CartException` subclass it must handle.
- **Mutations are wrapped in `transaction.atomic()`.** An agent
  writing a new mutation follows the same pattern by copy-and-adapt
  and does not need to reason about rollback semantics from scratch.

---

## Canonical prompts

The patterns below are ready to paste into an agent session. Each
one is self-contained: the agent can produce a correct, testable
implementation without additional context beyond the `django-cart`
source.

### Custom tax calculator

> [!tip] Prompt template
> ```
> In my Django project I use django-cart. Generate a TaxCalculator
> subclass that computes US state sales tax. Requirements:
>
> - Subclass cart.tax.TaxCalculator.
> - Read the state from the request's session (key "state_code").
> - Look up the rate from a RATES dict I provide. Missing state → 0.
> - Return Decimal rounded to 2 decimal places, never a float.
> - Wire it in via the CART_TAX_CALCULATOR setting.
> - Write a pytest that constructs a Cart with one $100 item, sets
>   session["state_code"] = "CA", and asserts cart.tax() ==
>   Decimal("7.25").
> ```

Expected agent output shape:

```python
# myapp/tax.py
from decimal import Decimal, ROUND_HALF_UP
from cart.tax import TaxCalculator
from cart.cart import Cart


US_STATE_RATES: dict[str, Decimal] = {
    "CA": Decimal("0.0725"),
    "NY": Decimal("0.08"),
    "TX": Decimal("0.0625"),
    # ...
}


class USStateTaxCalculator(TaxCalculator):
    def calculate(self, cart: Cart) -> Decimal:
        request = getattr(cart, "_request", None)
        state = None
        if request is not None:
            state = request.session.get("state_code")
        rate = US_STATE_RATES.get(state, Decimal("0"))
        amount = cart.summary() * rate
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

```python
# settings.py
CART_TAX_CALCULATOR = "myapp.tax.USStateTaxCalculator"
```

### Custom inventory checker backed by a stock column

> [!tip] Prompt template
> ```
> Generate an InventoryChecker subclass that reads a `stock` integer
> column from my Product model. Requirements:
>
> - Subclass cart.inventory.InventoryChecker.
> - check(product, quantity) returns True iff product.stock >= quantity.
> - reserve(product, quantity) decrements stock atomically via
>   an F() expression; returns True on success, False if insufficient.
> - release(product, quantity) increments stock back.
> - Wire it in via CART_INVENTORY_CHECKER.
> - Pytest: create a Product with stock=3, call cart.add(product, price,
>   quantity=5, check_inventory=True), assert InsufficientStock is
>   raised and the item is NOT in the cart.
> ```

### Redis-backed session adapter

> [!tip] Prompt template
> ```
> Generate a CartSessionAdapter that stores the cart id in Redis
> keyed by the Django session key. Requirements:
>
> - Subclass cart.session.CartSessionAdapter.
> - Implement: get(key, default=None), set(key, value), delete(key),
>   get_or_create_cart_id(), set_cart_id(cart_id).
> - Constructor takes (request).
> - Use redis-py's StrictRedis with host/port from settings.
> - The only key written is f"django-cart:{request.session.session_key}".
> - Wire via CARTS_SESSION_ADAPTER_CLASS.
> - Pytest: use fakeredis to verify that set_cart_id(42) followed by
>   get_or_create_cart_id() returns 42.
> ```

---

## Guidelines for agent pull requests

When an agent opens a PR against a downstream project that uses
`django-cart`, the following checklist helps humans merge quickly.

### Ground every extension in the library's abstract base

If an agent writes a class that *duck-types* the interface (e.g.
has `calculate` and `get_options` but does not inherit from
`ShippingCalculator`), `get_shipping_calculator()` still works
because of duck-typing, but `isinstance` checks in downstream code
silently fail and type checkers cannot verify correctness. The
abstract base is cheap — always inherit.

### Preserve the `Decimal`-only arithmetic invariant

Cart arithmetic is always `Decimal` end-to-end. If an agent
introduces `float` anywhere — tax rates, shipping rates, discount
values, quantities — the result is a subtle drift bug that no test
catches until production. Reject `float` literals in code review.

### Add tests, not assertions about tests

Tests should exercise real database state (use
`pytest.mark.django_db` + the `cart` fixture from `conftest.py`),
not mocks of django-cart internals. An agent that writes a test
that mocks `cart.summary()` to `Decimal("100.00")` and then asserts
the mocked value is not verifying anything. See
[`tests/README.md`](../tests/README.md) for the canonical pattern.

### Prefer one pluggable subsystem per PR

If an agent needs tax, shipping, and inventory at once, have it
generate three PRs — each adds one subclass + one settings wire-up
+ one test. Each PR is reviewable in under five minutes. Bundled
changes obscure regressions.

---

## Constraints and sharp edges for agents

These are behaviours an agent cannot infer from the source alone.
List them in your project's `AGENTS.md` / `CLAUDE.md` rules file
when `django-cart` is in use.

### The factory fallback is silent

`get_tax_calculator()`, `get_shipping_calculator()`, and
`get_inventory_checker()` swallow `ImportError` / `AttributeError`
and return the default implementation. An agent that points the
setting at a nonexistent path will see "tax is always 0.00" at
runtime without any error message. If your agent configures one
of these settings, have it assert the class imports cleanly in a
startup check.

The session adapter factory (`CARTS_SESSION_ADAPTER_CLASS`) is the
one exception — it raises `ImportError` loudly because session
storage is too critical to fall back silently.

### `validate_price=True` skips when `product.price` is falsy

`Cart.add(product, unit_price, validate_price=True)` reads
`getattr(product, "price", None)` and *skips* validation when the
attribute is absent or `None` / `0`. This is intentional for
products with no price attribute. An agent writing a test against
`validate_price` on a product whose `price` is `None` will see no
`PriceMismatchError` where it might expect one.

### `Cart.__init__` always materialises a cart

Constructing `Cart(request)` creates a DB row (and writes
`CART-ID` to the session) if none exists. An agent writing a
"peek if cart exists without creating one" helper cannot reuse
the `Cart` class — it must query the session adapter directly.

### Mutations are atomic but rows are not locked during reads

`Cart.add()` / `Cart.update()` / `Cart.merge()` wrap the mutation
in `transaction.atomic()`, but the pre-mutation `SELECT` does not
use `SELECT FOR UPDATE`. Two concurrent writers can both read
`quantity=N` and both write `N+q`, losing one write. `Cart.checkout()`
(post-P0-2) does use `select_for_update()` on the `Discount` row.
If an agent generates a new mutation that must be concurrent-safe,
have it replicate the `checkout()` pattern, not the `add()` pattern.

---

## Verifying an agent-generated extension

Run the full test suite after every change. From the repo root:

```bash
uv run pytest
```

The suite should pass with zero xfails and zero regressions. If an
agent-generated change causes a pre-existing test to fail, the
change is almost always wrong — do not relax the existing
assertion.

For coverage of the new code:

```bash
uv run coverage run -m pytest
uv run coverage report
```

The advisory floor is 90%. If a new subclass drops coverage below
that, the agent has missed a branch and the PR should cycle back.

---

## Where to read more

- [Main README](../README.md) — user-facing API and quick start.
- [`tests/README.md`](../tests/README.md) — canonical test pattern
  the agent should imitate.
- [`docs/ROADMAP_2026_04.md`](ROADMAP_2026_04.md) — current plan
  of record, including the P3 features an agent might be asked
  to land.
- [`CLAUDE.md`](../CLAUDE.md) at the repo root — project-specific
  rules and gotchas kept up to date for agents working on the
  library itself (not on downstream projects that use it).
