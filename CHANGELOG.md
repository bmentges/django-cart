# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_No unreleased changes._

## [3.0.12] — 2026-04-21

### Added
- `cart.middleware.CartCookieMiddleware` — new middleware that flushes
  pending cookie state from the active session adapter onto the
  outgoing response. Required when `CARTS_SESSION_ADAPTER_CLASS` is
  set to `CookieSessionAdapter` (or any custom cookie-backed adapter);
  harmless to leave installed when using `DjangoSessionAdapter`. (#P0-A)
- `CartSessionAdapter.flush_to_response(request, response)` — new ABC
  hook. Default implementation is a no-op; `CookieSessionAdapter`
  overrides it to diff its in-memory cookie state against
  `request.COOKIES` and call `response.set_cookie` /
  `delete_cookie` for added, changed, and removed entries.

### Fixed
- **P0-A** · `CookieSessionAdapter` now actually persists the cart id
  across requests when wired via `CARTS_SESSION_ADAPTER_CLASS`. Before
  this release, the adapter constructed by `Cart.__init__` received
  `request` only, so writes went to an in-memory dict and the browser
  never saw `Set-Cookie: CART-ID=…` — every request created a new
  abandoned cart row. `Cart._build_session_adapter` now caches the
  adapter on `request._cart_session` and `CartCookieMiddleware`
  flushes pending cookies onto the response.

## [3.0.11] — 2026-04-21

### Changed — Licensing

- **Relicensed from LGPL-3.0 to MIT.** Downstream projects can now
  embed, modify, and redistribute `django-cart` under any license
  compatible with MIT (including proprietary). The only requirement
  is to preserve the copyright notice and the permission notice in
  substantial copies. Prior tagged releases (v2.x and v3.0.0
  through v3.0.10) remain available under LGPL-3.0; only v3.0.11
  onward is MIT-licensed.

### Added
- `cart_serializable()` output now includes `content_type_id` per item so
  the payload is self-describing and can restore into a fresh cart.
  Existing consumers that only read `quantity` / `unit_price` /
  `total_price` are unaffected. (#61)
- CHANGELOG backfilled for v3.0.0–v3.0.10; adopted Keep-a-Changelog
  headings. Added CI step that fails if `CHANGELOG.md` does not mention
  the current `pyproject.toml` version.
- Full README rewrite (educational tone, engineers + agents audience,
  five Mermaid diagrams, corrected template-tag signatures, correct
  custom session-adapter interface).
- `docs/AGENTS.md` — guide for coding-agent-driven extension of
  downstream projects that use `django-cart`.
- Roadmap `docs/ROADMAP_2026_04.md` §P3-10 reserves a slot for
  high-precision decimal representation (cryptocurrency-style
  fractional quantities) as a near-future feature. No code change
  yet.

### Changed
- `Cart.checkout()` is now idempotent — calling it twice on the same
  cart is a no-op (no duplicate signal, no second counter increment).
  It also wraps its mutations in `transaction.atomic()` and, when a
  discount is applied, locks the `Discount` row via
  `select_for_update()` before revalidating and incrementing. (#63)
- `Discount.increment_usage()` now uses an `F()` expression for race
  safety. Concurrent increments can no longer lose updates. Callers
  must `refresh_from_db()` to observe the new value. (#63)
- `Cart.__init__` no longer accesses `request.session` directly. Session
  I/O is routed through the adapter named by
  `CARTS_SESSION_ADAPTER_CLASS` (default `DjangoSessionAdapter`). (#64)

### Fixed
- **P0-1** · `Cart.from_serializable` on a fresh cart is no longer a
  silent no-op. Items are created from the payload using
  `content_type_id`. Legacy payloads without that field now raise
  `ValueError` with a clear message rather than silently returning an
  empty cart. (#61)
- **P0-2** · Applied discounts with `max_uses` now actually enforce the
  cap. `Cart.checkout()` increments `Discount.current_uses` in the
  same atomic transaction that marks the cart checked out, and
  revalidates the discount under row-level lock. If the discount
  became invalid between apply and checkout (expired, deactivated,
  cap reached via a concurrent checkout), the whole checkout rolls
  back with `InvalidDiscountError`. (#63)
- **P0-3** · `CARTS_SESSION_ADAPTER_CLASS` is now read by
  `Cart.__init__`. Accepts both a dotted import string and a class
  object, matching the two forms documented in the README. Bad dotted
  paths raise `ImportError` loudly (no silent fallback — session
  storage is too critical). (#64)
- **P0-4** · `CookieSessionAdapter` now round-trips cookies across
  requests. `__init__` hydrates `self._cookies` from `request.COOKIES`
  when a request is passed, so a cart id written to one response is
  recoverable on the next request. (#65)
- CI: the `publish` job no longer tries to re-upload the previous tag
  on every master push. Gated on `startsWith(github.ref, 'refs/tags/v')`
  and uses `twine upload --skip-existing` for tag-repush idempotency.
  (#62)

## [3.0.10] — 2026-04-21

### Removed
- `runtests.py` — pytest is the only supported test runner.

### Changed
- Advisory coverage floor of 90% set in `pyproject.toml`
  (`[tool.coverage.report] fail_under = 90`). Local-only; CI does not
  run `coverage report`.
- **P-1 test overhaul complete.** Every subsequent behaviour change
  lands TDD-first on the new pytest foundation. (PR #60)

## [3.0.9] — 2026-04-21

### Added
- Four `@pytest.mark.xfail(strict=True)` regression tests for known P0
  bugs (P0-1 through P0-4) authored during the behavioural coverage
  audit. Each xfail is cleared by the corresponding P0 fix PR.

### Removed
- Reflection-only tests — assertions on `__annotations__`, admin config
  tuples, `hasattr` on private caches, `issubclass(X, Exception)`.
  Replaced with tests that would fail if the feature actually broke
  for a user, or deleted outright. (PR #59)

## [3.0.8] — 2026-04-21

### Fixed
- Two `CartIterationTest` classes in `tests/test_cart.py` shadowed each
  other; Python used only the second definition, silently dropping two
  tests. Renamed the second to `CartIterationExtraTest` so both run.
  (Silent test loss fixed as part of PR #58.)

### Changed
- `tests/test_cart.py` (~2200 lines) split into 19 focused files, one
  concern per file. (PR #58)

## [3.0.7] — 2026-04-20

### Changed
- `tests/test_v300.py` split into focused files by subsystem (discounts,
  tax, shipping, inventory). (PR #57)

## [3.0.6] — 2026-04-20

### Changed
- Mock-based `tests/test_integration.py` replaced with a real HTTP
  integration suite that exercises views, middleware, and session
  storage via Django's test client. (PR #56)

## [3.0.5] — 2026-04-20

### Changed
- Session adapter tests migrated to pytest. (PR #53)
- Signals, templatetags, and performance tests migrated to pytest.
  Wall-clock performance assertions replaced with
  `django_assert_num_queries`. (PR #54/#55)

## [3.0.4]

Skipped — no release. (Earmarked in an earlier plan, reassigned in the
v3.0.3 retrospective to v3.0.5.)

## [3.0.3] — 2026-04-20

### Added
- `tests/conftest.py` — single source of canonical pytest fixtures
  (`rf_request`, `cart`, `other_cart`, `user_cart`, `product`,
  `product_no_price`, `product_factory`, `discount_percent`,
  `discount_fixed`).
- `tests/README.md` — canonical test pattern and fixture catalogue.

### Changed
- Established pytest + pytest-django as the test foundation of the P-1
  overhaul (Phase 0). No behaviour change. (PR #52)

## [3.0.2] — 2026-03-29

### Added
- `docs/PROJECT_ANALYSIS.md` — audit of the repository. (Partly
  superseded by `docs/ROADMAP_2026_04.md`.)

## [3.0.1] — 2026-03-29

### Changed
- `docs/ROADMAP.md` simplified to a short "future considerations" list.
  (Superseded by `docs/ROADMAP_2026_04.md` from v3.0.3 onward.)

## [3.0.0] — 2026-03-29

First minor feature release on top of the v2.x line. Adds discount
codes, tax, shipping, and inventory checking as pluggable subsystems,
plus supporting Cart API. (PR #51)

### Added
- **Discount system.** New `Discount` model with `code`,
  `discount_type` (`percent` / `fixed`), `value`, `min_cart_value`,
  `max_uses`, `current_uses`, `active`, `valid_from`, `valid_until`.
  `Cart` gains an optional `discount` FK.
  - `Cart.apply_discount(code)` / `Cart.remove_discount()`
  - `Cart.discount_amount()` / `Cart.discount_code()`
  - `InvalidDiscountError` exception
- **Tax.** `TaxCalculator` abstract base + `DefaultTaxCalculator`
  (returns `Decimal("0.00")`) + `get_tax_calculator()` factory.
  Configurable via `CART_TAX_CALCULATOR` setting (dotted path).
  `Cart.tax()` returns the calculated amount.
- **Shipping.** `ShippingCalculator` + `DefaultShippingCalculator`
  (returns `Decimal("0.00")` and one "free" option). Configurable via
  `CART_SHIPPING_CALCULATOR`. `Cart.shipping()` and
  `Cart.shipping_options()`.
- **Inventory.** `InventoryChecker` + `DefaultInventoryChecker` (always
  `True`). Configurable via `CART_INVENTORY_CHECKER`. Opt-in via
  `check_inventory=True` on `Cart.add()` and `Cart.update()`.
  `InsufficientStock` exception.
- `Cart.total()` — grand total = `summary + tax + shipping - discount`.
- `Cart.can_checkout()` — minimum-order validation using the new
  `CART_MIN_ORDER_AMOUNT` setting. `MinimumOrderNotMet` exception.
- `cart/migrations/0005_add_discount_model.py`.

### Changed
- Factory functions for tax / shipping / inventory swallow
  `ImportError` / `AttributeError` from misconfigured dotted paths and
  silently fall back to the default. (Known debugging pain — see
  `docs/ROADMAP_2026_04.md` §P1-4 for the planned fix.)

## [2.7.0]

- Add PriceMismatchError exception for price validation security.
- Add validate_price parameter to add() and update() methods.
- Add in-memory caching layer with _cache dict for summary() and count().
- Add _invalidate_cache() method called on all cart mutations.
- Add composite database index on Item model (cart, content_type, object_id).
- Add cart/migrations/0004_add_item_indexes.py for database performance.
- Add 16 new tests covering price validation, caching, and database indexes.

## [2.6.1]

- Add cart merge functionality with three strategies: 'add' (default), 'replace', 'keep_higher'.
- Add user binding via optional ForeignKey on Cart model.
- Add bind_to_user() method to associate cart with user account.
- Add get_user_carts() classmethod to retrieve all carts for a user.
- Add add_bulk() method for efficient multiple item operations.
- Add CART_MAX_QUANTITY_PER_ITEM setting to enforce per-item quantity limits.
- Add cart/migrations/0003_add_user_fk.py for user ForeignKey migration.
- Add 25 new tests covering merge, user binding, bulk operations, and max quantity.

## [2.5.2]

- Remove SonarCloud from CI/CD workflow (simpler pipeline, no more coverage tracking in CI).

## [2.5.1]

- Fix SonarCloud issues: remove unused imports from migration file.
- Add sonar.exclusions to exclude migrations and tests from SonarCloud analysis.

## [2.5.0]

- Add Django signals for extensibility: cart_item_added, cart_item_removed, cart_item_updated, cart_checked_out, cart_cleared.
- Add cart templatetags: cart_item_count, cart_summary, cart_is_empty, cart_link.
- Add session adapter classes: CartSessionAdapter (base), DjangoSessionAdapter, CookieSessionAdapter.
- Signals are optional - cart works without signals module.
- Add from_serializable classmethod to Cart for deserialization.
- Add comprehensive tests for signals (7 tests), session adapters (12 tests), and template tags (10 tests).

## [2.4.1]

- Add V240EdgeCaseTest class with edge case tests for v2.4.0 features.
- Add test_performance_with_decimal_precision to verify performance with small decimal values.
- Add test_integration_with_custom_session_backend to verify session backend compatibility.

## [2.4.0]

- Add Dependabot configuration for automated dependency updates (.github/dependabot.yml).
- Add CartViewIntegrationTest class for request-level cart operations.
- Add CartSessionIntegrationTest class for session persistence tests.
- Add CartSerializationIntegrationTest class with full serialization test coverage.
- Add CartPerformanceTest class with timing benchmarks for add, summary, and iteration.
- Add CartAdminOperationsTest class for admin changelist, search, and filter operations.
- Add test_integration.py with 16 integration tests.
- Add test_performance.py with 3 performance benchmark tests.

## [2.3.0]

- Add type hints to cart/models.py for better IDE support and static analysis.
- Add MinValueValidator to unit_price field to prevent negative prices.
- Fix Item.product N+1 query issue by adding caching with _product_cache attribute.
- Improve Cart.__str__ representation to include cart ID and item count.
- Add .pre-commit-config.yaml with black, isort, flake8, and mypy hooks.
- Add 22 new tests covering type hints, unit price validation, product caching, and string representation.

## [2.2.13]

- Separate SonarCloud analysis into dedicated job that runs only on master/main branch pushes (not on PRs or tags).
- Publish job now depends only on test job, not on SonarCloud.

## [2.2.12]

- Update Changelog section in README.md with all tags from v2.0.0 to v2.2.11.

## [2.2.11]

- Fix SonarCloud coverage path issue - add step to replace GitHub workspace paths in coverage.xml.

## [2.2.10]

- (tag only)

## [2.2.9]

- Add sonar-project.properties for SonarCloud configuration.
- Fix SonarCloud CI integration.

## [2.2.8]

- Fix SonarCloud action inputs in CI workflow.

## [2.2.7]

- Fix SonarCloud configuration in CI - pass SONAR_PROJECT_KEY and SONAR_ORGANIZATION.

## [2.2.6]

- Add SonarCloud integration to CI workflow.

## [2.2.5]

- Remove unused tests placeholder file (cart/tests.py).
- 100% code coverage achieved.

## [2.2.4]

- Add coverage tool to dev dependencies.
- Create .coveragerc configuration.
- Add README section for running code coverage.
- Add 11 admin tests covering CartAdmin and ItemInline.
- Add 18 new tests for edge cases.
- Test count increased from 63 to 92.
- Code coverage increased to 79%.

## [2.2.3]

- Fixing tag (version bump).

## [2.2.2]

- Replace deprecated get_object_for_this_type with model_class().objects.get().
- Remove total_price from ItemInline.readonly_fields (computed property optimization).

## [2.2.1]

- Fix ContentType lookup for proxy model support - use product._meta.model instead of type(product).

## [2.2.0]

- Refactor test infrastructure.
- Remove FakeProduct model from cart migration.
- Create dedicated test_app with FakeProduct model.
- Add fixture file with sample test products.

## [2.1.0]

- Fix race conditions in Cart.add() and Cart.update() with atomic transactions.
- Add CartAtomicTest with 6 tests for atomic behavior.

## [2.0.0]

- Dropped Python 2 / Django < 4.2 support.
- Replaced `ugettext_lazy` → `gettext_lazy`.
- Replaced `__unicode__` → `__str__`.
- Replaced `import models` → `from . import models` (relative import).
- `Cart.new()` → private `Cart._new()`; `creation_date` now uses `timezone.now()` instead of `datetime.datetime.now()`.
- `Item.item_set` → `Item.items` (`related_name="items"`).
- Added `unique_together` constraint on `(cart, content_type, object_id)`.
- Added `__contains__`, `__len__` to `Cart`.
- Added `unique_count()`, `checkout()` methods.
- `cart_serializable()` now includes `unit_price`.
- `update()` no longer silently ignores `unit_price=None` — only updates price when explicitly provided.
- Added `InvalidQuantity` exception; `add()` and `update()` now validate quantities.
- Added `clean_carts` management command.
- Full test suite added.
