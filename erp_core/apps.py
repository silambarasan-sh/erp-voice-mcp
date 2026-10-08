"""App configuration for erp_core."""

from django.apps import AppConfig

class ErpCoreConfig(AppConfig):
    """Configuration for the ERP core application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "erp_core"
    verbose_name = "ERP Core System"
