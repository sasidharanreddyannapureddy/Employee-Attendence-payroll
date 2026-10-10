from decimal import Decimal
from datetime import date, time

from django.test import TestCase
from django.urls import reverse

from . import services
from .models import Attendance, Employee, LeaveRequest, Salary


class SalaryTests(TestCase):
    def setUp(self):
        self.emp = Employee.objects.create(name="Test", designation="Dev", basic_salary=Decimal("30000"))

    def test_formula_30_day_month_3_absences(self):
        # September 2026 has 30 days: per day = 1000, deduction = 3000, net = 27000
        for d in (1, 2, 3):
            Attendance.objects.create(emp=self.emp, date=f"2026-09-0{d}", status="A")
        data = services.calculate_salary(self.emp, 2026, 9)
        self.assertEqual(data["per_day"], Decimal("1000.00"))
        self.assertEqual(data["salary"].deduction, Decimal("3000.00"))
        self.assertEqual(data["salary"].net, Decimal("27000.00"))
        self.assertEqual(Salary.objects.count(), 1)

    def test_report_includes_employee_without_records(self):
        rows, _ = services.build_report(2026, 9)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["absent"], 0)

    def test_overtime_added_to_salary(self):
        Attendance.objects.create(
            emp=self.emp,
            date="2026-09-04",
            status=Attendance.PRESENT,
            check_in=time(9, 0),
            check_out=time(19, 0),
        )
        data = services.calculate_salary(self.emp, 2026, 9)
        self.assertEqual(data["salary"].overtime_hours, Decimal("2.00"))
        self.assertEqual(data["salary"].overtime_pay, Decimal("375.00"))
        self.assertEqual(data["salary"].net, Decimal("30375.00"))

    def test_approved_leave_updates_attendance(self):
        leave = LeaveRequest.objects.create(
            emp=self.emp,
            start_date=date(2026, 9, 8),
            end_date=date(2026, 9, 9),
            reason="Medical appointment",
        )
        services.approve_leave_request(leave)
        self.assertEqual(Attendance.objects.filter(status=Attendance.LEAVE).count(), 2)

    def test_pages_load(self):
        for name in ("dashboard", "report", "employee_list", "mark_attendance", "leave_requests"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(self.client.get(reverse("payslip", args=[self.emp.id])).status_code, 200)
        pdf = self.client.get(reverse("payslip_pdf", args=[self.emp.id]))
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
