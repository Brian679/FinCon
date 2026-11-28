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

# Offence schedule (standard fines, USD) – council may change these on the website
OFFENCES = [
    ("TRD-01", "Trading without a valid licence", "Trading By-laws s.4", 50),
    ("TRD-02", "Illegal vending / trading outside a designated site", "Trading By-laws s.9", 20),
    ("HLT-01", "Selling food without a health certificate", "Public Health By-laws", 40),
    ("HLT-02", "Illegal dumping of refuse", "Public Health By-laws", 30),
    ("BLD-01", "Building without approved plans", "Building By-laws s.12", 150),
    ("NR-01", "Illegal sand / gravel extraction", "Natural Resources By-laws", 200),
    ("NR-02", "Illegal gold panning / mining", "Natural Resources By-laws", 300),
    ("NR-03", "Illegal tree cutting / charcoal burning", "Natural Resources By-laws", 100),
    ("NR-04", "Starting a veld fire", "Natural Resources By-laws", 150),
    ("NR-05", "Over-extraction beyond permit", "Natural Resources By-laws", 150),
    ("WL-01", "Poaching / snaring", "CAMPFIRE By-laws", 500),
    ("LV-01", "Stray livestock in township", "Pound By-laws", 15),
    ("TRF-01", "Illegal parking / rank violation", "Traffic & Ranks By-laws", 10),
]

REVENUE_HEADS = [
    # code, name, category, amount, frequency, vote
    ("RATES", "Rates – commercial stands (half-yearly)", "RATES", 0, "HALF", "I-100"),
    ("RES-LEVY", "Residential stand levy (annual)", "LEVY", 60, "ANNUAL", "I-110"),
    ("DEV-LEVY", "Development levy", "LEVY", 5, "ANNUAL", "I-110"),
    ("UNIT-TAX", "Unit tax", "LEVY", 2, "ANNUAL", "I-110"),
    ("FARM-LEVY", "Farm levy (per hectare)", "LEVY", 5, "ANNUAL", "I-110"),
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
    ("STAND-APP", "Stand application / waiting-list fee", "LAND", 20, "ONCE", "I-150"),
    ("CERT-RES", "Proof of residence letter (free)", "FEES", 0, "ONCE", "I-130"),
    ("CERT-CLR", "Rates clearance certificate", "FEES", 10, "ONCE", "I-130"),
    ("CERT-OWN", "Stand ownership confirmation letter", "FEES", 10, "ONCE", "I-130"),
    ("CESSION", "Cession (transfer) fee", "LAND", 50, "ONCE", "I-150"),
    ("BURIAL", "Burial order / cemetery fee", "FEES", 10, "ONCE", "I-130"),
    ("FINES", "By-law fines & penalties", "FINES", 0, "ONCE", "I-130"),
    ("PENALTY", "Late payment penalties", "FINES", 0, "ONCE", "I-130"),
    ("TROPHY", "CAMPFIRE trophy fees", "FEES", 0, "ONCE", "I-130"),
    ("NAT-RES", "Natural resources permits & royalties", "FEES", 0, "ONCE", "I-130"),
    ("SUNDRY", "Sundry income", "OTHER", 0, "ONCE", "I-130"),
]

DEMO_INTERN_DEPARTMENT = {"intern": "TECH", "social.intern": "SOCIAL", "admin.intern": "ADMIN"}   # interns are placed in a department when their account is made

DEMO_STAFF = [
    # username, first, last, role
    ("ceo", "Tendai", "Mutasa", "CEO"),
    ("ict.admin", "Farai", "Moyo", "SYSADMIN"),
    ("treasurer", "Rudo", "Sithole", "TREASURER"),
    ("accountant", "Tatenda", "Ncube", "ACCOUNTANT"),
    ("cashier", "Chipo", "Dube", "REVENUE_CLERK"),
    ("collector", "Kudzai", "Chirwa", "REVENUE_CLERK"),
    ("exp.clerk", "Simba", "Gumbo", "EXPENDITURE_CLERK"),
    ("admin.officer", "Nyasha", "Chikore", "ADMIN_OFFICER"),
    ("hr.officer", "Ruvimbo", "Mhlanga", "HR_OFFICER"),
    ("procurement", "Kuda", "Mapfumo", "PROCUREMENT_OFFICER"),
    ("registry", "Blessing", "Zhou", "RECORDS_CLERK"),
    ("reception", "Rumbidzai", "Makoni", "RECEPTIONIST"),
    ("liaison", "Chiedza", "Mutero", "LIAISON_OFFICER"),
    ("land.officer", "Tawanda", "Gwenzi", "LAND_OFFICER"),
    ("data.officer", "Panashe", "Nyoni", "DATA_OFFICER"),
    ("intern", "Tafadzwa", "Mhere", "INTERN"),
    ("social.intern", "Nokuthula", "Dube", "INTERN"),
    ("admin.intern", "Tatenda", "Chari", "INTERN"),
    ("growthpoint", "Itai", "Chimedza", "GROWTH_POINT_MANAGER"),
    ("chief.auditor", "Patience", "Mazarura", "CHIEF_AUDITOR"),
    ("auditor", "Tinashe", "Chari", "AUDITOR"),
    ("social.director", "Memory", "Sibanda", "SOCIAL_HEAD"),
    ("social.officer", "Tapiwa", "Marufu", "SOCIAL_OFFICER"),
    ("eho", "Gift", "Matanda", "HEALTH_OFFICER"),
    ("natres.officer", "Tonderai", "Mhike", "NATURAL_RESOURCES_OFFICER"),
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
                                                                       budget_line=votes.get(vote), per_hectare=code == "FARM-LEVY"))
        from finance.models import Offence

        for code, name, by_law, fine in OFFENCES:
            Offence.objects.get_or_create(code=code, defaults=dict(name=name, by_law=by_law, default_fine=Decimal(fine)))
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
            u.user_type, u.role, u.department = User.UserType.STAFF, role, roles.role_department(role) or DEMO_INTERN_DEPARTMENT.get(username, "")
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
        self._demo_registers(User)
        # first month of rates
        from finance.services import run_property_billing

        today = timezone.localdate()
        run_property_billing(User.objects.get(username="treasurer"), today.year, 1 if today.month <= 6 else 2)
        self.stdout.write(self.style.SUCCESS(f"Demo data created. All demo users have password '{pwd}'. Client login: resident"))


    def _demo_registers(self, User):
        """Shops by area, leases, assets and departmental registers for demonstrations."""
        from datetime import timedelta

        from departments.models import (Asset, AssetMaintenance, BuildingPlan, CommunityActivity, CouncilMeeting, ICTTicket, Incident,
                                        Policy, Resolution, Risk)
        from finance.models import Lease, TradingArea

        if TradingArea.objects.exists():
            return
        u = {x.username: x for x in User.objects.all()}
        today = timezone.localdate()
        checheche = TradingArea.objects.create(name="Checheche Growth Point", kind="GP", ward=22)
        selinda = TradingArea.objects.create(name="Mount Selinda Business Centre", kind="SC", ward=6)
        TradingArea.objects.create(name="Chipinge Township", kind="TS", ward=1)
        TradingArea.objects.create(name="Chiriga Market", kind="MKT", ward=14)
        Property.objects.filter(location="Checheche Growth Point").update(area=checheche, business_name="Checheche General Dealers")
        Property.objects.filter(location="Chipinge Township").update(area=TradingArea.objects.get(name="Chipinge Township"))
        Property.objects.filter(location="Mount Selinda").update(area=selinda, location="Mount Selinda Business Centre")
        shops = [("B13", "Tendai Bottle Store", "Tendai Sibanda", "0772111222"), ("B14", "Tafara Hardware", "Tafara Hardware (Pvt) Ltd", "0772000001"),
                 ("B15", "Mai Rufaro Butchery", "Rufaro Mutasa", "0713444555"), ("B16", "Checheche Pharmacy", "Checheche Pharmacy (Pvt) Ltd", "0774666777"),
                 ("B17", "Vacant council shop", "Chipinge RDC", "")]
        for stand, biz, owner, phone in shops:
            acc = ClientAccount.objects.create(name=owner, account_type="BUS" if "Pvt" in owner or stand == "B17" else "IND", phone=phone, ward=22)
            Property.objects.create(account=acc, area=checheche, location=checheche.name, stand_number=stand, business_name=biz if stand != "B17" else "",
                                    land_use="COM", monthly_rates=Decimal("40"), valuation=Decimal("30000"), ward=22, is_council_owned=stand in ("B15", "B17"))
        for stand, biz, owner, phone in [("S2", "Selinda Grocers", "Selinda Grocers", "0775888999"), ("S3", "Mission Tailors", "Ruth Gwenzi", "0773123123")]:
            acc = ClientAccount.objects.create(name=owner, account_type="BUS", phone=phone, ward=6)
            Property.objects.create(account=acc, area=selinda, location=selinda.name, stand_number=stand, business_name=biz, land_use="COM",
                                    monthly_rates=Decimal("30"), valuation=Decimal("20000"), ward=6)
        butchery = Property.objects.get(stand_number="B15")
        Lease.objects.create(lessee=butchery.account, premises=butchery, purpose="Butchery – council shop", monthly_rent=Decimal("120"),
                             deposit=Decimal("0"), start_date=today.replace(month=1, day=1), end_date=today.replace(month=12, day=31) + timedelta(days=730))
        # assets & infrastructure
        a1 = Asset.objects.create(name="Motor grader CAT 140K", category="PLANT", department="TECH", serial_number="CRDC-G01", location="Council yard",
                                  acquisition_date=today - timedelta(days=4 * 365), cost=Decimal("185000"), useful_life_years=15, custodian=u["engineer"])
        Asset.objects.create(name="Toyota Hilux GD6 (CEO)", category="VEHICLE", department="EXEC", serial_number="AFX 2231", acquisition_date=today - timedelta(days=700),
                             cost=Decimal("52000"), useful_life_years=8)
        b1 = Asset.objects.create(name="Borehole – Village 12", category="BOREHOLE", department="SOCIAL", location="Village 12", ward=22, cost=Decimal("6500"),
                                  acquisition_date=today - timedelta(days=3000), condition="BROKEN", status="REPAIR")
        Asset.objects.create(name="Borehole – Checheche clinic", category="BOREHOLE", department="SOCIAL", location="Checheche clinic", ward=22, cost=Decimal("7200"))
        Asset.objects.create(name="Public ablution block – Checheche bus terminus", category="ABLUTION", department="SOCIAL", location="Checheche", ward=22,
                             cost=Decimal("18000"), condition="FAIR")
        Asset.objects.create(name="High-mast light – Checheche market", category="LIGHT", department="TECH", location="Checheche market", ward=22,
                             cost=Decimal("9000"), condition="POOR")
        Asset.objects.create(name="Revenue hall computers (6)", category="ICT", department="FINANCE", location="Head office", cost=Decimal("4800"), useful_life_years=4,
                             acquisition_date=today - timedelta(days=500))
        AssetMaintenance.objects.create(asset=b1, work_done="Pump rods corroded – borehole not delivering water. Spares requested.", condition_after="BROKEN",
                                        performed_by="WASH team")
        AssetMaintenance.objects.create(asset=a1, work_done="250-hour service, blades replaced", cost=Decimal("1350"), performed_by="CAT dealer Mutare")
        # social services
        Incident.objects.create(incident_type="HWC", title="Elephants destroy maize fields", description="Herd of 6 elephants raided fields at night.",
                                ward=22, location="Village 12", households_affected=9, crops_hectares=Decimal("4.5"), status="RESPONDING",
                                reported_by=u["social.officer"], lead_officer=u["social.officer"], response="Parks (ZimParks) notified; scaring units deployed.")
        Incident.objects.create(incident_type="STORM", title="Storm damages Mt Selinda school roof", description="Strong winds blew off 2 classroom roofs.",
                                ward=6, location="Mt Selinda", households_affected=0, people_injured=1, reported_by=u["social.director"])
        CommunityActivity.objects.create(activity_type="HYGIENE", title="Handwashing campaign – Checheche market", department="SOCIAL", ward=22,
                                         venue="Checheche market", date=today - timedelta(days=3), participants=140, status="DONE", officer=u["eho"],
                                         report="Demonstrations at 3 points; 40 tippy-taps installed. Vendors asked for more water points.")
        CommunityActivity.objects.create(activity_type="CONSULT", title="Ward 22 budget consultation (WDC)", department="FINANCE", ward=22,
                                         venue="Checheche hall", date=today + timedelta(days=9), officer=u["accountant"])
        CommunityActivity.objects.create(activity_type="FIRE", title="Fireguard construction – Ward 14", department="SOCIAL", ward=14, date=today - timedelta(days=20),
                                         participants=55, status="VERIFIED", officer=u["social.officer"], verified_by=u["social.director"], report="12 km of fireguards cleared.")
        # technical: building plans
        BuildingPlan.objects.create(applicant_name="Tafara Hardware (Pvt) Ltd", phone="0772000001", stand_number="B14", location="Checheche Growth Point", ward=22,
                                    development_type="COM", description="Warehouse extension 12m x 20m", floor_area=Decimal("240"), fee=Decimal("50"),
                                    status="RECOMMEND", reviewed_by=u["tech.officer"], review_notes="Structural drawings compliant; setbacks OK.")
        BuildingPlan.objects.create(applicant_name="Grace Chiwara", phone="0715000444", stand_number="455", location="Gaza Township", ward=3,
                                    development_type="RES", description="4-roomed house", floor_area=Decimal("96"), fee=Decimal("50"))
        # audit: risks
        Risk.objects.create(department="FINANCE", title="Cash collected not banked daily", description="Cash held overnight at Checheche sub-office.",
                            category="FRAUD", likelihood=4, impact=4, existing_controls="Daily cash-up", mitigation="Weekly surprise cash counts; safe at sub-office",
                            owner=u["treasurer"], review_date=today + timedelta(days=60))
        Risk.objects.create(department="TECH", title="Plant breakdown delays road programme", description="Single grader for district.", category="OPS",
                            likelihood=3, impact=4, owner=u["engineer"], mitigation="Hire agreement with private contractor")
        Risk.objects.create(department="ADMIN", title="Server data loss", description="No off-site backups.", category="ICT", likelihood=2, impact=5,
                            owner=u["ict.admin"], mitigation="Nightly encrypted off-site backup", review_date=today - timedelta(days=2))
        # administration
        m = CouncilMeeting.objects.create(meeting_type="FULL", title="Ordinary full council meeting – November", date=timezone.now() - timedelta(days=12),
                                          agenda="1. Confirmation of minutes\n2. Finance report\n3. Roads programme\n4. Licence fees 2027", status="HELD",
                                          minutes="Council resolved as recorded below.")
        Resolution.objects.create(meeting=m, text="Treasurer to enforce shop licence renewals at all growth points by 31 January.", department="FINANCE",
                                  responsible=u["treasurer"], due_date=today + timedelta(days=60), status="IN_PROGRESS")
        Resolution.objects.create(meeting=m, text="Engineer to present a costed plan for Ward 7 road before the rainy season.", department="TECH",
                                  responsible=u["engineer"], due_date=today + timedelta(days=14))
        Resolution.objects.create(meeting=m, text="Repair Village 12 borehole within 30 days.", department="SOCIAL", responsible=u["social.director"],
                                  due_date=today + timedelta(days=30))
        CouncilMeeting.objects.create(meeting_type="FIN", title="Finance & General Purposes committee", date=timezone.now() + timedelta(days=6),
                                      agenda="Budget 2027 first draft; debtors report")
        ICTTicket.objects.create(raised_by=u["cashier"], department="FINANCE", category="PRINT", subject="Receipt printer not printing",
                                 description="Counter 2 thermal printer shows paper jam.", priority="HIGH")
        ICTTicket.objects.create(raised_by=u["engineer"], department="TECH", category="NET", subject="No internet at council yard", description="Since Monday.",
                                 status="IN_PROGRESS", assigned_to=u["ict.admin"])
        Policy.objects.create(title="Shop licensing by-law", kind="BYLAW", department="FINANCE", version="2.1", status="ADOPTED",
                              adopted_on=today - timedelta(days=400), review_date=today + timedelta(days=330),
                              summary="Licence categories, fees, inspections and penalties for trading without a licence.")
        Policy.objects.create(title="ICT acceptable use policy", department="ADMIN", version="1.0", status="CONSULT", review_date=today - timedelta(days=5))
        Policy.objects.create(title="Strategic plan 2026–2030", kind="STRATEGY", department="EXEC", version="1.0", status="ADOPTED", adopted_on=today - timedelta(days=200))
        self._demo_more_areas(u)
        self._demo_requests(u)
        self._demo_mail(u)
        self._demo_payroll(u)
        self._demo_farms_and_intern(u)
        self._demo_social(u)
        self._demo_charter_registers(u)
        self._demo_admin(u)
        self._demo_available_stands(u)
        self._demo_many_places(u)

    def _demo_available_stands(self, u):
        """Surveyed stands the Growth Point Manager can allocate (illustrative only)."""
        from departments.models import AvailableStand
        from finance.models import TradingArea

        plan = [("Checheche", "RES", "CH-H", 41, 8, 300, 1500), ("Checheche", "COM", "CH-C", 11, 4, 450, 6000),
                ("Chipinge", "RES", "CT-", 701, 5, 400, 2500), ("Middle Sabi", "RES", "MS-", 101, 3, 300, 1200)]
        for name, kind, prefix, start, n, size, price in plan:
            area = TradingArea.objects.filter(name__icontains=name).first()
            if area is None:
                continue
            for i in range(n):
                AvailableStand.objects.get_or_create(area=area, stand_number=f"{prefix}{start + i}",
                                                     defaults=dict(stand_type=kind, size_sqm=size, price=price, created_by=u["growthpoint"]))

    def _demo_many_places(self, u):
        """A resident with several places on two accounts: her house, two shops (one through her company), a farm and a fine –
        all owed in one list in the app and paid at once. She also asks for a proof-of-residence letter (illustrative only)."""
        from datetime import date, timedelta

        from finance import services as fin
        from finance.models import Bill, ClientAccount as Acc, Offence, Property, RevenueHead

        User = get_user_model()
        if Property.objects.filter(stand_number="C21").exists():
            return
        tsitsi, _ = User.objects.get_or_create(username="tsitsi", defaults=dict(first_name="Tsitsi", last_name="Mapfumo", phone="0716000555",
                                                                               national_id="63-445566M63", user_type=User.UserType.CLIENT, ward=3))
        tsitsi.set_password("Chipinge@2026")
        tsitsi.save()
        own = Acc.objects.create(name="Tsitsi Mapfumo", account_type="IND", phone="0716000555", id_number="63-445566M63", ward=3)
        company = Acc.objects.create(name="Mapfumo Hardware (Pvt) Ltd", account_type="BUS", phone="0716000555", id_number="4321/2019", ward=22)
        for acc in (own, company):
            acc.portal_users.add(tsitsi)
        house = Property.objects.create(account=own, stand_number="612", location="Gaza Township", ward=3, land_use="RES",
                                        monthly_rates=Decimal("18"), valuation=Decimal("18000"))
        shop = Property.objects.create(account=own, stand_number="C21", location="Checheche Growth Point", ward=22, land_use="COM",
                                       monthly_rates=Decimal("40"), valuation=Decimal("40000"), business_name="Tsitsi's Tuck Shop")
        farm = Property.objects.create(account=own, stand_number="CB-F15", location="Chibuwe farms", ward=25, land_use="AGR", hectares=Decimal("25"))
        hardware = Property.objects.create(account=company, stand_number="B20", location="Checheche Growth Point", ward=22, land_use="COM",
                                           monthly_rates=Decimal("55"), valuation=Decimal("55000"), business_name="Mapfumo Hardware")
        today = timezone.localdate()
        period, due = f"{today.year:04d}-{today.month:02d}", today + timedelta(days=21)
        heads = {h.code: h for h in RevenueHead.objects.filter(code__in=["RATES", "DEV-LEVY", "FARM-LEVY", "LIC-SHOP"])}
        # this year's bills come from the council's billing run (house: annual levy; shops: half-yearly rates; farm: levy per hectare)
        fin.run_property_billing(u["treasurer"], today.year, 1 if today.month <= 6 else 2)
        for prop, head, amount, what in ((shop, "DEV-LEVY", 5, "Development levy"), (hardware, "DEV-LEVY", 5, "Development levy"),
                                         (hardware, "LIC-SHOP", 60, "Shop licence")):
            Bill.objects.create(account=prop.account, property=prop, revenue_head=heads[head], amount=Decimal(amount),
                                period=period if head == "RATES" else str(today.year), description=f"{what} – {prop}", due_date=due,
                                created_by=u["treasurer"])
        fin.issue_fine(u["collector"], offence=Offence.objects.get(code="TRF-01"), offender_name="Tsitsi Mapfumo", account=own, phone="0716000555",
                       location="Chipinge CBD – loading bay", vehicle_reg="AEZ 4412")
        for acc in (own, company):
            acc.recalculate()
        # the people on her stands, and a proof of residence for her son (asked from her account)
        son = fin.save_stand_beneficiary(tsitsi, house, full_name="Tafadzwa Mapfumo", relationship="CHILD", national_id="63-556677T63",
                                         phone="0779123456", date_of_birth=date(2003, 5, 14))
        fin.save_stand_beneficiary(tsitsi, house, full_name="Rutendo Mapfumo", relationship="CHILD", date_of_birth=date(2012, 9, 2))
        fin.save_stand_beneficiary(tsitsi, house, full_name="Simba Mapfumo", relationship="SPOUSE", national_id="63-334455S63", phone="0772334455")
        fin.save_stand_beneficiary(tsitsi, shop, full_name="Blessing Dube", relationship="MANAGER", national_id="63-221100B63", phone="0783221100",
                                   notes="Runs the tuck shop")
        fin.save_stand_beneficiary(tsitsi, farm, full_name="Simba Mapfumo", relationship="CO_OWNER", national_id="63-334455S63", phone="0772334455")
        fin.request_certificate(tsitsi, kind="RESIDENCE", property=house, purpose="Opening a bank account", beneficiary=son)

    def _demo_mail(self, u):
        """Reception: scanned letters sent to the CEO (one already given to a department), phone messages, and a purchase waiting for its invoice."""
        from datetime import timedelta

        from django.core.files.uploadedfile import SimpleUploadedFile

        from workflow import attachments as att
        from workflow import funds as fr
        from workflow import services as wf
        from workflow.models import FundsRequest, FundsRequestLine

        today = timezone.localdate()
        rec, ceo = u["reception"], u["ceo"]

        def scan(name):
            return SimpleUploadedFile(name, b"%PDF-1.4\n% scanned letter (demo)\n", content_type="application/pdf")

        letters = [
            ("Ministry of Local Government, Public Works and National Housing", "2027 budget consultation meetings – dates to confirm", "Needs a reply by Friday."),
            ("Zimbabwe National Water Authority (ZINWA)", "Borehole drilling programme for wards 12 and 18", ""),
            ("Chipinge Business Association", "Request to extend market trading hours in December", "Delivered by hand."),
            ("Provincial Development Coordinator, Manicaland", "Road rehabilitation – Chipinge to Checheche section", ""),
        ]
        made = []
        for i, (sender, subject, note) in enumerate(letters):
            c = wf.log_correspondence(rec, sender=sender, subject=subject, department="EXEC", addressed_to=ceo, routing_note=note,
                                      date_received=today - timedelta(days=i))
            att.add(rec, "correspondence", c, scan(f"{c.reference} scan.pdf"), "SCAN")
            made.append(c)
        wf.route_letter(ceo, made[3], "task", to_user=u["engineer"], title="Prepare the road section costing for the PDC",
                        due_date=today + timedelta(days=7), note="Give the PDC the costed works plan.")
        wf.take_phone_message(rec, caller_name="Mr T. Dube (ZINWA)", caller_phone="0772 410 553", message="About the borehole drilling letter – wants a meeting date.",
                              for_user=u["engineer"])
        wf.take_phone_message(rec, caller_name="Mrs R. Sibanda", caller_phone="0715 880 214", message="Asking when the rates statement for stand 612 will be ready.",
                              for_department="FINANCE", call_back=True)
        wf.take_phone_message(rec, caller_name="Office of the PDC", caller_phone="020 2 2601", message="Please call back about Thursday's meeting.", for_user=ceo)
        # a purchase fully approved – waiting for the invoice before Finance pays
        req = FundsRequest.objects.create(requested_by=u["tech.officer"], created_by=u["tech.officer"], request_type="REPAIRS",
                                          title="Grader tyres (2)", purpose="Grader CRDC-07 is off the road – both front tyres worn out.")
        FundsRequestLine.objects.create(request=req, description="Grader tyre 14.00-24", quantity=2, unit_cost=650)
        att.add(u["tech.officer"], "funds", req, SimpleUploadedFile("Tyre quotation – Chipinge Motors.pdf", b"%PDF-1.4\n% quotation (demo)\n",
                                                                     content_type="application/pdf"), "QUOTE")
        fr.submit(u["tech.officer"], req)
        for who in ("engineer", "admin.officer", "ceo", "accountant", "treasurer"):
            fr.decide(u[who], req, "approve")

    def _demo_requests(self, u):
        """Requests for funds / purchases at different stages, and memos."""
        from datetime import timedelta

        from workflow import funds as fr
        from workflow import memos as mm
        from workflow.models import FundsRequest, FundsRequestLine

        today = timezone.localdate()

        def make(who, rtype, title, purpose, lines, **kw):
            req = FundsRequest.objects.create(requested_by=u[who], created_by=u[who], request_type=rtype, title=title, purpose=purpose, **kw)
            for desc, qty, cost in lines:
                FundsRequestLine.objects.create(request=req, description=desc, quantity=Decimal(str(qty)), unit_cost=Decimal(str(cost)))
            req.recalc_total()
            if rtype in ("PURCHASE", "FUEL", "REPAIRS", "TRAINING"):        # the quotation goes with the request
                from django.core.files.uploadedfile import SimpleUploadedFile

                from workflow import attachments as att

                att.add(u[who], "funds", req, SimpleUploadedFile(f"Quotation – {title[:40]}.pdf", b"%PDF-1.4\n% demo quotation\n",
                                                                  content_type="application/pdf"), "QUOTE")
            return req

        # 1. Technical officer's T&S – approved by HOD, now with the Administration Officer (reminder sent)
        r1 = make("tech.officer", "TRAVEL", "T&S – Musirizwi bridge inspection, Ward 3", "Inspect flood damage on the Musirizwi bridge before the rains.",
                  [("Subsistence allowance – 3 days", 3, 30), ("Accommodation – 2 nights", 2, 60), ("Fuel – council vehicle ADR 4471 (litres)", 80, 1.6)],
                  destination="Ward 3, Musirizwi", depart_date=today + timedelta(days=5), return_date=today + timedelta(days=7),
                  travellers="Prosper Mlambo, Takudzwa Nyathi", needed_by=today + timedelta(days=4), payment_method="MOBILE",
                  payment_details="EcoCash 0773 555 101")
        fr.submit(u["tech.officer"], r1)
        fr.decide(u["engineer"], r1, "approve", "Inspection is urgent – rains are coming.")
        FundsRequest.objects.filter(pk=r1.pk).update(stage_since=timezone.now() - timedelta(days=3))
        r1.refresh_from_db()
        fr.remind(u["tech.officer"], r1, "We travel on Monday – please assist.")
        # 2. Health officer's purchase – waiting for the Social Services head
        r2 = make("eho", "PURCHASE", "Water testing kits for borehole programme", "Quarterly testing of 40 community boreholes (WASH).",
                  [("Water testing kit (50 tests)", 4, 85), ("Chlorine tablets – box", 10, 12)], needed_by=today + timedelta(days=14))
        fr.submit(u["eho"], r2)
        # 3. HR officer's workshop fees – with the Accountant
        r3 = make("hr.officer", "TRAINING", "LGAZ HR practitioners workshop – Mutare", "Annual HR workshop; new labour law amendments.",
                  [("Registration fee", 1, 150), ("Subsistence – 2 days", 2, 30), ("Bus fare return", 1, 20)],
                  destination="Mutare", depart_date=today + timedelta(days=12), return_date=today + timedelta(days=13), travellers="Ruvimbo Mhlanga")
        fr.submit(u["hr.officer"], r3)
        fr.decide(u["admin.officer"], r3, "approve", "Approved – within training budget.")
        fr.decide(u["ceo"], r3, "approve", "Approved.")
        # 4. Social officer's advance – fully approved, paid
        r4 = make("social.officer", "ADVANCE", "Cash advance – drought relief food distribution, Ward 21",
                  "Transport and casual labour for food distribution to 300 households.",
                  [("Truck hire – 1 day", 1, 250), ("Casual labourers – 6 × 2 days", 12, 10)], payment_method="CASH", needed_by=today - timedelta(days=2))
        fr.submit(u["social.officer"], r4)
        for who in ("social.director", "admin.officer", "ceo", "accountant", "treasurer"):
            fr.decide(u[who], r4, "approve")
        try:
            from finance import services as fin
            from finance.models import BankAccount

            v = fr.prepare_payment(u["exp.clerk"], r4)
            fin.decide_voucher(u["accountant"], v, True)
            fin.decide_voucher(u["treasurer"], v, True)
            v.refresh_from_db()
            bank = BankAccount.objects.filter(currency="USD").first()
            if v.is_ready_for_payment and bank:
                fin.pay_voucher(u["exp.clerk"], v, bank_account=bank, payment_reference="CASH-0412")
        except Exception:  # noqa: BLE001 - demo data only
            pass
        # 5. Engineer's fuel – approved, with Finance to prepare payment
        r5 = make("engineer", "FUEL", "Diesel for grader – Ward 7 road programme", "Grading of 12 km of the Ward 7 feeder road.",
                  [("Diesel (litres)", 400, 1.55)], payee_name="Zuva Petroleum Chipinge", payment_method="EFT")
        fr.submit(u["engineer"], r5)
        for who in ("admin.officer", "ceo", "accountant", "treasurer"):
            fr.decide(u[who], r5, "approve")
        # the fuel was bought: invoice attached, purchase confirmed – now with Finance to prepare the payment
        from django.core.files.uploadedfile import SimpleUploadedFile

        from workflow import attachments as att

        att.add(u["engineer"], "funds", r5, SimpleUploadedFile("Zuva Petroleum invoice 4471.pdf", b"%PDF-1.4\n% demo invoice\n",
                                                                content_type="application/pdf"), "INVOICE")
        fr.confirm_purchase(u["engineer"], r5, "400 litres delivered to the Chipinge depot.")
        # 6. Cashier's request returned for changes
        r6 = make("cashier", "PURCHASE", "Receipt book printing", "Manual receipt books for offline collection at Checheche.",
                  [("Receipt books (100 leaves)", 20, 6.5)])
        fr.submit(u["cashier"], r6)
        fr.decide(u["treasurer"], r6, "return", "Attach two quotations from printers.")
        # memos between departments
        m1 = mm.send(u["engineer"], kind="ACTION", to_department="SOCIAL", subject="Borehole at Chako school – water quality",
                     body="The new borehole drilled under the roads programme is ready. Please test the water before it is opened to the community.")
        mm.to_task(u["social.director"], m1, assigned_to=u["eho"], due_date=today + timedelta(days=7))
        mm.reply(u["eho"], m1, "Sampling booked for Thursday; results in 48 hours.")
        mm.send(u["hr.officer"], kind="MESSAGE", to_department="FINANCE", subject="Overtime rates for December payroll",
                body="Please confirm the approved overtime rates so that the December payroll can be prepared.")
        mm.send(u["cashier"], kind="ACTION", to_department="ADMIN", to_user=u["ict.admin"], subject="Second receipt printer for Checheche",
                body="Collections at Checheche have doubled – please arrange a second printer.", priority="HIGH")
        mm.send(u["treasurer"], kind="INFO", to_department="TECH", subject="Roads budget vote at 82% utilisation",
                body="For information: vote 0410 (roads maintenance) is 82% spent with four months remaining.")

    def _demo_more_areas(self, u):
        """More growth points / business centres with shops at every stage of payment,
        so the areas overview shows a realistic picture (demo only)."""
        import random
        from datetime import date

        from finance import services as fin
        from finance.models import Bill, Licence, Property, RevenueHead, TradingArea

        rnd = random.Random(2026)
        today = timezone.localdate()
        levy = RevenueHead.objects.get(code="DEV-LEVY")
        shop_lic = RevenueHead.objects.get(code="LIC-SHOP")
        places = [("Chisumbanje Business Centre", "SC", 9), ("Chibuwe Business Centre", "SC", 7), ("Birchenough Bridge Growth Point", "GP", 8),
                  ("Mutema Business Centre", "SC", 6), ("Middle Sabi Business Centre", "SC", 5), ("Tanganda Business Centre", "SC", 4),
                  ("Rimbi Business Centre", "SC", 5), ("Mahenye Business Centre", "SC", 4)]
        trades = ["General Dealer", "Butchery", "Bottle Store", "Hardware", "Grinding Mill", "Bakery", "Pharmacy", "Tailoring", "Hair Salon",
                  "Fast Foods", "Agro-dealer", "Phone Shop"]
        surnames = ["Moyo", "Sithole", "Dube", "Ncube", "Mlambo", "Chikore", "Gumbo", "Mapfumo", "Zhou", "Sibanda", "Mutasa", "Chari",
                    "Nyathi", "Marufu", "Matanda", "Mhlanga", "Mukwena", "Chipunza", "Rusere", "Dhliwayo"]
        cashier = u["collector"]
        for n, (name, kind, count) in enumerate(places):
            area = TradingArea.objects.create(name=name, kind=kind)
            for i in range(count):
                owner = f"{rnd.choice(['T.', 'R.', 'S.', 'M.', 'P.', 'K.', 'G.'])} {rnd.choice(surnames)}"
                biz = f"{owner.split()[1]} {rnd.choice(trades)}"
                acc = ClientAccount.objects.create(name=owner, account_type="IND", phone=f"07{rnd.randint(71, 78)}{rnd.randint(100000, 999999)}")
                prop = Property.objects.create(account=acc, area=area, location=name, stand_number=f"{name[:2].upper()}{i + 1}", business_name=biz,
                                               land_use="COM", monthly_rates=Decimal("0"), valuation=Decimal("15000"))
                bill = Bill.objects.create(account=acc, property=prop, revenue_head=levy, amount=Decimal("45"),
                                           description=f"Shop levy {today.year} – {biz}", due_date=date(today.year, 3, 31), period=str(today.year))
                roll = rnd.random()
                if roll < 0.5:  # fully paid with a valid licence
                    fin.issue_receipt(cashier, revenue_head=levy, amount=Decimal("45"), account=acc, bill=bill, channel="FIELD")
                    Licence.objects.create(account=acc, property=prop, business_name=biz, premises=f"Stand {prop.stand_number}, {name}",
                                           status=Licence.Status.ISSUED, fee=Decimal("60"), revenue_head=shop_lic, issue_date=today.replace(month=1, day=15),
                                           expiry_date=date(today.year, 12, 31))
                elif roll < 0.7:  # part paid
                    fin.issue_receipt(cashier, revenue_head=levy, amount=Decimal(rnd.choice(["15", "20", "30"])), account=acc, bill=bill, channel="FIELD")
                    Licence.objects.create(account=acc, property=prop, business_name=biz, premises=f"Stand {prop.stand_number}, {name}",
                                           status=Licence.Status.ISSUED, fee=Decimal("60"), revenue_head=shop_lic, issue_date=today.replace(month=2, day=1),
                                           expiry_date=date(today.year, 12, 31))
                elif roll < 0.85:  # levy paid but licence expired last year
                    fin.issue_receipt(cashier, revenue_head=levy, amount=Decimal("45"), account=acc, bill=bill, channel="FIELD")
                    Licence.objects.create(account=acc, property=prop, business_name=biz, premises=f"Stand {prop.stand_number}, {name}",
                                           status=Licence.Status.EXPIRED, fee=Decimal("60"), revenue_head=shop_lic,
                                           issue_date=date(today.year - 1, 1, 10), expiry_date=date(today.year - 1, 12, 31))
                # else: nothing paid, no licence

    def _demo_farms_and_intern(self, u):
        """Demo farms (farm levy $5 a hectare) and work given to the Technical Services intern."""
        from finance import services as fin
        from finance.models import ClientAccount as Acc, Property, RevenueHead
        from workflow import services as wf

        farms = [("Chako Estates (Pvt) Ltd", "CORP", "Middle Sabi", "MS-F12", 120), ("S. Mlambo", "IND", "Middle Sabi", "MS-F31", 8),
                 ("Tanganda Farmers Co-operative", "CORP", "Tanganda", "TG-F4", 45), ("R. Dhliwayo", "IND", "Chibuwe", "CB-F9", 12.5)]
        for name, kind, place, number, ha in farms:
            acc = Acc.objects.create(name=name, account_type="FARM" if kind == "CORP" else "IND", phone=f"07724{ha * 10:05.0f}")
            Property.objects.create(account=acc, location=f"{place} farms", stand_number=number, land_use="AGR", hectares=Decimal(str(ha)))
        year = timezone.localdate().year
        fin.run_levy_billing(u["treasurer"], RevenueHead.objects.get(code="FARM-LEVY"), year)
        first = Property.objects.get(stand_number="MS-F31")
        bill = first.bills.first()
        fin.issue_receipt(u["collector"], revenue_head=bill.revenue_head, amount=bill.amount, account=first.account, bill=bill, channel="FIELD")
        for title, desc, due in (("Survey culvert sites – Ward 7", "Measure and photograph the 4 culverts on the Chipinge–Checheche road.", 5),
                                 ("Update the road condition register", "Enter last week's inspection notes into the register.", 9)):
            wf.create_task(u["engineer"], title=title, description=desc, assigned_to=u["intern"], department="TECH",
                           due_date=timezone.localdate() + timezone.timedelta(days=due))

    def _demo_social(self, u):
        """Demo CAMPFIRE, natural resources, farms, water points and fines (illustrative only)."""
        from datetime import timedelta

        from finance import services as fin
        from finance.models import ClientAccount as Acc, Offence
        from social import services as sv
        from social.models import Farm, HuntingQuota, ResourcePermit, WaterPoint, WildlifeRecord

        today = timezone.localdate()
        nro = u["natres.officer"]
        for sp, rt, ward, place, n, days in (("ELEPHANT", "AERIAL", 29, "Save Valley boundary, Mahenye", 46, 60), ("BUFFALO", "AERIAL", 29, "Mahenye", 120, 60),
                                             ("HIPPO", "GROUND", 25, "Save River, Chisumbanje", 18, 30), ("CROC", "GROUND", 25, "Save River pools", 35, 30),
                                             ("LION", "SIGHTING", 29, "Mahenye ward 29 – cattle kraal", 3, 8), ("ELEPHANT", "PAC", 25, "Chinyamukwakwa fields", 5, 4),
                                             ("KUDU", "POACHING", 26, "Tamandai – 6 snares removed", 1, 2), ("IMPALA", "CAMERA", 29, "Mahenye camp", 22, 12)):
            WildlifeRecord.objects.create(species=sp, record_type=rt, ward=ward, location=place, count=n, date=today - timedelta(days=days),
                                          recorded_by=nro, created_by=nro)
        quotas = {}
        for sp, ward, conc, q, fee in (("ELEPHANT", 29, "Mahenye CAMPFIRE area", 3, 25000), ("BUFFALO", 29, "Mahenye CAMPFIRE area", 8, 3500),
                                       ("LEOPARD", 29, "Mahenye CAMPFIRE area", 2, 5500), ("CROC", 25, "Save River", 4, 2500),
                                       ("HIPPO", 25, "Save River", 2, 3000)):
            quotas[sp] = HuntingQuota.objects.create(year=today.year, species=sp, ward=ward, concession=conc, quota=q, trophy_fee=Decimal(fee),
                                                     created_by=nro)
        operator = Acc.objects.create(name="Save Valley Safaris (Pvt) Ltd", account_type="BUS", phone="0772551100", email="bookings@example.com")
        h1 = sv.book_hunt(nro, quota=quotas["BUFFALO"], operator=operator, client_name="J. Miller", client_nationality="USA",
                          professional_hunter="T. Hove", hunt_date=today - timedelta(days=20))
        sv.hunt_action(nro, h1, "hunted", trophy_details="Bull, 42 inch spread")
        fin.issue_receipt(u["collector"], revenue_head=h1.bill.revenue_head, amount=h1.trophy_fee, account=operator, bill=h1.bill,
                          method="BANK", reference="RTGS-SVS-118")
        h2 = sv.book_hunt(nro, quota=quotas["ELEPHANT"], operator=operator, client_name="H. Schmidt", client_nationality="Germany",
                          professional_hunter="T. Hove", hunt_date=today - timedelta(days=6))
        sv.hunt_action(nro, h2, "hunted", trophy_details="Bull, tusks 28 kg / 26 kg")
        sv.book_hunt(nro, quota=quotas["CROC"], operator=operator, client_name="P. Novak", client_nationality="Czech Republic",
                     hunt_date=today + timedelta(days=12))
        sand_co = Acc.objects.create(name="Mutema Builders & Sand Supply", account_type="BUS", phone="0773441200")
        p1 = ResourcePermit.objects.create(permit_type="SAND", holder=sand_co, ward=12, location="Musikavanhu river bed, Mutema", unit="M3",
                                           quantity_allowed=Decimal("200"), unit_fee=Decimal("3"), valid_from=today - timedelta(days=30),
                                           valid_to=today + timedelta(days=150), ema_reference="EMA/MAN/SND/2026/044", applied_by=nro, created_by=nro,
                                           conditions="Max depth 1.5 m; no extraction within 50 m of the bridge; rehabilitate pits monthly.")
        sv.decide_permit(u["social.director"], p1, "approve", "EMA approval seen")
        p1.refresh_from_db()
        fin.issue_receipt(u["collector"], revenue_head=p1.bill.revenue_head, amount=p1.fee, account=sand_co, bill=p1.bill)
        for d, q, reg in ((20, "12", "ACX 4471"), (12, "12", "ACX 4471"), (3, "18", "AEF 2290")):
            sv.record_extraction(nro, p1, quantity=q, date=today - timedelta(days=d), vehicle_reg=reg, destination="Chipinge town")
        miner = Acc.objects.create(name="Tanganda Gold Syndicate", account_type="BUS", phone="0779120033")
        ResourcePermit.objects.create(permit_type="MINING", holder=miner, ward=8, location="Tanganda – claim TG/14", unit="MONTH",
                                      quantity_allowed=Decimal("6"), unit_fee=Decimal("75"), valid_from=today, valid_to=today + timedelta(days=180),
                                      ema_reference="MMCZ/PRO/2026/310", applied_by=nro, created_by=nro)
        timber = Acc.objects.create(name="Chipinge Timbers", account_type="BUS", phone="0772339900")
        p3 = ResourcePermit.objects.create(permit_type="TIMBER", holder=timber, ward=3, location="Chirinda forest buffer block C", unit="M3",
                                           quantity_allowed=Decimal("40"), unit_fee=Decimal("12"), valid_from=today, valid_to=today + timedelta(days=90),
                                           ema_reference="FC/HAR/2026/017", applied_by=nro, created_by=nro)
        sv.decide_permit(u["social.director"], p3, "approve", "Forestry Commission harvesting plan attached")
        farms = [("Chako Estates", "Chako Estates (Pvt) Ltd", "MS-F12", 22, "Middle Sabi farms", 120, "ESTATE", "PLANT", "Macadamia, coffee", 0, 0, 80),
                 ("Mlambo Plot 31", "S. Mlambo", "MS-F31", 22, "Middle Sabi farms", 8, "IRRIG", "CROPS", "Wheat, maize, sugar beans", 6, 10, 8),
                 ("Tanganda Co-op Farm 4", "Tanganda Farmers Co-operative", "TG-F4", 8, "Tanganda farms", 45, "A2", "MIXED", "Tea, maize", 60, 40, 10),
                 ("Dhliwayo A1 plot", "R. Dhliwayo", "CB-F9", 25, "Chibuwe farms", 12.5, "A1", "MIXED", "Cotton, sorghum", 14, 22, 0)]
        for name, owner, number, ward, place, ha, ftype, act, crops, cattle, goats, irr in farms:
            acc = Acc.objects.filter(name=owner).first()
            prop = acc.properties.filter(stand_number=number).first() if acc else None
            f = Farm(name=name, owner=acc, farm_number=number, ward=ward, location=place, hectares=Decimal(str(ha)), farm_type=ftype, activity=act,
                     main_crops=crops, cattle=cattle, goats_sheep=goats, irrigated_hectares=Decimal(irr), created_by=nro)
            f.property = prop
            f.save()
        eho = u["eho"]
        for name, kind, ward, village, hh, status, days in (("Chibuwe Primary School borehole", "BOREHOLE", 25, "Chibuwe", 140, "WORKING", 40),
                                                             ("Mahenye clinic solar borehole", "SOLAR", 29, "Mahenye", 220, "WORKING", 15),
                                                             ("Chinyamukwakwa village well", "WELL", 25, "Chinyamukwakwa", 60, "BROKEN", 210),
                                                             ("Checheche piped scheme", "PIPED", 22, "Checheche", 900, "REPAIR", 3),
                                                             ("Tamandai bush pump", "BOREHOLE", 26, "Tamandai", 85, "DRY", 95)):
            WaterPoint.objects.create(name=name, point_type=kind, ward=ward, village=village, households_served=hh, status=status,
                                      last_serviced=today - timedelta(days=days), committee_contact="Chair – 077x xxx xxx", created_by=eho,
                                      notes="Pump rods rusted – parts requested" if status == "BROKEN" else "")
        fines = [(u["natres.officer"], "NR-01", "B. Ncube", "63-555123B13", "0774112233", "Save River bridge – 2 loads", "ADG 1180"),
                 (u["eho"], "HLT-01", "Mai Rudo fast foods", "", "0771009988", "Checheche rank", ""),
                 (u["collector"], "TRD-02", "K. Dube", "", "0778667700", "Chipinge CBD pavement", "")]
        issued = []
        for officer, code, name, nid, phone, place, reg in fines:
            issued.append(fin.issue_fine(officer, offence=Offence.objects.get(code=code), offender_name=name, national_id=nid, phone=phone,
                                         location=place, vehicle_reg=reg))
        fin.issue_receipt(u["collector"], revenue_head=issued[2].bill.revenue_head, amount=issued[2].amount, account=issued[2].account,
                          bill=issued[2].bill)

    def _demo_charter_registers(self, u):
        """Demo roads, lights, work orders, registry files, health inspections, ablutions / waste, schools & clinics, and leave
        at different approval steps (illustrative only)."""
        from datetime import timedelta

        from departments import leave as lv
        from departments import registers as rg
        from departments.models import LeaveRequest, PublicLight, RecordFile, Road, WorkOrder
        from social.models import HealthInspection, SanitationFacility, SocialFacility

        today = timezone.localdate()
        eng, tech = u["engineer"], u["tech.officer"]
        roads = {}
        for name, no, ward, a, b, km, surf, cond, days in (("Chipinge – Checheche road (district section)", "D-101", 22, "Chipinge", "Checheche", 58, "TAR", "FAIR", 200),
                                                            ("Checheche – Chibuwe road", "D-114", 25, "Checheche", "Chibuwe", 24, "GRAVEL", "POOR", 400),
                                                            ("Mutema – Rimbi road", "D-131", 12, "Mutema", "Rimbi", 18, "GRAVEL", "GOOD", 60),
                                                            ("Mahenye access road", "D-140", 29, "Chilonga turn-off", "Mahenye", 31, "EARTH", "IMPASSABLE", 700)):
            roads[no] = Road.objects.create(name=name, road_number=no, ward=ward, start_point=a, end_point=b, length_km=km, surface=surf, condition=cond,
                                            last_graded=today - timedelta(days=days), bridges_culverts=3, created_by=eng)
        lights = []
        for kind, place, ward, pole, status in (("HIGHMAST", "Checheche growth point – bus terminus", 22, "HM-01", "WORKING"),
                                               ("HIGHMAST", "Chisumbanje business centre", 25, "HM-04", "FAULTY"),
                                               ("STREET", "Chipinge – Checheche road, Checheche turn-off", 22, "SL-118", "VANDAL"),
                                               ("SOLAR", "Birchenough Bridge market", 30, "SS-07", "WORKING")):
            lights.append(PublicLight.objects.create(light_type=kind, location=place, ward=ward, pole_number=pole, status=status,
                                                     last_checked=today - timedelta(days=12), created_by=tech))
        w1 = WorkOrder.objects.create(kind="ROAD", title="Grade and reshape Checheche – Chibuwe road (km 0–8)", location="Checheche – Chibuwe road", ward=25,
                                      road=roads["D-114"], assigned_to=tech, due_date=today + timedelta(days=10), created_by=eng)
        rg.work_action(tech, w1, "start", notes="Grader and water bowser on site")
        w2 = WorkOrder.objects.create(kind="LIGHT", title="Replace lamp and ballast – high-mast HM-04", location="Chisumbanje business centre", ward=25,
                                      light=lights[1], assigned_to=tech, due_date=today + timedelta(days=3), created_by=eng)
        rg.work_action(tech, w2, "done", notes="New 400 W lamp and ballast fitted, tested at dusk", materials="400 W lamp, ballast", labour_days="1",
                       cost="320")
        WorkOrder.objects.create(kind="DRAIN", title="Clear blocked culvert at Mutema clinic", location="Mutema clinic", ward=12, road=roads["D-131"],
                                 assigned_to=u["intern"], due_date=today + timedelta(days=5), created_by=eng)
        reg = u["registry"]
        for no, title, dept, cat, loc, conf in (("ADM/HR/014", "Personnel files A – M", "ADMIN", "Personnel", "Cabinet 3, drawer 1", True),
                                                ("FIN/STD/221", "Checheche stand allocations 2019–2026", "FINANCE", "Stands", "Shelf B4", False),
                                                ("ADM/CNL/2026", "Full council minutes 2026", "ADMIN", "Council minutes", "Strong room", False),
                                                ("TECH/RD/101", "D-101 road rehabilitation contract", "TECH", "Contracts", "Shelf C1", False)):
            RecordFile.objects.create(file_number=no, title=title, department=dept, category=cat, location=loc, confidential=conf,
                                      retain_until=today.replace(year=today.year + 7), created_by=reg)
        rg.record_action(reg, RecordFile.objects.get(file_number="TECH/RD/101"), "lend", borrower=eng.pk, due_back=today + timedelta(days=5))
        eho = u["eho"]
        for prem, kind, owner, ward, place, score, result, findings, fu in (
                ("Checheche Fast Foods", "FOOD", "Mai Rudo", 22, "Checheche rank", 58, "FOLLOWUP", "No running water at the wash basin; food handlers' certificates expired.", 14),
                ("Chisumbanje butchery", "BUTCHERY", "T. Matanda", 25, "Chisumbanje BC", 82, "PASS", "Cold room 3 °C, clean. Keep the fly screens closed.", None),
                ("Chibuwe slaughter slab", "ABATTOIR", "Council", 25, "Chibuwe", 34, "FAIL", "Effluent running into the stream – slab closed until drainage is fixed.", 7),
                ("Mahenye Primary School", "SCHOOL", "Ministry of Education", 29, "Mahenye", 75, "PASS", "Toilets adequate; hand-washing station needs soap.", None)):
            HealthInspection.objects.create(premises=prem, premises_type=kind, owner=owner, ward=ward, location=place, score=score, result=result,
                                            findings=findings, date=today - timedelta(days=3), inspector=eho, created_by=eho,
                                            follow_up_date=today + timedelta(days=fu) if fu else None)
        for name, kind, ward, place, status, days, coll in (("Checheche bus terminus toilets", "ABLUTION", 22, "Checheche", "NEEDS", 2, ""),
                                                            ("Chipinge CBD skip – market", "REFUSE", 1, "Chipinge market", "GOOD", 1, "Mon & Thu"),
                                                            ("Checheche dumpsite", "DUMPSITE", 22, "Checheche – 3 km east", "BLOCKED", 30, ""),
                                                            ("Birchenough Bridge market toilets", "ABLUTION", 30, "Birchenough Bridge", "GOOD", 1, "")):
            SanitationFacility.objects.create(name=name, kind=kind, ward=ward, location=place, status=status, last_serviced=today - timedelta(days=days),
                                              collection_days=coll, created_by=eho)
        so = u["social.officer"]
        for name, kind, ward, place, pop, rooms, cond, needs in (
                ("Chinyamukwakwa Primary School", "PRIMARY", 25, "Chinyamukwakwa", 860, 12, "POOR", "4 classroom block, 2 staff houses, borehole repair"),
                ("Mahenye Clinic", "CLINIC", 29, "Mahenye", 9400, 8, "FAIR", "Maternity waiting shelter, solar power for the fridge"),
                ("Checheche High School", "SECONDARY", 22, "Checheche", 1240, 22, "BUILDING", "Science laboratory under construction (CDF)"),
                ("Tamandai ECD centre", "ECD", 26, "Tamandai", 85, 2, "POOR", "Roofing, child-friendly toilets")):
            SocialFacility.objects.create(name=name, kind=kind, ward=ward, location=place, population_served=pop, classrooms_or_beds=rooms, condition=cond,
                                          needs=needs, responsible_authority="Ministry" if kind != "ECD" else "Community", created_by=so)
        # housing: stand applications at the growth points (Growth Point Manager)
        from departments import services as dsv
        from departments.models import StandApplication

        gp = u["growthpoint"]
        for name, nid, phone, kind, place, ward, act in (("Tendai Mapfumo", "63-221144K63", "0772110022", "RES", "Checheche growth point", 22, "allocate"),
                                                         ("Rufaro Sithole", "63-998877R63", "0773220011", "RES", "Checheche growth point", 22, "shortlist"),
                                                         ("Kudakwashe Moyo", "14-554433K14", "0774330022", "COM", "Birchenough Bridge growth point", 30, ""),
                                                         ("Mai Chipo Ncube", "63-776655C63", "0775440033", "RES", "Chisumbanje growth point", 25, "")):
            st = StandApplication.objects.create(applicant_name=name, national_id=nid, phone=phone, stand_type=kind, preferred_location=place,
                                                 ward=ward, created_by=gp)
            if act == "allocate":
                dsv.stand_action(gp, st, "shortlist")
                dsv.stand_action(gp, st, "allocate", stand="CH-H17", note="Serviced residential stand, 300 m²")
            elif act:
                dsv.stand_action(gp, st, act)
        # leave at each approval step
        def apply(user, start, days, kind="ANNUAL", reason=""):
            r = LeaveRequest.objects.create(employee=user, leave_type=kind, start_date=today + timedelta(days=start),
                                            end_date=today + timedelta(days=start + days), reason=reason, created_by=user)
            lv.submit(r)
            r.refresh_from_db()
            return r
        a = apply(u["eho"], 14, 4, reason="Family wedding in Mutare")                         # waiting for the Director of Social Services
        b = apply(u["tech.officer"], 21, 6, reason="Annual leave")                            # Engineer approved → waiting for HR
        lv.decide(eng, b, True, "Grader work will be done by then")
        c = apply(u["cashier"], 30, 2, reason="Graduation")                                    # HOD + HR approved → waiting for CEO
        lv.decide(u["treasurer"], c, True, "Relief cashier arranged")
        lv.decide(u["hr.officer"], c, True, "Days available")
        d = apply(u["registry"], 9, 1, kind="COMPASS", reason="Funeral")                       # fully approved
        for who in (u["admin.officer"], u["hr.officer"], u["ceo"]):
            d.refresh_from_db()
            if d.status == "PENDING":
                lv.decide(who, d, True, "Condolences")

    def _demo_admin(self, u):
        """Demo land bank, stakeholder meetings, public notices, audit plan and a resident's sand permit (illustrative only)."""
        from datetime import timedelta

        from departments.models import AuditEngagement, Engagement, LandParcel, PublicNotice
        from social import services as sv

        today = timezone.localdate()
        lo = u["land.officer"]
        for no, name, ward, loc, ha, use, status, stands in (("CRDC/LP/014", "Checheche extension phase 2", 22, "Checheche growth point", 38, "RES", "PLANNED", 420),
                                                             ("CRDC/LP/015", "Checheche light industrial site", 22, "Checheche – Chipinge road", 12, "IND", "VACANT", 40),
                                                             ("CRDC/LP/021", "Birchenough Bridge market extension", 30, "Birchenough Bridge", 2.5, "COM", "ALLOCATED", 24),
                                                             ("CRDC/LP/033", "Chisumbanje clinic site", 25, "Chisumbanje", 1.2, "INST", "RESERVED", 0),
                                                             ("CRDC/LP/040", "Mutema open space", 12, "Mutema business centre", 0.8, "OPEN", "ENCROACHED", 0)):
            LandParcel.objects.create(parcel_number=no, name=name, ward=ward, location=loc, hectares=ha, land_use=use, status=status, stands_planned=stands,
                                      survey_diagram=f"GP {no[-3:]}/2024" if status != "VACANT" else "", created_by=lo,
                                      notes="Informal structures being put up – notice served" if status == "ENCROACHED" else "")
        li = u["liaison"]
        for title, kind, days, ward, venue, att, issues, res, status in (
                ("Ward 22 WADCO meeting", "WARD", -9, 22, "Checheche hall", 46, "Refuse collection at the rank; stand allocation waiting list",
                 "Refuse skip to be moved; Growth Point Manager to publish the waiting list", "FOLLOWUP"),
                ("2027 budget consultation – Chibuwe", "BUDGET", -20, 25, "Chibuwe Primary School", 132, "Road D-114, borehole repairs, clinic staff houses",
                 "Priorities captured for the 2027 budget", "HELD"),
                ("Chief Musikavanhu – traditional leaders' meeting", "TRAD", 6, 12, "Chief's court, Mutema", 0, "", "", "PLANNED"),
                ("World Vision WASH partners' meeting", "PARTNER", 13, None, "Council boardroom", 0, "", "", "PLANNED")):
            Engagement.objects.create(title=title, kind=kind, date=today + timedelta(days=days), ward=ward, venue=venue, attendance=att, issues_raised=issues,
                                      resolutions=res, status=status, officer=li, created_by=li)
        for title, cat, body, ward, until in (
                ("Water interruption – Checheche, Friday", "WATER", "Water supply to Checheche growth point will be off on Friday 08:00–16:00 while the main pump is repaired.", 22, 7),
                ("2027 budget consultation meetings", "MEETING", "Residents are invited to the ward budget consultation meetings. See the schedule at your ward centre or the council offices.", None, 30),
                ("Shop licences – renew by 31 January", "DEADLINE", "All shop and business licences expire on 31 December. Pay the licence fee, lease and levy in the app and your licence is issued automatically.", None, 60),
                ("Cholera alert – boil drinking water", "HEALTH", "Cases reported in a neighbouring district. Boil or treat drinking water, wash hands with soap and report diarrhoea cases to the nearest clinic.", None, 21)):
            PublicNotice.objects.create(title=title, category=cat, body=body, ward=ward, expires_on=today + timedelta(days=until), posted_by=li, created_by=li)
        ca = u["chief.auditor"]
        for title, kind, dept, q, who, status, concl in (
                ("Revenue collection & cash-ups", "FIN", "FINANCE", f"{today.year}-Q4", "auditor", "FIELDWORK", ""),
                ("Payroll & PAYE compliance", "COMP", "FINANCE", f"{today.year}-Q4", "chief.auditor", "PLANNED", ""),
                ("CAMPFIRE revenue sharing to wards", "PERF", "SOCIAL", f"{today.year}-Q3", "auditor", "DONE",
                 "Community shares paid within 30 days in 9 of 10 cases; one ward paid late – recommend quarterly reconciliations."),
                ("Fuel & vehicle usage", "STOCK", "TECH", f"{today.year + 1}-Q1", "auditor", "PLANNED", "")):
            AuditEngagement.objects.create(title=title, audit_type=kind, department=dept, quarter=q, auditor=u[who], status=status, conclusion=concl,
                                           created_by=ca)
        # a resident applies for a sand permit in the client app
        resident = u["resident"]
        acc = resident.client_accounts.first()
        if acc:
            sv.client_apply_permit(resident, holder=acc, permit_type="SAND", location="Musikavanhu river, Mutema – collection point 3", quantity=6,
                                   ward=12, days=30, purpose="Building a house – 2 loads")
        from departments.services import apply_for_stand
        from finance import services as fin
        from finance.models import Property

        # a renter: runs a bottle store in a shop owned by someone else – own account, linked as tenant
        User = get_user_model()
        renter, _ = User.objects.get_or_create(username="tenant", defaults=dict(first_name="Farai", last_name="Mutasa", phone="0773556677",
                                                                               national_id="63-778899F63", user_type=User.UserType.CLIENT, ward=22))
        renter.set_password("Chipinge@2026")
        renter.save()
        shop = Property.objects.filter(stand_number="B13").first()
        if shop:
            claim = fin.submit_claim(renter, stand_number="B13", area=shop.area, business_name="Farai's Bottle Store", claim_type="RENT",
                                     notes="Renting from Tendai Sibanda since March 2026")
            fin.decide_claim(u["cashier"], claim, True, note="Lease agreement seen")
        # the renter also applies for a residential stand of their own (waiting-list fee to pay)
        apply_for_stand(renter, stand_type="RES", preferred_location="Checheche growth point – extension phase 2", ward=22)

    def _demo_payroll(self, u):
        """Demo salaries and two months of payroll (illustrative amounts only – not real council salaries)."""
        from payroll import services as pr
        from payroll.models import Payslip

        User = get_user_model()
        bands = {"EXEC": ("D1", 2800), "HEAD": ("C2", 1800), "OFFICER": ("B3", 1000), "CLERK": ("A4", 650)}
        for user in User.objects.filter(user_type=User.UserType.STAFF, is_active=True).exclude(role=""):
            grade, basic = ("INT", 250) if user.role == "INTERN" else bands.get(user.level or "OFFICER", ("B3", 1000))
            basic = Decimal(basic)
            payer = u["accountant"] if user.pk != u["accountant"].pk else u["treasurer"]
            pr.update_salary(payer, user, grade=grade, basic_salary=basic, housing_allowance=(basic * Decimal("0.15")).quantize(Decimal("1")),
                             transport_allowance=Decimal("80"), paye=(basic * Decimal("0.12")).quantize(Decimal("1")), nssa=Decimal("27"),
                             pension=(basic * Decimal("0.06")).quantize(Decimal("1")), medical_aid=Decimal("25"), payment_method="EFT",
                             bank_name="CBZ Bank Chipinge", bank_account=f"01{user.pk:04d}77{user.pk:03d}")
        today = timezone.localdate()
        prev = (today.replace(day=1) - timezone.timedelta(days=1))
        for (y, m), paid_share in (((prev.year, prev.month), 1.0), ((today.year, today.month), 0.0)):
            pr.run_payroll(u["accountant"], y, m)
            pr.approve_payroll(u["treasurer"], y, m)
            pr.approve_payroll(u["ceo"], y, m)          # the Treasurer's own payslip
            for n, slip in enumerate(Payslip.objects.filter(year=y, month=m, status="APPROVED").order_by("employee__username")):
                payer = u["exp.clerk"] if slip.employee_id != u["exp.clerk"].pk else u["treasurer"]
                if paid_share == 1.0:
                    amount = slip.net if n % 5 else (slip.net / 2).quantize(Decimal("0.01"))    # a few people only half paid last month
                elif n % 3 == 0:
                    amount = (slip.net * Decimal("0.6")).quantize(Decimal("0.01"))             # this month: some advances
                else:
                    continue
                pr.pay_payslip(payer, slip, amount=amount, method="EFT", reference=f"RTGS-SAL-{y}{m:02d}-{n + 1:03d}")
