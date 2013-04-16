from django.core.exceptions import ImproperlyConfigured

import models

def cart(request):
    try:
        return {'cart': request.cart}
    except AttributeError:
        raise ImproperlyConfigured(
            'cart.context_processors.CartContextProcessor requires that the \
CartMiddleware be installed'
        )
