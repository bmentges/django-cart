"""Test settings for the custom-user-model scenario.

Used only by the dedicated pytest run that verifies django-cart
installs and operates cleanly on a project with a swapped
``AUTH_USER_MODEL``. Invoke as::

    pytest --ds=tests.settings_custom_user tests/test_cart_custom_user.py

``AUTH_USER_MODEL`` is resolved at Django's app-registry init time and
cannot be swapped mid-process, so this file must not be imported by the
default suite.
"""

from tests.settings import *  # noqa: F401, F403
from tests.settings import INSTALLED_APPS  # noqa: F401 — explicit so mypy sees it

AUTH_USER_MODEL = "custom_user_app.CustomUser"

# Inject the custom-user app before ``cart`` so its model is loaded into
# the registry by the time Django resolves Cart.user → AUTH_USER_MODEL.
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "cart"] + [
    "tests.custom_user_app",
    "cart",
]
