from datetime import date
from decimal import Decimal

from django.db import migrations

BANDS = [("0", "100", "0"), ("100", "300", "20"), ("300", "1000", "25"), ("1000", "2000", "30"), ("2000", "3000", "35"), ("3000", None, "40")]


def load(apps, schema_editor):
    TaxTable = apps.get_model("payroll", "TaxTable")
    TaxBand = apps.get_model("payroll", "TaxBand")
    if TaxTable.objects.filter(currency="USD").exists():
        return
    t = TaxTable.objects.create(name="ZIMRA PAYE – USD monthly", currency="USD", effective_from=date(2025, 1, 1),
                                source="Commonly published ZIMRA USD monthly table – CHECK against zimra.co.zw before the first live payroll")
    for lo, hi, rate in BANDS:
        TaxBand.objects.create(table=t, lower=Decimal(lo), upper=Decimal(hi) if hi else None, rate=Decimal(rate))


class Migration(migrations.Migration):
    dependencies = [("payroll", "0002_payslip_aids_levy_payslip_income_tax_and_more")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
