from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase
from django.test.client import RequestFactory
from django.utils import timezone
from models import Cart, Item, ProductDoesNotExist
from django.contrib.auth.models import User
import datetime
from decimal import Decimal

import middleware


class CartAndItemModelsTestCase(TestCase):

    def _create_cart_in_database(self, creation_date=timezone.now(), 
            checked_out=False):
        """
            Helper function so I don't repeat myself
        """
        cart = Cart()
        cart.creation_date = creation_date
        cart.checked_out = False
        cart.save()
        return cart

    def _create_item_in_database(self, cart, product, quantity=1, 
            unit_price=Decimal("100")):
        """
            Helper function so I don't repeat myself
        """  
        item = Item()
        item.cart = cart
        item.product = product
        item.quantity = quantity
        item.unit_price = unit_price
        item.save() 

        return item

    def _create_user_in_database(self):
        """
            Helper function so I don't repeat myself
        """ 
        user = User(username="user_for_sell", password="sold", 
                email="example@example.com")
        user.save() 
        return user

    def test_cart_creation(self):
        creation_date = timezone.now()
        cart = self._create_cart_in_database(creation_date)
        id = cart.id

        cart_from_database = Cart.objects.get(pk=id)
        self.assertEquals(cart, cart_from_database)
        

    def test_item_creation_and_association_with_cart(self):
        """
            This test is a little bit tricky since the Item tracks
            any model via django's content type framework. This was
            made in order to enable you to associate an item in the
            cart with your product model.
            
            As I wont make a product model here, I will assume my test
            store sells django users (django.contrib.auth.models.User) 
            (lol) so I can test that this is working.

            So if you are reading this test to understand the API,
            you just need to change the user for your product model
            in your code and you're good to go.
        """
        user = self._create_user_in_database()

        cart = self._create_cart_in_database()
        item = self._create_item_in_database(cart, user, quantity=1, unit_price=Decimal("100"))

        # get the first item in the cart
        item_in_cart = cart.item_set.all()[0]
        self.assertEquals(item_in_cart, item, 
                "First item in cart should be equal the item we created")
        self.assertEquals(item_in_cart.product, user,
                "Product associated with the first item in cart should equal the user we're selling")
        self.assertEquals(item_in_cart.unit_price, Decimal("100"), 
                "Unit price of the first item stored in the cart should equal 100")
        self.assertEquals(item_in_cart.quantity, 1, 
                "The first item in cart should have 1 in it's quantity")


    def test_total_item_price(self):
        """
        Since the unit price is a Decimal field, prefer to associate
        unit prices instantiating the Decimal class in 
        decimal.Decimal.
        """
        user = self._create_user_in_database()
        cart = self._create_cart_in_database()

        # not safe to do as the field is Decimal type. It works for integers but
        # doesn't work for float
        item_with_unit_price_as_integer = self._create_item_in_database(cart, product=user, quantity=3, unit_price=100)

        self.assertEquals(item_with_unit_price_as_integer.total_price, 300)
        
        # this is the right way to associate unit prices
        item_with_unit_price_as_decimal = self._create_item_in_database(cart,
                product=user, quantity=4, unit_price=Decimal("3.20"))
        self.assertEquals(item_with_unit_price_as_decimal.total_price, Decimal("12.80"))

    def test_item_unicode(self):
        user = self._create_user_in_database()
        cart = self._create_cart_in_database()

        item = self._create_item_in_database(cart, product=user, quantity=3, unit_price=Decimal("100"))

        self.assertEquals(item.__unicode__(), "3 units of User")


class CartAddItemTests(TestCase):

    def setUp(self):
        self.cart = Cart.objects.create(creation_date=timezone.now())
        self.item = User.objects.create_user(username='test-user', password='')

    def test_with_nonexistent_item(self):
        self.assertEqual(Item.objects.count(), 0)

        self.cart.add_item(self.item)

        self.assertEqual(self.cart.item_set.count(), 1)

    def test_with_existing_item_adds_to_quantity(self):
        self.assertEqual(Item.objects.count(), 0)

        self.cart.add_item(self.item, quantity=1)
        self.cart.add_item(self.item, quantity=1)

        self.assertEqual(self.cart.item_set.count(), 1)
        self.assertEqual(self.cart.item_set.all()[0].quantity, 2)


class CartRemoveItemTests(TestCase):

    def setUp(self):
        self.cart = Cart.objects.create(creation_date=timezone.now())
        self.item = User.objects.create_user(username='test-user', password='')

    def test_remove_item_that_exists(self):
        self.cart.add_item(self.item)
        self.assertEqual(Item.objects.count(), 1)

        self.cart.remove_item(self.item)
        self.assertEqual(self.cart.item_set.count(), 0)
        self.assertEqual(Item.objects.count(), 0)

    def test_remove_item_that_does_not_exist_raises_ProductDoesNotExist(self):
        self.assertEqual(Item.objects.count(), 0)

        self.assertRaises(ProductDoesNotExist, self.cart.remove_item, self.item)


class CartItemsTests(TestCase):

    def setUp(self):
        self.cart = Cart.objects.create(creation_date=timezone.now())
        
    def test_empty_items(self):
        self.assertEqual(self.cart.items(), [])

    def test_items(self):
        item = User.objects.create_user(username='test-user', password='')
        self.cart.add_item(item)

        self.assertEqual(self.cart.items(), list(Item.objects.all()))


class CartSummaryTests(TestCase):

    def setUp(self):
        self.cart = Cart.objects.create(creation_date=timezone.now())
        self.item = User.objects.create_user(username='test-user', password='')

    def test_zero(self):
        self.assertEqual(self.cart.summary(), 0)

    def test_summary(self):
        self.cart.add_item(self.item, unit_price=100)

        self.assertEqual(self.cart.summary(), 100)

    def test_summary_with_quantity(self):
        self.cart.add_item(self.item, unit_price=100, quantity=3)

        self.assertEqual(self.cart.summary(), 300)


class CartEmptyTests(TestCase):

    def setUp(self):
        self.cart = Cart.objects.create(creation_date=timezone.now())

    def test_already_empty(self):
        self.cart.empty()
        self.assertTrue(self.cart.is_empty())

    def test_empty(self):
        item = User.objects.create_user(username='test-user', password='')

        self.cart.add_item(item)
        self.assertFalse(self.cart.is_empty())

        self.cart.empty()
        self.assertTrue(self.cart.is_empty())


class CartItemCountTests(TestCase):

    def setUp(self):
        self.cart = Cart.objects.create(creation_date=timezone.now())

    def test_zero(self):
        self.assertEqual(self.cart.item_count(), 0)

    def test_item_count(self):
        item1 = User.objects.create_user(username='test-user1', password='')
        item2 = User.objects.create_user(username='test-user2', password='')
        self.cart.add_item(item1)
        self.cart.add_item(item2)

        self.assertEqual(self.cart.item_count(), 2)


class CartMiddlewareTests(TestCase):
    SESSION_CART_ID = 'CART-ID'

    def setUp(self):
        self.request = RequestFactory().get('')
        self.request.session = {}

        self.cart_middleware = middleware.CartMiddleware()

    def test_no_cart_in_session(self):
        self.cart_middleware.process_request(self.request)

        assert hasattr(self.request, 'cart')
        self.assertEqual(self.request.cart, Cart.objects.get(id=1))
        self.assertEqual(self.request.session[CartMiddlewareTests.SESSION_CART_ID], 1)

    def test_cart_in_session(self):
        Cart.objects.create(creation_date=timezone.now())
        self.request.session[CartMiddlewareTests.SESSION_CART_ID] = 1

        self.cart_middleware.process_request(self.request)

        self.assertEqual(self.request.cart.id, 1)
        self.assertEqual(self.request.session[CartMiddlewareTests.SESSION_CART_ID], 1)

    def test_invalid_cart_in_session(self):
        self.request.session[CartMiddlewareTests.SESSION_CART_ID] = 2

        self.cart_middleware.process_request(self.request)

        self.assertEqual(self.request.cart.id, 1)
        self.assertEqual(self.request.session[CartMiddlewareTests.SESSION_CART_ID], 1)
