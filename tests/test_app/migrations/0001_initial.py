from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="FakeProduct",
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
                ("name", models.CharField(max_length=100)),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2, default="0.00", max_digits=10
                    ),
                ),
            ],
            options={
                "app_label": "test_app",
            },
        ),
    ]
