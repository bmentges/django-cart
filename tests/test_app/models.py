from django.db import models


class FakeProduct(models.Model):
    """Lightweight product model used only in tests."""
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2, default="0.00")

    class Meta:
        app_label = "test_app"

    def __str__(self):
        return self.name
