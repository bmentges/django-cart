from django.utils import timezone

import models

CART_ID = 'CART-ID'


class CartMiddleware(object):

    def process_request(self, request):
        try:
            cart_id = request.session[CART_ID]
            request.cart = models.Cart.objects.get(pk=cart_id)
        except (KeyError, models.Cart.DoesNotExist):
            request.cart = models.Cart.objects.create(creation_date=timezone.now())
            request.session[CART_ID] = request.cart.pk
