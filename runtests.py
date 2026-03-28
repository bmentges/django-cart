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
            "django.contrib.admin",
            "django.contrib.sessions",
            "django.contrib.messages",
            "cart",
            "tests.test_app",
        ],
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
        ],
        TEMPLATES=[
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": [],
                "APP_DIRS": True,
                "OPTIONS": {
                    "context_processors": [
                        "django.template.context_processors.request",
                        "django.contrib.auth.context_processors.auth",
                        "django.contrib.messages.context_processors.messages",
                    ],
                },
            },
        ],
        USE_TZ=True,
        DEFAULT_AUTO_FIELD="django.db.models.AutoField",
    )

django.setup()

if __name__ == "__main__":
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, failfast=False)
    module = sys.argv[1] if len(sys.argv) > 1 else "tests"
    failures = test_runner.run_tests([module])
    sys.exit(bool(failures))
    