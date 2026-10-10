import calendar
from datetime import datetime
from io import BytesIO

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from . import services
from .forms import LeaveRequestForm
from .models import Attendance, Employee, LeaveRequest

MONTHS = [(i, calendar.month_name[i]) for i in range(1, 13)]


def get_period(request):
    """Read ?month=&year= from the query string, falling back to the current month."""
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
    except ValueError:
        return today.year, today.month
    if not (1 <= month <= 12 and 1900 <= year <= 9999):
        return today.year, today.month
    return year, month


def report_url(year, month):
    return f"{reverse('report')}?year={year}&month={month}"


# ---------- Dashboard: daily check-in / check-out ----------

def dashboard(request):
    today = timezone.localdate()
    records = {a.emp_id: a for a in Attendance.objects.filter(date=today)}
    rows = [{"emp": e, "rec": records.get(e.id)} for e in Employee.objects.all()]
    stats = {
        "employees": Employee.objects.count(),
        "present": Attendance.objects.filter(date=today, status=Attendance.PRESENT).count(),
        "leave": Attendance.objects.filter(date=today, status=Attendance.LEAVE).count(),
        "pending_leave": LeaveRequest.objects.filter(status=LeaveRequest.PENDING).count(),
    }
    return render(request, "payroll/dashboard.html", {"rows": rows, "today": today, "stats": stats})


@require_POST
def check_in(request, emp_id):
    emp = get_object_or_404(Employee, pk=emp_id)
    now = timezone.localtime().time().replace(microsecond=0)
    rec, created = Attendance.objects.get_or_create(
        emp=emp, date=timezone.localdate(),
        defaults={"status": Attendance.PRESENT, "check_in": now},
    )
    if created:
        messages.success(request, f"{emp.name} checked in at {now:%H:%M}.")
    elif rec.check_in is None:
        rec.status, rec.check_in = Attendance.PRESENT, now
        rec.save()
        messages.success(request, f"{emp.name} checked in at {now:%H:%M}.")
    else:
        messages.info(request, f"{emp.name} has already checked in today.")
    return redirect("dashboard")


@require_POST
def check_out(request, emp_id):
    emp = get_object_or_404(Employee, pk=emp_id)
    now = timezone.localtime().time().replace(microsecond=0)
    rec = Attendance.objects.filter(emp=emp, date=timezone.localdate()).first()
    if rec is None or rec.check_in is None:
        messages.error(request, f"{emp.name} has not checked in today.")
    else:
        rec.check_out = now
        rec.save()
        messages.success(request, f"{emp.name} checked out at {now:%H:%M}.")
    return redirect("dashboard")


# ---------- Bulk attendance marking for any date ----------

def mark_attendance(request):
    raw = request.POST.get("date") or request.GET.get("date")
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        day = timezone.localdate()

    employees = Employee.objects.all()
    valid = {code for code, _ in Attendance.STATUS_CHOICES}

    if request.method == "POST":
        for e in employees:
            status = request.POST.get(f"status_{e.id}")
            if status in valid:
                defaults = {"status": status}
                if status != Attendance.PRESENT:
                    defaults.update({"check_in": None, "check_out": None})
                Attendance.objects.update_or_create(emp=e, date=day, defaults=defaults)
        messages.success(request, f"Attendance saved for {day:%d %b %Y}.")
        return redirect(f"{reverse('mark_attendance')}?date={day.isoformat()}")

    existing = {a.emp_id: a.status for a in Attendance.objects.filter(date=day)}
    rows = [{"emp": e, "status": existing.get(e.id, "")} for e in employees]
    return render(request, "payroll/mark_attendance.html", {
        "rows": rows, "day": day, "statuses": Attendance.STATUS_CHOICES,
    })


# ---------- Monthly report, salary generation, salary slip ----------

def report(request):
    year, month = get_period(request)
    rows, totals = services.build_report(year, month)
    return render(request, "payroll/report.html", {
        "rows": rows, "totals": totals, "year": year, "month": month,
        "month_name": calendar.month_name[month], "months": MONTHS,
    })


def leave_requests(request):
    if request.method == "POST":
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave = form.save()
            messages.success(request, f"Leave request created for {leave.emp.name}.")
            return redirect("leave_requests")
    else:
        form = LeaveRequestForm()

    requests = LeaveRequest.objects.select_related("emp")
    pending_count = requests.filter(status=LeaveRequest.PENDING).count()
    return render(request, "payroll/leave_requests.html", {
        "form": form, "requests": requests, "pending_count": pending_count,
    })


@require_POST
def review_leave(request, leave_id, decision):
    leave = get_object_or_404(LeaveRequest, pk=leave_id)
    if leave.status != LeaveRequest.PENDING:
        messages.info(request, "This leave request has already been reviewed.")
        return redirect("leave_requests")

    if decision == "approve":
        services.approve_leave_request(leave)
        messages.success(request, f"Approved leave for {leave.emp.name} and updated attendance.")
    elif decision == "reject":
        leave.status = LeaveRequest.REJECTED
        leave.reviewed_at = timezone.now()
        leave.save(update_fields=["status", "reviewed_at"])
        messages.success(request, f"Rejected leave for {leave.emp.name}.")
    else:
        messages.error(request, "Invalid leave action.")
    return redirect("leave_requests")


@require_POST
def generate_salaries(request):
    try:
        year, month = int(request.POST["year"]), int(request.POST["month"])
        if not (1 <= month <= 12 and 1900 <= year <= 9999):
            raise ValueError
    except (KeyError, ValueError):
        messages.error(request, "Invalid month or year.")
        return redirect("report")
    count = 0
    for emp in Employee.objects.all():
        services.calculate_salary(emp, year, month)
        count += 1
    messages.success(request, f"Salary saved for {count} employees ({calendar.month_name[month]} {year}).")
    return redirect(report_url(year, month))


def payslip(request, emp_id):
    emp = get_object_or_404(Employee, pk=emp_id)
    year, month = get_period(request)
    data = services.calculate_salary(emp, year, month)
    return render(request, "payroll/payslip.html", {
        "emp": emp, "year": year, "month": month,
        "month_name": calendar.month_name[month], **data,
    })


def payslip_pdf(request, emp_id):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    emp = get_object_or_404(Employee, pk=emp_id)
    year, month = get_period(request)
    data = services.calculate_salary(emp, year, month)
    salary = data["salary"]

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Salary Slip - {emp.name}",
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("SALARY SLIP", styles["Title"]),
        Paragraph(f"{calendar.month_name[month]} {year}", styles["Heading3"]),
        Spacer(1, 8 * mm),
    ]
    employee_table = Table([
        ["Employee", emp.name, "Employee ID", str(emp.id)],
        ["Designation", emp.designation, "Days in month", str(data["days_in_month"])],
    ], colWidths=[32 * mm, 62 * mm, 32 * mm, 42 * mm])
    employee_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f3f4f6")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([employee_table, Spacer(1, 8 * mm)])

    pay_table = Table([
        ["Attendance", "Days"],
        ["Present", data["present"]],
        ["Leave", data["leave"]],
        ["Absent", data["absent"]],
        ["", ""],
        ["Earnings and deductions", "Amount"],
        ["Basic salary", f"Rs. {salary.gross:,.2f}"],
        ["Per day pay", f"Rs. {data['per_day']:,.2f}"],
        ["Overtime hours", f"{salary.overtime_hours:,.2f}"],
        ["Overtime pay", f"Rs. {salary.overtime_pay:,.2f}"],
        [f"Deduction ({data['absent']} absent day(s))", f"- Rs. {salary.deduction:,.2f}"],
        ["Net salary", f"Rs. {salary.net:,.2f}"],
    ], colWidths=[108 * mm, 60 * mm])
    pay_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 5), (-1, 5), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 5), (-1, 5), colors.white),
        ("BACKGROUND", (0, 11), (-1, 11), colors.HexColor("#d1fae5")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 5), (-1, 5), "Helvetica-Bold"),
        ("FONTNAME", (0, 11), (-1, 11), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(pay_table)
    story.append(Spacer(1, 18 * mm))
    story.append(Paragraph("Employee signature ____________________     Authorised signatory ____________________", styles["Normal"]))
    doc.build(story)

    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    filename = f"salary-slip-{emp.id}-{year}-{month:02d}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ---------- Employee master data (CRUD) ----------

class EmployeeList(ListView):
    model = Employee
    template_name = "payroll/employee_list.html"
    context_object_name = "employees"


class EmployeeCreate(CreateView):
    model = Employee
    fields = ["name", "designation", "basic_salary"]
    template_name = "payroll/employee_form.html"
    success_url = reverse_lazy("employee_list")


class EmployeeUpdate(UpdateView):
    model = Employee
    fields = ["name", "designation", "basic_salary"]
    template_name = "payroll/employee_form.html"
    success_url = reverse_lazy("employee_list")


class EmployeeDelete(DeleteView):
    model = Employee
    template_name = "payroll/employee_confirm_delete.html"
    success_url = reverse_lazy("employee_list")
