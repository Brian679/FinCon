from django.urls import path

from . import views as v

app_name = "payroll"
urlpatterns = [
    path("profile/", v.my_profile, name="profile"),
    path("finance/payroll/", v.payroll_home, name="payroll"),
    path("finance/payroll/salaries/", v.salaries, name="salaries"),
    path("finance/payroll/salaries/<int:user_id>/", v.salary_edit, name="salary_edit"),
    path("finance/payroll/owed/", v.arrears, name="arrears"),
    path("finance/payroll/tax/", v.tax_tables, name="tax"),
    path("finance/payroll/payslips/<uuid:pk>/", v.payslip_detail, name="payslip"),
]
