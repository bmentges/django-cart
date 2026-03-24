#!/usr/bin/env python
"""
Standalone test runner. Run from the repository root:

    python runtests.py
    python runtests.py tests.test_cart.CartAddTest
"""
import sys
import django
from django.conf import settings
from django.test.utils import get_runner

if not settings.configured:
    settings.configure(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "cart",
        ],
        USE_TZ=True,
        DEFAULT_AUTO_FIELD="django.db.models.AutoField",
    )

django.setup()

# Register FakeProduct so ContentType can resolve it
from tests.test_cart import FakeProduct  # noqa: E402  (must come after setup)
from django.contrib.contenttypes.models import ContentType  # noqa: E402

if __name__ == "__main__":
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, failfast=False)
    module = sys.argv[1] if len(sys.argv) > 1 else "tests"
    failures = test_runner.run_tests([module])
    sys.exit(bool(failures))
