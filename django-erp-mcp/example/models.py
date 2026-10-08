"""Example Django models demonstrating django-erp-mcp exposure."""

from django.db import models


class Customer(models.Model):
    """Sample Customer model."""
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "example_app"

    def __str__(self) -> str:
        return f"{self.name} ({self.city})"


class Invoice(models.Model):
    """Sample Invoice model."""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="invoices")
    invoice_no = models.CharField(max_length=64, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, default="pending")
    due_date = models.DateField()

    class Meta:
        app_label = "example_app"

    def __str__(self) -> str:
        return f"{self.invoice_no}: ₹{self.amount} [{self.status}]"
