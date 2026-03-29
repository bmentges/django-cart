from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cart", "0003_add_user_fk"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="item",
            index=models.Index(fields=["cart", "content_type", "object_id"], name="cart_item_cart_id_content"),
        ),
    ]
