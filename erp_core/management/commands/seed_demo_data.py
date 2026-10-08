"""Django management command to populate the database with realistic sample ERP demo data.

Seeds:
- 5 Indian Suppliers
- 10 Indian Customers
- 25 Items (with items below reorder level)
- 30 Invoices (paid, pending, overdue)
- 15 Employees
- 8 Pending Leave Requests (plus approved/rejected requests)
- Sample Purchase Orders with Purchase Order Lines
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from django.core.management.base import BaseCommand
from django.utils import timezone

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


class Command(BaseCommand):
    """Seed demo data with realistic Indian business context."""

    help = "Seeds database with Indian business names, 30 invoices, 25 items, 5 suppliers, 15 employees, and 8 pending leave requests."

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write(self.style.NOTICE("Clearing existing demo data..."))
        LeaveRequest.objects.all().delete()
        Employee.objects.all().delete()
        PurchaseOrderLine.objects.all().delete()
        PurchaseOrder.objects.all().delete()
        Invoice.objects.all().delete()
        Item.objects.all().delete()
        Customer.objects.all().delete()
        Supplier.objects.all().delete()

        today = timezone.now().date()

        # 1. Seed 5 Indian Suppliers
        self.stdout.write("Seeding 5 Indian suppliers...")
        suppliers_data = [
            {"name": "Reliance Industrial Polymers", "phone": "+91 98201 11223", "lead_time_days": 4},
            {"name": "Tata Advanced Components", "phone": "+91 98202 22334", "lead_time_days": 6},
            {"name": "Havells Electricals India", "phone": "+91 98203 33445", "lead_time_days": 5},
            {"name": "Bharat Heavy Machinery", "phone": "+91 98204 44556", "lead_time_days": 10},
            {"name": "Godrej Logistics & Containers", "phone": "+91 98205 55667", "lead_time_days": 3},
        ]
        suppliers = [Supplier.objects.create(**data) for data in suppliers_data]

        # 2. Seed 10 Indian Customers
        self.stdout.write("Seeding 10 Indian customers...")
        customers_data = [
            {"name": "Infosys Tech Labs", "city": "Bengaluru"},
            {"name": "Wipro Digital Solutions", "city": "Bengaluru"},
            {"name": "Mahindra Auto Works", "city": "Pune"},
            {"name": "Bajaj Electricals Ltd", "city": "Mumbai"},
            {"name": "Larsen & Toubro Construction", "city": "Chennai"},
            {"name": "Sun Pharma Enterprises", "city": "Vadodara"},
            {"name": "Apollo Hospitals Network", "city": "Hyderabad"},
            {"name": "Zomato Logistics Hub", "city": "Gurugram"},
            {"name": "Swiggy Distribution Center", "city": "Bengaluru"},
            {"name": "Delhivery Parcel Fleet", "city": "Delhi"},
        ]
        customers = [Customer.objects.create(**data) for data in customers_data]

        # 3. Seed 25 Items (with some below reorder level)
        self.stdout.write("Seeding 25 items (some below reorder level)...")
        # Format: (sku, name, stock_qty, reorder_level, supplier_index)
        items_specs = [
            # Low stock items (stock_qty <= reorder_level)
            ("SKU-IND-001", "Industrial Copper Busbar 100A", 3, 10, 0),    # LOW
            ("SKU-IND-002", "Heavy-Duty Servo Motor 2HP", 2, 8, 1),       # LOW
            ("SKU-IND-003", "Precision Ball Bearings 6204", 4, 15, 3),    # LOW
            ("SKU-IND-004", "Polypropylene Resin Granules 25kg", 5, 20, 0),# LOW
            ("SKU-IND-005", "Microcontroller Core PCB v2", 4, 12, 1),     # LOW
            ("SKU-IND-006", "High-Pressure Hydraulic Seal 50mm", 1, 6, 3),# LOW
            # Normal / well-stocked items
            ("SKU-IND-007", "LED Industrial High-Bay Fixture", 45, 10, 2),
            ("SKU-IND-008", "Stepping Motor Driver Board 24V", 35, 8, 1),
            ("SKU-IND-009", "Stainless Steel Flange Bolt M12", 250, 50, 3),
            ("SKU-IND-010", "Modular Terminal Blocks Din-Rail", 180, 40, 2),
            ("SKU-IND-011", "Industrial Cable Ties 300mm", 500, 100, 2),
            ("SKU-IND-012", "Pneumatic Solenoid Valve 5/2", 28, 10, 3),
            ("SKU-IND-013", "Digital Multimeter Fluke Model", 18, 5, 2),
            ("SKU-IND-014", "Heavy duty Corrugated Pallet Box", 80, 25, 4),
            ("SKU-IND-015", "Heat Shrink Sleeving 10mm Roll", 60, 15, 2),
            ("SKU-IND-016", "Linear Motion Slide Rail 400mm", 22, 10, 1),
            ("SKU-IND-017", "Three-Phase Circuit Breaker 63A", 30, 8, 2),
            ("SKU-IND-018", "Rotary Optical Encoder 1024-PPR", 24, 6, 1),
            ("SKU-IND-019", "Industrial Rubber Conveyor Belt", 15, 5, 4),
            ("SKU-IND-020", "Synthetic Gear Oil Grade-320 20L", 25, 8, 0),
            ("SKU-IND-021", "Tungsten Carbide Cutting Insert", 110, 20, 3),
            ("SKU-IND-022", "High-Temperature Ceramic Terminal", 75, 20, 2),
            ("SKU-IND-023", "Aluminium Extrusion Profile 40x40", 40, 15, 1),
            ("SKU-IND-024", "Steel Security Seal Wire Barcode", 320, 50, 4),
            ("SKU-IND-025", "Insulated Safety Hand Gloves 11kV", 55, 15, 0),
        ]

        items = []
        for sku, name, stock_qty, reorder_level, sup_idx in items_specs:
            item = Item.objects.create(
                sku=sku,
                name=name,
                stock_qty=stock_qty,
                reorder_level=reorder_level,
                supplier=suppliers[sup_idx],
            )
            items.append(item)

        # 4. Seed 30 Invoices (paid, pending, overdue)
        self.stdout.write("Seeding 30 invoices...")
        statuses = [
            "paid", "pending", "overdue", "pending", "paid",
            "overdue", "pending", "paid", "pending", "pending",
            "paid", "overdue", "pending", "paid", "pending",
            "overdue", "paid", "pending", "paid", "pending",
            "pending", "overdue", "paid", "pending", "paid",
            "overdue", "pending", "pending", "paid", "pending",
        ]
        amounts = [
            Decimal("45000.00"), Decimal("125000.50"), Decimal("82000.00"), Decimal("34500.00"), Decimal("67000.00"),
            Decimal("189000.00"), Decimal("52000.00"), Decimal("94000.00"), Decimal("112000.00"), Decimal("27500.00"),
            Decimal("310000.00"), Decimal("15600.00"), Decimal("78500.00"), Decimal("225000.00"), Decimal("41000.00"),
            Decimal("165000.00"), Decimal("88000.00"), Decimal("19500.00"), Decimal("340000.00"), Decimal("62500.00"),
            Decimal("143000.00"), Decimal("95000.00"), Decimal("51000.00"), Decimal("180000.00"), Decimal("72000.00"),
            Decimal("285000.00"), Decimal("39000.00"), Decimal("118000.00"), Decimal("64000.00"), Decimal("155000.00"),
        ]

        invoices = []
        for i in range(30):
            inv_no = f"INV-2026-{100 + i + 1}"
            cust = customers[i % len(customers)]
            st = statuses[i]
            amt = amounts[i]

            if st == "paid":
                due = today - timedelta(days=10 + (i % 15))
            elif st == "overdue":
                due = today - timedelta(days=2 + (i % 20))
            else:  # pending
                due = today + timedelta(days=5 + (i % 25))

            inv = Invoice.objects.create(
                customer=cust,
                invoice_no=inv_no,
                amount=amt,
                status=st,
                due_date=due,
            )
            invoices.append(inv)

        # 5. Seed Purchase Orders and Lines
        self.stdout.write("Seeding sample purchase orders and lines...")
        po1 = PurchaseOrder.objects.create(supplier=suppliers[0], status="draft")
        PurchaseOrderLine.objects.create(po=po1, item=items[0], qty=25)
        PurchaseOrderLine.objects.create(po=po1, item=items[3], qty=50)

        po2 = PurchaseOrder.objects.create(supplier=suppliers[1], status="confirmed")
        PurchaseOrderLine.objects.create(po=po2, item=items[1], qty=15)
        PurchaseOrderLine.objects.create(po=po2, item=items[4], qty=30)

        po3 = PurchaseOrder.objects.create(supplier=suppliers[3], status="draft")
        PurchaseOrderLine.objects.create(po=po3, item=items[2], qty=40)
        PurchaseOrderLine.objects.create(po=po3, item=items[5], qty=20)

        # 6. Seed 15 Employees
        self.stdout.write("Seeding 15 employees...")
        employees_data = [
            ("Aarav Sharma", "Engineering"),
            ("Priya Patel", "Operations"),
            ("Rohan Verma", "Finance"),
            ("Sneha Iyer", "Human Resources"),
            ("Vikram Malhotra", "Sales"),
            ("Ananya Reddy", "Engineering"),
            ("Rahul Gupta", "Operations"),
            ("Neha Deshmukh", "Finance"),
            ("Karan Mehta", "Engineering"),
            ("Pooja Joshi", "Human Resources"),
            ("Aditya Nair", "Sales"),
            ("Kavita Sundaram", "Engineering"),
            ("Manpreet Singh", "Operations"),
            ("Deepa Menon", "Finance"),
            ("Amit Kulkarni", "Sales"),
        ]
        employees = [Employee.objects.create(name=name, department=dept) for name, dept in employees_data]

        # 7. Seed 8 Pending Leave Requests (plus 2 approved, 1 rejected)
        self.stdout.write("Seeding 8 pending leave requests...")
        pending_requests_data = [
            (employees[0], today + timedelta(days=3), today + timedelta(days=5), "Family function in Ahmedabad"),
            (employees[1], today + timedelta(days=7), today + timedelta(days=10), "Sister's wedding ceremony in Jaipur"),
            (employees[2], today + timedelta(days=2), today + timedelta(days=4), "Tax audit travel to Delhi office"),
            (employees[4], today + timedelta(days=5), today + timedelta(days=6), "Client escalation meeting in Pune"),
            (employees[6], today + timedelta(days=12), today + timedelta(days=15), "Annual family pilgrimage to Tirupati"),
            (employees[8], today + timedelta(days=4), today + timedelta(days=7), "Home renovation and moving assistance"),
            (employees[10], today + timedelta(days=8), today + timedelta(days=9), "Personal banking and passport renewal"),
            (employees[12], today + timedelta(days=6), today + timedelta(days=8), "Child admission counseling in Chandigarh"),
        ]
        for emp, f_date, t_date, reason in pending_requests_data:
            LeaveRequest.objects.create(
                employee=emp,
                from_date=f_date,
                to_date=t_date,
                status="pending",
                reason=reason,
            )

        # Also add a few approved and rejected requests to reflect realistic active ERP history
        LeaveRequest.objects.create(
            employee=employees[3],
            from_date=today - timedelta(days=5),
            to_date=today - timedelta(days=4),
            status="approved",
            reason="Medical consultation and dental treatment",
        )
        LeaveRequest.objects.create(
            employee=employees[5],
            from_date=today - timedelta(days=3),
            to_date=today - timedelta(days=1),
            status="approved",
            reason="Attended tech conference in Hyderabad",
        )
        LeaveRequest.objects.create(
            employee=employees[7],
            from_date=today + timedelta(days=1),
            to_date=today + timedelta(days=2),
            status="rejected",
            reason="Quarter-end close conflict - requested reschedule",
        )

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded demo data: "
            f"{len(suppliers)} Suppliers, {len(customers)} Customers, "
            f"{len(items)} Items, {len(invoices)} Invoices, "
            f"{len(employees)} Employees, 8 Pending Leave Requests."
        ))
