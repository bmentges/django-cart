"""Middleware for cart session-adapter persistence.

Only required when ``CARTS_SESSION_ADAPTER_CLASS`` is configured to a
cookie-based adapter (e.g. :class:`cart.session.CookieSessionAdapter`).
The default :class:`cart.session.DjangoSessionAdapter` stores state
through Django's ``SessionMiddleware`` and does not need this one.

Wire it into ``settings.MIDDLEWARE`` after any middleware that might
itself construct a cart from the request — in practice, adding it at
the tail of the list is fine::

    MIDDLEWARE = [
        # ... existing middleware ...
        "cart.middleware.CartCookieMiddleware",
    ]
"""
from __future__ import annotations


class CartCookieMiddleware:
    """Flush cookie-based cart session state onto the outgoing response.

    Looks for a session adapter stashed on ``request._cart_session`` by
    :meth:`cart.cart.Cart._build_session_adapter` and calls its
    :meth:`~cart.session.CartSessionAdapter.flush_to_response` hook.
    Adapters without pending state (notably ``DjangoSessionAdapter``)
    return a no-op, so this middleware is safe to leave installed even
    when the active adapter isn't cookie-based.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        adapter = getattr(request, "_cart_session", None)
        if adapter is not None:
            adapter.flush_to_response(request, response)
        return response
