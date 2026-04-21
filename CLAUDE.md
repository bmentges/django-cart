# CLAUDE.md

Guidance for Claude Code when working in this repository. Conversational rules
shared by the maintainer already live under `.claude/rules/`; this file covers
**project-specific** architecture, conventions, and gotchas that are not
derivable from the code in seconds.

---

## 1. What this project is

`django-cart` is a lightweight, session-backed shopping cart library for Django
4.2+. It is distributed on PyPI and has been maintained since ~2012. The public
API surface is the `Cart` class in `cart/cart.py`; everything else (models,
templatetags, signals, pluggable calculators) exists to support that class.

- Package name on PyPI: **`django-cart`**
- Importable app name: **`cart`** (not `django_cart`)
- Python: **3.10+**, Django: **4.2+** (CI matrix up to Py 3.14 / Dj 6.0)
- Current version: see `pyproject.toml` (`version` field). Bump this when
  releasing; CI publishes on tag push.
- License: **MIT** (`LICENSE`). Relicensed from LGPL-3.0 in v3.0.11 —
  see `CHANGELOG.md` for the rationale. Copying code in from other MIT /
  BSD / Apache-2.0 projects is fine; avoid copying from GPL / LGPL /
  AGPL sources without clearing it first.

---

## 2. Repository map

```
cart/                        # the installable Django app
├── __init__.py              # (legacy default_app_config — see gotcha §7.1)
├── apps.py                  # CartConfig
├── admin.py                 # CartAdmin + ItemInline (Discount NOT registered — §7.7)
├── cart.py                  # Cart class + exceptions + CART_ID — main API
├── models.py                # Cart, Item (GFK), ItemManager, Discount, DiscountType
├── signals.py               # 5 Django signals (optional import in cart.py)
├── session.py               # CartSessionAdapter, DjangoSessionAdapter, CookieSessionAdapter
│                            #   ⚠️ declared but NOT wired into Cart — see §7.2
├── tax.py                   # TaxCalculator base + DefaultTaxCalculator + get_tax_calculator()
├── shipping.py              # ShippingCalculator base + default + factory
├── inventory.py             # InventoryChecker base + default + factory
├── templatetags/cart_tags.py  # cart_item_count, cart_summary, cart_is_empty, cart_link
├── management/commands/clean_carts.py  # cron-friendly purge command
├── migrations/              # 0001..0005 — do NOT squash without version bump
└── views.py                 # intentionally empty

tests/
├── settings.py              # used by pytest (pyproject sets DJANGO_SETTINGS_MODULE)
├── urls.py                  # admin only — most tests don't hit HTTP
├── test_app/                # FakeProduct + FakeProductNoPrice (test-only product models)
├── fixtures/fake_products.json  # present but UNUSED by tests (§7.9)
├── test_cart.py             # ~2200 lines, 177 tests — the bulk of the suite
├── test_v300.py             # discounts/tax/shipping/inventory (64 tests)
├── test_integration.py      # "integration" — still uses MagicMock requests (§7.3)
├── test_performance.py      # 3 loose timing benchmarks
├── test_session.py          # session adapters (14 tests)
├── test_signals.py          # 7 tests
└── test_templatetags.py     # 13 tests

docs/
├── PROJECT_ANALYSIS.md              # Mar 2026 analysis (partly stale — ref v2.2.13)
├── PROJECT_ANALYSIS_2026_03_29_0243am.md  # earlier snapshot
└── ROADMAP.md                       # thin "future considerations" list

pyproject.toml               # pytest + coverage config (runtests.py deleted in Phase 8; .coveragerc folded in at Phase 0)
.pre-commit-config.yaml      # black, isort, flake8, mypy — NOT run in CI (§7.8)
.github/workflows/ci.yml     # test matrix + publish-on-tag to PyPI
.github/dependabot.yml       # weekly pip + gh-actions updates
```

---

## 3. Core architecture

### 3.1 The `Cart` facade

`cart.cart.Cart` is a thin wrapper around one `cart.models.Cart` row. On
construction:

1. Look up `CART-ID` in `request.session`.
2. If it points to a non-checked-out DB cart, reuse it; otherwise create one
   and write its id back into `request.session`.
3. Initialise `self._cache = {}` — an **in-memory** cache for `count()` and
   `summary()` invalidated by every mutation. Not a Django cache.

Everything else (`add`, `update`, `remove`, `merge`, `apply_discount`, `tax`,
`shipping`, `total`, …) operates on `self.cart` and its related `items`.

### 3.2 Products via ContentType (generic FKs)

`Item` stores a product as `(content_type, object_id)`. The custom
`ItemManager._inject_content_type` translates `product=<instance>` kwargs in
`.get()` / `.filter()` into `content_type=…, object_id=…` — so call sites read
naturally (`Item.objects.filter(cart=c, product=p)`) while the schema stays
generic.

`Item.product` is a cached property: first access resolves via
`content_type.model_class().objects.get(pk=object_id)` and stores on
`_product_cache`. This avoids N+1 when iterating a single `Cart` instance but
does NOT share cache across items — a 50-item cart iteration is still 50
queries for products. See ROADMAP for prefetch work.

### 3.3 Pluggable subsystems

Tax, shipping, and inventory all follow the same pattern:

```
cart/<subsystem>.py:
    class XxxBase(ABC):              # abstract interface
    class DefaultXxx(XxxBase):       # no-op default
    def get_xxx() -> XxxBase:        # import_string from CART_XXX setting, falls back to default
```

Settings names:

| Subsystem | Setting                       | Default behaviour           |
|-----------|-------------------------------|-----------------------------|
| Tax       | `CART_TAX_CALCULATOR`         | returns `Decimal("0.00")`   |
| Shipping  | `CART_SHIPPING_CALCULATOR`    | returns `Decimal("0.00")`, one "free" option |
| Inventory | `CART_INVENTORY_CHECKER`      | always `True`               |

The factories **swallow `ImportError`/`AttributeError`** and silently fall back
to the default — so a typo in the dotted path yields "works, but with no tax"
rather than a clear error. Keep this in mind when debugging configuration.

### 3.4 Discounts

`Discount` is a real DB model with `code`, `discount_type` (`PERCENT` or
`FIXED`), `value`, `min_cart_value`, `max_uses`, `current_uses`, `active`,
`valid_from`, `valid_until`. `Cart` has a nullable FK to `Discount`.

`Cart.apply_discount(code)`:
- rejects if a discount is already applied
- calls `Discount.is_valid_for_cart(self)` which checks active / window / max
  uses / min cart value
- stores the FK on the cart

**⚠️ `current_uses` is never incremented automatically** — see §7.5.

### 3.5 Signals (optional)

`cart/signals.py` defines `cart_item_added`, `cart_item_removed`,
`cart_item_updated`, `cart_checked_out`, `cart_cleared`. They are imported
defensively in `cart/cart.py` inside a `try/except ImportError` so the module
still works if the signals file is removed — this is belt-and-braces; the
fallback branch is not covered by tests.

### 3.6 Session adapters

`cart/session.py` defines `CartSessionAdapter` + two concrete subclasses.
**None of them is actually wired into `Cart`.** See §7.2.

---

## 4. Data model

```
Cart                              Item                          Discount
├── id                            ├── id                        ├── id
├── creation_date                 ├── cart → Cart (CASCADE)     ├── code (unique)
├── checked_out                   ├── quantity (PositiveInt)    ├── discount_type (percent|fixed)
├── user → auth.User (nullable)   ├── unit_price (>=0)          ├── value
└── discount → Discount (SET_NULL)├── content_type + object_id  ├── min_cart_value (nullable)
                                  └── unique_together           ├── max_uses (nullable)
                                        (cart, content_type,    ├── current_uses
                                         object_id)             ├── active
                                  + composite index on          ├── valid_from (nullable)
                                        (cart, content_type,    └── valid_until (nullable)
                                         object_id)
```

Migrations: `0001_initial` → `0002_add_unit_price_validator` →
`0003_add_user_fk` → `0004_add_item_indexes` → `0005_add_discount_model`.
All shipped in releases — never edit a migration in place; always add a new one.

---

## 5. Environment & commands

The maintainer's preference is **`uv`** (see `.claude/rules/preferences.md`).
Don't use pip/poetry unless the user explicitly asks.

```bash
# Set up a venv and install the package + dev deps
uv venv
uv pip install -e ".[dev]"

# Run the full test suite (two options, see §7.4 about the divergence)
uv run python runtests.py                  # standalone Django settings
uv run pytest                              # uses tests/settings.py via pyproject

# Run a specific test class
uv run python runtests.py tests.test_cart.CartAddTest

# Coverage
uv run coverage run runtests.py
uv run coverage report        # currently 94% (not 100% as older docs claim — see §7.6)
uv run coverage html          # → htmlcov/

# Lint / format (pre-commit config exists, not run in CI)
uv run pre-commit run --all-files

# Management command
uv run python -m django test            # not used here; no manage.py
uv run python manage.py clean_carts     # only from downstream projects

# Build & publish (normally handled by CI on tag push)
uv run python -m build
uv run twine upload dist/*
```

There is no `manage.py` in the repo — only downstream projects get one.

---

## 6. Conventions used in this codebase

- **No `from .models import Cart`** inside `cart/cart.py`; it uses `from . import models` and prefixes as `models.Cart`, `models.Item` to avoid name collision with the `Cart` class in that module. Preserve that pattern.
- **Lazy imports inside methods** (`from .tax import get_tax_calculator` inside `Cart.tax()`) are intentional — they avoid import cycles and let `cart` load without all subsystems. Don't hoist them to module top.
- **`gettext_lazy` for all verbose names** (`_("cart")`, etc.). Keep any new model fields i18n-friendly.
- **Docstrings are Sphinx-style** (`:param:`, `:returns:`, `:raises:`) in `cart/cart.py` but Google-style (`Args:`, `Returns:`) in newer files (`tax.py`, `shipping.py`, `inventory.py`, `models.Discount`). Match the neighbour's style when editing rather than converting.
- **Type hints on all new public functions.** Models declare types via class-level annotations (Cart/Item models do, Discount mostly does not — acceptable inconsistency).
- **Decimal literals:** always `Decimal("0.00")` with quotes, never `Decimal(0)` or float. `decimal_places=2`, `max_digits=18` for money; `max_digits=10` for discount metadata.
- **Atomic blocks wrap mutations** (`with transaction.atomic():`). Adding a new mutation path? Wrap it.
- **Cache invalidation:** every mutation calls `self._invalidate_cache()`. New mutations must do the same or `summary()`/`count()` will lie.
- **No `manage.py`, no `urls.py`** for the app itself; the library is URL-agnostic.

---

## 7. Gotchas and sharp edges

### 7.1 `cart/__init__.py` still uses `default_app_config`

```python
default_app_config = "cart.apps.CartConfig"
```

Deprecated since Django 3.2 and slated for removal in Django 6.0. Currently
harmless, but any Django 6.x compatibility sweep should drop it (Django now
auto-discovers `AppConfig` subclasses).

### 7.2 ~~`CARTS_SESSION_ADAPTER_CLASS` is documented but not implemented~~ (resolved in v3.0.12)

Historically: the setting was documented in the README but `Cart.__init__`
called `request.session.get(CART_ID)` directly, and `CookieSessionAdapter.get()`
read from an in-memory dict that never saw `request.COOKIES` — so the feature
silently no-op'd end to end.

Closed in three hops:

- **v3.0.11 — P0-3:** `Cart.__init__` now reads `CARTS_SESSION_ADAPTER_CLASS`
  and routes through the returned adapter. Bad dotted paths raise
  `ImportError` loudly.
- **v3.0.11 — P0-4:** `CookieSessionAdapter.__init__` hydrates
  `self._cookies` from `request.COOKIES`, so a cart id written to one response
  is recoverable from the next request's `Cookie` header.
- **v3.0.12 — P0-A:** The adapter's `set` path now reaches the response.
  `Cart._build_session_adapter` stashes the adapter on `request._cart_session`
  and `cart.middleware.CartCookieMiddleware` calls the new
  `CartSessionAdapter.flush_to_response(request, response)` hook to emit
  `Set-Cookie` / `Delete-Cookie` for changed state. Before v3.0.12, the
  adapter was constructed with `response=None`, so writes stuck in the
  in-memory dict and the browser never received `CART-ID`.

Downstream wiring:

```python
# settings.py
CARTS_SESSION_ADAPTER_CLASS = "cart.session.CookieSessionAdapter"
MIDDLEWARE = [..., "cart.middleware.CartCookieMiddleware"]
```

The middleware is harmless for `DjangoSessionAdapter` (it calls the ABC's
no-op `flush_to_response`) — leaving it installed on a mixed-adapter
project is safe.

### 7.3 "Integration" tests are not HTTP integration tests

`tests/test_integration.py` is named aspirationally. Every test uses
`make_request()` → `MagicMock` with a dict session, the same pattern as the
unit tests. Nothing goes through Django's test client, middleware, or URL
routing. A real integration failure at the view/middleware boundary would not
be caught.

### 7.4 ~~Two divergent test configurations~~ (resolved in v3.0.10)

Historically: `pyproject.toml` targeted pytest at `tests.settings` while
`runtests.py` reconfigured Django inline with different `INSTALLED_APPS`,
middleware, and `TEMPLATES`. The two runners could diverge silently.

P-1 Phase 8 (v3.0.10) deleted `runtests.py`; pytest + `tests/settings.py`
is now the only test-runner path. Left here as a pointer for anyone
reading older commit messages that still mention the landmine.

### 7.5 `Discount.current_uses` never increments automatically

`Discount.increment_usage()` exists in `cart/models.py` but is never called
from `Cart.apply_discount()`, `Cart.checkout()`, or anywhere else. Verified at
runtime: apply + checkout leaves `current_uses=0`. That means `max_uses`
enforcement only fires if a downstream user manually bumps the counter.
Neither tests nor docs mention this responsibility. Real bug.

### 7.6 `Cart.from_serializable` does not restore items

Despite its name, the method creates a new (empty) cart, then iterates the
data dict looking for **pre-existing** items by `object_id` and updates them.
On a fresh cart there is nothing to update, so the call is a silent no-op.
Runtime-verified. The existing tests only pass because they pre-populate the
cart before calling the method, which masks the bug.

The method should create items from the data (resolving `content_type` + a
product-lookup strategy) or be renamed to something like
`update_from_serialized` and explicitly documented as "update existing items
only."

### 7.7 Admin coverage is incomplete

`cart.admin` registers `Cart` (with `ItemInline`) but **not** `Discount`.
Users creating discounts today either go through the shell or add the
registration in their own project. `Item` is also not registered standalone,
which is fine (it's inline).

### 7.8 Pre-commit is not enforced in CI

`.pre-commit-config.yaml` wires black, isort, flake8, mypy — but
`.github/workflows/ci.yml` only runs tests. Contributors who skip pre-commit
locally can push unformatted/untyped code, and CI will accept it. Add a lint
job or integrate `pre-commit run --all-files` into the existing test job.
Also: hook versions (black 24.1, flake8 7.0, mypy 1.8) are ~18 months old as
of Apr 2026 — refresh during any lint pass.

### 7.9 Test helpers are duplicated; fixtures are unused

`make_request`, `make_product`, etc. are redefined in `test_cart.py`,
`test_integration.py`, `test_performance.py`, `test_v300.py`. Moving them to a
shared `tests/_helpers.py` or `conftest.py` is safe and reduces drift.

`tests/fixtures/fake_products.json` exists but no test calls
`loaddata`/`fixtures = [...]` — it's dead weight. Either use it in a
fixture-based test or delete it.

### 7.10 Silent test loss from class-name collision

Two classes are both named `CartIterationTest` in `tests/test_cart.py`
(lines 579 and 1277). Python uses the second definition; the first class's
tests (`test_iter_returns_items`, `test_iter_with_single_item`) never run.
This is why a grep for `def test_` reports 292 but `runtests.py` reports
290 — the discrepancy is real.

Rename one of them (e.g. the second to `CartIterationExtraTest`).

### 7.11 `Cart.checkout()` does not validate or reserve

- It does **not** call `can_checkout()` — so checkout from an empty cart or
  below `CART_MIN_ORDER_AMOUNT` is allowed.
- It does **not** call any `InventoryChecker.reserve()`; `reserve()` is on the
  abstract interface but unused by library code. A user wanting stock
  reservation must override `checkout` or reserve from their own view.
- It does **not** increment `Discount.current_uses` (see §7.5).

Whether to fold these in is a design call (the library's "simple" ethos vs.
the expectations set by those features' presence).

### 7.12 `validate_price=True` silently skips if `product.price is None`

`Cart.add(..., validate_price=True)` reads `getattr(product, 'price', None)`
and skips validation when it's falsy. That's intentional for products with
no `price` attribute — but it also silently skips for products that *have*
the attribute set to `None`/`0`. Worth a sentence in the docstring.

### 7.13 Atomic blocks lock the transaction, not the row

`Cart.add` / `Cart.update` / `Cart.merge` wrap mutations in
`transaction.atomic()` but read with `.first()` without `select_for_update()`.
Under concurrent requests on Postgres/MySQL two workers can both read
`quantity=N` and both write `N+q`, clobbering one add. The in-repo
"CartAtomicTest" suite does not exercise real concurrency; it verifies
rollback on exception only. The README's "safe concurrent cart modifications"
is aspirational.

### 7.14 Minor documentation drifts

- README template-tag examples pass `request` as a positional argument
  (`{% cart_item_count request %}`). The tags use `takes_context=True` and
  take **no** positional args. `cart_link` example also has the argument
  order wrong (`request "class" "text"` vs the real signature
  `text, css_class`).
- README claims "290 tests" — matches run count but hides §7.10.
- `docs/PROJECT_ANALYSIS.md` says "100% code coverage". Real figure: **94%**
  (coverage excludes migrations + tests per `.coveragerc`).
- `docs/ROADMAP.md` is sparse; most recent real planning lives in
  `PROJECT_ANALYSIS.md` §10. `docs/ROADMAP_2026_04.md` (written alongside
  this file) is the current plan of record.
- `CHANGELOG.md` stops at v2.7.0; v3.0.0, v3.0.1, v3.0.2 are in git tags but
  not the changelog.

---

## 8. When making changes

### New mutation on `Cart`
1. Wrap the DB work in `transaction.atomic()`.
2. Call `self._invalidate_cache()` after success.
3. Emit the appropriate signal if one applies (and guard with
   `if cart_item_* is not None:` to preserve the optional-signal contract).
4. Add both a happy-path and an error-path test. Prefer real DB state
   assertions over mock assertions.

### New model field
1. Add it to `cart/models.py` with `verbose_name=_("…")` and a validator if
   relevant.
2. Run `python manage.py makemigrations` from a downstream project (the repo
   has no manage.py; use `runtests.py`'s settings or a throwaway Django
   project). Commit the generated migration as `000N_<desc>.py`.
3. If the field is money, use `DecimalField(max_digits=18, decimal_places=2)`;
   for discount-like metadata `max_digits=10` matches the existing style.
4. Never edit a prior migration. Never squash without a major version bump.

### Adding a configurable subsystem
Mirror the tax/shipping/inventory pattern: abstract base + default + factory
reading `CART_*_CLASS` via `django.utils.module_loading.import_string`. Handle
`ImportError`/`AttributeError` by falling back to the default (current
convention) **and** log a warning — the silent fallback is a known source of
debugging pain (§3.3).

### Bumping the version
1. Edit `pyproject.toml` → `project.version`.
2. Add a CHANGELOG entry (backfill v3.0.0–3.0.2 while you're there).
3. Commit, tag `vX.Y.Z`, push tag — CI publishes to PyPI automatically. PyPI
   credentials live in the `PYPI_API_TOKEN` repo secret.

### Touching the README
The maintainer treats this as the canonical user documentation. Verify every
code example executes against the current API — specifically the template-tag
usage, the merge flow, and the session-adapter setting (§7.2, §7.14).

---

## 9. Test strategy guidelines

**Status:** the P-1 test overhaul is **complete** as of v3.0.10.
pytest + pytest-django with `conftest.py` fixtures is the only test
pattern. The maintainer's founding decisions (2026-04-20):

- **Framework:** **pytest + pytest-django**. No `TestCase` subclasses.
  `pyproject.toml` sets `python_classes = []` so accidental class-based
  tests are uncollected (noisy in review).
- **Discipline:** **TDD.** Every bug fix lands as a failing test first,
  then the fix. Every new feature lands the same way. No exceptions.
- **Reflection tests:** **delete, don't preserve.** A test that asserts
  `__annotations__`, `admin.list_display`, `hasattr(obj, '_private')`,
  or `issubclass(X, Exception)` verifies Python/Django mechanics, not
  django-cart behaviour. Replace with a test that would fail if the
  feature actually broke for a user — or delete outright.
- **Coverage:** informational, not enforced. `pyproject.toml` sets
  `[tool.coverage.report] fail_under = 90` so `coverage report` exits
  non-zero locally when coverage drops below 90%. CI does not run
  `coverage report`; it is advisory, never a merge blocker.

### Working rules (post-migration; during migration, follow the file
you're editing)

- Prefer real DB state assertions (`cart.cart.items.first().quantity == 3`)
  over mock call assertions.
- **No `MagicMock(request)`.** Use the `rf_request` fixture
  (`RequestFactory().get("/")` with `session = {}` attached) or build
  a real one inline. `MagicMock` silently hides session-layer bugs.
- **No helper functions in test files.** Helpers live in
  `tests/conftest.py` as fixtures (`cart`, `product`, `discount`,
  `user_cart`, `rf_request`, …).
- **No wall-clock performance assertions.** Use
  `django_assert_num_queries` from pytest-django.
- **One behaviour per test function.** If the docstring needs "and",
  split it. Use `@pytest.mark.parametrize` for tables of inputs.
- **Transaction behaviour:** `@pytest.mark.django_db(transaction=True)`
  replaces `TransactionTestCase`. Mark it explicitly; the overhead is
  worth paying only when the behaviour needs it.
- **Settings overrides:** `@pytest.mark.django_db` combined with
  `settings` fixture (from pytest-django) beats `@override_settings`;
  use it.
- **Test file naming:** mirrors the module under test — `test_cart_add.py`,
  `test_cart_merge.py`, `test_discount_model.py`, `test_session_adapters.py`.
  One concern per file.

### Coverage

- The target is **100% behavioural coverage**, not 100% line coverage.
  Line coverage is the lagging indicator.
- `coverage report --fail-under=100` runs in CI once P-1 Phase 8 lands.
- Before that, coverage is the eyeball guide and the behavioural audit
  checklist (ROADMAP P-1 Phase 7) is the gate.
- If you add a code path, add a test. If the test wouldn't fail when
  the behaviour broke, it's not buying anything — delete or rewrite it.

### Reference

The roadmap in `docs/ROADMAP_2026_04.md` §P-1 is the full migration
plan (phases, canonical pattern, explicit delete list, behavioural
audit list, risks). Cite it in PR descriptions when migrating tests so
reviewers can check the relevant phase's exit criterion.

---

## 10. External references

- PyPI: <https://pypi.org/project/django-cart/>
- GitHub: <https://github.com/bmentges/django-cart>
- Project analysis: `docs/PROJECT_ANALYSIS.md` (partly stale)
- Active roadmap: `docs/ROADMAP_2026_04.md`
- Release history: `CHANGELOG.md` + git tags

---

*Last updated: 2026-04-20.*
