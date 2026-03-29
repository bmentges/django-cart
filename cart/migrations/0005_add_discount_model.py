import django.db.models.deletion
from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cart", "0004_add_item_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="Discount",
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
                    "code",
                    models.CharField(
                        help_text="Unique code to apply the discount",
                        max_length=50,
                        unique=True,
                        verbose_name="discount code",
                    ),
                ),
                (
                    "discount_type",
                    models.CharField(
                        choices=[("percent", "Percentage"), ("fixed", "Fixed Amount")],
                        default="percent",
                        max_length=10,
                        verbose_name="discount type",
                    ),
                ),
                (
                    "value",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Percentage or fixed amount depending on discount type",
                        max_digits=10,
                        validators=[MinValueValidator(0)],
                        verbose_name="discount value",
                    ),
                ),
                (
                    "min_cart_value",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Minimum cart subtotal required to apply discount",
                        max_digits=10,
                        null=True,
                        validators=[MinValueValidator(0)],
                        verbose_name="minimum cart value",
                    ),
                ),
                (
                    "max_uses",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Maximum number of times this discount can be used (null for unlimited)",
                        null=True,
                        verbose_name="maximum uses",
                    ),
                ),
                (
                    "current_uses",
                    models.PositiveIntegerField(default=0, verbose_name="current uses"),
                ),
                (
                    "active",
                    models.BooleanField(
                        default=True,
                        help_text="Whether this discount can be used",
                        verbose_name="active",
                    ),
                ),
                (
                    "valid_from",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="valid from"
                    ),
                ),
                (
                    "valid_until",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="valid until"
                    ),
                ),
            ],
            options={
                "verbose_name": "discount",
                "verbose_name_plural": "discounts",
            },
        ),
        migrations.AddField(
            model_name="cart",
            name="discount",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="applied_carts",
                to="cart.discount",
                verbose_name="applied discount",
            ),
        ),
    ]
