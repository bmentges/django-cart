# django-cart test suite

This document is the canonical pattern for writing tests in this repo.
Deviations fail review. For the migration plan that produced this pattern,
see `docs/ROADMAP_2026_04.md` §P-1.

---

## TL;DR

- **Framework:** pytest + pytest-django. No `TestCase` subclasses in new code.
- **Discipline:** TDD. Failing test first, then the change that makes it pass.
- **Mocks:** no `MagicMock` for requests. Use the `rf_request` fixture.
- **Helpers:** declare fixtures in `tests/conftest.py`. Never in test files.
- **Assertions:** prefer DB state over mock call assertions. Query counts
  (`django_assert_num_queries`) over wall-clock timings.
- **Naming:** `test_<module>_<concern>.py`, one behaviour per function.

---

## Running the suite

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Full suite
uv run pytest

# One file
uv run pytest tests/test_conftest.py

# One test
uv run pytest tests/test_conftest.py::test_cart_fixture_creates_persisted_cart

# Deselect slow tests
uv run pytest -m "not slow"

# Coverage
uv run coverage run -m pytest
uv run coverage report
uv run coverage html   # -> htmlcov/
```

---

## The canonical pattern

Every test file looks like this:

```python
# tests/test_cart_add.py
"""Cart.add behaviour."""
from __future__ import annotations

from decimal import Decimal

import pytest

from cart.cart import InvalidQuantity


def test_add_new_product_sets_quantity(cart, product):
    cart.add(product, unit_price=Decimal("5.00"), quantity=2)

    assert cart.count() == 2
    assert cart.cart.items.first().quantity == 2


def test_add_existing_product_accumulates_quantity(cart, product):
    cart.add(product, unit_price=Decimal("5.00"), quantity=2)
    cart.add(product, unit_price=Decimal("5.00"), quantity=3)

    assert cart.count() == 5


def test_add_with_quantity_below_one_raises(cart, product):
    with pytest.raises(InvalidQuantity):
        cart.add(product, unit_price=Decimal("5.00"), quantity=0)


@pytest.mark.parametrize(
    "quantity,expected_count",
    [
        (1, 1),
        (5, 5),
        (100, 100),
    ],
)
def test_add_respects_quantity_parameter(cart, product, quantity, expected_count):
    cart.add(product, unit_price=Decimal("5.00"), quantity=quantity)
    assert cart.count() == expected_count
```

Notes:

- `from __future__ import annotations` — always. Enables PEP 604 syntax
  uniformly across Python 3.10+.
- The file is a plain module. No classes. No `setUp`/`tearDown`.
- Each test function names the behaviour it verifies. Docstrings are
  optional when the name is clear; prefer a clear name over a docstring.
- `pytest.mark.parametrize` replaces the "table of similar tests" pattern
  that used to yield 6-method `TestCase` classes.
- Assertion messages matter only when the assertion itself is opaque.
  `assert cart.count() == 2` needs no message; `assert result` does.

---

## Fixtures (catalogue)

Fixtures shared across test files live in `tests/conftest.py`. Pull them
in by declaring them as arguments to your test function — pytest wires
them up automatically. Fixtures used by a single file may be declared at
the top of that file; `tests/test_session_adapters.py` is the reference
example of the local-fixture pattern.

| Fixture             | Returns                                       | Depends on                        | Typical use                                              |
| ------------------- | --------------------------------------------- | --------------------------------- | -------------------------------------------------------- |
| `rf_request`        | Real Django request with `session={}` attached | —                                 | The foundation. Pass to `Cart(...)` or assert session state. |
| `cart`              | Fresh `Cart` bound to `rf_request`            | `db`, `rf_request`                | 90% of tests. "I need a cart."                           |
| `other_cart`        | Independent second `Cart` with its own session | `db`                              | Merges, session isolation, guest-vs-user flows.          |
| `user_cart`         | `Cart` bound to a new `User`                  | `db`, `django_user_model`         | User-binding tests. Checkout-while-authenticated flows.  |
| `product`           | `FakeProduct` named "Test Product" at $10.00  | `db`                              | Default product. "I need a product."                     |
| `product_no_price`  | `FakeProductNoPrice` (no `price` field)       | `db`                              | Price-validation skip paths.                             |
| `product_factory`   | Callable `(name, price) -> FakeProduct`       | `db`                              | Tests needing multiple distinct products.                |
| `discount_percent`  | 20%-off `Discount`, code `PERCENT20`          | `db`                              | Default discount. "I need a working discount."           |
| `discount_fixed`    | $10 fixed `Discount`, code `FIXED10`          | `db`                              | Fixed-amount branch coverage.                            |

### When you need something else

- **A specific product configuration** — use `product_factory(...)` with
  your arguments. Don't add a new fixture.
- **A discount with constraints** (expiry, `max_uses`, `min_cart_value`) —
  build the `Discount` inline in the test. Don't parameterise an existing
  fixture.
- **A specific user** — use `django_user_model` (pytest-django fixture) and
  build inline. Don't extend `user_cart`.
- **A second product type** — if it's used by three or more tests, add it
  as a fixture in `conftest.py`. Otherwise, inline.

### What NOT to do

- ❌ Re-declare `make_request`, `make_product`, `make_cart_model` helpers
  in a test file. These exist in legacy files during Phase 1–5 only;
  new code uses fixtures.
- ❌ Use `MagicMock()` as a stand-in for a request. The `rf_request`
  fixture is always the right answer.
- ❌ Reach into `cart._cache` or `item._product_cache` to verify caching
  behaviour. Verify the observable effect (`django_assert_num_queries`)
  instead.
- ❌ Write a test whose only assertion is a type check or attribute
  existence (`isinstance(x, Y)`, `hasattr(x, "z")`). If the behaviour isn't
  user-observable, the test isn't earning its keep.

---

## Marks

Custom markers registered in `pyproject.toml`:

| Mark                                    | Meaning                                         |
| --------------------------------------- | ----------------------------------------------- |
| `@pytest.mark.django_db`                | Grants DB access. Usually already provided by a fixture; use when a test needs DB but none of its fixtures require `db`. |
| `@pytest.mark.django_db(transaction=True)` | Replaces `TransactionTestCase`. Use for tests that exercise real transaction commit/rollback (atomicity, concurrent-write races). |
| `@pytest.mark.slow`                     | Performance or scale tests. Skip in fast loops with `-m "not slow"`. |
| `@pytest.mark.xfail(strict=True, reason="P0-X")` | A regression test for a bug scheduled for a future release. Keeps the suite green while documenting the defect. The fix PR removes the marker. `strict=True` means an unexpected pass also fails the build — prevents silently-fixed bugs from drifting into production without a CHANGELOG note. |

Do not invent new markers without updating `pyproject.toml` first. The
`--strict-markers` option means an undeclared mark fails the run.

---

## Database access

pytest-django controls DB access via the `db` fixture (or the
`@pytest.mark.django_db` marker — they're equivalent). Fixtures in this
repo that touch the DB declare `db` as a dependency, so any test that
pulls in `cart`, `product`, `discount_*`, etc. gets DB access for free.

Tests that touch the DB directly but use no such fixture must add the
marker explicitly:

```python
@pytest.mark.django_db
def test_something_that_uses_orm_directly(rf_request):
    CartModel.objects.create()
    ...
```

By default, each test runs in a transaction that's rolled back at the
end — fast and isolating. For tests that need to observe transaction
boundaries directly (atomicity, `select_for_update`, threading), use
`@pytest.mark.django_db(transaction=True)`. It's slower; use it only when
necessary.

---

## Query-count assertions

Replace wall-clock performance assertions with query counts. Query
counts are reproducible across hardware; wall clock is not.

```python
def test_iteration_does_not_trigger_n_plus_one(
    cart, product_factory, django_assert_num_queries
):
    for i in range(10):
        cart.add(product_factory(name=f"P{i}"), Decimal("5.00"))

    # Expect: one query to fetch items, one per distinct content_type
    # for the batched product lookup (once items_with_products() lands).
    with django_assert_num_queries(2):
        items = list(cart.items_with_products())
```

If you genuinely need wall-clock assertions (very rare, and usually a
smell), mark the test `@pytest.mark.slow` so it can be skipped in fast
loops.

---

## Writing a regression test for a known bug

During the overhaul, Phase 7 populates the suite with regression tests
for known P0 bugs. Each is marked `xfail`:

```python
@pytest.mark.xfail(
    strict=True,
    reason="P0-2 — Discount.current_uses never increments. "
           "Scheduled for 3.0.4.",
)
def test_apply_then_checkout_increments_current_uses(cart, product, discount_percent):
    cart.add(product, unit_price=Decimal("10.00"), quantity=2)
    cart.apply_discount("PERCENT20")
    cart.checkout()

    discount_percent.refresh_from_db()
    assert discount_percent.current_uses == 1
```

When the fix lands in 3.0.4:

1. Commit A removes the `@pytest.mark.xfail` decorator only.
   Tests go red on this commit.
2. Commit B implements the fix. Tests go green on this commit.

This split makes the diff review trivial — reviewers can see the
behaviour change separately from the scaffolding change.

---

## Migration status (Phase 0)

The suite is partway through the overhaul described in `docs/ROADMAP_2026_04.md`
§P-1. As of now:

- ✅ Phase 0: scaffolding (this document, `conftest.py`,
  `test_conftest.py`, `pyproject.toml` config) merged. Released v3.0.3.
- ✅ Phase 1: `test_session.py` rewritten as `test_session_adapters.py`,
  the reference pytest example. Shipped in v3.0.5.
- ✅ Phase 2: `test_signals.py`, `test_templatetags.py`,
  `test_performance.py` migrated. Wall-clock timings replaced with
  `django_assert_num_queries` / `django_assert_max_num_queries` bounds.
  Shipped in v3.0.5 (combined with Phase 1; v3.0.4 skipped).
- ✅ Phase 3: `test_integration.py` (mock-based, misnamed) replaced with
  `test_http_integration.py` using Django's real test client against
  minimal views wired into `tests/urls.py`. Shipped in v3.0.6.
- ✅ Phase 4: `test_v300.py` split into seven focused files —
  `test_tax.py`, `test_shipping.py`, `test_inventory.py` (includes
  `Cart.add(check_inventory=True)` integration),
  `test_discount_model.py`, `test_cart_discounts.py`,
  `test_cart_tax_shipping.py`, `test_cart_checkout.py` (seeded; Phase 5
  adds more). Test doubles (`Custom*Calculator`, `*InventoryChecker`)
  moved from the file's bottom into the relevant test file that
  references them via dotted path. Shipped in v3.0.7.
- ✅ Phase 5: `test_cart.py` (~2200 lines, 49 `TestCase` subclasses)
  split into 19 focused pytest files — `test_cart_model.py`,
  `test_item_model.py`, `test_item_manager.py`, `test_cart_init.py`,
  `test_cart_add.py`, `test_cart_remove.py`, `test_cart_update.py`,
  `test_cart_query.py`, `test_cart_iteration.py`,
  `test_cart_checkout.py` (extended from Phase 4),
  `test_cart_merge.py`, `test_cart_bulk.py`,
  `test_cart_user_binding.py`, `test_cart_serialization.py`,
  `test_cart_caching.py`, `test_cart_max_quantity.py`,
  `test_cart_price_validation.py`, `test_cart_admin.py` (HTTP-level
  replacement for the legacy config-reflection classes),
  `test_cart_atomic.py`, `test_clean_carts_command.py`. The two
  shadowed tests from the duplicate `CartIterationTest` class are
  recovered (P1-5 dissolves). Shipped in v3.0.8.
- ✅ Phases 6+7 (combined): behavioural coverage audit + remaining
  reflection sweep. Four `@pytest.mark.xfail(strict=True)` regression
  tests added for known P0 bugs (P0-1 `from_serializable`, P0-2
  `Discount.current_uses`, P0-3 `CARTS_SESSION_ADAPTER_CLASS`, P0-4
  `CookieSessionAdapter` round-trip). Coverage fills added for
  merge max-quantity cap paths, `add_bulk` rollback on invalid-quantity,
  misconfigured calculator/checker fallbacks, `can_checkout` minimum-
  met branch. Positive template-render tests via Django's template
  engine for the four cart template tags (doc-fix for P0-5 needs no
  xfail — behaviour is correct today). Coverage: 95% → 98%. Targets
  v3.0.9.
- ⏭ Phase 6: reflection-only tests deleted.
- ⏭ Phase 7: behavioural coverage audit, P0 regression `xfail` tests.
- ⏭ Phase 8: `runtests.py` deleted, CI flipped to pytest-only, coverage
  gate enabled.

While multiple phases are in flight, legacy `TestCase` files coexist with
new pytest files. Both run via `pytest` (pytest-django discovers
`TestCase` subclasses). Do not rewrite the legacy files ad-hoc — follow
the phase order in the roadmap so progress is trackable.
