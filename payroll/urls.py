from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("checkin/<int:emp_id>/", views.check_in, name="check_in"),
    path("checkout/<int:emp_id>/", views.check_out, name="check_out"),
    path("attendance/mark/", views.mark_attendance, name="mark_attendance"),
    path("leave/", views.leave_requests, name="leave_requests"),
    path("leave/<int:leave_id>/<str:decision>/", views.review_leave, name="review_leave"),
    path("report/", views.report, name="report"),
    path("report/generate/", views.generate_salaries, name="generate_salaries"),
    path("payslip/<int:emp_id>/", views.payslip, name="payslip"),
    path("payslip/<int:emp_id>/pdf/", views.payslip_pdf, name="payslip_pdf"),
    path("employees/", views.EmployeeList.as_view(), name="employee_list"),
    path("employees/add/", views.EmployeeCreate.as_view(), name="employee_add"),
    path("employees/<int:pk>/edit/", views.EmployeeUpdate.as_view(), name="employee_edit"),
    path("employees/<int:pk>/delete/", views.EmployeeDelete.as_view(), name="employee_delete"),
]
