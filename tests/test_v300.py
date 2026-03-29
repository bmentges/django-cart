"""
Tests for v3.0.0 features: Discounts, Tax, Shipping, and Inventory.
"""
from decimal import Decimal
from unittest import mock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model

from cart.cart import Cart, InvalidDiscountError, InsufficientStock, MinimumOrderNotMet
from cart.models import Cart as CartModel, Item, Discount, DiscountType
from cart.tax import TaxCalculator, DefaultTaxCalculator, get_tax_calculator
from cart.shipping import ShippingCalculator, DefaultShippingCalculator, get_shipping_calculator
from cart.inventory import InventoryChecker, DefaultInventoryChecker, get_inventory_checker

from tests.test_app.models import FakeProduct


User = get_user_model()


class LargeTaxCalculator(TaxCalculator):
    """Tax calculator that returns a large tax amount for testing."""
    def calculate(self, cart):
        return Decimal("500.00")


def make_request(session=None):
    """Return a minimal mock request with a dict-based session."""
    request = mock.MagicMock()
    request.session = session if session is not None else {}
    return request


class TaxCalculatorTest(TestCase):
    """Tests for TaxCalculator classes."""

    def test_default_tax_calculator_returns_zero(self):
        """DefaultTaxCalculator should return 0 tax."""
        calculator = DefaultTaxCalculator()
        mock_cart = mock.MagicMock()
        mock_cart.summary.return_value = Decimal("100.00")
        
        result = calculator.calculate(mock_cart)
        
        self.assertEqual(result, Decimal("0.00"))

    def test_tax_calculator_interface_is_abstract(self):
        """TaxCalculator should be an abstract base class."""
        self.assertTrue(hasattr(TaxCalculator, '__abstractmethods__'))
        self.assertIn('calculate', TaxCalculator.__abstractmethods__)

    def test_get_tax_calculator_returns_default(self):
        """get_tax_calculator should return DefaultTaxCalculator by default."""
        calculator = get_tax_calculator()
        self.assertIsInstance(calculator, DefaultTaxCalculator)

    @override_settings(CART_TAX_CALCULATOR='tests.test_v300.CustomTaxCalculator')
    def test_custom_tax_calculator_from_settings(self):
        """Custom tax calculator should be used when configured via settings."""
        calculator = get_tax_calculator()
        self.assertIsInstance(calculator, CustomTaxCalculator)
        mock_cart = mock.MagicMock()
        mock_cart.summary.return_value = Decimal("100.00")
        self.assertEqual(calculator.calculate(mock_cart), Decimal("10.00"))

    def test_custom_tax_calculator(self):
        """Custom tax calculator can be instantiated and used."""
        class CustomTaxCalculator(TaxCalculator):
            def calculate(self, cart):
                return Decimal("10.00")
        
        calculator = CustomTaxCalculator()
        mock_cart = mock.MagicMock()
        self.assertEqual(calculator.calculate(mock_cart), Decimal("10.00"))


class ShippingCalculatorTest(TestCase):
    """Tests for ShippingCalculator classes."""

    def test_default_shipping_calculator_returns_zero(self):
        """DefaultShippingCalculator should return 0 shipping."""
        calculator = DefaultShippingCalculator()
        mock_cart = mock.MagicMock()
        mock_cart.summary.return_value = Decimal("100.00")
        
        result = calculator.calculate(mock_cart)
        
        self.assertEqual(result, Decimal("0.00"))

    def test_default_shipping_options_returns_single_option(self):
        """DefaultShippingCalculator.get_options should return one free shipping option."""
        calculator = DefaultShippingCalculator()
        mock_cart = mock.MagicMock()
        mock_cart.summary.return_value = Decimal("100.00")
        
        options = calculator.get_options(mock_cart)
        
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0]['id'], 'free')
        self.assertEqual(options[0]['name'], 'Free Shipping')
        self.assertEqual(str(options[0]['price']), '0.00')

    def test_shipping_calculator_interface_is_abstract(self):
        """ShippingCalculator should be an abstract base class."""
        self.assertTrue(hasattr(ShippingCalculator, '__abstractmethods__'))
        self.assertIn('calculate', ShippingCalculator.__abstractmethods__)
        self.assertIn('get_options', ShippingCalculator.__abstractmethods__)

    def test_get_shipping_calculator_returns_default(self):
        """get_shipping_calculator should return DefaultShippingCalculator by default."""
        calculator = get_shipping_calculator()
        self.assertIsInstance(calculator, DefaultShippingCalculator)

    @override_settings(CART_SHIPPING_CALCULATOR='tests.test_v300.CustomShippingCalculator')
    def test_custom_shipping_calculator_from_settings(self):
        """Custom shipping calculator should be used when configured via settings."""
        calculator = get_shipping_calculator()
        self.assertIsInstance(calculator, CustomShippingCalculator)
        mock_cart = mock.MagicMock()
        mock_cart.summary.return_value = Decimal("100.00")
        self.assertEqual(calculator.calculate(mock_cart), Decimal("15.00"))
        options = calculator.get_options(mock_cart)
        self.assertEqual(len(options), 2)

    def test_custom_shipping_calculator(self):
        """Custom shipping calculator can be instantiated and used."""
        class CustomShippingCalculator(ShippingCalculator):
            def calculate(self, cart):
                return Decimal("15.00")
            
            def get_options(self, cart):
                return [
                    {'id': 'express', 'name': 'Express Shipping', 'price': Decimal("25.00")},
                    {'id': 'standard', 'name': 'Standard Shipping', 'price': Decimal("10.00")},
                ]
        
        calculator = CustomShippingCalculator()
        mock_cart = mock.MagicMock()
        self.assertEqual(calculator.calculate(mock_cart), Decimal("15.00"))
        options = calculator.get_options(mock_cart)
        self.assertEqual(len(options), 2)


class InventoryCheckerTest(TestCase):
    """Tests for InventoryChecker classes."""

    def test_default_inventory_checker_always_available(self):
        """DefaultInventoryChecker should always return available=True."""
        checker = DefaultInventoryChecker()
        mock_product = mock.MagicMock()
        
        result = checker.check(mock_product, 1)
        
        self.assertTrue(result)

    def test_inventory_checker_interface_is_abstract(self):
        """InventoryChecker should be an abstract base class."""
        self.assertTrue(hasattr(InventoryChecker, '__abstractmethods__'))
        self.assertIn('check', InventoryChecker.__abstractmethods__)
        self.assertIn('reserve', InventoryChecker.__abstractmethods__)

    def test_get_inventory_checker_returns_default(self):
        """get_inventory_checker should return DefaultInventoryChecker by default."""
        checker = get_inventory_checker()
        self.assertIsInstance(checker, DefaultInventoryChecker)

    @override_settings(CART_INVENTORY_CHECKER='tests.test_v300.CustomInventoryChecker')
    def test_custom_inventory_checker_from_settings(self):
        """Custom inventory checker should be used when configured via settings."""
        checker = get_inventory_checker()
        self.assertIsInstance(checker, CustomInventoryChecker)

    def test_custom_inventory_checker(self):
        """Custom inventory checker can be instantiated and used."""
        class CustomInventoryChecker(InventoryChecker):
            def check(self, product, quantity):
                return quantity <= 5
            
            def reserve(self, product, quantity):
                return quantity <= 5
        
        checker = CustomInventoryChecker()
        self.assertTrue(checker.check(mock.MagicMock(), 3))
        self.assertFalse(checker.check(mock.MagicMock(), 10))

    def test_inventory_checker_release_default(self):
        """DefaultInventoryChecker.release should return True."""
        checker = DefaultInventoryChecker()
        result = checker.release(mock.MagicMock(), 1)
        self.assertTrue(result)


class DiscountModelTest(TestCase):
    """Tests for Discount model."""

    def setUp(self):
        self.product = FakeProduct.objects.create(name="Test Product", price=Decimal("100.00"))
        self.request = make_request()

    def create_cart_with_items(self):
        """Create a Cart with items using the Cart class."""
        cart = Cart(self.request)
        cart.add(self.product, unit_price=Decimal("100.00"), quantity=2)
        return cart

    def test_discount_type_choices(self):
        """Discount should have correct type choices."""
        self.assertEqual(DiscountType.PERCENT, "percent")
        self.assertEqual(DiscountType.FIXED, "fixed")

    def test_create_percent_discount(self):
        """Can create a percentage-based discount."""
        discount = Discount.objects.create(
            code="SAVE20",
            discount_type=DiscountType.PERCENT,
            value=Decimal("20.00"),
        )
        
        self.assertEqual(discount.code, "SAVE20")
        self.assertEqual(discount.discount_type, "percent")
        self.assertEqual(discount.value, Decimal("20.00"))
        self.assertTrue(discount.active)

    def test_create_fixed_discount(self):
        """Can create a fixed amount discount."""
        discount = Discount.objects.create(
            code="FLAT10",
            discount_type=DiscountType.FIXED,
            value=Decimal("10.00"),
        )
        
        self.assertEqual(discount.code, "FLAT10")
        self.assertEqual(discount.discount_type, "fixed")
        self.assertEqual(discount.value, Decimal("10.00"))

    def test_discount_code_unique(self):
        """Discount codes must be unique."""
        Discount.objects.create(code="UNIQUE", value=Decimal("10.00"))
        
        with self.assertRaises(Exception):
            Discount.objects.create(code="UNIQUE", value=Decimal("20.00"))

    def test_calculate_percent_discount(self):
        """Percent discount should calculate correctly."""
        discount = Discount.objects.create(
            code="SAVE20",
            discount_type=DiscountType.PERCENT,
            value=Decimal("20.00"),
        )
        cart = self.create_cart_with_items()
        
        result = discount.calculate_discount(cart)
        
        self.assertEqual(result, Decimal("40.00"))  # 20% of 200

    def test_calculate_fixed_discount(self):
        """Fixed discount should return the value."""
        discount = Discount.objects.create(
            code="FLAT25",
            discount_type=DiscountType.FIXED,
            value=Decimal("25.00"),
        )
        cart = self.create_cart_with_items()
        
        result = discount.calculate_discount(cart)
        
        self.assertEqual(result, Decimal("25.00"))

    def test_calculate_fixed_discount_exceeds_subtotal(self):
        """Fixed discount should not exceed subtotal."""
        discount = Discount.objects.create(
            code="BIGFLAT",
            discount_type=DiscountType.FIXED,
            value=Decimal("500.00"),  # More than cart total of 200
        )
        cart = self.create_cart_with_items()
        
        result = discount.calculate_discount(cart)
        
        self.assertEqual(result, Decimal("200.00"))  # Capped at cart total

    def test_is_valid_for_cart_with_no_restrictions(self):
        """Discount with no restrictions should be valid."""
        discount = Discount.objects.create(
            code="NO_RESTRICT",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
        )
        cart = self.create_cart_with_items()
        
        is_valid, message = discount.is_valid_for_cart(cart)
        
        self.assertTrue(is_valid)
        self.assertEqual(message, "")

    def test_is_valid_for_cart_min_cart_value_not_met(self):
        """Discount should be invalid if cart value is below minimum."""
        discount = Discount.objects.create(
            code="MIN50",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
            min_cart_value=Decimal("500.00"),
        )
        cart = self.create_cart_with_items()  # Cart total is 200
        
        is_valid, message = discount.is_valid_for_cart(cart)
        
        self.assertFalse(is_valid)
        self.assertIn("Minimum cart value", message)

    def test_is_valid_for_cart_min_cart_value_met(self):
        """Discount should be valid if cart value meets minimum."""
        discount = Discount.objects.create(
            code="MIN50",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
            min_cart_value=Decimal("100.00"),
        )
        cart = self.create_cart_with_items()  # Cart total is 200
        
        is_valid, message = discount.is_valid_for_cart(cart)
        
        self.assertTrue(is_valid)

    def test_is_valid_for_cart_max_uses_exceeded(self):
        """Discount should be invalid if max uses exceeded."""
        discount = Discount.objects.create(
            code="LIMITED",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
            max_uses=1,
            current_uses=1,
        )
        cart = self.create_cart_with_items()
        
        is_valid, message = discount.is_valid_for_cart(cart)
        
        self.assertFalse(is_valid)
        self.assertIn("maximum number of uses", message)

    def test_is_valid_for_cart_inactive(self):
        """Inactive discount should be invalid."""
        discount = Discount.objects.create(
            code="INACTIVE",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
            active=False,
        )
        cart = self.create_cart_with_items()
        
        is_valid, message = discount.is_valid_for_cart(cart)
        
        self.assertFalse(is_valid)
        self.assertIn("no longer active", message)

    def test_is_valid_for_cart_not_yet_valid(self):
        """Discount should be invalid if not yet valid."""
        from django.utils import timezone
        from datetime import timedelta
        discount = Discount.objects.create(
            code="FUTURE",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
            valid_from=timezone.now() + timedelta(days=1),
        )
        cart = self.create_cart_with_items()
        
        is_valid, message = discount.is_valid_for_cart(cart)
        
        self.assertFalse(is_valid)
        self.assertIn("not yet valid", message)

    def test_is_valid_for_cart_expired(self):
        """Discount should be invalid if expired."""
        from django.utils import timezone
        from datetime import timedelta
        discount = Discount.objects.create(
            code="EXPIRED",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
            valid_until=timezone.now() - timedelta(days=1),
        )
        cart = self.create_cart_with_items()
        
        is_valid, message = discount.is_valid_for_cart(cart)
        
        self.assertFalse(is_valid)
        self.assertIn("expired", message)

    def test_discount_str(self):
        """Discount string representation should include code."""
        discount = Discount.objects.create(
            code="TEST",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
        )
        
        self.assertIn("TEST", str(discount))


class CartDiscountMethodsTest(TestCase):
    """Tests for Cart discount-related methods."""

    def setUp(self):
        self.product = FakeProduct.objects.create(name="Test Product", price=Decimal("100.00"))
        self.request = make_request()
        self.cart = Cart(self.request)
        self.cart.add(self.product, unit_price=Decimal("100.00"), quantity=2)

    def test_discount_amount_no_discount(self):
        """discount_amount should return 0 when no discount applied."""
        result = self.cart.discount_amount()
        self.assertEqual(result, Decimal("0.00"))

    def test_discount_code_no_discount(self):
        """discount_code should return None when no discount applied."""
        result = self.cart.discount_code()
        self.assertIsNone(result)

    def test_apply_discount_success(self):
        """apply_discount should successfully apply a valid discount."""
        discount = Discount.objects.create(
            code="SAVE10",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
        )
        
        result = self.cart.apply_discount("SAVE10")
        
        self.assertEqual(result, discount)
        self.assertEqual(self.cart.discount_code(), "SAVE10")
        self.assertEqual(self.cart.discount_amount(), Decimal("20.00"))  # 10% of 200

    def test_apply_discount_invalid_code(self):
        """apply_discount should raise error for invalid code."""
        with self.assertRaises(InvalidDiscountError) as context:
            self.cart.apply_discount("INVALID")
        
        self.assertIn("does not exist", str(context.exception))

    def test_apply_discount_already_applied(self):
        """apply_discount should raise error if discount already applied."""
        discount = Discount.objects.create(
            code="FIRST",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
        )
        self.cart.apply_discount("FIRST")
        
        with self.assertRaises(InvalidDiscountError) as context:
            self.cart.apply_discount("SECOND")
        
        self.assertIn("already applied", str(context.exception))

    def test_apply_discount_not_valid(self):
        """apply_discount should raise error if discount not valid for cart."""
        discount = Discount.objects.create(
            code="MIN100",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
            min_cart_value=Decimal("1000.00"),  # Cart is only 200
        )
        
        with self.assertRaises(InvalidDiscountError) as context:
            self.cart.apply_discount("MIN100")
        
        self.assertIn("Minimum cart value", str(context.exception))

    def test_remove_discount(self):
        """remove_discount should remove the applied discount."""
        discount = Discount.objects.create(
            code="REMOVE",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
        )
        self.cart.apply_discount("REMOVE")
        
        self.cart.remove_discount()
        
        self.assertIsNone(self.cart.discount_code())
        self.assertEqual(self.cart.discount_amount(), Decimal("0.00"))

    def test_remove_discount_no_discount(self):
        """remove_discount should work when no discount is applied."""
        self.cart.remove_discount()  # Should not raise
        self.assertEqual(self.cart.discount_amount(), Decimal("0.00"))

    def test_discount_updates_cart_cache(self):
        """Applying discount should invalidate cart cache."""
        discount = Discount.objects.create(
            code="CACHE_TEST",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
        )
        
        original_summary = self.cart.summary()
        self.cart.apply_discount("CACHE_TEST")
        
        self.assertEqual(self.cart.discount_amount(), Decimal("20.00"))


class CartTaxShippingMethodsTest(TestCase):
    """Tests for Cart tax, shipping, and total methods."""

    def setUp(self):
        self.product = FakeProduct.objects.create(name="Test Product", price=Decimal("100.00"))
        self.request = make_request()
        self.cart = Cart(self.request)
        self.cart.add(self.product, unit_price=Decimal("100.00"), quantity=2)

    def test_tax_default_returns_zero(self):
        """tax() should return Decimal('0.00') with default calculator."""
        result = self.cart.tax()
        self.assertEqual(result, Decimal("0.00"))

    def test_shipping_default_returns_zero(self):
        """shipping() should return Decimal('0.00') with default calculator."""
        result = self.cart.shipping()
        self.assertEqual(result, Decimal("0.00"))

    def test_shipping_options_returns_list(self):
        """shipping_options() should return a list."""
        result = self.cart.shipping_options()
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_total_without_discount(self):
        """total() should return subtotal when no discount."""
        result = self.cart.total()
        self.assertEqual(result, Decimal("200.00"))  # 200 - 0 + 0 + 0

    def test_total_with_discount(self):
        """total() should subtract discount."""
        Discount.objects.create(
            code="SAVE10",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
        )
        self.cart.apply_discount("SAVE10")
        
        result = self.cart.total()
        self.assertEqual(result, Decimal("180.00"))  # 200 - 20 + 0 + 0

    @override_settings(CART_TAX_CALCULATOR='tests.test_v300.TaxCalculator10Percent')
    def test_total_with_custom_tax(self):
        """total() should add custom tax."""
        result = self.cart.total()
        self.assertEqual(result, Decimal("220.00"))  # 200 - 0 + 20 + 0

    @override_settings(CART_SHIPPING_CALCULATOR='tests.test_v300.ShippingCalculatorFlatRate')
    def test_total_with_custom_shipping(self):
        """total() should add custom shipping."""
        result = self.cart.total()
        self.assertEqual(result, Decimal("210.00"))  # 200 - 0 + 0 + 10

    def test_total_never_negative(self):
        """total() should never return negative even with large discount exceeding subtotal."""
        discount = Discount.objects.create(
            code="HUGE",
            discount_type=DiscountType.FIXED,
            value=Decimal("500.00"),
        )
        self.cart.apply_discount("HUGE")
        result = self.cart.total()
        self.assertEqual(result, Decimal("0.00"))


class CartCheckoutMethodsTest(TestCase):
    """Tests for Cart checkout-related methods."""

    def setUp(self):
        self.product = FakeProduct.objects.create(name="Test Product", price=Decimal("100.00"))
        self.request = make_request()

    def create_cart_with_items(self, quantity=2):
        """Create a Cart with items."""
        cart = Cart(self.request)
        cart.add(self.product, unit_price=Decimal("100.00"), quantity=quantity)
        return cart

    def test_can_checkout_empty_cart(self):
        """can_checkout should return False for empty cart."""
        cart = Cart(self.request)
        
        can_checkout, message = cart.can_checkout()
        
        self.assertFalse(can_checkout)
        self.assertEqual(message, "Cart is empty.")

    def test_can_checkout_with_items(self):
        """can_checkout should return True for cart with items."""
        cart = self.create_cart_with_items()
        
        can_checkout, message = cart.can_checkout()
        
        self.assertTrue(can_checkout)
        self.assertEqual(message, "")

    @override_settings(CART_MIN_ORDER_AMOUNT=Decimal("500.00"))
    def test_can_checkout_below_minimum_setting(self):
        """can_checkout should return False if cart below CART_MIN_ORDER_AMOUNT."""
        cart = self.create_cart_with_items(quantity=2)  # 200 total, below 500 minimum
        
        can_checkout, message = cart.can_checkout()
        
        self.assertFalse(can_checkout)
        self.assertIn("500.00", message)


class CartInventoryTest(TestCase):
    """Tests for Cart inventory checking in add()."""

    def setUp(self):
        self.product = FakeProduct.objects.create(name="Test Product", price=Decimal("100.00"))
        self.request = make_request()
        self.cart = Cart(self.request)

    def test_add_without_inventory_check(self):
        """add() should work without inventory checking by default."""
        item = self.cart.add(self.product, unit_price=Decimal("100.00"), quantity=2)
        
        self.assertIsNotNone(item)
        self.assertEqual(item.quantity, 2)

    @override_settings(CART_INVENTORY_CHECKER='tests.test_v300.FailingInventoryChecker')
    def test_add_with_inventory_check_failing(self):
        """add() should raise InsufficientStock when inventory checker fails."""
        with self.assertRaises(InsufficientStock):
            self.cart.add(self.product, unit_price=Decimal("100.00"), quantity=2, check_inventory=True)

    @override_settings(CART_INVENTORY_CHECKER='tests.test_v300.PassingInventoryChecker')
    def test_add_with_inventory_check_passing(self):
        """add() should succeed when inventory checker returns True."""
        item = self.cart.add(self.product, unit_price=Decimal("100.00"), quantity=2, check_inventory=True)
        self.assertIsNotNone(item)


class NewExceptionsTest(TestCase):
    """Tests for new exception classes."""

    def test_invalid_discount_error(self):
        """InvalidDiscountError should be raisable."""
        with self.assertRaises(InvalidDiscountError):
            raise InvalidDiscountError("Test message")

    def test_insufficient_stock(self):
        """InsufficientStock should be raisable."""
        with self.assertRaises(InsufficientStock):
            raise InsufficientStock("Test message")

    def test_minimum_order_not_met(self):
        """MinimumOrderNotMet should be raisable."""
        with self.assertRaises(MinimumOrderNotMet):
            raise MinimumOrderNotMet("Test message")

    def test_exceptions_inherit_from_cart_exception(self):
        """New exceptions should inherit from CartException."""
        from cart.cart import CartException
        
        self.assertTrue(issubclass(InvalidDiscountError, CartException))
        self.assertTrue(issubclass(InsufficientStock, CartException))
        self.assertTrue(issubclass(MinimumOrderNotMet, CartException))


class DiscountModelFieldsTest(TestCase):
    """Tests for Discount model fields and metadata."""

    def test_discount_verbose_names(self):
        """Discount should have proper verbose names."""
        discount = Discount.objects.create(
            code="TEST",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10.00"),
        )
        
        self.assertEqual(discount._meta.verbose_name, "discount")
        self.assertEqual(discount._meta.verbose_name_plural, "discounts")

    def test_discount_default_values(self):
        """Discount should have proper defaults."""
        discount = Discount.objects.create(
            code="DEFAULTS",
            value=Decimal("10.00"),
        )
        
        self.assertEqual(discount.discount_type, "percent")
        self.assertTrue(discount.active)
        self.assertEqual(discount.current_uses, 0)
        self.assertIsNone(discount.min_cart_value)
        self.assertIsNone(discount.max_uses)
        self.assertIsNone(discount.valid_from)
        self.assertIsNone(discount.valid_until)


class CartDiscountFieldTest(TestCase):
    """Tests for Cart model's discount field."""

    def test_cart_discount_field_exists(self):
        """Cart model should have discount field."""
        cart = CartModel.objects.create()
        
        self.assertTrue(hasattr(cart, 'discount'))

    def test_cart_discount_default_is_null(self):
        """Cart discount field should default to None."""
        cart = CartModel.objects.create()
        
        self.assertIsNone(cart.discount)

    def test_cart_can_have_discount(self):
        """Cart can have a discount applied."""
        cart = CartModel.objects.create()
        discount = Discount.objects.create(
            code="CART_DISC",
            discount_type=DiscountType.PERCENT,
            value=Decimal("5.00"),
        )
        
        cart.discount = discount
        cart.save()
        
        cart.refresh_from_db()
        self.assertEqual(cart.discount, discount)


# Custom calculator classes for testing settings-based configuration

class CustomTaxCalculator(TaxCalculator):
    """Custom tax calculator for testing."""
    def calculate(self, cart):
        return Decimal("10.00")


class CustomShippingCalculator(ShippingCalculator):
    """Custom shipping calculator for testing."""
    def calculate(self, cart):
        return Decimal("15.00")
    
    def get_options(self, cart):
        return [
            {'id': 'express', 'name': 'Express Shipping', 'price': Decimal("25.00")},
            {'id': 'standard', 'name': 'Standard Shipping', 'price': Decimal("10.00")},
        ]


class CustomInventoryChecker(InventoryChecker):
    """Custom inventory checker for testing."""
    def check(self, product, quantity):
        return quantity <= 5
    
    def reserve(self, product, quantity):
        return quantity <= 5


class FailingInventoryChecker(InventoryChecker):
    """Inventory checker that always fails for testing."""
    def check(self, product, quantity):
        return False
    
    def reserve(self, product, quantity):
        return False


class PassingInventoryChecker(InventoryChecker):
    """Inventory checker that always passes for testing."""
    def check(self, product, quantity):
        return True
    
    def reserve(self, product, quantity):
        return True


class TaxCalculator10Percent(TaxCalculator):
    """10% tax calculator for testing."""
    def calculate(self, cart):
        return cart.summary() * Decimal("0.10")


class ShippingCalculatorFlatRate(ShippingCalculator):
    """Flat rate shipping for testing."""
    def calculate(self, cart):
        return Decimal("10.00")
    
    def get_options(self, cart):
        return [
            {'id': 'flat', 'name': 'Flat Rate', 'price': Decimal("10.00")},
        ]
