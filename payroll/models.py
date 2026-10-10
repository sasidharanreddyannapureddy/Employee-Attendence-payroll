import datetime as dt

from django.db import models


class Employee(models.Model):
    name = models.CharField(max_length=100)
    designation = models.CharField(max_length=100)
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Attendance(models.Model):
    PRESENT, ABSENT, LEAVE = "P", "A", "L"
    STATUS_CHOICES = [(PRESENT, "Present"), (ABSENT, "Absent"), (LEAVE, "Leave")]

    emp = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField()
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=PRESENT)
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["emp", "date"], name="one_record_per_employee_per_day"),
        ]

    def __str__(self):
        return f"{self.emp} {self.date} {self.status}"

    @property
    def hours(self):
        if self.check_in and self.check_out:
            today = dt.date.today()
            delta = dt.datetime.combine(today, self.check_out) - dt.datetime.combine(today, self.check_in)
            return round(delta.total_seconds() / 3600, 2)
        return None


class LeaveRequest(models.Model):
    PENDING, APPROVED, REJECTED = "P", "A", "R"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    ]

    emp = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_requests")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=PENDING)
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer_note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["status", "-requested_at"]

    def __str__(self):
        return f"{self.emp} {self.start_date} to {self.end_date} ({self.get_status_display()})"

    @property
    def days(self):
        return (self.end_date - self.start_date).days + 1


class Salary(models.Model):
    emp = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="salaries")
    month = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    gross = models.DecimalField(max_digits=10, decimal_places=2)
    deduction = models.DecimalField(max_digits=10, decimal_places=2)
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    overtime_pay = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net = models.DecimalField(max_digits=10, decimal_places=2)
    generated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(fields=["emp", "month", "year"], name="one_salary_per_employee_per_month"),
        ]

    def __str__(self):
        return f"{self.emp} {self.month}/{self.year}"
