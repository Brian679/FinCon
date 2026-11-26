from core.crud import BaseModelForm

from .models import SalaryProfile


class SalaryForm(BaseModelForm):
    class Meta:
        model = SalaryProfile
        fields = ["grade", "currency", "basic_salary", "housing_allowance", "transport_allowance", "other_allowances", "paye", "nssa", "pension",
                  "medical_aid", "other_deductions", "payment_method", "bank_name", "bank_account", "is_active", "notes"]
