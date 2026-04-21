"""
Session adapter classes for cart storage.

Provides pluggable backends for different session storage mechanisms.
"""

from abc import ABC, abstractmethod
from typing import Any


class CartSessionAdapter(ABC):
    """
    Abstract base class for cart session adapters.

    Subclass this to implement custom session storage backends.
    """

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from the session."""
        raise NotImplementedError

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Store a value in the session."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove a value from the session."""
        raise NotImplementedError

    @abstractmethod
    def get_or_create_cart_id(self) -> int | None:
        """Get the current cart ID, or None if no cart exists."""
        raise NotImplementedError

    @abstractmethod
    def set_cart_id(self, cart_id: int) -> None:
        """Store the cart ID in the session."""
        raise NotImplementedError

    def flush_to_response(self, request, response) -> None:
        """Persist any pending state to *response*.

        Called by :class:`cart.middleware.CartCookieMiddleware` once the
        view has returned. Default implementation is a no-op — Django
        session-backed adapters rely on ``SessionMiddleware`` for
        persistence and do not need this hook. Cookie-based adapters
        override to write their pending state to ``Set-Cookie``.
        """
        return None


class DjangoSessionAdapter(CartSessionAdapter):
    """
    Default adapter using Django's session framework.
    """

    def __init__(self, request):
        self._session = request.session

    def get(self, key: str, default: Any = None) -> Any:
        return self._session.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._session[key] = value

    def delete(self, key: str) -> None:
        del self._session[key]

    def get_or_create_cart_id(self) -> int | None:
        from .cart import CART_ID

        return self._session.get(CART_ID)

    def set_cart_id(self, cart_id: int) -> None:
        from .cart import CART_ID

        self._session[CART_ID] = cart_id


class CookieSessionAdapter(CartSessionAdapter):
    """
    Adapter using HTTP cookies for cart storage.

    Useful for scenarios where server-side sessions are not available.
    """

    def __init__(self, request=None, response=None):
        self._request = request
        self._response = response
        self._cookies = dict(request.COOKIES) if request is not None else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._cookies.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._cookies[key] = value
        if self._response is not None:
            self._response.set_cookie(key, value)

    def delete(self, key: str) -> None:
        if key in self._cookies:
            del self._cookies[key]
        if self._response is not None:
            self._response.delete_cookie(key)

    def get_or_create_cart_id(self) -> int | None:
        from .cart import CART_ID

        value = self._cookies.get(CART_ID)
        if value:
            try:
                return int(value)
            except (ValueError, TypeError):
                return None
        return None

    def set_cart_id(self, cart_id: int) -> None:
        from .cart import CART_ID

        self.set(CART_ID, str(cart_id))

    def flush_to_response(self, request, response) -> None:
        """Write pending cookie mutations to *response*.

        Diffs ``self._cookies`` against ``request.COOKIES`` and calls
        ``response.set_cookie`` for added/changed entries and
        ``response.delete_cookie`` for entries that were removed. This
        is the bridge that makes ``CARTS_SESSION_ADAPTER_CLASS =
        "cart.session.CookieSessionAdapter"`` actually round-trip a
        cart id through the browser — without it (pre-v3.0.12), set
        operations only mutated the in-memory ``_cookies`` dict.
        """
        before = request.COOKIES
        after = self._cookies
        for key, value in after.items():
            if before.get(key) != value:
                response.set_cookie(key, value)
        for key in before:
            if key not in after:
                response.delete_cookie(key)
