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
    ("collector", "Kudzai", "Chirwa", "REVENUE_CLERK"),
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
        self._demo_registers(User)
        # first month of rates
        from finance.services import run_rates_billing

        today = timezone.localdate()
        run_rates_billing(User.objects.get(username="treasurer"), today.year, today.month)
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
        # 3. HR officer's workshop fees – with the Treasurer
        r3 = make("hr.officer", "TRAINING", "LGAZ HR practitioners workshop – Mutare", "Annual HR workshop; new labour law amendments.",
                  [("Registration fee", 1, 150), ("Subsistence – 2 days", 2, 30), ("Bus fare return", 1, 20)],
                  destination="Mutare", depart_date=today + timedelta(days=12), return_date=today + timedelta(days=13), travellers="Ruvimbo Mhlanga")
        fr.submit(u["hr.officer"], r3)
        fr.decide(u["admin.officer"], r3, "approve", "Approved – within training budget.")
        # 4. Social officer's advance – fully approved, paid
        r4 = make("social.officer", "ADVANCE", "Cash advance – drought relief food distribution, Ward 21",
                  "Transport and casual labour for food distribution to 300 households.",
                  [("Truck hire – 1 day", 1, 250), ("Casual labourers – 6 × 2 days", 12, 10)], payment_method="CASH", needed_by=today - timedelta(days=2))
        fr.submit(u["social.officer"], r4)
        for who in ("social.director", "admin.officer", "treasurer", "ceo"):
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
        for who in ("admin.officer", "treasurer", "ceo"):
            fr.decide(u[who], r5, "approve")
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
