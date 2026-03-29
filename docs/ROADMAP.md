# django-cart Development Roadmap

**Current Version:** 3.0.0 (In Progress)  
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

1. [v2.6.0 - Cart Operations & Persistence](#v260---cart-operations--persistence)
2. [v2.7.0 - Security & Production Readiness](#v270---security--production-readiness)
3. [v3.0.0 - E-commerce Features (Major Release)](#v300---e-commerce-features-major-release)
4. [Future Considerations](#future-considerations)

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
