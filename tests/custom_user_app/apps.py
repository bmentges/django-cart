from django.apps import AppConfig


class CustomUserAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tests.custom_user_app"
    label = "custom_user_app"
