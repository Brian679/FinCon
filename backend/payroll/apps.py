from django.apps import AppConfig


class PayrollConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payroll"
    verbose_name = "Payroll & salaries"

    def ready(self):
        from core import audit

        from . import models as m

        # every salary change, payslip and salary payment is in the tamper-evident audit trail
        audit.register(m.SalaryProfile, m.Payslip, m.SalaryPayment)
