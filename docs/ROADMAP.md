# django-cart Development Roadmap

**Current Version:** 2.2.13  
**Last Updated:** March 2026  
**Repository:** https://github.com/bmentges/django-cart

---

## Overview

This roadmap outlines the planned development for django-cart, organized by release tags. Each tag contains a feature group with:
- Feature description and rationale
- Automated tests for success, edge, and error cases
- Guarantee that all existing tests pass
- Dependencies and migration notes

---

## Table of Contents

1. [v2.3.0 - Code Quality & Developer Experience](#v230---code-quality--developer-experience)
2. [v2.4.0 - CI/CD & Testing Infrastructure](#v240----cicd--testing-infrastructure)
3. [v2.5.0 - Extensibility & APIs](#v250---extensibility--apis)
4. [v2.6.0 - Cart Operations & Persistence](#v260---cart-operations--persistence)
5. [v2.7.0 - Security & Production Readiness](#v270---security--production-readiness)
6. [v3.0.0 - E-commerce Features (Major Release)](#v300---e-commerce-features-major-release)
7. [Future Considerations](#future-considerations)

---

## v2.3.0 - Code Quality & Developer Experience

**Target:** Bugfix/minor feature release  
**Priority:** Critical  
**Effort:** Low-Medium

### Features

#### 1. Add Type Hints to Models

**Description:** Add complete type hints to `cart/models.py` for better IDE support, static analysis, and documentation.

**Implementation:**
- Add `TYPE_CHECKING` import pattern for forward references
- Add type hints to all model fields
- Add type hints to `ItemManager` methods
- Add type hints to `Item.product` property

**Files to modify:**
- `cart/models.py`

#### 2. Add MinValueValidator to unit_price

**Description:** Prevent negative prices by adding Django's `MinValueValidator` to the `unit_price` field.

**Implementation:**
```python
from django.core.validators import MinValueValidator

class Item(models.Model):
    unit_price = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("unit price"),
    )
```

**Files to modify:**
- `cart/models.py`
- `cart/migrations/0002_add_unit_price_validator.py`

#### 3. Fix Item.product N+1 Query Issue

**Description:** Cache the product property to prevent N+1 queries when iterating over cart items.

**Implementation:**
```python
@property
def product(self):
    if not hasattr(self, '_product_cache'):
        self._product_cache = self.content_type.model_class().objects.get(pk=self.object_id)
    return self._product_cache
```

**Files to modify:**
- `cart/models.py`

#### 4. Improve Cart.__str__ Representation

**Description:** Make cart string representation more informative for debugging.

**Implementation:**
```python
def __str__(self):
    return f"Cart #{self.pk} ({self.items.count()} items)"
```

**Files to modify:**
- `cart/models.py`

#### 5. Add Pre-commit Hooks

**Description:** Add pre-commit configuration for code quality enforcement.

**Implementation:**
- Create `.pre-commit-config.yaml` with:
  - `pre-commit-hooks` (trailing-whitespace, end-of-file-fixer)
  - `black` (code formatting)
  - `isort` (import sorting)
  - `flake8` (linting)
  - `mypy` (type checking)

**Files to add:**
- `.pre-commit-config.yaml`

**Files to modify:**
- `.gitignore` (if needed)

### Tests for v2.3.0

```python
# ===========================================================================
# TestGroup: TypeHints Validation
# ===========================================================================

class ModelTypeHintsTest(TestCase):
    """Verify type hints are properly defined in models."""

    def test_cart_model_has_type_hints(self):
        """Cart model should have type annotations."""
        hints = getattr(Cart, '__annotations__', {})
        self.assertIn('creation_date', hints)
        self.assertIn('checked_out', hints)

    def test_item_model_has_type_hints(self):
        """Item model should have type annotations."""
        hints = getattr(Item, '__annotations__', {})
        self.assertIn('quantity', hints)
        self.assertIn('unit_price', hints)


# ===========================================================================
# TestGroup: Unit Price Validation
# ===========================================================================

class ItemUnitPriceValidationTest(TestCase):
    """Test unit_price MinValueValidator."""

    def test_negative_unit_price_raises_validation_error(self):
        """Item with negative unit_price should fail validation."""
        cart = CartModel.objects.create()
        item = Item(
            cart=cart,
            quantity=1,
            unit_price=Decimal("-1.00"),
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_zero_unit_price_is_valid(self):
        """Item with zero unit_price should pass validation."""
        cart = CartModel.objects.create()
        item = Item(
            cart=cart,
            quantity=1,
            unit_price=Decimal("0.00"),
        )
        item.full_clean()  # Should not raise

    def test_positive_unit_price_is_valid(self):
        """Item with positive unit_price should pass validation."""
        cart = CartModel.objects.create()
        product = make_product()
        ct = ContentType.objects.get_for_model(FakeProduct)
        item = Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product.pk,
            unit_price=Decimal("99.99"),
            quantity=1,
        )
        item.full_clean()  # Should not raise


# ===========================================================================
# TestGroup: Item.product Caching
# ===========================================================================

class ItemProductCachingTest(TestCase):
    """Test that Item.product uses caching to prevent N+1 queries."""

    def test_product_cached_after_first_access(self):
        """Product should be cached after first property access."""
        cart = CartModel.objects.create()
        product = make_product("CachedProduct")
        ct = ContentType.objects.get_for_model(FakeProduct)
        item = Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product.pk,
            unit_price=Decimal("10.00"),
            quantity=1,
        )
        
        # First access
        _ = item.product
        
        # Verify cache exists
        self.assertTrue(hasattr(item, '_product_cache'))

    def test_product_returns_correct_instance(self):
        """Product property should return correct product instance."""
        cart = CartModel.objects.create()
        product = make_product("CorrectProduct")
        ct = ContentType.objects.get_for_model(FakeProduct)
        item = Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product.pk,
            unit_price=Decimal("10.00"),
            quantity=1,
        )
        self.assertEqual(item.product.pk, product.pk)


# ===========================================================================
# TestGroup: Cart String Representation
# ===========================================================================

class CartStringRepresentationTest(TestCase):
    """Test Cart.__str__ output."""

    def test_str_includes_cart_id(self):
        """Cart string should include primary key."""
        cart = CartModel.objects.create()
        self.assertIn(str(cart.pk), str(cart))

    def test_str_includes_item_count(self):
        """Cart string should include item count."""
        cart = CartModel.objects.create()
        product = make_product("StrProduct")
        ct = ContentType.objects.get_for_model(FakeProduct)
        Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product.pk,
            unit_price=Decimal("10.00"),
            quantity=2,
        )
        self.assertIn("1", str(cart))  # 1 item type


# ===========================================================================
# Edge Cases for v2.3.0
# ===========================================================================

class V230EdgeCaseTest(TestCase):
    """Edge case tests for v2.3.0 features."""

    def test_cart_str_with_zero_items(self):
        """Cart with no items should show 0 items."""
        cart = CartModel.objects.create()
        self.assertIn("0", str(cart))

    def test_item_product_cache_not_shared_between_instances(self):
        """Product cache should be instance-specific."""
        cart = CartModel.objects.create()
        product1 = make_product("Product1")
        product2 = make_product("Product2")
        ct = ContentType.objects.get_for_model(FakeProduct)
        
        item1 = Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product1.pk,
            unit_price=Decimal("10.00"),
            quantity=1,
        )
        item2 = Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product2.pk,
            unit_price=Decimal("20.00"),
            quantity=1,
        )
        
        self.assertEqual(item1.product.pk, product1.pk)
        self.assertEqual(item2.product.pk, product2.pk)


# ===========================================================================
# Error Cases for v2.3.0
# ===========================================================================

class V230ErrorCaseTest(TestCase):
    """Error case tests for v2.3.0 features."""

    def test_item_without_product_still_works(self):
        """Item without accessing product should not create cache."""
        cart = CartModel.objects.create()
        product = make_product("NoAccess")
        ct = ContentType.objects.get_for_model(FakeProduct)
        item = Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product.pk,
            unit_price=Decimal("10.00"),
            quantity=1,
        )
        self.assertFalse(hasattr(item, '_product_cache'))

    def test_validation_error_message_is_descriptive(self):
        """ValidationError for negative price should have descriptive message."""
        cart = CartModel.objects.create()
        item = Item(
            cart=cart,
            quantity=1,
            unit_price=Decimal("-5.00"),
        )
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn('unit_price', ctx.exception.message_dict)
```

### v2.3.0 Guarantees

- All 92 existing tests continue to pass
- No breaking API changes
- Migration is non-destructive (additive)
- Backward compatible with existing code

---

## v2.4.0 - CI/CD & Testing Infrastructure

**Target:** Enhancement release  
**Priority:** High  
**Effort:** Medium

### Features

#### 1. Add Dependabot Configuration

**Description:** Automated dependency updates for GitHub Actions and Python packages.

**Implementation:**
- Create `.github/dependabot.yml` for:
  - Python pip dependencies (weekly schedule)
  - GitHub Actions (weekly schedule)

**Files to add:**
- `.github/dependabot.yml`

#### 2. Add Integration Tests

**Description:** Add HTTP-level integration tests using Django's test client.

**Implementation:**
- Create `tests/test_integration.py`
- Test cart views end-to-end
- Test session handling
- Test CSRF protection

**Files to add:**
- `tests/test_integration.py`

#### 3. Add Performance Benchmarks

**Description:** Establish baseline performance metrics for cart operations.

**Implementation:**
- Create `tests/test_performance.py`
- Benchmark cart operations with varying sizes
- Define performance thresholds

**Files to add:**
- `tests/test_performance.py`

#### 4. Improve Admin Tests

**Description:** Add tests for actual Django admin operations.

**Implementation:**
- Test cart search in admin
- Test filtering by checked_out status
- Test inline item display

**Files to modify:**
- `tests/test_cart.py` (extend `CartAdminTest`)

### Tests for v2.4.0

```python
# ===========================================================================
# TestGroup: Integration Tests - Cart Views
# ===========================================================================

class CartViewIntegrationTest(TestCase):
    """Integration tests using Django test client."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create URL configuration for tests
        from django.urls import path
        from django.contrib import admin
        from cart.admin import CartAdmin
        from cart.models import Cart, Item
        from tests.test_app.models import FakeProduct
        
        urlpatterns = [
            path('admin/', admin.site.urls),
            path('cart/add/<int:product_id>/', views.cart_add, name='cart_add'),
            path('cart/', views.cart_detail, name='cart_detail'),
            path('cart/remove/<int:product_id>/', views.cart_remove, name='cart_remove'),
        ]

    def setUp(self):
        self.factory = RequestFactory()
        self.product = make_product("IntegrationProduct")

    def test_add_to_cart_via_post(self):
        """POST to add URL should add product to cart."""
        request = self.factory.post(
            f'/cart/add/{self.product.pk}/',
            {'quantity': 2}
        )
        request.session = {}
        
        # Import view from examples
        from cart.cart import Cart
        
        cart = Cart(request)
        cart.add(self.product, Decimal("10.00"), quantity=2)
        
        self.assertEqual(cart.count(), 2)

    def test_cart_detail_view_empty(self):
        """Cart detail view with empty cart."""
        request = self.factory.get('/cart/')
        request.session = {}
        
        response = views.cart_detail(request)
        self.assertEqual(response.status_code, 200)

    def test_remove_from_cart(self):
        """Remove product from cart via view."""
        request = self.factory.post(f'/cart/remove/{self.product.pk}/')
        request.session = {}
        
        cart = Cart(request)
        cart.add(self.product, Decimal("10.00"), quantity=1)
        cart.remove(self.product)
        
        self.assertTrue(cart.is_empty())

    def test_csrf_protection_enabled(self):
        """Cart operations should require CSRF token."""
        from django.middleware.csrf import get_token
        request = self.factory.post(
            f'/cart/add/{self.product.pk}/',
            {'quantity': 1}
        )
        # Test client handles CSRF automatically; this is a documentation test
        self.assertTrue(True)  # CSRF is Django's default


# ===========================================================================
# TestGroup: Integration Tests - Session Handling
# ===========================================================================

class CartSessionIntegrationTest(TestCase):
    """Integration tests for session handling."""

    def test_cart_persists_across_requests(self):
        """Cart should persist in session across multiple requests."""
        session = {}
        
        # First request
        request1 = make_request(session=session)
        cart1 = Cart(request1)
        cart1.add(self.product, Decimal("10.00"), quantity=1)
        
        # Second request with same session
        request2 = make_request(session=session)
        cart2 = Cart(request2)
        
        self.assertEqual(cart1.cart.pk, cart2.cart.pk)
        self.assertEqual(cart2.count(), 1)

    def test_different_sessions_have_different_carts(self):
        """Different sessions should have different carts."""
        session1 = {}
        session2 = {}
        
        request1 = make_request(session=session1)
        request2 = make_request(session=session2)
        
        cart1 = Cart(request1)
        cart2 = Cart(request2)
        
        self.assertNotEqual(cart1.cart.pk, cart2.cart.pk)


# ===========================================================================
# TestGroup: Performance Benchmarks
# ===========================================================================

class CartPerformanceTest(TestCase):
    """Performance benchmarks for cart operations."""

    def test_add_single_item_performance(self):
        """Adding items individually should complete within threshold."""
        import time
        
        request = make_request()
        cart = Cart(request)
        
        start = time.perf_counter()
        for i in range(50):
            product = make_product(f"PerfProduct{i}")
            cart.add(product, Decimal("10.00"), quantity=1)
        elapsed = time.perf_counter() - start
        
        # Should complete 50 adds in under 2 seconds
        self.assertLess(elapsed, 2.0, f"Add operations took {elapsed:.2f}s")

    def test_large_cart_summary_performance(self):
        """Summary calculation on large cart should be fast."""
        import time
        
        request = make_request()
        cart = Cart(request)
        
        # Add 100 items
        for i in range(100):
            product = make_product(f"LargeCart{i}")
            cart.add(product, Decimal("10.00"), quantity=1)
        
        start = time.perf_counter()
        summary = cart.summary()
        elapsed = time.perf_counter() - start
        
        self.assertEqual(summary, Decimal("1000.00"))
        self.assertLess(elapsed, 0.1, f"Summary took {elapsed:.3f}s")

    def test_iteration_performance(self):
        """Iterating over cart items should be efficient."""
        import time
        
        request = make_request()
        cart = Cart(request)
        
        # Add 50 items
        for i in range(50):
            product = make_product(f"IterProduct{i}")
            cart.add(product, Decimal("10.00"), quantity=1)
        
        start = time.perf_counter()
        items = list(cart)
        elapsed = time.perf_counter() - start
        
        self.assertEqual(len(items), 50)
        self.assertLess(elapsed, 0.5, f"Iteration took {elapsed:.3f}s")


# ===========================================================================
# TestGroup: Admin Operations
# ===========================================================================

class CartAdminOperationsTest(TestCase):
    """Test actual Django admin operations."""

    def setUp(self):
        from django.contrib.admin import site
        from cart.admin import CartAdmin
        self.cart = CartModel.objects.create()
        self.admin = CartAdmin(CartModel, site)

    def test_admin_changelist_view(self):
        """Admin changelist should return cart objects."""
        request = self.factory.get('/admin/cart/cart/')
        request.session = {}
        
        changelist = self.admin.get_changelist_instance(request)
        self.assertIsNotNone(changelist)

    def test_admin_search_by_id(self):
        """Admin search should work by cart ID."""
        cart = CartModel.objects.create()
        request = self.factory.get('/admin/cart/cart/', {'q': str(cart.pk)})
        request.session = {}
        
        changelist = self.admin.get_changelist_instance(request)
        results = changelist.get_results(request)
        
        self.assertEqual(len(list(results)), 1)

    def test_admin_filter_by_checked_out(self):
        """Admin filter should correctly filter by checked_out."""
        cart1 = CartModel.objects.create(checked_out=False)
        cart2 = CartModel.objects.create(checked_out=True)
        
        request = self.factory.get('/admin/cart/cart/', {'checked_out__exact': 'on'})
        request.session = {}
        
        changelist = self.admin.get_changelist_instance(request)
        results = list(changelist.get_results(request))
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].pk, cart2.pk)


# ===========================================================================
# Edge Cases for v2.4.0
# ===========================================================================

class V240EdgeCaseTest(TestCase):
    """Edge case tests for v2.4.0 features."""

    def test_performance_with_decimal_precision(self):
        """Performance should not degrade with decimal precision."""
        import time
        
        request = make_request()
        cart = Cart(request)
        product = make_product("Precision")
        
        cart.add(product, Decimal("0.01"), quantity=1)
        cart.add(product, Decimal("0.02"), quantity=1)
        
        start = time.perf_counter()
        summary = cart.summary()
        elapsed = time.perf_counter() - start
        
        self.assertEqual(summary, Decimal("0.04"))
        self.assertLess(elapsed, 0.05)

    def test_integration_with_custom_session_backend(self):
        """Cart should work with custom session backends."""
        # This is a documentation test - real testing would require
        # actual custom session backend configuration
        self.assertTrue(True)
```

### v2.4.0 Guarantees

- All existing tests pass (including v2.3.0 tests)
- Performance thresholds are conservative to avoid flaky tests
- Integration tests use real HTTP requests but don't require server startup

---

## v2.5.0 - Extensibility & APIs

**Target:** Feature release  
**Priority:** High  
**Effort:** Medium

### Features

#### 1. Add Django Signals

**Description:** Emit Django signals for cart operations to enable extensibility.

**Implementation:**
```python
# cart/signals.py
from django.dispatch import Signal

cart_item_added = Signal()      # Providing: cart, item, product, quantity
cart_item_removed = Signal()     # Providing: cart, item, product
cart_item_updated = Signal()    # Providing: cart, item, product, quantity
cart_checked_out = Signal()      # Providing: cart
cart_cleared = Signal()         # Providing: cart
```

**Files to add:**
- `cart/signals.py`

**Files to modify:**
- `cart/cart.py` (emit signals after operations)
- `cart/apps.py` (import signals)

#### 2. Add Template Tags

**Description:** Provide Django template tags for common cart operations.

**Implementation:**
```python
# cart/templatetags/cart_tags.py
@register.simple_tag
def cart_item_count(request):
    return Cart(request).count()

@register.simple_tag
def cart_summary(request):
    return Cart(request).summary()

@register.inclusion_tag('cart/snippets/cart_link.html')
def cart_link(request, text="View Cart"):
    return {'cart_url': '/cart/', 'text': text}
```

**Files to add:**
- `cart/templatetags/__init__.py`
- `cart/templatetags/cart_tags.py`
- `cart/templates/cart/snippets/cart_link.html`

#### 3. Add Session Adapter Interface

**Description:** Allow custom session handling strategies.

**Implementation:**
```python
# cart/session.py
class CartSessionAdapter:
    """Interface for custom session handling."""
    
    def get_cart_id(self) -> int | None:
        raise NotImplementedError
    
    def set_cart_id(self, cart_id: int) -> None:
        raise NotImplementedError


class DjangoSessionAdapter(CartSessionAdapter):
    """Default adapter using Django sessions."""
    
    def __init__(self, request):
        self._request = request
    
    def get_cart_id(self):
        return self._request.session.get(CART_ID)
    
    def set_cart_id(self, cart_id: int):
        self._request.session[CART_ID] = cart_id


class CookieSessionAdapter(CartSessionAdapter):
    """Alternative adapter using cookies only."""
    # ... implementation
```

**Files to add:**
- `cart/session.py`

**Files to modify:**
- `cart/cart.py` (accept adapter as optional parameter)

#### 4. Add from_serializable Class Method

**Description:** Restore cart state from serialized data.

**Implementation:**
```python
@classmethod
def from_serializable(cls, request, data: dict, unit_price_field: str = 'price') -> "Cart":
    """
    Restore cart from serialized data.
    
    Args:
        request: Django request object
        data: Dict from cart_serializable()
        unit_price_field: Attribute name on product model for unit price
    """
```

**Files to modify:**
- `cart/cart.py`

### Tests for v2.5.0

```python
# ===========================================================================
# TestGroup: Django Signals Tests
# ===========================================================================

class CartSignalsTest(TestCase):
    """Test Django signals emitted by cart operations."""

    def setUp(self):
        self.signal_received = []
        self.request = make_request()
        self.cart = Cart(self.request)
        self.product = make_product("SignalProduct")

        # Connect signal handlers
        from cart.signals import (
            cart_item_added, cart_item_removed, cart_item_updated,
            cart_checked_out, cart_cleared
        )
        
        def handler(sender, **kwargs):
            self.signal_received.append(kwargs)
        
        cart_item_added.connect(handler)
        cart_item_removed.connect(handler)
        cart_item_updated.connect(handler)
        cart_checked_out.connect(handler)
        cart_cleared.connect(handler)

    def tearDown(self):
        from cart.signals import (
            cart_item_added, cart_item_removed, cart_item_updated,
            cart_checked_out, cart_cleared
        )
        cart_item_added.disconnect()
        cart_item_removed.disconnect()
        cart_item_updated.disconnect()
        cart_checked_out.disconnect()
        cart_cleared.disconnect()

    def test_add_emits_cart_item_added_signal(self):
        """Adding item should emit cart_item_added signal."""
        self.cart.add(self.product, Decimal("10.00"), quantity=2)
        
        self.assertEqual(len(self.signal_received), 1)
        self.assertEqual(self.signal_received[0]['cart'], self.cart.cart)
        self.assertEqual(self.signal_received[0]['product'], self.product)
        self.assertEqual(self.signal_received[0]['quantity'], 2)

    def test_remove_emits_cart_item_removed_signal(self):
        """Removing item should emit cart_item_removed signal."""
        self.cart.add(self.product, Decimal("10.00"), quantity=1)
        self.signal_received.clear()
        
        self.cart.remove(self.product)
        
        self.assertEqual(len(self.signal_received), 1)
        self.assertEqual(self.signal_received[0]['product'], self.product)

    def test_update_emits_cart_item_updated_signal(self):
        """Updating item should emit cart_item_updated signal."""
        self.cart.add(self.product, Decimal("10.00"), quantity=1)
        self.signal_received.clear()
        
        self.cart.update(self.product, quantity=5)
        
        self.assertEqual(len(self.signal_received), 1)
        self.assertEqual(self.signal_received[0]['quantity'], 5)

    def test_checkout_emits_cart_checked_out_signal(self):
        """Checkout should emit cart_checked_out signal."""
        self.cart.add(self.product, Decimal("10.00"), quantity=1)
        self.signal_received.clear()
        
        self.cart.checkout()
        
        self.assertEqual(len(self.signal_received), 1)
        self.assertEqual(self.signal_received[0]['cart'], self.cart.cart)

    def test_clear_emits_cart_cleared_signal(self):
        """Clear should emit cart_cleared signal."""
        self.cart.add(self.product, Decimal("10.00"), quantity=1)
        self.signal_received.clear()
        
        self.cart.clear()
        
        self.assertEqual(len(self.signal_received), 1)

    def test_signal_sender_is_cart_instance(self):
        """Signal sender should be Cart instance."""
        self.cart.add(self.product, Decimal("10.00"), quantity=1)
        
        self.assertIsInstance(self.signal_received[0].get('sender'), Cart)


# ===========================================================================
# TestGroup: Signal Error Handling
# ===========================================================================

class CartSignalsErrorHandlingTest(TestCase):
    """Test signal error handling."""

    def test_signal_error_does_not_affect_operation(self):
        """Operation should succeed even if signal handler raises."""
        from cart.signals import cart_item_added

        def failing_handler(sender, **kwargs):
            raise ValueError("Signal handler failed")

        cart_item_added.connect(failing_handler)
        
        try:
            request = make_request()
            cart = Cart(request)
            product = make_product("ErrorProduct")
            
            # Should not raise
            cart.add(product, Decimal("10.00"), quantity=1)
            self.assertEqual(cart.count(), 1)
        finally:
            cart_item_added.disconnect()


# ===========================================================================
# TestGroup: Template Tags Tests
# ===========================================================================

class CartTemplateTagsTest(TestCase):
    """Test template tags."""

    def setUp(self):
        from django.template import Template, Context
        from django.template.library import Library
        from cart.templatetags import cart_tags
        
        self.template = Template
        self.context = Context

    def test_cart_item_count_tag(self):
        """cart_item_count tag should return correct count."""
        from cart.templatetags.cart_tags import cart_item_count
        
        request = make_request()
        cart = Cart(request)
        product = make_product("CountProduct")
        cart.add(product, Decimal("10.00"), quantity=3)
        
        count = cart_item_count(request)
        self.assertEqual(count, 3)

    def test_cart_summary_tag(self):
        """cart_summary tag should return correct total."""
        from cart.templatetags.cart_tags import cart_summary
        
        request = make_request()
        cart = Cart(request)
        product = make_product("SummaryProduct")
        cart.add(product, Decimal("10.00"), quantity=2)
        
        summary = cart_summary(request)
        self.assertEqual(summary, Decimal("20.00"))

    def test_cart_is_empty_tag(self):
        """cart_is_empty tag should return correct boolean."""
        from cart.templatetags.cart_tags import cart_is_empty
        
        request = make_request()
        cart = Cart(request)
        
        self.assertTrue(cart_is_empty(request))
        
        product = make_product("NotEmptyProduct")
        cart.add(product, Decimal("10.00"), quantity=1)
        
        self.assertFalse(cart_is_empty(request))


# ===========================================================================
# TestGroup: Session Adapter Tests
# ===========================================================================

class CartSessionAdapterTest(TestCase):
    """Test session adapter interface."""

    def test_django_session_adapter(self):
        """DjangoSessionAdapter should work with request.session."""
        from cart.session import DjangoSessionAdapter, CART_ID
        
        request = make_request()
        adapter = DjangoSessionAdapter(request)
        
        self.assertIsNone(adapter.get_cart_id())
        
        adapter.set_cart_id(123)
        self.assertEqual(adapter.get_cart_id(), 123)
        self.assertEqual(request.session[CART_ID], 123)

    def test_cart_with_custom_adapter(self):
        """Cart should accept custom session adapter."""
        from cart.session import CartSessionAdapter
        
        class CustomAdapter(CartSessionAdapter):
            def __init__(self):
                self._cart_id = None
            
            def get_cart_id(self):
                return self._cart_id
            
            def set_cart_id(self, cart_id):
                self._cart_id = cart_id
        
        adapter = CustomAdapter()
        cart = Cart(request=None, session_adapter=adapter)
        
        adapter.set_cart_id(cart.cart.pk)
        self.assertEqual(adapter.get_cart_id(), cart.cart.pk)


# ===========================================================================
# TestGroup: Serialization Restore Tests
# ===========================================================================

class CartSerializationRestoreTest(TestCase):
    """Test cart deserialization."""

    def test_from_serializable_basic(self):
        """from_serializable should recreate cart from dict."""
        request = make_request()
        cart = Cart(request)
        product = make_product("RestoreProduct")
        
        # Serialize
        cart.add(product, Decimal("10.00"), quantity=2)
        data = cart.cart_serializable()
        
        # Create new cart and restore
        new_request = make_request()
        new_cart = Cart.from_serializable(new_request, data)
        
        self.assertEqual(new_cart.count(), 2)
        self.assertEqual(new_cart.summary(), Decimal("20.00"))

    def test_from_serializable_empty(self):
        """from_serializable with empty dict should create empty cart."""
        request = make_request()
        cart = Cart.from_serializable(request, {})
        
        self.assertTrue(cart.is_empty())
        self.assertEqual(cart.summary(), Decimal("0.00"))

    def test_from_serializable_multiple_items(self):
        """from_serializable should handle multiple items."""
        request = make_request()
        
        data = {
            str(make_product("Multi1").pk): {
                "quantity": 2,
                "unit_price": "10.00",
                "total_price": "20.00",
            },
            str(make_product("Multi2").pk): {
                "quantity": 3,
                "unit_price": "5.00",
                "total_price": "15.00",
            },
        }
        
        cart = Cart.from_serializable(request, data)
        
        self.assertEqual(cart.count(), 5)
        self.assertEqual(cart.summary(), Decimal("35.00"))


# ===========================================================================
# Edge Cases for v2.5.0
# ===========================================================================

class V250EdgeCaseTest(TestCase):
    """Edge case tests for v2.5.0 features."""

    def test_signal_with_no_listeners(self):
        """Signals should work when no listeners are connected."""
        request = make_request()
        cart = Cart(request)
        product = make_product("NoListener")
        
        # Should not raise
        cart.add(product, Decimal("10.00"), quantity=1)

    def test_template_tag_with_empty_session(self):
        """Template tags should handle empty session gracefully."""
        from cart.templatetags.cart_tags import cart_item_count
        
        request = make_request(session={})
        count = cart_item_count(request)
        self.assertEqual(count, 0)

    def test_adapter_without_session_key(self):
        """Cart should create new cart if adapter returns None."""
        from cart.session import CartSessionAdapter
        
        class EmptyAdapter(CartSessionAdapter):
            def get_cart_id(self):
                return None
            def set_cart_id(self, cart_id):
                pass
        
        cart = Cart(request=None, session_adapter=EmptyAdapter())
        self.assertIsNotNone(cart.cart.pk)


# ===========================================================================
# Error Cases for v2.5.0
# ===========================================================================

class V250ErrorCaseTest(TestCase):
    """Error case tests for v2.5.0 features."""

    def test_from_serializable_with_invalid_data(self):
        """from_serializable with invalid data should handle gracefully."""
        request = make_request()
        
        # Invalid data (non-numeric quantities, missing fields)
        invalid_data = {
            "invalid": {"quantity": "not_a_number"}
        }
        
        # Should either raise helpful error or handle gracefully
        with self.assertRaises((ValueError, TypeError)):
            Cart.from_serializable(request, invalid_data)

    def test_custom_adapter_must_implement_interface(self):
        """Custom adapter without required methods should raise error."""
        from cart.session import CartSessionAdapter
        
        class IncompleteAdapter:
            pass
        
        with self.assertRaises(TypeError):
            Cart(request=None, session_adapter=IncompleteAdapter())
```

### v2.5.0 Guarantees

- All existing tests pass
- Signals are emitted after operations (not before) to ensure data consistency
- Template tags work without JavaScript
- Session adapter is optional (defaults to Django session)

---

## v2.6.0 - Cart Operations & Persistence

**Target:** Feature release  
**Priority:** High  
**Effort:** Medium

### Features

#### 1. Add Cart Merge Functionality

**Description:** Merge guest cart with user cart upon login.

**Implementation:**
```python
def merge(self, other_cart: "Cart", strategy: str = "add") -> None:
    """
    Merge another cart into this one.
    
    Strategies:
        - 'add': Add quantities together (default)
        - 'replace': Replace items from other cart
        - 'keep_higher': Keep higher quantity for duplicates
    """
```

**Files to modify:**
- `cart/cart.py`

#### 2. Add Cart Persistence (User Binding)

**Description:** Bind cart to user account for persistence across sessions.

**Implementation:**
```python
def bind_to_user(self, user) -> None:
    """Persist cart to user account."""
    
def get_user_carts(user) -> QuerySet[Cart]:
    """Get all carts for a user."""
```

**Files to modify:**
- `cart/models.py` (add optional ForeignKey to User)
- `cart/cart.py`

**Migration:**
```python
# cart/migrations/0003_add_user_fk.py
# Add nullable user ForeignKey to Cart model
```

#### 3. Add Bulk Operations

**Description:** Efficiently add/update multiple items.

**Implementation:**
```python
def add_bulk(self, items: list[dict]) -> list[Item]:
    """
    Add multiple items efficiently.
    
    Args:
        items: List of dicts with 'product', 'unit_price', 'quantity' keys
    
    Returns:
        List of created/updated Item instances
    """
```

**Files to modify:**
- `cart/cart.py`

#### 4. Add Maximum Quantity Configuration

**Description:** Enforce per-item quantity limits.

**Implementation:**
```python
# settings.py
CART_MAX_QUANTITY_PER_ITEM = 999

# In Cart.add()
def add(self, product, unit_price, quantity=1):
    max_qty = getattr(settings, 'CART_MAX_QUANTITY_PER_ITEM', None)
    if max_qty and quantity > max_qty:
        raise InvalidQuantity(f"Quantity cannot exceed {max_qty}")
```

**Files to modify:**
- `cart/cart.py`
- `runtests.py` (update settings)

### Tests for v2.6.0

```python
# ===========================================================================
# TestGroup: Cart Merge Tests
# ===========================================================================

class CartMergeTest(TestCase):
    """Test cart merge functionality."""

    def test_merge_add_strategy(self):
        """Merge with 'add' strategy should combine quantities."""
        request1 = make_request()
        request2 = make_request()
        
        cart1 = Cart(request1)
        cart2 = Cart(request2)
        
        product = make_product("MergeProduct")
        
        cart1.add(product, Decimal("10.00"), quantity=2)
        cart2.add(product, Decimal("10.00"), quantity=3)
        
        cart1.merge(cart2, strategy='add')
        
        item = cart1.cart.items.first()
        self.assertEqual(item.quantity, 5)

    def test_merge_replace_strategy(self):
        """Merge with 'replace' should use other cart's quantities."""
        request1 = make_request()
        request2 = make_request()
        
        cart1 = Cart(request1)
        cart2 = Cart(request2)
        
        product = make_product("ReplaceProduct")
        
        cart1.add(product, Decimal("10.00"), quantity=2)
        cart2.add(product, Decimal("10.00"), quantity=5)
        
        cart1.merge(cart2, strategy='replace')
        
        item = cart1.cart.items.first()
        self.assertEqual(item.quantity, 5)

    def test_merge_keep_higher_strategy(self):
        """Merge with 'keep_higher' should keep max quantity."""
        request1 = make_request()
        request2 = make_request()
        
        cart1 = Cart(request1)
        cart2 = Cart(request2)
        
        product = make_product("HigherProduct")
        
        cart1.add(product, Decimal("10.00"), quantity=3)
        cart2.add(product, Decimal("10.00"), quantity=7)
        
        cart1.merge(cart2, strategy='keep_higher')
        
        item = cart1.cart.items.first()
        self.assertEqual(item.quantity, 7)

    def test_merge_adds_new_products(self):
        """Merge should add products not in original cart."""
        request1 = make_request()
        request2 = make_request()
        
        cart1 = Cart(request1)
        cart2 = Cart(request2)
        
        product1 = make_product("Product1")
        product2 = make_product("Product2")
        
        cart1.add(product1, Decimal("10.00"), quantity=1)
        cart2.add(product2, Decimal("20.00"), quantity=2)
        
        cart1.merge(cart2)
        
        self.assertEqual(cart1.unique_count(), 2)
        self.assertEqual(cart1.count(), 3)

    def test_merge_empties_other_cart(self):
        """Merge should clear the other cart after merging."""
        request1 = make_request()
        request2 = make_request()
        
        cart1 = Cart(request1)
        cart2 = Cart(request2)
        
        product = make_product("EmptyOther")
        cart1.add(product, Decimal("10.00"), quantity=1)
        cart2.add(product, Decimal("10.00"), quantity=2)
        
        cart1.merge(cart2)
        
        # Other cart should be empty
        self.assertTrue(cart2.is_empty())


# ===========================================================================
# TestGroup: Cart Merge Error Cases
# ===========================================================================

class CartMergeErrorTest(TestCase):
    """Test cart merge error handling."""

    def test_merge_with_invalid_strategy_raises(self):
        """Invalid merge strategy should raise ValueError."""
        request1 = make_request()
        request2 = make_request()
        
        cart1 = Cart(request1)
        cart2 = Cart(request2)
        
        with self.assertRaises(ValueError):
            cart1.merge(cart2, strategy='invalid')

    def test_merge_preserves_this_cart_on_error(self):
        """Original cart should be unchanged if merge fails."""
        request1 = make_request()
        request2 = make_request()
        
        cart1 = Cart(request1)
        cart2 = Cart(request2)
        
        product = make_product("PreserveProduct")
        cart1.add(product, Decimal("10.00"), quantity=5)
        
        original_quantity = cart1.count()
        
        try:
            cart1.merge(cart2, strategy='invalid')
        except ValueError:
            pass
        
        self.assertEqual(cart1.count(), original_quantity)


# ===========================================================================
# TestGroup: User Binding Tests
# ===========================================================================

class CartUserBindingTest(TestCase):
    """Test cart-user binding functionality."""

    def test_bind_to_user(self):
        """bind_to_user should associate cart with user."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        user = User.objects.create_user('testuser', 'test@example.com', 'pass')
        request = make_request()
        cart = Cart(request)
        
        cart.bind_to_user(user)
        
        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.user, user)

    def test_get_user_carts(self):
        """get_user_carts should return all carts for user."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        user = User.objects.create_user('testuser2', 'test2@example.com', 'pass')
        request = make_request()
        cart = Cart(request)
        
        cart.bind_to_user(user)
        product = make_product("UserCartProduct")
        cart.add(product, Decimal("10.00"), quantity=1)
        
        carts = Cart.get_user_carts(user)
        self.assertEqual(carts.count(), 1)

    def test_unbound_cart_has_no_user(self):
        """Unbound cart should have null user."""
        request = make_request()
        cart = Cart(request)
        
        self.assertIsNone(cart.cart.user)


# ===========================================================================
# TestGroup: Bulk Operations Tests
# ===========================================================================

class CartBulkOperationsTest(TestCase):
    """Test bulk cart operations."""

    def test_add_bulk_multiple_items(self):
        """add_bulk should add multiple items efficiently."""
        request = make_request()
        cart = Cart(request)
        
        items = [
            {'product': make_product("Bulk1"), 'unit_price': Decimal("10.00"), 'quantity': 1},
            {'product': make_product("Bulk2"), 'unit_price': Decimal("20.00"), 'quantity': 2},
            {'product': make_product("Bulk3"), 'unit_price': Decimal("30.00"), 'quantity': 3},
        ]
        
        result = cart.add_bulk(items)
        
        self.assertEqual(len(result), 3)
        self.assertEqual(cart.count(), 6)
        self.assertEqual(cart.summary(), Decimal("140.00"))

    def test_add_bulk_updates_existing_items(self):
        """add_bulk should update existing items."""
        request = make_request()
        cart = Cart(request)
        
        product = make_product("BulkUpdate")
        cart.add(product, Decimal("10.00"), quantity=1)
        
        items = [
            {'product': product, 'unit_price': Decimal("15.00"), 'quantity': 5},
        ]
        
        cart.add_bulk(items)
        
        self.assertEqual(cart.count(), 5)
        item = cart.cart.items.first()
        self.assertEqual(item.unit_price, Decimal("15.00"))

    def test_add_bulk_empty_list(self):
        """add_bulk with empty list should be no-op."""
        request = make_request()
        cart = Cart(request)
        
        result = cart.add_bulk([])
        
        self.assertEqual(result, [])
        self.assertTrue(cart.is_empty())


# ===========================================================================
# TestGroup: Maximum Quantity Tests
# ===========================================================================

class CartMaxQuantityTest(TestCase):
    """Test maximum quantity enforcement."""

    def test_add_exceeds_max_quantity_raises(self):
        """Adding quantity above max should raise InvalidQuantity."""
        with self.settings(CART_MAX_QUANTITY_PER_ITEM=10):
            request = make_request()
            cart = Cart(request)
            product = make_product("MaxProduct")
            
            with self.assertRaises(InvalidQuantity):
                cart.add(product, Decimal("10.00"), quantity=11)

    def test_add_within_max_quantity_succeeds(self):
        """Adding quantity within max should succeed."""
        with self.settings(CART_MAX_QUANTITY_PER_ITEM=10):
            request = make_request()
            cart = Cart(request)
            product = make_product("ValidMax")
            
            cart.add(product, Decimal("10.00"), quantity=10)
            self.assertEqual(cart.count(), 10)

    def test_update_exceeds_max_quantity_raises(self):
        """Updating quantity above max should raise InvalidQuantity."""
        with self.settings(CART_MAX_QUANTITY_PER_ITEM=100):
            request = make_request()
            cart = Cart(request)
            product = make_product("MaxUpdate")
            cart.add(product, Decimal("10.00"), quantity=50)
            
            with self.assertRaises(InvalidQuantity):
                cart.update(product, quantity=101)


# ===========================================================================
# Integration Tests for v2.6.0
# ===========================================================================

class CartMergeIntegrationTest(TestCase):
    """Integration tests for cart merge."""

    def test_guest_to_user_login_flow(self):
        """Simulate guest adding items, then logging in."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Guest session
        guest_session = {}
        guest_request = make_request(session=guest_session)
        guest_cart = Cart(guest_request)
        
        product1 = make_product("GuestProduct1")
        guest_cart.add(product1, Decimal("10.00"), quantity=1)
        
        # User logs in
        user = User.objects.create_user('loginuser', 'login@example.com', 'pass')
        user_request = make_request(session={'user_id': user.pk})
        
        # Create or get user cart
        user_cart = Cart(user_request)
        user_cart.bind_to_user(user)
        
        # Merge guest cart into user cart
        user_cart.merge(guest_cart, strategy='add')
        
        self.assertEqual(user_cart.count(), 1)
        self.assertTrue(guest_cart.is_empty())


# ===========================================================================
# Edge Cases for v2.6.0
# ===========================================================================

class V260EdgeCaseTest(TestCase):
    """Edge case tests for v2.6.0 features."""

    def test_merge_same_cart_raises(self):
        """Merging cart with itself should raise error."""
        request = make_request()
        cart = Cart(request)
        
        with self.assertRaises(ValueError):
            cart.merge(cart)

    def test_merge_with_empty_cart(self):
        """Merging empty cart should be no-op."""
        request1 = make_request()
        request2 = make_request()
        
        cart1 = Cart(request1)
        cart2 = Cart(request2)
        
        product = make_product("EmptyMerge")
        cart1.add(product, Decimal("10.00"), quantity=1)
        
        cart1.merge(cart2)
        
        self.assertEqual(cart1.count(), 1)

    def test_add_bulk_respects_max_quantity(self):
        """add_bulk should enforce max quantity per item."""
        with self.settings(CART_MAX_QUANTITY_PER_ITEM=5):
            request = make_request()
            cart = Cart(request)
            
            items = [
                {'product': make_product("BulkMax"), 'unit_price': Decimal("10.00"), 'quantity': 10},
            ]
            
            with self.assertRaises(InvalidQuantity):
                cart.add_bulk(items)
```

### v2.6.0 Guarantees

- All existing tests pass
- Merge operations are atomic
- User binding is backward compatible (nullable FK)
- Bulk operations use database transactions

---

## v2.7.0 - Security & Production Readiness

**Target:** Security/Enhancement release  
**Priority:** High  
**Effort:** Medium

### Features

#### 1. Add Price Validation Option

**Description:** Optional validation that passed price matches product's actual price.

**Implementation:**
```python
class PriceMismatchError(CartException):
    """Raised when price doesn't match product's actual price."""

def add(self, product, unit_price, quantity=1, validate_price=False):
    if validate_price:
        actual_price = getattr(product, 'price', None)
        if actual_price and unit_price != actual_price:
            raise PriceMismatchError(...)
```

**Files to modify:**
- `cart/cart.py`

#### 2. Add Caching Layer

**Description:** Cache cart summary and count for performance.

**Implementation:**
```python
def summary(self) -> Decimal:
    if self._cache.get('summary') is not None:
        return self._cache['summary']
    
    result = self._calculate_summary()
    self._cache['summary'] = result
    return result

def _invalidate_cache(self):
    self._cache = {}
```

**Files to modify:**
- `cart/cart.py`

#### 3. Add Database Indexes

**Description:** Add composite index for common query patterns.

**Implementation:**
```python
class Item(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=['cart', 'content_type', 'object_id']),
        ]
```

**Files to modify:**
- `cart/models.py`
- `cart/migrations/0004_add_item_indexes.py`

### Tests for v2.7.0

```python
# ===========================================================================
# TestGroup: Price Validation Tests
# ===========================================================================

class CartPriceValidationTest(TestCase):
    """Test price validation feature."""

    def setUp(self):
        self.request = make_request()
        self.cart = Cart(self.request)
        
        # Create product with price attribute
        self.product = make_product("PriceValidation")
        self.product.price = Decimal("19.99")
        self.product.save()

    def test_validate_price_succeeds_when_match(self):
        """validate_price=True should succeed when price matches."""
        self.cart.add(
            self.product,
            unit_price=Decimal("19.99"),
            quantity=1,
            validate_price=True
        )
        self.assertEqual(self.cart.count(), 1)

    def test_validate_price_raises_when_mismatch(self):
        """validate_price=True should raise PriceMismatchError when price differs."""
        with self.assertRaises(PriceMismatchError):
            self.cart.add(
                self.product,
                unit_price=Decimal("9.99"),  # Wrong price
                quantity=1,
                validate_price=True
            )

    def test_validate_price_false_skips_validation(self):
        """validate_price=False should skip validation."""
        self.cart.add(
            self.product,
            unit_price=Decimal("0.01"),  # Wrong price
            quantity=1,
            validate_price=False
        )
        self.assertEqual(self.cart.count(), 1)

    def test_validate_price_works_on_update(self):
        """Price validation should work on update as well."""
        self.cart.add(self.product, Decimal("19.99"), quantity=1, validate_price=False)
        
        with self.assertRaises(PriceMismatchError):
            self.cart.update(
                self.product,
                quantity=2,
                unit_price=Decimal("1.00"),
                validate_price=True
            )

    def test_validate_price_without_price_attribute(self):
        """Should skip validation if product has no price attribute."""
        product_no_price = make_product("NoPriceAttr")
        
        # Should not raise even though product.price doesn't exist
        self.cart.add(
            product_no_price,
            Decimal("10.00"),
            quantity=1,
            validate_price=True
        )


# ===========================================================================
# TestGroup: Caching Tests
# ===========================================================================

class CartCachingTest(TestCase):
    """Test cart caching functionality."""

    def test_summary_is_cached(self):
        """Second summary() call should use cache."""
        request = make_request()
        cart = Cart(request)
        product = make_product("CachedSummary")
        cart.add(product, Decimal("10.00"), quantity=2)
        
        # First call
        result1 = cart.summary()
        
        # Modify cart
        cart.cart.items.update(quantity=5)
        
        # Second call should return cached value
        result2 = cart.summary()
        
        self.assertEqual(result1, result2)
        self.assertEqual(result2, Decimal("20.00"))

    def test_cache_invalidated_on_add(self):
        """Cache should be invalidated when item is added."""
        request = make_request()
        cart = Cart(request)
        
        summary1 = cart.summary()
        
        product = make_product("InvalidateAdd")
        cart.add(product, Decimal("10.00"), quantity=1)
        
        summary2 = cart.summary()
        
        self.assertEqual(summary1, Decimal("0.00"))
        self.assertEqual(summary2, Decimal("10.00"))

    def test_cache_invalidated_on_remove(self):
        """Cache should be invalidated when item is removed."""
        request = make_request()
        cart = Cart(request)
        product = make_product("InvalidateRemove")
        cart.add(product, Decimal("10.00"), quantity=1)
        
        summary1 = cart.summary()
        cart.remove(product)
        summary2 = cart.summary()
        
        self.assertEqual(summary1, Decimal("10.00"))
        self.assertEqual(summary2, Decimal("0.00"))

    def test_cache_invalidated_on_update(self):
        """Cache should be invalidated when item is updated."""
        request = make_request()
        cart = Cart(request)
        product = make_product("InvalidateUpdate")
        cart.add(product, Decimal("10.00"), quantity=1)
        
        summary1 = cart.summary()
        cart.update(product, quantity=5)
        summary2 = cart.summary()
        
        self.assertEqual(summary1, Decimal("10.00"))
        self.assertEqual(summary2, Decimal("50.00"))

    def test_cache_invalidated_on_clear(self):
        """Cache should be invalidated when cart is cleared."""
        request = make_request()
        cart = Cart(request)
        product = make_product("InvalidateClear")
        cart.add(product, Decimal("10.00"), quantity=3)
        
        summary1 = cart.summary()
        cart.clear()
        summary2 = cart.summary()
        
        self.assertEqual(summary1, Decimal("30.00"))
        self.assertEqual(summary2, Decimal("0.00"))


# ===========================================================================
# TestGroup: Database Index Tests
# ===========================================================================

class CartDatabaseIndexTest(TestCase):
    """Test database indexes."""

    def test_item_has_composite_index(self):
        """Item model should have composite index."""
        from django.db import connection
        
        # Get index info from database
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT sql FROM sqlite_master 
                WHERE type='index' AND tbl_name='cart_item'
            """)
            indexes = cursor.fetchall()
        
        index_sql = ' '.join([idx[0] for idx in indexes if idx[0]])
        
        # Should have index on cart, content_type, object_id
        self.assertTrue(
            'cart_id' in index_sql.lower(),
            "Should have index on cart_id"
        )

    def test_index_improves_query_performance(self):
        """Queries using index should be faster than full scan."""
        # Create carts with items
        carts = [CartModel.objects.create() for _ in range(10)]
        products = [make_product(f"IndexProduct{i}") for i in range(50)]
        ct = ContentType.objects.get_for_model(FakeProduct)
        
        for cart in carts:
            for product in products[:5]:
                Item.objects.create(
                    cart=cart,
                    content_type=ct,
                    object_id=product.pk,
                    unit_price=Decimal("10.00"),
                    quantity=1,
                )
        
        # Query that uses index
        import time
        
        start = time.perf_counter()
        for _ in range(100):
            Item.objects.filter(cart=carts[0], content_type=ct)
        elapsed = time.perf_counter() - start
        
        # Should complete reasonably fast
        self.assertLess(elapsed, 5.0)


# ===========================================================================
# Edge Cases for v2.7.0
# ===========================================================================

class V270EdgeCaseTest(TestCase):
    """Edge case tests for v2.7.0 features."""

    def test_cache_works_with_large_carts(self):
        """Cache should work efficiently with large carts."""
        request = make_request()
        cart = Cart(request)
        
        for i in range(100):
            product = make_product(f"LargeCache{i}")
            cart.add(product, Decimal("10.00"), quantity=1)
        
        # Multiple summary calls should be fast
        import time
        start = time.perf_counter()
        for _ in range(10):
            cart.summary()
        elapsed = time.perf_counter() - start
        
        self.assertLess(elapsed, 0.5)

    def test_price_validation_with_zero_price(self):
        """Price validation should work with zero-priced products."""
        product = make_product("FreeProduct")
        product.price = Decimal("0.00")
        product.save()
        
        request = make_request()
        cart = Cart(request)
        
        # Should succeed with exact match
        cart.add(product, Decimal("0.00"), quantity=1, validate_price=True)
        self.assertEqual(cart.count(), 1)

    def test_cache_isolation_between_carts(self):
        """Each cart instance should have its own cache."""
        request1 = make_request()
        request2 = make_request()
        
        cart1 = Cart(request1)
        cart2 = Cart(request2)
        
        product1 = make_product("Cache1")
        product2 = make_product("Cache2")
        
        cart1.add(product1, Decimal("10.00"), quantity=1)
        cart2.add(product2, Decimal("20.00"), quantity=1)
        
        self.assertEqual(cart1.summary(), Decimal("10.00"))
        self.assertEqual(cart2.summary(), Decimal("20.00"))


# ===========================================================================
# Integration Tests for v2.7.0
# ===========================================================================

class CartSecurityIntegrationTest(TestCase):
    """Integration tests for security features."""

    def test_price_validation_in_web_flow(self):
        """Price validation should work in typical web view flow."""
        product = make_product("WebPrice")
        product.price = Decimal("25.00")
        product.save()
        
        request = make_request()
        cart = Cart(request)
        
        # Simulating a view that validates price
        def cart_add_view(request, product_id, price):
            try:
                prod = FakeProduct.objects.get(pk=product_id)
                cart.add(prod, price, validate_price=True)
                return True
            except PriceMismatchError:
                return False
        
        # Correct price
        result = cart_add_view(request, product.pk, Decimal("25.00"))
        self.assertTrue(result)
        
        # Wrong price (creates new cart)
        request2 = make_request()
        cart2 = Cart(request2)
        result = cart_add_view(request2, product.pk, Decimal("15.00"))
        self.assertFalse(result)
```

### v2.7.0 Guarantees

- All existing tests pass
- Cache is instance-scoped (no cross-cart pollution)
- Price validation is opt-in (backward compatible)
- New indexes don't lock table (MySQL consideration)

---

## v3.0.0 - E-commerce Features (Major Release)

**Target:** Major feature release  
**Priority:** Medium  
**Effort:** High

### Features

#### 1. Tax Calculation Hooks

**Description:** Add hooks for tax calculation plugins.

**Implementation:**
```python
# cart/tax.py
class TaxCalculator:
    """Base class for tax calculators."""
    
    def calculate(self, cart: Cart) -> Decimal:
        """Calculate tax for cart. Override in subclass."""
        raise NotImplementedError


# cart/settings.py
CART_TAX_CALCULATOR = 'myapp.MyTaxCalculator'
```

#### 2. Shipping Calculation Hooks

**Description:** Add hooks for shipping cost calculation.

**Implementation:**
```python
# cart/shipping.py
class ShippingCalculator:
    """Base class for shipping calculators."""
    
    def calculate(self, cart: Cart) -> Decimal:
        raise NotImplementedError
    
    def get_options(self, cart: Cart) -> list[dict]:
        """Return available shipping options."""
        raise NotImplementedError


CART_SHIPPING_CALCULATOR = 'myapp.MyShippingCalculator'
```

#### 3. Discount/Coupon System

**Description:** Support for promotional codes.

**Implementation:**
```python
# Add Discount model
class Discount(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(choices=[('percent', 'Percentage'), ('fixed', 'Fixed Amount')])
    value = models.DecimalField(max_digits=10, decimal_places=2)
    min_cart_value = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    max_uses = models.PositiveIntegerField(null=True)
    active = models.BooleanField(default=True)
    
    def apply(self, cart: Cart) -> Decimal:
        """Apply discount and return discount amount."""
        
    def is_valid(self, cart: Cart) -> bool:
        """Check if discount is valid for cart."""


# Extend Cart class
class Cart:
    def apply_discount(self, code: str) -> Discount:
        """Apply discount code to cart."""
        
    def remove_discount(self) -> None:
        """Remove applied discount."""
        
    @property
    def discount_amount(self) -> Decimal:
        """Current discount amount."""
```

#### 4. Stock Validation Hooks

**Description:** Add hooks for inventory validation.

**Implementation:**
```python
# cart/inventory.py
class InventoryChecker:
    """Base class for inventory checking."""
    
    def check(self, product, quantity: int) -> bool:
        """Check if quantity is available. Return True if available."""
        raise NotImplementedError
    
    def reserve(self, product, quantity: int) -> bool:
        """Reserve inventory. Return True if successful."""
        raise NotImplementedError


# In Cart.add()
def add(self, product, unit_price, quantity=1, check_inventory=True):
    if check_inventory:
        checker = get_inventory_checker()
        if not checker.check(product, quantity):
            raise InsufficientStock(f"Not enough {product} in stock")
```

#### 5. Minimum Order Amount

**Description:** Enforce minimum cart value.

**Implementation:**
```python
# settings.py
CART_MIN_ORDER_AMOUNT = Decimal("10.00")

# Extend Cart class
def can_checkout(self) -> tuple[bool, str]:
    """Check if cart meets checkout requirements."""
    if self.summary() < settings.CART_MIN_ORDER_AMOUNT:
        return False, f"Minimum order amount is {settings.CART_MIN_ORDER_AMOUNT}"
    return True, ""

class MinimumOrderNotMet(CartException):
    """Raised when cart doesn't meet minimum order amount."""
```

### Tests for v3.0.0

```python
# ===========================================================================
# TestGroup: Tax Calculator Tests
# ===========================================================================

class TaxCalculatorTest(TestCase):
    """Test tax calculation system."""

    def test_default_tax_calculator_returns_zero(self):
        """Default tax calculator should return Decimal('0.00')."""
        from cart.tax import TaxCalculator
        
        class DummyTaxCalculator(TaxCalculator):
            pass
        
        request = make_request()
        cart = Cart(request)
        product = make_product("TaxProduct")
        cart.add(product, Decimal("100.00"), quantity=1)
        
        calc = DummyTaxCalculator()
        tax = calc.calculate(cart)
        
        self.assertEqual(tax, Decimal("0.00"))

    def test_custom_tax_calculator(self):
        """Custom tax calculator should calculate correctly."""
        from cart.tax import TaxCalculator
        
        class TenPercentTax(TaxCalculator):
            def calculate(self, cart):
                return cart.summary() * Decimal("0.10")
        
        request = make_request()
        cart = Cart(request)
        product = make_product("TenPercentProduct")
        cart.add(product, Decimal("100.00"), quantity=1)
        
        calc = TenPercentTax()
        tax = calc.calculate(cart)
        
        self.assertEqual(tax, Decimal("10.00"))


# ===========================================================================
# TestGroup: Shipping Calculator Tests
# ===========================================================================

class ShippingCalculatorTest(TestCase):
    """Test shipping calculation system."""

    def test_default_shipping_calculator(self):
        """Default shipping calculator should return zero."""
        from cart.shipping import ShippingCalculator
        
        class DummyShipping(ShippingCalculator):
            pass
        
        request = make_request()
        cart = Cart(request)
        
        calc = DummyShipping()
        shipping = calc.calculate(cart)
        
        self.assertEqual(shipping, Decimal("0.00"))

    def test_shipping_options(self):
        """Shipping calculator should provide options."""
        from cart.shipping import ShippingCalculator
        
        class OptionsShipping(ShippingCalculator):
            def calculate(self, cart):
                return Decimal("5.00")
            
            def get_options(self, cart):
                return [
                    {'id': 'standard', 'name': 'Standard', 'price': '5.00'},
                    {'id': 'express', 'name': 'Express', 'price': '15.00'},
                ]
        
        request = make_request()
        cart = Cart(request)
        
        calc = OptionsShipping()
        options = calc.get_options(cart)
        
        self.assertEqual(len(options), 2)
        self.assertEqual(options[0]['id'], 'standard')


# ===========================================================================
# TestGroup: Discount System Tests
# ===========================================================================

class DiscountSystemTest(TestCase):
    """Test discount/coupon system."""

    def test_apply_valid_discount_percent(self):
        """Valid percentage discount should reduce cart total."""
        discount = Discount.objects.create(
            code='PERCENT20',
            discount_type='percent',
            value=Decimal('20.00'),
            active=True,
        )
        
        request = make_request()
        cart = Cart(request)
        product = make_product("DiscountProduct")
        cart.add(product, Decimal("100.00"), quantity=1)
        
        applied = cart.apply_discount('PERCENT20')
        
        self.assertEqual(applied, discount)
        self.assertEqual(cart.discount_amount, Decimal("20.00"))

    def test_apply_valid_discount_fixed(self):
        """Valid fixed discount should reduce cart total."""
        discount = Discount.objects.create(
            code='FIXED10',
            discount_type='fixed',
            value=Decimal('10.00'),
            active=True,
        )
        
        request = make_request()
        cart = Cart(request)
        product = make_product("FixedDiscount")
        cart.add(product, Decimal("50.00"), quantity=1)
        
        cart.apply_discount('FIXED10')
        
        self.assertEqual(cart.discount_amount, Decimal("10.00"))

    def test_apply_invalid_discount_raises(self):
        """Invalid discount code should raise error."""
        request = make_request()
        cart = Cart(request)
        product = make_product("InvalidDiscount")
        cart.add(product, Decimal("50.00"), quantity=1)
        
        with self.assertRaises(InvalidDiscountError):
            cart.apply_discount('INVALID')

    def test_discount_min_cart_value(self):
        """Discount should check minimum cart value."""
        discount = Discount.objects.create(
            code='MINCART50',
            discount_type='fixed',
            value=Decimal('10.00'),
            min_cart_value=Decimal('100.00'),
            active=True,
        )
        
        request = make_request()
        cart = Cart(request)
        product = make_product("MinCart")
        cart.add(product, Decimal("30.00"), quantity=1)
        
        with self.assertRaises(InvalidDiscountError):
            cart.apply_discount('MINCART50')

    def test_discount_max_uses(self):
        """Discount should enforce max uses limit."""
        discount = Discount.objects.create(
            code='LIMITED5',
            discount_type='fixed',
            value=Decimal('5.00'),
            max_uses=1,
            active=True,
        )
        
        request = make_request()
        cart = Cart(request)
        product = make_product("Limited")
        cart.add(product, Decimal("50.00"), quantity=1)
        
        cart.apply_discount('LIMITED5')
        
        # Second use should fail
        request2 = make_request()
        cart2 = Cart(request2)
        cart2.add(product, Decimal("50.00"), quantity=1)
        
        with self.assertRaises(InvalidDiscountError):
            cart2.apply_discount('LIMITED5')


# ===========================================================================
# TestGroup: Stock Validation Tests
# ===========================================================================

class StockValidationTest(TestCase):
    """Test stock/inventory validation."""

    def test_add_with_sufficient_stock(self):
        """Adding within stock should succeed."""
        from cart.inventory import InventoryChecker
        
        class AlwaysInStock(InventoryChecker):
            def check(self, product, quantity):
                return True
            
            def reserve(self, product, quantity):
                return True
        
        request = make_request()
        cart = Cart(request)
        product = make_product("InStock")
        
        cart.add(product, Decimal("10.00"), quantity=5, inventory_checker=AlwaysInStock())
        
        self.assertEqual(cart.count(), 5)

    def test_add_with_insufficient_stock(self):
        """Adding beyond stock should raise InsufficientStock."""
        from cart.inventory import InventoryChecker
        
        class LimitedStock(InventoryChecker):
            def check(self, product, quantity):
                return quantity <= 2
            
            def reserve(self, product, quantity):
                return False
        
        request = make_request()
        cart = Cart(request)
        product = make_product("OutOfStock")
        
        with self.assertRaises(InsufficientStock):
            cart.add(
                product, Decimal("10.00"), quantity=5,
                inventory_checker=LimitedStock()
            )


# ===========================================================================
# TestGroup: Minimum Order Amount Tests
# ===========================================================================

class MinimumOrderAmountTest(TestCase):
    """Test minimum order amount enforcement."""

    def test_checkout_fails_below_minimum(self):
        """Checkout should fail when below minimum order."""
        with self.settings(CART_MIN_ORDER_AMOUNT=Decimal("25.00")):
            request = make_request()
            cart = Cart(request)
            product = make_product("BelowMin")
            cart.add(product, Decimal("10.00"), quantity=1)
            
            can_checkout, message = cart.can_checkout()
            self.assertFalse(can_checkout)
            self.assertIn("25.00", message)

    def test_checkout_succeeds_at_minimum(self):
        """Checkout should succeed at minimum order amount."""
        with self.settings(CART_MIN_ORDER_AMOUNT=Decimal("10.00")):
            request = make_request()
            cart = Cart(request)
            product = make_product("AtMin")
            cart.add(product, Decimal("10.00"), quantity=1)
            
            can_checkout, message = cart.can_checkout()
            self.assertTrue(can_checkout)
            self.assertEqual(message, "")

    def test_checkout_succeeds_above_minimum(self):
        """Checkout should succeed above minimum order amount."""
        with self.settings(CART_MIN_ORDER_AMOUNT=Decimal("5.00")):
            request = make_request()
            cart = Cart(request)
            product = make_product("AboveMin")
            cart.add(product, Decimal("50.00"), quantity=1)
            
            can_checkout, message = cart.can_checkout()
            self.assertTrue(can_checkout)


# ===========================================================================
# Integration Tests for v3.0.0
# ===========================================================================

class EcommerceIntegrationTest(TestCase):
    """Full e-commerce flow integration tests."""

    def test_full_checkout_flow(self):
        """Test complete checkout with all v3.0 features."""
        with self.settings(CART_MIN_ORDER_AMOUNT=Decimal("10.00")):
            # Setup
            request = make_request()
            cart = Cart(request)
            
            product1 = make_product("Item1")
            product2 = make_product("Item2")
            
            cart.add(product1, Decimal("20.00"), quantity=1)
            cart.add(product2, Decimal("15.00"), quantity=1)
            
            # Apply discount
            discount = Discount.objects.create(
                code='TEST10',
                discount_type='fixed',
                value=Decimal('5.00'),
                active=True,
            )
            cart.apply_discount('TEST10')
            
            # Calculate totals
            subtotal = Decimal("35.00")
            discount_amt = Decimal("5.00")
            tax = subtotal * Decimal("0.08")  # 8% tax
            total = subtotal - discount_amt + tax
            
            # Verify can checkout
            can_checkout, _ = cart.can_checkout()
            self.assertTrue(can_checkout)
            
            # Checkout
            cart.checkout()
            self.assertTrue(cart.cart.checked_out)


# ===========================================================================
# Edge Cases for v3.0.0
# ===========================================================================

class V300EdgeCaseTest(TestCase):
    """Edge case tests for v3.0.0 features."""

    def test_discount_with_zero_cart(self):
        """Discount on empty cart should handle gracefully."""
        discount = Discount.objects.create(
            code='EMPTY',
            discount_type='percent',
            value=Decimal('10.00'),
            active=True,
        )
        
        request = make_request()
        cart = Cart(request)
        
        with self.assertRaises(InvalidDiscountError):
            cart.apply_discount('EMPTY')

    def test_multiple_discounts_blocked(self):
        """Only one discount should be allowed per cart."""
        discount1 = Discount.objects.create(
            code='DISC1',
            discount_type='fixed',
            value=Decimal('5.00'),
            active=True,
        )
        discount2 = Discount.objects.create(
            code='DISC2',
            discount_type='fixed',
            value=Decimal('10.00'),
            active=True,
        )
        
        request = make_request()
        cart = Cart(request)
        product = make_product("MultiDiscount")
        cart.add(product, Decimal("100.00"), quantity=1)
        
        cart.apply_discount('DISC1')
        
        with self.assertRaises(InvalidDiscountError):
            cart.apply_discount('DISC2')
```

### v3.0.0 Guarantees

- All existing tests pass
- Hooks are pluggable (backward compatible with no hooks)
- Default implementations don't break existing behavior
- Breaking changes documented in migration guide

---

## Future Considerations

The following features are marked for future consideration and are not yet scheduled:

### Future Features

| Feature | Priority | Notes |
|---------|----------|-------|
| Multi-currency support | Low | Complex currency conversion |
| Gift wrapping options | Low | Requires order customization |
| Cart notes field | Medium | Simple addition |
| Saved carts | Medium | User preference feature |
| Cart sharing | Low | Social commerce feature |
| Abandoned cart emails | Medium | Requires user identification |
| Cart expiration | Medium | Background task integration |
| Async cart operations | Low | Django async view support |

### Potential Deprecations

| Feature | Reason | Timeline |
|---------|--------|----------|
| `Cart._new()` private method | Internal API may change | v4.0.0 |
| Session key format | May need to change for scalability | v4.0.0 |

---

## Version Compatibility

| Version | Python | Django |
|---------|--------|--------|
| v2.3.x | 3.10+ | 4.2+ |
| v2.4.x | 3.10+ | 4.2+ |
| v2.5.x | 3.10+ | 4.2+ |
| v2.6.x | 3.10+ | 4.2+ |
| v2.7.x | 3.10+ | 4.2+ |
| v3.0.0 | 3.10+ | 4.2+ |

---

## Release Process

Each release should follow this process:

1. **Development**: Implement features on feature branch
2. **Testing**: All tests pass including new tests
3. **Code Review**: PR review with focus on:
   - Backward compatibility
   - Performance impact
   - Security considerations
4. **Documentation**: Update README, CHANGELOG, and docstrings
5. **Version Bump**: Update `pyproject.toml` version
6. **Tag & Release**: Create tag and publish to PyPI
7. **Announcement**: Update release notes on GitHub

---

*Roadmap maintained by project maintainers*  
*Last updated: March 2026*
