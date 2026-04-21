# django-cart Roadmap — April 2026

**Version analysed:** 3.0.2
**Date:** 2026-04-20
**Method:** static analysis + runtime verification of bugs + coverage run
**Baseline metrics:**

| Metric              | Value                                            |
| ------------------- | ------------------------------------------------ |
| Tests defined       | 292                                              |
| Tests actually run  | 290 (2 silently shadowed — see **P1-5**)         |
| Coverage (stmt+br)  | **94%** on `cart/` (not 100% as older docs claim) |
| Runtime             | 7.3 s on SQLite in-memory                         |
| LOC (library)       | ~1 200 excluding migrations                       |

The plan is ordered by **impact × reversibility**, not by feature glamour.
Each item below has a concrete acceptance test so "done" is unambiguous.

---

## Priority legend

| Tier     | Meaning                                                                          |
| -------- | -------------------------------------------------------------------------------- |
| **P-1**  | Foundation work. Blocks everything below it. Ships first.                        |
| **P0**   | Shipping bug OR doc lies to users. Fix in the next patch release after P-1.      |
| **P1**   | Correctness / safety / test-reliability gap that should land before any feature. |
| **P2**   | Quality improvements: coverage, CI, ergonomics.                                  |
| **P3**   | Features / nice-to-haves.                                                         |

---

## P-1 — Test overhaul (precedes everything else)

**Decision (2026-04-20, maintainer):** migrate the suite off Django's
`TestCase` onto **pytest + pytest-django** with `conftest.py` fixtures,
before any P0 bug fix lands. TDD discipline from this point forward:
every subsequent item below lands as "failing test first, then the
change that makes it pass." Reflection-only tests get **deleted**, not
preserved.

### Rationale

- Three confirmed P0 bugs that the existing 292-test suite failed to
  catch (`from_serializable`, discount `current_uses`,
  `CARTS_SESSION_ADAPTER_CLASS`). The suite exists, but it doesn't
  verify behaviour — it verifies line execution.
- Duplicated helpers across four test files, two classes sharing the
  same name (silent test loss), "integration" tests that use
  `MagicMock`, perf bounds loose enough to hide a 10× regression,
  divergent test-runner configurations. All deferred maintenance
  dragging down every future change.
- Landing P0 fixes against the current suite means each regression test
  is written in the style we're about to throw away. Doubles the work.

### The canonical pattern

Every new test file follows exactly this shape. Deviations fail review.

```python
# tests/test_cart_add.py
import pytest
from decimal import Decimal
from cart.cart import Cart, InvalidQuantity

pytestmark = pytest.mark.django_db


def test_add_new_product_sets_quantity(cart, product):
    cart.add(product, unit_price=Decimal("5.00"), quantity=2)
    assert cart.count() == 2


def test_add_below_one_raises(cart, product):
    with pytest.raises(InvalidQuantity):
        cart.add(product, unit_price=Decimal("5.00"), quantity=0)


@pytest.mark.parametrize("strategy,expected", [
    ("add", 5),
    ("replace", 3),
    ("keep_higher", 3),
])
def test_merge_strategies(cart, other_cart, product, strategy, expected):
    cart.add(product, Decimal("10.00"), quantity=2)
    other_cart.add(product, Decimal("10.00"), quantity=3)
    cart.merge(other_cart, strategy=strategy)
    assert cart.cart.items.first().quantity == expected
```

**Rules enforced in CI:**

- No `unittest.TestCase` subclasses. Grep check in the lint job.
- No `MagicMock` for `request`. Use the `rf_request` fixture
  (`RequestFactory().get("/")` with `session = {}` attached).
- No helper functions defined in test files. Helpers live in
  `conftest.py` as fixtures.
- No wall-clock performance assertions. Use `django_assert_num_queries`.
- Test file names mirror the module under test: `test_cart_<verb>.py`,
  `test_discount_<behaviour>.py`, `test_session_adapters.py`, etc.
- One behaviour per test function. If it needs "and" in the docstring,
  split it.

### Canonical fixtures (in `tests/conftest.py`)

```python
cart              → fresh Cart bound to a RequestFactory request
other_cart        → second Cart with independent session
user_cart         → Cart bound to a freshly created User
product           → FakeProduct with price=Decimal("10.00")
product_no_price  → FakeProductNoPrice instance
product_factory   → callable: product_factory(name=..., price=...)
discount_percent  → 20% Discount
discount_fixed    → $10 fixed Discount
rf_request        → RequestFactory().get("/") with session={}
```

### Phasing

| Phase | Scope                                                                                                               | Exit criterion                                                                       |
| ----- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 0     | Write `conftest.py` with the canonical fixtures. Write `tests/README.md` documenting the pattern above. Add a pytest config block to `pyproject.toml`. Add `tests/test_conftest.py` that exercises every fixture (tests the scaffolding itself). | Docs + scaffolding merged. Zero existing tests touched.                              |
| 1     | Rewrite `tests/test_session.py` (14 tests, smallest) as the reference implementation. Cite it as "the style" from `tests/README.md`. | Old file deleted, new file merged, all green.                                        |
| 2     | Migrate `test_signals.py`, `test_templatetags.py`. Rewrite `test_performance.py` to use `django_assert_num_queries` instead of wall clock. | All green, no wall-clock assertions remain.                                          |
| 3     | Replace `test_integration.py` (MagicMock-based) with `test_http_integration.py` using the real Django test client + `tests/urls.py` wired to minimal example views. | At least 5 tests call `client.post(...)` / `client.get(...)`.                        |
| 4     | Migrate `test_v300.py`: split into `test_discount_model.py`, `test_cart_discounts.py`, `test_tax.py`, `test_shipping.py`, `test_inventory.py`. Delete the ad-hoc `Custom*Calculator` classes at the bottom of the file; move them into the fixture/parametrize system. | All green. One concern per file.                                                     |
| 5     | Migrate `test_cart.py` (~2200 lines, 177 tests). Split into: `test_cart_init.py`, `test_cart_add.py`, `test_cart_update.py`, `test_cart_remove.py`, `test_cart_query.py` (count/summary/is_empty/contains), `test_cart_iteration.py`, `test_cart_checkout.py`, `test_cart_merge.py`, `test_cart_bulk.py`, `test_cart_user_binding.py`, `test_cart_serialization.py`, `test_cart_caching.py`, `test_cart_max_quantity.py`, `test_cart_price_validation.py`, `test_cart_admin.py` (behavioural admin only, see deletion list), `test_cart_atomic.py` (TransactionTestCase-equivalent via `pytest.mark.django_db(transaction=True)`), `test_clean_carts_command.py`, `test_item_model.py`, `test_item_manager.py`. Rename the shadowed `CartIterationTest` out of existence (P1-5 dissolves here). | All green.                                                                           |
| 6     | **Deletion pass** — remove all reflection-only tests. See explicit delete list below.                                | Coverage may drop temporarily; acceptable. Proceed to Phase 7.                       |
| 7     | **Behavioural coverage audit.** For every currently-uncovered line (see P2-4 list) AND every currently-covered-but-untested behaviour (see list below), add a test. If the behaviour is correct, the test asserts the current reality and goes green. If the behaviour is a known bug (P0-1/P0-2/P0-3/etc.), the test asserts the post-fix reality and is marked `@pytest.mark.xfail(strict=True, reason="P0-X — scheduled for 3.0.4")`. Decision 2026-04-20: **xfail, not defer**. Regression tests belong in the suite the moment the bug is understood, so 3.0.4's fixes land as "remove the xfail marker, run the test, it turns green" — no new-test authoring happens inside the bug-fix release. `strict=True` means an unexpected pass fails CI, preventing silently-fixed bugs from drifting into production without a release note. | `coverage report --fail-under=100` AND every behaviour in the audit checklist has a named test (green or `xfail(strict=True)`). |
| 8     | Unify test runner. Delete `runtests.py` in favour of `pytest` alone. Delete `tests/fixtures/fake_products.json` (unused). Update CI to run pytest only. Update README "Testing" section. | `grep -r runtests\.py` returns nothing. CI green.                                    |

### Explicit delete list (Phase 6)

Tests that exist but verify Python/Django mechanics, not django-cart
behaviour. Removing them is safe; replacing them with behavioural
equivalents where a real risk exists is Phase 7 work.

- `ModelTypeHintsTest.*` — asserts `__annotations__` exists. Tests Python.
- `CartStringRepresentationTest.test_str_includes_cart_id`,
  `test_str_includes_item_count`, `V230EdgeCaseTest.test_cart_str_with_zero_items`
  — assert substrings in `__str__`. Keep one combined test
  (`test_cart_str_shape`) that asserts format shape; drop the rest.
- `CartAdminTest.test_cart_admin_has_list_display`,
  `test_cart_admin_has_list_filter`, `test_item_count_short_description`,
  `ItemInlineTest.test_inline_model_is_item`,
  `test_inline_extra_is_zero`, `test_inline_readonly_fields`,
  `test_inline_total_price_short_description`,
  `test_cart_admin_has_inlines` — admin-configuration reflection. Replace
  with one `test_admin_renders_cart_changelist` that hits
  `/admin/cart/cart/` via `client` with a superuser and asserts 200 +
  that the item count column shows.
- `ItemProductCachingTest.test_product_cached_after_first_access` —
  asserts `hasattr(item, '_product_cache')`. Replace with
  `assertNumQueries(1)` on two sequential `.product` accesses.
- `DiscountModelFieldsTest.test_discount_verbose_names`,
  `test_discount_default_values` — attribute reflection. Delete.
  Defaults are already exercised by `CartDiscountFieldTest`.
- `CartDatabaseIndexTest.test_item_has_composite_index` — asserts
  `Item._meta.indexes` has a specific entry. Django guarantees this
  from the migration; it's tautological. Delete. The performance
  assertion is better expressed as a query-plan check, which is out of
  scope for SQLite anyway — so drop the entire class.
- `NewExceptionsTest.*` — asserts `raise InvalidDiscountError` works
  and `issubclass(InvalidDiscountError, CartException)` is true. Tests
  Python. Delete.
- `CartSessionAdapterTest.test_cannot_instantiate_directly` — asserts
  ABC mechanics. Delete.
- `test_tax_calculator_interface_is_abstract`,
  `test_shipping_calculator_interface_is_abstract`,
  `test_inventory_checker_interface_is_abstract` — same reasoning.
  Delete.

Expected deletion count: ~25 tests. The suite size drops from 290 to
~265 before Phase 7 rebuilds it up with behavioural tests.

### Behavioural coverage audit list (Phase 7)

Behaviours currently either uncovered or covered only by reflection.
Each gets a dedicated test.

- `Discount.increment_usage` — runtime effect (race-free increment,
  rollback on checkout failure). Currently dead code; Phase 7 wires it
  in during the P0-2 fix that immediately follows this overhaul.
- `CookieSessionAdapter.set_cart_id` round-trip via two sequential
  `RequestFactory` requests with copied cookies.
- `get_tax_calculator` / `get_shipping_calculator` /
  `get_inventory_checker` with a misconfigured dotted path — asserts
  the warning log AND the fallback to default.
- `Cart.merge` hitting `max_qty` cap on an existing item (lines 373, 381
  uncovered).
- `Cart.add_bulk` raising `InvalidQuantity` on mid-list violation and
  rolling back the whole batch (line 441 uncovered).
- `Cart.from_serializable` on a fresh cart — test asserts the post-fix
  behaviour (see P0-1). This test gets written in Phase 7, fails, and
  the P0-1 fix in 3.0.4 makes it pass.
- `Cart.apply_discount` then `checkout` increments `current_uses` —
  test gets written in Phase 7, fails, P0-2 fix makes it pass.
- `CARTS_SESSION_ADAPTER_CLASS` honoured — test gets written in
  Phase 7, fails, P0-3 fix makes it pass.
- Concurrent `add()` on same (cart, product) from two threads — test
  gets written in Phase 7, may or may not fail depending on DB backend;
  informs P1-1 priority.
- Template rendering using each tag in the **README-documented** form
  (not the implementation form). Fails today because README is wrong
  (P0-5).

### Acceptance for P-1 overall

1. Zero `TestCase` subclasses in `tests/`.
2. Zero `MagicMock(request)` in `tests/`.
3. `grep -r 'def make_request\|def make_product' tests/` returns zero
   hits (helpers live in fixtures only).
4. `coverage report --fail-under=100` passes with a `cart/` source tree
   that has had dead branches (`try/except ImportError` in `cart.py`,
   `if TYPE_CHECKING: pass` lines) deleted.
5. CI has one test job running `pytest`. No `runtests.py`.
6. `tests/README.md` exists and documents the pattern, cited from
   CLAUDE.md §9.
7. Every behaviour in the Phase 7 audit list has a named test — even
   if some of those tests are currently `@pytest.mark.xfail(reason="P0-X
   fix pending")` because the fix ships in 3.0.4.

### Risks and mitigations

| Risk                                                                                                     | Mitigation                                                                                                                                              |
| -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Migration takes longer than budgeted and blocks urgent bug fixes.                                        | Phases 0–2 land incrementally on master behind feature-flag-free merges. If an emergency P0 arrives mid-migration, fix it in the legacy style on a hotfix branch and re-migrate the tests during Phase 5. |
| "100% coverage" goal devolves into gaming the metric.                                                    | Phase 7 audit list is the real gate. Coverage is the lagging indicator. Review new tests for "would this fail if the behaviour broke?" — if no, reject. |
| pytest-django's `django_db` fixture has surprising semantics around transactions.                        | Document in `tests/README.md`. Use `@pytest.mark.django_db(transaction=True)` explicitly for atomic-behaviour tests (replacing `TransactionTestCase`).  |
| Rewriting test_cart.py (177 tests) is a big merge.                                                       | Phase 5 lands as a series of PRs per split file, each green. Not one giant PR.                                                                          |

### Out of scope for P-1

- Changing any cart behaviour. This is a pure test refactor. If a test
  migration reveals a bug, that bug goes onto the P0 queue for 3.0.4.
  It does **not** get fixed inside this overhaul.
- Adding new behavioural features (P3 items). Wait for the foundation.
- Migrating to a different Django ORM testing library (factory_boy,
  etc.). pytest fixtures are enough.

---

## P0 — Bugs and documentation lies (after P-1 lands)

**Workflow convention (decided 2026-04-20):** every P0 item below has a
failing regression test authored during **P-1 Phase 7**, marked
`@pytest.mark.xfail(strict=True, reason="P0-X — scheduled for 3.0.4")`.
The fix PR in 3.0.4 removes the xfail marker as the first step and then
makes the change that turns the test green. Do NOT author the test and
the fix in the same commit; split them so the diff shows "test was
failing → is now passing" cleanly. `strict=True` guards against a
bug that silently fixes itself (via dependency bump, Django upgrade,
whatever) slipping into production without a CHANGELOG note.

### P0-1 · `Cart.from_serializable` silently does nothing on a fresh cart
**File:** `cart/cart.py:308-336`
**Symptom:** Call on an empty cart → returns an empty cart. Verified:
`Cart.from_serializable(req, {...}).cart.items.all()` → `[]`.
**Cause:** The method looks for pre-existing `Item` rows by `object_id` and
updates them; on a fresh cart nothing matches so nothing happens. Existing
tests mask this by pre-populating the cart first.
**Fix options:**
1. Rename to `update_from_serializable` and document clearly that it only
   updates existing items.
2. Make it actually create items from the payload. This requires resolving
   the product — serialised data has only `object_id`, not `content_type`,
   so we need a convention (store `content_type` too, or require the caller
   to pass a content-type-getter callable).
**Recommendation:** #1 for 3.0.x (least blast radius), #2 as a 3.1.0 feature
with the new serialisation format bumped to include `content_type`.
**Acceptance:** a new test calls `from_serializable` on a *brand new* cart
and asserts either (a) the items exist as expected, or (b) the method raises
a clear error naming the rename. Either is fine; the current silent no-op
is not.

### P0-2 · `Discount.current_uses` never increments
**Files:** `cart/cart.py:485-520` (apply_discount), `cart/cart.py:277-282`
(checkout), `cart/models.py:228-231` (`increment_usage`, dead code).
**Symptom:** A discount created with `max_uses=1` can be applied and checked
out an unlimited number of times. Verified at runtime: after `apply_discount`
+ `checkout`, `Discount.current_uses == 0`.

**Decision (2026-04-20, maintainer):** increment on **checkout**, not on
`apply_discount`. Rationale: "1 use" means "1 purchase", not "1 try".
Abandoned carts must not burn uses; apply/remove/apply cycles stay free.

**Fix:**
1. Inside `Cart.checkout()`, in the same `transaction.atomic()` that sets
   `checked_out=True`, when `self.cart.discount is not None`:
   a. Re-run `self.cart.discount.is_valid_for_cart(self)` with
      `select_for_update()` on the `Discount` row. If it now returns
      `(False, msg)` (the code exhausted or expired between apply and
      checkout), raise `InvalidDiscountError(msg)` — the whole checkout
      rolls back. Do **not** silently strip the discount; surprise price
      changes at checkout are worse than a visible error.
   b. Otherwise update via `Discount.objects.filter(pk=…).update(
      current_uses=F("current_uses") + 1)` so the increment is atomic at
      the DB level. No Python read-modify-write.
2. Rewrite `Discount.increment_usage()` to use the `F()` expression too,
   or delete it if no longer needed anywhere.
**Acceptance:**
- Test 1: apply `max_uses=1` discount, check out, create second cart,
  apply same code → `InvalidDiscountError` with "maximum number of uses".
- Test 2: two concurrent `checkout()` calls on the last remaining use
  (using `TransactionTestCase` + threads) → one succeeds, one raises
  `InvalidDiscountError`. Final `current_uses` equals `max_uses`, never
  `max_uses + 1`.
- Test 3: apply discount, expire it (set `valid_until` to past),
  checkout → `InvalidDiscountError("expired")`, cart is NOT marked
  checked out, `current_uses` unchanged.

### P0-3 · `CARTS_SESSION_ADAPTER_CLASS` does nothing
**Files:** `cart/cart.py:75-92` (Cart init), `cart/session.py` (unused
classes), `README.md:580-625` (documents the setting).
**Symptom:** Users setting `CARTS_SESSION_ADAPTER_CLASS=…` get zero
behavioural change; `Cart.__init__` always uses `request.session`.
Verified runtime.
**Fix options:**
1. **Wire it up.** Replace `request.session.get(CART_ID)` /
   `request.session[CART_ID] = …` with an adapter instance loaded via
   `import_string(settings.CARTS_SESSION_ADAPTER_CLASS)`. Default to
   `DjangoSessionAdapter`. This keeps the documented API truthful.
2. **Remove the promise.** Delete `cart/session.py`, the tests for it, and
   the README section. Clean but embarrassing after four releases.
**Recommendation:** #1. Side-effect: `CookieSessionAdapter` also needs
fixing (it never reads `request.COOKIES` — see P0-4) for the cookie path
to actually work.
**Acceptance:** test that sets `CARTS_SESSION_ADAPTER_CLASS` to a custom
in-memory adapter class and asserts `Cart(request)` does not touch
`request.session` at all.

### P0-4 · `CookieSessionAdapter` cannot round-trip cookies
**File:** `cart/session.py:70-109`
**Symptom:** Even when wired in, a cart id set on response N is not
recoverable on request N+1 because `get()` reads from an in-memory
`self._cookies` dict that's empty at the start of every request.
**Fix:** In `__init__`, populate `self._cookies` from `request.COOKIES` when
`request is not None`. Serialise/parse numeric cart ids as strings (already
done in `get_or_create_cart_id`).
**Acceptance:** test simulates two sequential requests with a shared cookie
jar (copy Set-Cookie headers from response 1 into request 2) and asserts the
same cart is returned. The current test only covers the in-memory case.

### P0-5 · Template-tag usage in README is wrong in three places
**File:** `README.md:520-531`
**Symptom:** README shows:
```
{% cart_item_count request %}
{% cart_summary request %}
{% cart_is_empty request %}
{% cart_link request "btn btn-primary" "View Cart" %}
```
All four tags are `@simple_tag(takes_context=True)` with no positional
`request` argument, and `cart_link` is `(text, css_class)`, not
`(request, css_class, text)`. Users copying these examples get
`TemplateSyntaxError`.
**Fix:** rewrite the examples to:
```
{% cart_item_count %}
{% cart_summary %}
{% cart_is_empty %}
{% cart_link "View Cart" "btn btn-primary" %}
```
**Acceptance:** snapshot-style test that renders a template using each tag
in the exact form shown in the README and asserts it produces the expected
HTML.

### P0-6 · CHANGELOG is three versions behind
**File:** `CHANGELOG.md`
**Symptom:** Last entry is v2.7.0. Tags `v3.0.0`, `v3.0.1`, `v3.0.2` exist
on GitHub but have no CHANGELOG section. Commit `07d9611 Bump version to
3.0.2` leaves no user-facing note.
**Fix:** Backfill v3.0.0 (discounts/tax/shipping/inventory — cross-check
`tests/test_v300.py`), v3.0.1 (see commit `64839e6`), v3.0.2 (see commit
`07d9611`). Adopt Keep-a-Changelog headings going forward (`### Added`,
`### Fixed`, `### Changed`).
**Acceptance:** CHANGELOG has an entry for every tag in `git tag -l 'v*'`.
Add a lint step (shell one-liner in CI) that fails if the top of the file
doesn't mention `pyproject.toml`'s current version.

### P0-7 · `docs/ROADMAP.md` and `docs/PROJECT_ANALYSIS.md` are stale
**Files:** `docs/ROADMAP.md` (generic, no dated work), `docs/PROJECT_ANALYSIS.md`
(says "100% coverage", "version analysed: 2.2.13", talks about adding
features that now exist).
**Fix:** replace `docs/ROADMAP.md` content with a pointer to this file
(`ROADMAP_2026_04.md`) and any future dated roadmaps. Prepend a "Status:
superseded" banner to `PROJECT_ANALYSIS.md` and `PROJECT_ANALYSIS_2026_03_29_0243am.md`.
Keep them for history; don't delete.

---

## P1 — Correctness, safety, and test reliability

### P1-1 · Race condition in `Cart.add` / `Cart.update` / `Cart.merge`
**Files:** `cart/cart.py:149-179, 195-244, 338-392`
**Symptom:** `_get_item()` + mutation-then-`save()` without `select_for_update`
inside `transaction.atomic()`. Two concurrent workers can both read the same
row and both write back, losing one update.
**Fix:** replace `_get_item` in mutation paths with a `select_for_update`
variant, OR replace the add/update quantity math with `F("quantity") + q`
and let the DB do the arithmetic. The latter is simpler and lock-free.
**Nuance:** for the "item does not exist yet" branch the `unique_together`
constraint already serialises concurrent creates — one raises
`IntegrityError`, which we can catch and turn into an update loop.
**Acceptance:** multithreaded test using two threads hitting the same
(cart, product) with `add(product, price, 1)` 100 times each, expecting
final quantity 200. Today this fails non-deterministically on Postgres
(SQLite's whole-DB lock hides it).

### P1-2 · `Cart.checkout()` bypasses `can_checkout` and inventory reservation
**File:** `cart/cart.py:277-282`
**Symptom:** Callers can successfully check out an empty cart, a cart below
`CART_MIN_ORDER_AMOUNT`, or a cart whose inventory has since disappeared.
All three validators exist as library code but nothing invokes them at
checkout time.

**Decision (2026-04-20, maintainer):** staged default-flip, not an
immediate breaking change. Users get one minor-release warning window,
then the strict default lands in 4.0.

**Fix — phased:**

**Phase 1 — 3.1.0 (non-breaking, adds warning):**
1. Change signature to `checkout(self, *, validate: bool | None = None)`.
   Keyword-only so positional-arg users (if any) are unaffected.
2. If `validate is None`:
   - Emit `DeprecationWarning("Cart.checkout() will validate by default
     starting in django-cart 4.0. Pass validate=True (strict) or
     validate=False (legacy) explicitly to silence this warning.")`
   - Behave exactly as today — no validation, no reservation, no
     increment-on-checkout guard. Preserves 100 % backwards compatibility
     for existing callers.
3. If `validate is True`:
   - Call `can_checkout()`; raise `CheckoutNotAllowed(msg)` (new exception
     inheriting `CartException`) if it returns `(False, msg)`.
   - If `CART_INVENTORY_CHECKER` is configured, call `reserve(product,
     qty)` for every item inside the same transaction. If any reservation
     fails, raise `InsufficientStock` and roll back; `checked_out` stays
     `False` and no inventory is consumed.
   - Perform the discount `current_uses` increment (P0-2).
4. If `validate is False`: legacy behaviour, no warning.
5. Register `CheckoutNotAllowed` in `cart/cart.py` alongside the other
   exceptions and re-export from the README exception table.

**Phase 2 — 4.0.0 (breaking):**
1. Flip default to `validate: bool = True` (no more `None`, no warning).
2. Remove the deprecation-warning branch.
3. CHANGELOG entry under a `### Breaking Changes` heading.
4. Update README: show `checkout(validate=False)` as the escape hatch
   rather than the default.

**Acceptance:**
- Phase 1: test `checkout()` with no kwarg emits exactly one
  `DeprecationWarning` and leaves cart state identical to the current
  behaviour. Test `checkout(validate=True)` on empty cart raises
  `CheckoutNotAllowed`. Test `checkout(validate=True)` with a failing
  inventory checker raises `InsufficientStock` and the cart stays
  `checked_out=False`. Test `checkout(validate=False)` never warns and
  never validates.
- Phase 2: same tests, minus the warning assertion, plus a test that
  `checkout()` without a kwarg now validates.

**Explicitly NOT doing:** settings-driven default
(`CART_STRICT_CHECKOUT=True`). Per-call behaviour gated on a project-wide
toggle ages badly; the kwarg stays the single source of truth.

### P1-3 · `Cart.add` inventory rollback is structurally redundant
**File:** `cart/cart.py:167-175`
**Symptom:** `check_inventory=True` check happens **after** the item has
been created/updated inside the transaction. If the check fails, code
`item.delete()`s and raises `InsufficientStock` — but the raise would roll
back the whole transaction anyway, making the explicit `.delete()`
pointless. Also, writing-then-deleting on every failure is wasteful.
**Fix:** move the inventory check to the top of `add()`, **before** the
mutation path, using the soon-to-be-computed total quantity
(`existing_qty + quantity`). No write happens on failure.
**Acceptance:** mock checker asserts `.check()` is called exactly once per
`add()` and that no INSERT/UPDATE hits the DB on a failed check.

### P1-4 · `get_*_calculator` / `get_*_checker` swallow configuration errors
**Files:** `cart/tax.py:94-98`, `cart/shipping.py:140-144`,
`cart/inventory.py:154-159`
**Symptom:** `try: ... except (ImportError, AttributeError): return
DefaultXxx()` means a typo'd dotted path silently reverts to no-op
behaviour. Debugging this is painful (taxes "don't work" but nothing
errors).
**Fix:** log `logger.warning("CART_%s misconfigured: %s", setting, exc)`
and re-raise in DEBUG mode only. Alternatively fail fast and require
callers to be explicit.
**Acceptance:** test captures logs with `assertLogs` and asserts the
warning mentions both the setting name and the bad path.

### P1-5 · Two `CartIterationTest` classes shadow each other
**File:** `tests/test_cart.py:579, tests/test_cart.py:1277`
**Symptom:** Python uses the later definition; the earlier class's tests
never run. This is why `grep -c 'def test_'` reports 292 but the runner
reports 290.
**Fix:** rename the later class to `CartIterationExtraTest` (or merge the
methods into the first class). Add a CI check: `python -c "from tests
import …; count = …; assert count == expected"` feels fragile — instead,
fail the build if any two test classes in the same module share a name.
**Acceptance:** `runtests.py` count matches `grep -c 'def test_'` across
all `tests/test_*.py`.

### P1-6 · Two divergent test configurations
**Files:** `runtests.py`, `tests/settings.py`, `pyproject.toml`
**Symptom:** pytest uses `tests/settings.py`; `python runtests.py` uses
its own `settings.configure(...)`. They differ in `INSTALLED_APPS`,
middleware, `TEMPLATES`, and `SECRET_KEY`. Equivalent *today* but trivially
divergent in the future.
**Fix:** rewrite `runtests.py` to set
`os.environ["DJANGO_SETTINGS_MODULE"] = "tests.settings"` and call the
test runner, removing its inline `settings.configure`. Drop the
redundancy.
**Acceptance:** `python runtests.py` and `pytest` both load the same
settings module; `diff <(python runtests.py) <(pytest)` is identical.

### P1-7 · "Integration" tests are unit tests
**File:** `tests/test_integration.py`
**Symptom:** Every test uses `MagicMock` for the request and a plain
dict for the session. Nothing exercises URL routing, middleware, form
handling, or response rendering.
**Fix:** add a proper `CartViewClientTest(TestCase)` that uses
`self.client.get(...)` / `self.client.post(...)` against a minimal
example view + URL wired into `tests/urls.py`. Cover: add, remove,
update, checkout, and the session-persistence assertion that proves
the cart survives across two real HTTP requests.
**Acceptance:** at least 5 tests use `self.client` and hit URLs, and at
least one verifies `response.wsgi_request.session` contains `CART-ID`.

### P1-8 · Performance tests have trivially loose bounds
**File:** `tests/test_performance.py`
**Symptom:** "Adding 50 items should complete in under **2 seconds**"
and "summary on 100 items under **0.1 s**". Current runtime on my machine
is ~0.04 s for the add test. The bounds are so loose a 10× regression
wouldn't fail them.
**Fix options:**
1. Tighten: 50 adds under 0.5 s, summary under 0.02 s.
2. Replace with `assertNumQueries(...)` — a 50-item add should be
   bounded query-count-wise, not wall-clock-wise. Query counts are
   reproducible across hardware; wall clock is not.
**Recommendation:** #2 for the assertions, keep #1 as a "smoke" check.
**Acceptance:** tests fail if `Cart.summary()` does more than 1 aggregate
query, iteration does more than `1 + n` queries (the n being
`Item.product` lookups), etc.

### P1-9 · `Item.product` N+1 on iteration
**File:** `cart/models.py:108-111`
**Symptom:** `for item in cart: print(item.product.name)` issues 1 query
per item. The per-item `_product_cache` only helps on repeated access to
the *same* item, not across items.
**Fix:** add `Cart.iter_items(prefetch_products=True)` or a
`Cart.items_with_products()` that groups items by `content_type`, fetches
each model's products in one query with `.filter(pk__in=[...])`, and
pre-populates `_product_cache` before yielding. Keep plain `__iter__`
unchanged for backwards compatibility.
**Acceptance:** `assertNumQueries(<= 1 + number_of_distinct_content_types)`
when consuming `cart.items_with_products()` on a mixed-model cart.

### P1-10 · `validate_price` semantics when `product.price is None`
**File:** `cart/cart.py:138-143, 212-217`
**Symptom:** If `product.price is None` the check silently passes. This is
arguably desirable for `FakeProductNoPrice`-style models (no `price` at
all) but surprising for models that define `price = …(null=True)` and
happen to have `None` on a specific instance.
**Fix:** split the two cases. If `hasattr(product, 'price')` and
`product.price is None` → raise `PriceMismatchError("Product has no
price configured")`. If `not hasattr(product, 'price')` → skip silently
(current behaviour). Document clearly.
**Acceptance:** two tests — one for each branch.

### P1-11 · Idempotent signal handling
**Files:** `cart/cart.py:10-23`
**Symptom:** The defensive `try/except ImportError` plus
`cart_item_added = None` guards are never actually hit; tests don't cover
lines 18-23 (the fallback branch). This is cargo-culting that hides what
the code actually does.
**Fix:** delete the try/except and the `if cart_item_added is not None`
guards. `cart/signals.py` is a first-class file and removing it would
break the package anyway.
**Acceptance:** coverage of `cart.py` rises to 100%. Tests still green.

---

## P2 — Quality, coverage, tooling

### P2-1 · Wire pre-commit into CI
**Files:** `.github/workflows/ci.yml`, `.pre-commit-config.yaml`
**Symptom:** Pre-commit exists but runs locally at best. CI accepts
unformatted, untyped, unlinted code.
**Fix:** add a `lint` job to `ci.yml`:
```yaml
lint:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v6
    - uses: actions/setup-python@v6
      with: { python-version: "3.12" }
    - run: pip install pre-commit
    - run: pre-commit run --all-files
```
and add `needs: [test, lint]` to `publish`.
**Acceptance:** introducing a deliberate style violation fails the PR check.

### P2-2 · Refresh pre-commit hook versions
**File:** `.pre-commit-config.yaml`
**Symptom:** `black 24.1.0`, `flake8 7.0.0`, `mypy v1.8.0` are ~18 months
old.
**Fix:** bump to latest stable, configure mypy with
`additional_dependencies: [django-stubs, types-*]`, run
`pre-commit autoupdate` as part of the same PR.
**Acceptance:** `pre-commit run --all-files` passes on the current tree
after the bump; any new violations are fixed in the same PR (do not adjust
configs to hide real issues).

### P2-3 · Add `mypy` / `ruff` configuration in `pyproject.toml`
**File:** `pyproject.toml`
**Symptom:** mypy and linters are invoked without project-level config,
so each developer's machine diverges.
**Fix:** add `[tool.mypy]`, `[tool.ruff]`, and `[tool.black]` sections to
`pyproject.toml`. Retire `flake8 + isort + black` in favour of `ruff`
(faster, one tool). Keep `mypy` separate.
**Acceptance:** `uv run ruff check cart/` and `uv run mypy cart/` both
produce zero findings on master.

### P2-4 · Close the 6% coverage gap
**Target:** `cart/*` coverage to ~98%+ (the ImportError fallbacks are
dead and should be deleted — see P1-11 — which alone lifts coverage).
**Missing lines (from latest run):**
| File                | Lines missing                                    |
| ------------------- | ------------------------------------------------ |
| `cart/cart.py`      | 18-23 (delete, P1-11), 373/381/441 (error branches in merge, add_bulk) |
| `cart/inventory.py` | 32 (`TYPE_CHECKING: pass` — delete), 136, 158-159 |
| `cart/models.py`    | 230-231 (`increment_usage` — called after P0-2)  |
| `cart/session.py`   | 107-108 (`CookieSessionAdapter.set_cart_id` — exercised after P0-4) |
| `cart/shipping.py`  | 143-144 (import-string error path — tested via P1-4) |
| `cart/tax.py`       | 97-98 (same)                                     |
**Acceptance:** `coverage report --fail-under=98` passes.

### P2-5 · Consolidate test helpers
**Files:** `tests/test_cart.py`, `tests/test_integration.py`,
`tests/test_performance.py`, `tests/test_v300.py`
**Symptom:** `make_request` and `make_product` are redefined four times.
**Fix:** move to `tests/_helpers.py`; replace inline copies with
`from tests._helpers import make_request, make_product`.
**Acceptance:** `grep -c 'def make_request' tests/` returns 1.

### P2-6 · Use (or remove) `tests/fixtures/fake_products.json`
**File:** `tests/fixtures/fake_products.json`
**Symptom:** Fixture present, zero tests load it.
**Fix:** either replace two or three `make_product(...)` call sites in
tests with `fixtures = ["fake_products"]`, or delete the file. The
maintainer's call — lean toward deletion if fixture usage is not a
deliberate pattern here.

### P2-7 · Restore SonarCloud or pick a single quality tool
**History:** v2.5.2 removed SonarCloud. `pyproject.toml` has
`[project.optional-dependencies].dev` with `coverage` but no
`coverage.xml` upload job in CI.
**Fix:** Pick one of:
1. Upload coverage to Codecov (simpler, free for OSS).
2. Re-enable SonarCloud with the working configuration from v2.5.1.
3. Do nothing — coverage is already printed in CI logs.
**Recommendation:** #1 — a public Codecov badge in README keeps the
maintainer honest about coverage regressions and is low-maintenance.

### P2-8 · Add `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`
**Gap:** 14-year-old public OSS project with no security disclosure
policy, no contributor guide, no CoC.
**Fix:**
- `SECURITY.md`: "Report vulnerabilities to <bruno@…>; we respond in 5
  business days; 90-day disclosure."
- `CONTRIBUTING.md`: how to run tests, coding style, commit style, PR
  expectations.
- `CODE_OF_CONDUCT.md`: Contributor Covenant v2.1 is the low-friction
  default.
- Add a GitHub issue/PR template pair (`.github/ISSUE_TEMPLATE/`,
  `.github/PULL_REQUEST_TEMPLATE.md`).

### P2-9 · Register `Discount` in admin
**File:** `cart/admin.py`
**Symptom:** `Discount` is a user-managed model (codes, expiry, usage) but
has no admin UI. Every downstream project either re-registers it or
manages via shell.
**Fix:** add a `DiscountAdmin` with `list_display`, `list_filter`,
`search_fields=("code",)`, `readonly_fields=("current_uses",)`,
`fieldsets` grouping rules vs metadata.
**Acceptance:** test that accesses `/admin/cart/discount/` with a
superuser receives a 200.

### P2-10 · `Discount` validation on save
**File:** `cart/models.py:124-226`
**Symptom:** Nothing prevents `Discount(valid_until=yesterday,
valid_from=tomorrow)`, `Discount(discount_type=PERCENT, value=150)`
(>100%), or `Discount(discount_type=FIXED, value=Decimal("-5.00"))`
(blocked by MinValueValidator but not via form validation).
**Fix:** override `clean()` on `Discount` and raise `ValidationError` for
the obvious invalid combinations. Use `ValidationError(code=...)` so
translators/consumers can map to UI messages.
**Acceptance:** tests cover each invalid combination and assert
`full_clean()` raises.

### P2-11 · Add `cart.exceptions` module (optional)
**Symptom:** Exceptions live in `cart/cart.py` and are imported as
`from cart.cart import PriceMismatchError`. Fine, but tempting to
re-export for cleaner API.
**Fix (optional):** add `cart/exceptions.py` with re-exports and make
`from cart.cart import ...` forward there. Keep both paths for
compatibility.
**Recommendation:** *skip* unless the exceptions grow past 10 types. The
current inline definitions are readable where they're raised.

---

## P3 — Features and nice-to-haves (post-3.1)

Only adopt these if the "simple cart" ethos isn't being violated. Each
one adds API surface — more surface means more maintenance forever.

### P3-1 · Async cart API
Django 5+ has stable async views. A `Cart.aadd(...)`, `Cart.aremove(...)`,
etc. using `sync_to_async` wrappers would unlock async-first downstream
apps. Non-trivial because of the `_cache` dict and request-scoped state
— get the design right before implementing.

### P3-2 · `Cart.items_with_products()` helper (N+1 batch loader)
Merge with P1-9; this is the feature-facing version of that performance
fix.

### P3-3 · `cart_notes` field on `Cart`
A user-supplied free-text note attached to the cart. Requested by
downstream users periodically (per `docs/ROADMAP.md`). Trivial: add a
`TextField(blank=True)`, one migration, pass-through getter/setter.

### P3-4 · Abandoned-cart identification API
`Cart.get_abandoned_carts(older_than: timedelta, user__isnull: bool =
False) -> QuerySet`. A classmethod so downstream Celery jobs can enqueue
reminder emails. Separate from `clean_carts`, which *deletes*
abandoned carts.

### P3-5 · Cart expiration
Complementary to `clean_carts`. Add an `expires_at: DateTimeField |
None` and reject operations on an expired cart. Requires integration
with whatever scheduler the downstream uses.

### P3-6 · Multi-currency
Large scope; likely out of scope for "simple". Flag as "use Saleor/
Oscar if you need this" in README.

### P3-7 · Cart sharing (public share-link)
Out of scope. Nice for social commerce, but every concern (privacy,
auth, rate-limiting the share endpoint) is the downstream's problem.

### P3-8 · Saved carts / wishlist
A checked-out-but-not-purchased flag? A separate `SavedCart` model? The
semantics are the tricky part, not the implementation. Needs a design
doc before any code.

### P3-9 · Structured events (beyond Django signals)
Optional emit of cart events as JSON to a webhook URL, Kafka topic, or
Django `BaseCommand` handler. Primarily for analytics pipelines. Could
be a third-party package — doesn't have to live here.

---

## Release sequencing

**Revised 2026-04-20 after v3.0.3 release.** The maintainer's cadence is
one patch release per merged PR, not one per cohesive milestone. Phase 0
shipped as v3.0.3; remaining phases each get their own patch release.
Bug fixes (the original "3.0.4") get pushed out and the version numbers
inflate, but this matches the project's historical rhythm (see v2.2.6
through v2.2.13).

```
v3.0.3 (shipped 2026-04-20) → P-1 Phase 0: pytest scaffolding,
                              conftest fixtures, canonical pattern doc.
                              No behaviour change. No API change.
v3.0.4 (pending — PR #53)   → P-1 Phase 1: migrate test_session.py to
                              tests/test_session_adapters.py as the
                              reference pytest example. Delete the
                              reflection test. No behaviour change.
v3.0.5 (this PR)            → P-1 Phase 2: migrate test_signals.py,
                              test_templatetags.py, test_performance.py.
                              Wall-clock perf assertions replaced with
                              django_assert_num_queries /
                              django_assert_max_num_queries bounds
                              (reproducible across hardware; catches
                              N+1 regressions that wall clock can mask).
                              No behaviour change.
v3.0.6 (patch)              → P-1 Phase 3: replace test_integration.py
                              (MagicMock-based) with a real HTTP test
                              suite via Django's test client.
v3.0.7 (patch)              → P-1 Phase 4: migrate test_v300.py; split
                              discounts / tax / shipping / inventory
                              into their own files.
v3.0.8 (patch)              → P-1 Phase 5: migrate test_cart.py (~2200
                              lines, 177 tests). May land as a series
                              of PRs per split file, each green, under
                              the 3.0.8 umbrella tag.
v3.0.9 (patch)              → P-1 Phase 6: deletion pass — remove all
                              reflection-only tests per the explicit
                              list in §P-1.
v3.0.10 (patch)             → P-1 Phase 7: behavioural coverage audit;
                              author @pytest.mark.xfail(strict=True)
                              regression tests for each known P0 bug.
v3.0.11 (patch)             → P-1 Phase 8: unify test runner, delete
                              runtests.py, tighten pytest config
                              (python_classes=[], filterwarnings=error),
                              enable coverage --fail-under=100 in CI.
                              P-1 complete.
v3.0.12 .. v3.0.18 (patch)  → P0 bug fixes, one per release, each
                              removing an @xfail marker as the fix:
                              3.0.12 = P0-1 (from_serializable)
                              3.0.13 = P0-2 (discount current_uses —
                                      gated, see note below)
                              3.0.14 = P0-3 (CARTS_SESSION_ADAPTER_CLASS)
                              3.0.15 = P0-4 (CookieSessionAdapter
                                      round-trip)
                              3.0.16 = P0-5 (README template-tag fix)
                              3.0.17 = P0-6 (CHANGELOG backfill)
                              3.0.18 = P0-7 (docs stale-banner)
v3.1.0 (minor)              → P1 block + P2-1, P2-2, P2-3, P2-9.
                              Cart.checkout() grows a validate kwarg.
                              Default is None → DeprecationWarning +
                              legacy behaviour. P0-2's discount
                              increment fires inside validate=True.
v3.1.x (patches)            → P2 polish and tooling — pre-commit in CI,
                              mypy/ruff config, Discount admin, etc.
                              One per change, per project convention.
v4.0.0 (major)              → Flip validate default to True. Discount
                              increment fires by default. Empty-cart /
                              below-min / stock-short checkouts raise.
                              Drop default_app_config. Drop Python 3.10.
                              Earliest October 2026 (needs one full
                              minor release cycle with the warning
                              visible in the wild).
```

**Note on P0-2 gating in the per-release plan:** the original plan gated
the Discount increment behind the validate=True branch (added in 3.1.0).
Under the per-release cadence, v3.0.13 lands the increment logic but it
can't fire yet — validate=True doesn't exist in 3.0.x. This means
v3.0.13 effectively fixes dead-code coverage (increment_usage stops
being orphaned in source) without changing runtime behaviour for any
caller. The behaviour change surfaces in 3.1.0, not 3.0.13. Acceptable;
keeps semver honest.

**Alternative:** merge the increment with a plain "increment on every
checkout" (no gating) in 3.0.13 and treat it as a bug fix, not a
behaviour change. Maintainer call — default plan above is the gated
version for semver cleanliness.

Cadence target: one patch release per PR merge, opportunistic. No hard
calendar deadlines beyond "4.0 no sooner than October 2026".

---

## Out of scope (explicitly)

- Rewriting the cart as a service / DRF viewset bundle. This library is
  deliberately framework-agnostic at the view layer.
- Migrating away from `ContentType` generic FKs. It's the headline feature.
- Supporting Django <4.2 or Python <3.10. Already dropped.
- Replacing LGPL-3.0 with a more permissive license. Maintainer-only
  decision.

---

## Verification checklist for each item

Before marking any item above "done":

1. Automated test covers the new behaviour *and* reproduces the old bug.
2. CHANGELOG has an entry under the correct version heading.
3. README updated if the user-visible API changed.
4. `coverage report` does not drop.
5. `pre-commit run --all-files` passes.
6. For P0/P1: runtime-verified manually against a freshly-installed
   wheel (not just the local tree).

---

*Authored 2026-04-20 alongside `CLAUDE.md`. When a newer dated roadmap
is added, link to it from `docs/ROADMAP.md` rather than editing this
file in place.*
