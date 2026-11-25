"""Load the Client Charter standards and finance master data.

    python manage.py seed_council                 # reference data only
    python manage.py seed_council --admin-password <pwd>   # also create the ICT administrator
    python manage.py seed_council --demo          # demo staff for every role + sample data (NOT for production)
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts import roles
from core import audit
from core.models import ServiceStandard
from finance.models import BankAccount, BudgetLine, ClientAccount, ExchangeRate, Property, RevenueHead, Supplier

STANDARDS = [
    # code, service, text, value, unit, digital
    ("attend-visitors", "Attend to visitors", "Within 5 minutes", 5, "MIN", False),
    ("answer-calls", "Answer telephone calls", "Within 3 rings", 3, "RINGS", False),
    ("acknowledge-emails", "Acknowledge emails", "Within 24 hours", 24, "HRS", False),
    ("respond-to-emails", "Respond to emails", "Within 3 working days", 3, "WDAYS", False),
    ("respond-to-correspondence", "Respond to correspondence", "Within 7 working days", 7, "WDAYS", False),
    ("issue-receipts", "Issue receipts", "Immediately", 0, "NOW", False),
    ("acknowledge-complaints", "Acknowledge complaints", "Within 48 hours", 48, "HRS", False),
    ("attend-water-faults", "Attend major water faults", "Within 24 hours", 24, "HRS", False),
    ("process-applications", "Process applications", "Within 30 working days", 30, "WDAYS", False),
    ("feedback-on-enquiries", "Provide feedback on enquiries", "Within 14 working days", 14, "WDAYS", False),
    ("digital-email-ack", "Email acknowledgement", "24 Hours", 24, "HRS", True),
    ("digital-email-response", "Email response", "3 Working Days", 3, "WDAYS", True),
    ("digital-social-media", "Social media response", "48 Hours", 48, "HRS", True),
    ("digital-payment-confirmation", "Payment confirmation", "Immediate", 0, "NOW", True),
    ("digital-confidentiality", "Data confidentiality", "At all times", 0, "ALWAYS", True),
    ("digital-availability", "Digital service availability", "24/7 (subject to maintenance)", 0, "ALWAYS", True),
]

BUDGET = [
    # vote, description, dept, kind, amount
    ("I-100", "Property & land rates", "FINANCE", "INCOME", 450000),
    ("I-110", "Development & unit tax levies", "FINANCE", "INCOME", 180000),
    ("I-120", "Shop & business licences", "FINANCE", "INCOME", 95000),
    ("I-130", "Rentals, fees & charges", "FINANCE", "INCOME", 60000),
    ("I-140", "Water & sanitation charges", "SOCIAL", "INCOME", 40000),
    ("I-150", "Stand sales", "SOCIAL", "INCOME", 120000),
    ("E-200", "Salaries & wages", "ADMIN", "EXPENDITURE", 520000),
    ("E-210", "Administration general expenses", "ADMIN", "EXPENDITURE", 60000),
    ("E-220", "ICT services", "ADMIN", "EXPENDITURE", 25000),
    ("E-300", "Finance operations & bank charges", "FINANCE", "EXPENDITURE", 30000),
    ("E-400", "Internal audit", "AUDIT", "EXPENDITURE", 8000),
    ("E-500", "Social services & public health", "SOCIAL", "EXPENDITURE", 45000),
    ("E-510", "Water, sanitation & hygiene", "SOCIAL", "EXPENDITURE", 70000),
    ("E-520", "Natural resources & environment", "SOCIAL", "EXPENDITURE", 20000),
    ("E-530", "Public safety & disaster risk", "SOCIAL", "EXPENDITURE", 15000),
    ("E-600", "Roads maintenance", "TECH", "EXPENDITURE", 140000),
    ("E-610", "Public lighting", "TECH", "EXPENDITURE", 25000),
    ("C-700", "Capital: roads construction", "TECH", "CAPITAL", 300000),
    ("C-710", "Capital: schools & clinics", "TECH", "CAPITAL", 200000),
    ("C-720", "Capital: boreholes", "SOCIAL", "CAPITAL", 60000),
]

REVENUE_HEADS = [
    # code, name, category, amount, frequency, vote
    ("RATES", "Property / land rates", "RATES", 0, "MONTHLY", "I-100"),
    ("DEV-LEVY", "Development levy", "LEVY", 5, "ANNUAL", "I-110"),
    ("UNIT-TAX", "Unit tax", "LEVY", 2, "ANNUAL", "I-110"),
    ("LIC-SHOP", "Shop licence", "LICENCE", 60, "ANNUAL", "I-120"),
    ("LIC-HAWKER", "Hawker / vendor licence", "LICENCE", 20, "ANNUAL", "I-120"),
    ("LIC-BUSINESS", "General business licence", "LICENCE", 80, "ANNUAL", "I-120"),
    ("LIC-LIQUOR", "Liquor licence recommendation", "LICENCE", 100, "ANNUAL", "I-120"),
    ("LIC-HEALTH", "Health / food handler certificate", "LICENCE", 15, "ANNUAL", "I-120"),
    ("LIC-TRANSPORT", "Public transport rank permit", "LICENCE", 30, "ANNUAL", "I-120"),
    ("LIC-ADVERT", "Advertising / billboard permit", "LICENCE", 50, "ANNUAL", "I-120"),
    ("MARKET", "Market stall fees", "FEES", 1, "ONCE", "I-130"),
    ("RENT", "Council property rentals", "RENT", 0, "MONTHLY", "I-130"),
    ("BUILD-PLAN", "Building plan approval fees", "FEES", 50, "ONCE", "I-130"),
    ("WATER", "Water & sanitation charges", "WATER", 0, "MONTHLY", "I-140"),
    ("STAND", "Stand purchase instalment", "LAND", 0, "ONCE", "I-150"),
    ("FINES", "By-law fines & penalties", "FINES", 0, "ONCE", "I-130"),
    ("SUNDRY", "Sundry income", "OTHER", 0, "ONCE", "I-130"),
]

DEMO_STAFF = [
    # username, first, last, role
    ("ceo", "Tendai", "Mutasa", "CEO"),
    ("ict.admin", "Farai", "Moyo", "SYSADMIN"),
    ("treasurer", "Rudo", "Sithole", "TREASURER"),
    ("accountant", "Tatenda", "Ncube", "ACCOUNTANT"),
    ("cashier", "Chipo", "Dube", "REVENUE_CLERK"),
    ("exp.clerk", "Simba", "Gumbo", "EXPENDITURE_CLERK"),
    ("admin.officer", "Nyasha", "Chikore", "ADMIN_OFFICER"),
    ("hr.officer", "Ruvimbo", "Mhlanga", "HR_OFFICER"),
    ("procurement", "Kuda", "Mapfumo", "PROCUREMENT_OFFICER"),
    ("registry", "Blessing", "Zhou", "RECORDS_CLERK"),
    ("chief.auditor", "Patience", "Mazarura", "CHIEF_AUDITOR"),
    ("auditor", "Tinashe", "Chari", "AUDITOR"),
    ("social.director", "Memory", "Sibanda", "SOCIAL_HEAD"),
    ("social.officer", "Tapiwa", "Marufu", "SOCIAL_OFFICER"),
    ("eho", "Gift", "Matanda", "HEALTH_OFFICER"),
    ("engineer", "Takudzwa", "Nyathi", "ENGINEER"),
    ("tech.officer", "Prosper", "Mlambo", "TECHNICAL_OFFICER"),
]


class Command(BaseCommand):
    help = "Seed Chipinge RDC reference data (charter standards, revenue heads, budget, banks)."

    def add_arguments(self, parser):
        parser.add_argument("--demo", action="store_true", help="Create demo users and sample data (password: Chipinge@2026)")
        parser.add_argument("--admin-username", default="ict.admin")
        parser.add_argument("--admin-password", default="")

    @transaction.atomic
    def handle(self, *args, **opts):
        User = get_user_model()
        system = User.objects.filter(is_superuser=True).first()
        token = audit.set_actor(system) if system else None
        year = timezone.localdate().year
        for code, service, text, value, unit, digital in STANDARDS:
            ServiceStandard.objects.update_or_create(code=code, defaults=dict(service=service, standard_text=text, value=value, unit=unit, is_digital=digital))
        votes = {}
        for vote, desc, dept, kind, amount in BUDGET:
            votes[vote], _ = BudgetLine.objects.get_or_create(financial_year=year, vote_code=vote,
                                                              defaults=dict(description=desc, department=dept, kind=kind, approved_amount=Decimal(amount)))
        for code, name, cat, amount, freq, vote in REVENUE_HEADS:
            RevenueHead.objects.get_or_create(code=code, defaults=dict(name=name, category=cat, default_amount=Decimal(amount), frequency=freq,
                                                                       budget_line=votes.get(vote)))
        if not BankAccount.objects.exists():
            BankAccount.objects.create(name="Main revenue account (USD)", bank="CBZ Bank Chipinge", account_number="0000000000001", currency="USD")
            BankAccount.objects.create(name="Main revenue account (ZWG)", bank="CBZ Bank Chipinge", account_number="0000000000002", currency="ZWG")
        if not ExchangeRate.objects.filter(currency="ZWG").exists():
            ExchangeRate.objects.create(currency="ZWG", rate=Decimal("26.80"))
        self.stdout.write(self.style.SUCCESS("Charter standards, revenue heads, budget votes and bank accounts loaded."))

        if opts["admin_password"]:
            u, created = User.objects.get_or_create(username=opts["admin_username"], defaults=dict(first_name="ICT", last_name="Administrator"))
            u.user_type, u.role, u.department = User.UserType.STAFF, "SYSADMIN", roles.role_department("SYSADMIN")
            u.is_superuser = u.is_staff = True
            u.set_password(opts["admin_password"])
            u.must_change_password = True
            u.save()
            self.stdout.write(self.style.SUCCESS(f"System administrator '{u.username}' {'created' if created else 'updated'}."))

        if opts["demo"]:
            self._demo(User)
        if token is not None:
            audit._actor.reset(token)

    def _demo(self, User):
        pwd = "Chipinge@2026"
        n = 1000
        for username, first, last, role in DEMO_STAFF:
            n += 1
            u, _ = User.objects.get_or_create(username=username, defaults=dict(first_name=first, last_name=last, employee_number=f"CRDC{n}",
                                                                               email=f"{username}@chipingerdc.gov.zw"))
            u.user_type, u.role, u.department = User.UserType.STAFF, role, roles.role_department(role)
            if role == "SYSADMIN":
                u.is_superuser = u.is_staff = True
            u.set_password(pwd)
            u.save()
        client, _ = User.objects.get_or_create(username="resident", defaults=dict(first_name="Johannes", last_name="Mhlanga", phone="0771234567",
                                                                                 national_id="63-123456A63", user_type=User.UserType.CLIENT, ward=1))
        client.set_password(pwd)
        client.save()
        if not ClientAccount.objects.exists():
            samples = [
                ("Johannes Mhlanga", "IND", "0771234567", "63-123456A63", 1, [("101", "Chipinge Township", "RES", 15)]),
                ("Checheche General Dealers (Pvt) Ltd", "BUS", "0712000111", "1234/2015", 22, [("B12", "Checheche Growth Point", "COM", 45)]),
                ("Mt Selinda Mission School", "INST", "0773000222", "", 6, [("M1", "Mount Selinda", "INST", 30)]),
                ("Tanganda Estates Farm 7", "FARM", "0774000333", "TE-77", 14, [("F7", "Tanganda", "AGR", 120)]),
                ("Grace Chiwara", "IND", "0715000444", "63-998877B63", 3, [("455", "Gaza Township", "RES", 12)]),
            ]
            for name, typ, phone, idn, ward, props in samples:
                acc = ClientAccount.objects.create(name=name, account_type=typ, phone=phone, id_number=idn, ward=ward)
                for stand, loc, use, rate in props:
                    Property.objects.create(account=acc, stand_number=stand, location=loc, ward=ward, land_use=use, monthly_rates=Decimal(rate),
                                            valuation=Decimal(rate) * 1000)
            ClientAccount.objects.filter(name="Johannes Mhlanga").first().portal_users.add(client)
        if not Supplier.objects.exists():
            Supplier.objects.create(name="Chipinge Stationers", category="Stationery", phone="0272000001", tax_number="BP200001")
            Supplier.objects.create(name="Eastern Highlands Construction", category="Construction", phone="0272000002", tax_number="BP200002")
            Supplier.objects.create(name="Manica Fuels", category="Fuel", phone="0272000003", tax_number="BP200003")
        # first month of rates
        from finance.services import run_rates_billing

        today = timezone.localdate()
        run_rates_billing(User.objects.get(username="treasurer"), today.year, today.month)
        self.stdout.write(self.style.SUCCESS(f"Demo data created. All demo users have password '{pwd}'. Client login: resident"))
