from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("cart", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.AlterField(
            model_name="item",
            name="unit_price",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=18,
                validators=[MinValueValidator(Decimal("0.00"))],
                verbose_name="unit price",
            ),
        ),
    ]
