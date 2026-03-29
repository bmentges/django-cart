# Changelog

All notable changes to this project will be documented in this file.

## v2.2.13

- Separate SonarCloud analysis into dedicated job that runs only on master/main branch pushes (not on PRs or tags)
- Publish job now depends only on test job, not on SonarCloud

## v2.2.12

- Update Changelog section in README.md with all tags from v2.0.0 to v2.2.11

## v2.2.11

- Fix SonarCloud coverage path issue - add step to replace GitHub workspace paths in coverage.xml

## v2.2.10

- (tag only)

## v2.2.9

- Add sonar-project.properties for SonarCloud configuration
- Fix SonarCloud CI integration

## v2.2.8

- Fix SonarCloud action inputs in CI workflow

## v2.2.7

- Fix SonarCloud configuration in CI - pass SONAR_PROJECT_KEY and SONAR_ORGANIZATION

## v2.2.6

- Add SonarCloud integration to CI workflow

## v2.2.5

- Remove unused tests placeholder file (cart/tests.py)
- 100% code coverage achieved

## v2.2.4

- Add coverage tool to dev dependencies
- Create .coveragerc configuration
- Add README section for running code coverage
- Add 11 admin tests covering CartAdmin and ItemInline
- Add 18 new tests for edge cases
- Test count increased from 63 to 92
- Code coverage increased to 79%

## v2.2.3

- Fixing tag (version bump)

## v2.2.2

- Replace deprecated get_object_for_this_type with model_class().objects.get()
- Remove total_price from ItemInline.readonly_fields (computed property optimization)

## v2.2.1

- Fix ContentType lookup for proxy model support - use product._meta.model instead of type(product)

## v2.2.0

- Refactor test infrastructure
- Remove FakeProduct model from cart migration
- Create dedicated test_app with FakeProduct model
- Add fixture file with sample test products

## v2.1.0

- Fix race conditions in Cart.add() and Cart.update() with atomic transactions
- Add CartAtomicTest with 6 tests for atomic behavior

## v2.0.0

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
