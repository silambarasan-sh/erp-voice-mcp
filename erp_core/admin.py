"""Admin configuration for ERP Core models."""

from django.contrib import admin
from erp_core.models import (
    Customer,
    Supplier,
    Item,
    Invoice,
    PurchaseOrder,
    PurchaseOrderLine,
    Employee,
    LeaveRequest,
)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "city")
    search_fields = ("name", "city")


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone", "lead_time_days")
    search_fields = ("name", "phone")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "stock_qty", "reorder_level", "supplier")
    list_filter = ("supplier",)
    search_fields = ("sku", "name")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_no", "customer", "amount", "status", "due_date", "created_at")
    list_filter = ("status", "due_date")
    search_fields = ("invoice_no", "customer__name")


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "supplier", "status", "created_at")
    list_filter = ("status",)
    inlines = [PurchaseOrderLineInline]


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "department")
    list_filter = ("department",)
    search_fields = ("name", "department")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "employee", "from_date", "to_date", "status")
    list_filter = ("status", "from_date")
    search_fields = ("employee__name", "reason")
