"""Tests for HR Leave domain services and operations."""

import pytest
from datetime import date, timedelta
from erp_core.models import Employee, LeaveRequest
from erp_core.services import HRLeaveService


@pytest.mark.django_db
def test_get_employee_leave_summary():
    """Verify querying employee leave summary by name."""
    res = HRLeaveService.get_employee_leave_summary("Aarav Sharma")
    assert res["success"] is True
    assert res["employee"]["name"] == "Aarav Sharma"
    assert "Engineering" in res["voice_summary"]

    missing = HRLeaveService.get_employee_leave_summary("Nonexistent Person")
    assert missing["success"] is False
    assert "could not find" in missing["voice_summary"].lower()


@pytest.mark.django_db
def test_request_leave_success():
    """Verify submitting a new leave request."""
    today = date.today()
    start = (today + timedelta(days=10)).isoformat()
    end = (today + timedelta(days=12)).isoformat()

    res = HRLeaveService.request_leave(
        employee_name="Priya Patel",
        from_date_str=start,
        to_date_str=end,
        reason="Family event in Ahmedabad",
    )
    assert res["success"] is True
    req = res["leave_request"]
    assert req["status"] == "pending"
    assert "pending approval" in res["voice_summary"].lower()


@pytest.mark.django_db
def test_list_pending_leave_requests():
    """Verify listing all pending leave requests (seeded 8 pending requests)."""
    res = HRLeaveService.list_pending_leave_requests()
    assert res["count"] == 8
    assert len(res["pending_requests"]) == 8
    assert "8 pending employee leave requests" in res["voice_summary"]


@pytest.mark.django_db
def test_decide_leave_request_approval():
    """Verify approving a leave request."""
    req = LeaveRequest.objects.filter(status="pending").first()
    res = HRLeaveService.decide_leave_request(request_id=req.id, approve=True)
    assert res["success"] is True
    assert res["leave_request"]["status"] == "approved"
    assert "approved" in res["voice_summary"].lower()

    req.refresh_from_db()
    assert req.status == "approved"


@pytest.mark.django_db
def test_decide_leave_request_rejection():
    """Verify rejecting a leave request."""
    req = LeaveRequest.objects.filter(status="pending").first()
    res = HRLeaveService.decide_leave_request(request_id=req.id, approve=False)
    assert res["success"] is True
    assert res["leave_request"]["status"] == "rejected"
    assert "rejected" in res["voice_summary"].lower()

    req.refresh_from_db()
    assert req.status == "rejected"
