"""Minimal custom user model for exercising django-cart's swappable
AUTH_USER_MODEL support. Loaded only under tests.settings_custom_user
(the default test suite keeps Django's built-in auth.User).
"""

from django.contrib.auth.models import AbstractUser


class CustomUser(AbstractUser):
    """An ``AbstractUser`` subclass — identical to ``auth.User`` in
    shape, but swapped in so Django's system checks fire against the
    non-default code path. If ``cart.Cart.user`` is hardcoded to
    ``auth.User``, loading this app raises
    ``cart.Cart has a relation with model auth.User, which has been
    swapped out`` at system-check time — exactly the user-facing
    failure this test suite needs to catch.
    """

    class Meta:
        db_table = "custom_user_app_customuser"
