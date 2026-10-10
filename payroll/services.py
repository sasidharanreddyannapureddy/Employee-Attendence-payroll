import calendar
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Q
from django.utils import timezone

from .models import Attendance, Employee, LeaveRequest, Salary

TWO_PLACES = Decimal("0.01")
STANDARD_DAY_HOURS = Decimal("8.00")
OVERTIME_MULTIPLIER = Decimal("1.50")


def month_bounds(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def decimal_hours(attendance):
    if not attendance.check_in or not attendance.check_out:
        return Decimal("0")
    started = datetime.combine(attendance.date, attendance.check_in)
    ended = datetime.combine(attendance.date, attendance.check_out)
    if ended < started:
        ended += timedelta(days=1)
    hours = Decimal(str((ended - started).total_seconds() / 3600))
    return hours.quantize(TWO_PLACES, ROUND_HALF_UP)


def overtime_hours_for(attendance):
    if attendance.status != Attendance.PRESENT:
        return Decimal("0")
    extra = decimal_hours(attendance) - STANDARD_DAY_HOURS
    return max(extra, Decimal("0")).quantize(TWO_PLACES, ROUND_HALF_UP)


def monthly_overtime_hours(emp, first, last):
    records = Attendance.objects.filter(
        emp=emp,
        date__range=(first, last),
        status=Attendance.PRESENT,
        check_in__isnull=False,
        check_out__isnull=False,
    )
    total = sum((overtime_hours_for(record) for record in records), Decimal("0"))
    return total.quantize(TWO_PLACES, ROUND_HALF_UP)


def compute_pay(basic, days_in_month, absent_days, overtime_hours=Decimal("0")):
    """Net pay includes absence deductions and overtime above 8 hours/day."""
    basic = Decimal(basic)
    overtime_hours = Decimal(overtime_hours)
    per_day = (basic / Decimal(days_in_month)).quantize(TWO_PLACES, ROUND_HALF_UP)
    hourly = (per_day / STANDARD_DAY_HOURS).quantize(TWO_PLACES, ROUND_HALF_UP)
    overtime_rate = (hourly * OVERTIME_MULTIPLIER).quantize(TWO_PLACES, ROUND_HALF_UP)
    overtime_pay = (overtime_rate * overtime_hours).quantize(TWO_PLACES, ROUND_HALF_UP)
    deduction = (basic * absent_days / Decimal(days_in_month)).quantize(TWO_PLACES, ROUND_HALF_UP)
    deduction = min(deduction, basic)  # never deduct more than the basic salary
    net = basic - deduction + overtime_pay
    return per_day, deduction, overtime_rate, overtime_pay, net


def approve_leave_request(leave_request):
    leave_request.status = LeaveRequest.APPROVED
    leave_request.reviewed_at = timezone.now()
    leave_request.save(update_fields=["status", "reviewed_at"])

    day = leave_request.start_date
    while day <= leave_request.end_date:
        Attendance.objects.update_or_create(
            emp=leave_request.emp,
            date=day,
            defaults={"status": Attendance.LEAVE, "check_in": None, "check_out": None},
        )
        day += timedelta(days=1)
    return leave_request


def build_report(year, month):
    """One row per employee with present/absent/leave counts (SQL GROUP BY via annotate)."""
    first, last = month_bounds(year, month)
    days_in_month = last.day
    in_month = Q(attendance__date__gte=first, attendance__date__lte=last)

    employees = Employee.objects.annotate(
        present=Count("attendance", filter=in_month & Q(attendance__status=Attendance.PRESENT)),
        absent=Count("attendance", filter=in_month & Q(attendance__status=Attendance.ABSENT)),
        leave=Count("attendance", filter=in_month & Q(attendance__status=Attendance.LEAVE)),
    ).order_by("name")

    rows = []
    total_gross = Decimal("0")
    total_deduction = Decimal("0")
    total_overtime = Decimal("0")
    total_net = Decimal("0")
    for e in employees:
        overtime_hours = monthly_overtime_hours(e, first, last)
        per_day, deduction, overtime_rate, overtime_pay, net = compute_pay(
            e.basic_salary, days_in_month, e.absent, overtime_hours
        )
        total_gross += e.basic_salary
        total_deduction += deduction
        total_overtime += overtime_pay
        total_net += net
        rows.append({
            "emp": e, "present": e.present, "absent": e.absent, "leave": e.leave,
            "per_day": per_day, "deduction": deduction, "overtime_hours": overtime_hours,
            "overtime_rate": overtime_rate, "overtime_pay": overtime_pay, "net": net,
        })
    return rows, {
        "gross": total_gross, "deduction": total_deduction,
        "overtime": total_overtime, "net": total_net,
    }


def calculate_salary(emp, year, month):
    """Calculate and save (create or update) the Salary row for one employee and month."""
    first, last = month_bounds(year, month)
    counts = Attendance.objects.filter(emp=emp, date__range=(first, last)).aggregate(
        present=Count("id", filter=Q(status=Attendance.PRESENT)),
        absent=Count("id", filter=Q(status=Attendance.ABSENT)),
        leave=Count("id", filter=Q(status=Attendance.LEAVE)),
    )
    overtime_hours = monthly_overtime_hours(emp, first, last)
    per_day, deduction, overtime_rate, overtime_pay, net = compute_pay(
        emp.basic_salary, last.day, counts["absent"], overtime_hours
    )
    salary, _ = Salary.objects.update_or_create(
        emp=emp, month=month, year=year,
        defaults={
            "gross": emp.basic_salary,
            "deduction": deduction,
            "overtime_hours": overtime_hours,
            "overtime_pay": overtime_pay,
            "net": net,
        },
    )
    return {
        "salary": salary,
        "present": counts["present"], "absent": counts["absent"], "leave": counts["leave"],
        "days_in_month": last.day, "per_day": per_day, "overtime_rate": overtime_rate,
    }
