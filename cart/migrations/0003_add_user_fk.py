"""Adds the nullable ``Cart.user`` FK.

The FK target is ``settings.AUTH_USER_MODEL`` via
``migrations.swappable_dependency`` — NOT a hardcoded ``auth.User``.

This migration was edited in place during the P1-B fix (v3.0.13). The
original (v3.0.0) migration targeted ``auth.user`` literally, which
rendered django-cart uninstallable on any project with a swapped
``AUTH_USER_MODEL``: system checks failed with ``cart.Cart has a
relation with model auth.User, which has been swapped out``, and
``migrate`` then failed earlier with ``no such table: auth_user``
because Django skips creating ``auth_user`` under a swapped user
model.

CLAUDE.md's "never edit a shipped migration" rule yields here because
the migration itself was the bug. Projects that had already applied
the old 0003 see no state drift — Django tracks migrations by name,
not by file content, so the new file simply produces the correct
state for anyone applying it fresh. On projects where ``AUTH_USER_MODEL
== "auth.User"`` (the default), the swappable reference resolves to
the same target as the original hardcode, so the on-disk FK column is
unchanged.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cart", "0002_add_unit_price_validator"),
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="cart",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="carts",
                to=settings.AUTH_USER_MODEL,
                verbose_name="user",
            ),
        ),
    ]
