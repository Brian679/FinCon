"""PAYE as ZIMRA works it out for a month:

    taxable income = gross pay − pension (up to the allowed maximum) − NSSA contribution
    income tax     = tax on taxable income from the bands (each slice at its own rate) − tax credits
    AIDS levy      = 3 % of the income tax
    PAYE           = income tax + AIDS levy
    NSSA           = 4.5 % of pay, up to the insurable earnings ceiling

The bands, rates and limits come from the TaxTable in force, which the Treasurer keeps in line
with ZIMRA's published tables – nothing is hard-coded here.
"""
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

ZERO = Decimal("0.00")


def q(v):
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class TaxResult:
    gross: Decimal
    nssa: Decimal
    pension_allowed: Decimal
    taxable: Decimal
    tax_before_credits: Decimal
    credits: Decimal
    income_tax: Decimal
    aids_levy: Decimal
    paye: Decimal
    table: str


def table_for(currency="USD", on=None):
    from .models import TaxTable

    on = on or timezone.localdate()
    return TaxTable.objects.alive().filter(currency=currency, effective_from__lte=on).order_by("-effective_from").first()


def band_tax(taxable, bands):
    """Each slice of income is taxed at its band's rate."""
    tax = ZERO
    for b in bands:
        if taxable <= b.lower:
            break
        top = taxable if b.upper is None else min(taxable, b.upper)
        tax += (top - b.lower) * b.rate / 100
    return q(tax)


def calculate(gross, *, pension=ZERO, credits=ZERO, currency="USD", on=None, table=None):
    table = table or table_for(currency, on)
    if table is None:
        raise ValueError(f"No PAYE table for {currency} – the Treasurer must enter ZIMRA's table first.")
    gross, pension, credits = q(gross), q(pension), q(credits)
    nssa = q(min(gross, table.nssa_ceiling) * table.nssa_rate / 100)
    pension_allowed = min(pension, table.pension_cap)
    taxable = max(ZERO, gross - pension_allowed - nssa)
    before = band_tax(taxable, list(table.bands.all()))
    income_tax = max(ZERO, before - credits)
    levy = q(income_tax * table.aids_levy_rate / 100)
    return TaxResult(gross, nssa, pension_allowed, taxable, before, credits, income_tax, levy, income_tax + levy, str(table))


# The table most Zimbabwean payroll systems use for USD salaries (monthly). Loaded as the starting
# point and marked "not yet checked": the Treasurer must confirm it against ZIMRA's published table.
DEFAULT_USD_BANDS = [("0", "100", "0"), ("100", "300", "20"), ("300", "1000", "25"), ("1000", "2000", "30"), ("2000", "3000", "35"),
                     ("3000", None, "40")]


def ensure_default_table():
    from .models import TaxBand, TaxTable

    if TaxTable.objects.filter(currency="USD").exists():
        return None
    t = TaxTable.objects.create(name="ZIMRA PAYE – USD monthly", currency="USD", effective_from=date(2025, 1, 1),
                                source="Commonly published ZIMRA USD monthly table – CHECK against zimra.co.zw before the first live payroll")
    for lo, hi, rate in DEFAULT_USD_BANDS:
        TaxBand.objects.create(table=t, lower=Decimal(lo), upper=Decimal(hi) if hi else None, rate=Decimal(rate))
    return t
