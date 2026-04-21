"""Schema polish: index clean_carts filter columns + gate Item.quantity ≥ 1.

``cart.models.Cart.checked_out`` and ``Cart.creation_date`` gain
``db_index=True``. The ``clean_carts`` management command filters on
both (``creation_date__lt=cutoff AND checked_out=False``) and does so
on potentially-large tables; without an index each invocation falls
back to a sequential scan. SQLite and every production backend we
support handles ``db_index=True`` identically.

``cart.models.Item.quantity`` gains ``MinValueValidator(1)``. The
:class:`cart.cart.Cart` API already rejected ``quantity < 1`` at
``.add()`` / ``.update()`` but a direct
``Item.objects.create(..., quantity=0)`` bypassed that contract; now
``full_clean()`` catches the mismatch. A DB-level ``CHECK`` is not
added here — the ``CheckConstraint(check=…)`` / ``…(condition=…)``
kwarg renamed between Django 5.0 and 6.0 and the supported matrix
spans both; the DB constraint will follow once 4.2 drops off.
"""

import django.utils.timezone
from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cart", "0005_add_discount_model"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cart",
            name="checked_out",
            field=models.BooleanField(
                db_index=True,
                default=False,
                verbose_name="checked out",
            ),
        ),
        migrations.AlterField(
            model_name="cart",
            name="creation_date",
            field=models.DateTimeField(
                db_index=True,
                default=django.utils.timezone.now,
                verbose_name="creation date",
            ),
        ),
        migrations.AlterField(
            model_name="item",
            name="quantity",
            field=models.PositiveIntegerField(
                validators=[MinValueValidator(1)],
                verbose_name="quantity",
            ),
        ),
    ]
