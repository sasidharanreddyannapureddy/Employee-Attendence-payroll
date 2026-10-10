import random
from datetime import time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from payroll import services
from payroll.models import Attendance, Employee, LeaveRequest


class Command(BaseCommand):
    help = "Create demo employees and attendance for last month and this month."

    def handle(self, *args, **options):
        if Employee.objects.exists():
            self.stdout.write("Employees already exist; nothing seeded.")
            return

        demo = [
            ("Anita Rao", "Software Engineer", 45000),
            ("Ravi Kumar", "Accountant", 32000),
            ("Sneha Patel", "HR Executive", 36000),
            ("Imran Shaikh", "Sales Manager", 52000),
            ("Lakshmi Devi", "Office Assistant", 18000),
        ]
        emps = [Employee.objects.create(name=n, designation=d, basic_salary=s) for n, d, s in demo]

        rng = random.Random(7)
        today = timezone.localdate()
        start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        records, day = [], start
        while day < today:
            if day.weekday() != 6:  # skip Sundays
                for e in emps:
                    r = rng.random()
                    if r < 0.08:
                        records.append(Attendance(emp=e, date=day, status="A"))
                    elif r < 0.13:
                        records.append(Attendance(emp=e, date=day, status="L"))
                    else:
                        has_overtime = rng.random() < 0.18
                        records.append(Attendance(
                            emp=e, date=day, status="P",
                            check_in=time(9, rng.randint(0, 30)),
                            check_out=time(18 if has_overtime else 17, rng.randint(0, 45)),
                        ))
            day += timedelta(days=1)
        Attendance.objects.bulk_create(records)

        approved = LeaveRequest.objects.create(
            emp=emps[2],
            start_date=today.replace(day=3),
            end_date=today.replace(day=4),
            reason="Family function",
        )
        services.approve_leave_request(approved)
        LeaveRequest.objects.create(
            emp=emps[0],
            start_date=today.replace(day=15),
            end_date=today.replace(day=16),
            reason="Medical appointment",
        )
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(emps)} employees, {len(records)} attendance rows, and demo leave requests."
        ))
