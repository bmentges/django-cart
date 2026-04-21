import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="Cart",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "creation_date",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        verbose_name="creation date",
                    ),
                ),
                (
                    "checked_out",
                    models.BooleanField(default=False, verbose_name="checked out"),
                ),
            ],
            options={
                "verbose_name": "cart",
                "verbose_name_plural": "carts",
                "ordering": ("-creation_date",),
            },
        ),
        migrations.CreateModel(
            name="Item",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("quantity", models.PositiveIntegerField(verbose_name="quantity")),
                (
                    "unit_price",
                    models.DecimalField(
                        decimal_places=2, max_digits=18, verbose_name="unit price"
                    ),
                ),
                ("object_id", models.PositiveIntegerField()),
                (
                    "cart",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="cart.Cart",
                        verbose_name="cart",
                    ),
                ),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="contenttypes.ContentType",
                    ),
                ),
            ],
            options={
                "verbose_name": "item",
                "verbose_name_plural": "items",
                "ordering": ("cart",),
                "unique_together": {("cart", "content_type", "object_id")},
            },
        ),
    ]
