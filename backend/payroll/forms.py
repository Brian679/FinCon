from core.crud import BaseModelForm

from .models import SalaryProfile


class SalaryForm(BaseModelForm):
    class Meta:
        model = SalaryProfile
        fields = ["grade", "currency", "basic_salary", "housing_allowance", "transport_allowance", "other_allowances", "pension", "medical_aid",
                  "other_deductions", "auto_tax", "tax_credits", "paye", "nssa", "payment_method", "bank_name", "bank_account", "is_active", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["paye"].help_text = "Only used when automatic PAYE is switched off"
        self.fields["nssa"].help_text = "Only used when automatic PAYE is switched off"
        self.fields["paye"].required = self.fields["nssa"].required = False
