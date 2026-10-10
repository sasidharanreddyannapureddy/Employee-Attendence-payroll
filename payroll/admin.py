from django.contrib import admin

from .models import Attendance, Employee, LeaveRequest, Salary


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "designation", "basic_salary")
    search_fields = ("name", "designation")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("emp", "date", "status", "check_in", "check_out")
    list_filter = ("status", "date")
    date_hierarchy = "date"


@admin.register(Salary)
class SalaryAdmin(admin.ModelAdmin):
    list_display = ("emp", "month", "year", "gross", "deduction", "overtime_pay", "net")
    list_filter = ("year", "month")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("emp", "start_date", "end_date", "days", "status", "requested_at", "reviewed_at")
    list_filter = ("status", "start_date")
    search_fields = ("emp__name", "reason")
