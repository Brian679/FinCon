import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.utils import timezone

from api import sync
from finance import services as fin
from finance.models import Bill, ClientAccount, Fine, Offence, Property, RevenueHead
from social import services as sv
from social.models import Beneficiary, Farm, HuntingQuota, ResourcePermit, TrophyHunt, WaterPoint

from .base import CouncilTestCase


class FineTests(CouncilTestCase):
    def test_fine_billed_paid_and_waiver_rules(self):
        eho = self.user("eho")
        off = Offence.objects.get(code="HLT-02")
        fine = fin.issue_fine(eho, offence=off, offender_name="New Offender", national_id="99-111222Z99", phone="0779000111", location="Market")
        self.assertEqual(fine.amount, off.default_fine)
        self.assertEqual(fine.bill.revenue_head.code, "FINES")
        self.assertTrue(ClientAccount.objects.filter(id_number="99-111222Z99").exists())      # account opened for the offender
        again = fin.issue_fine(eho, offence=off, offender_name="New Offender", national_id="99-111222Z99", location="Market")
        self.assertEqual(again.account_id, fine.account_id)                                     # same person → same account
        with self.assertRaises(PermissionDenied):
            fin.issue_fine(self.user("engineer"), offence=off, offender_name="x", location="y")
        fin.issue_receipt(self.user("cashier"), revenue_head=fine.bill.revenue_head, amount=fine.amount, account=fine.account, bill=fine.bill)
        fine.refresh_from_db()
        self.assertEqual(fine.status, Fine.Status.PAID)
        with self.assertRaises(PermissionDenied):
            fin.decide_fine(eho, again, "waive", "x")                                           # issuer cannot waive
        with self.assertRaises(ValidationError):
            fin.decide_fine(self.user("treasurer"), again, "waive", "")                         # reason required
        fin.decide_fine(self.user("treasurer"), again, "waive", "First offence – warning given")
        again.refresh_from_db()
        again.bill.refresh_from_db()
        self.assertEqual(again.status, Fine.Status.WAIVED)
        self.assertEqual(again.bill.status, Bill.Status.CANCELLED)

    def test_late_penalties_once_a_month_and_not_on_fines(self):
        treasurer = self.user("treasurer")
        bill = Bill.objects.alive().filter(account=self.acc, status="UNPAID").first()
        Bill.objects.filter(pk=bill.pk).update(due_date=timezone.localdate() - timedelta(days=60))
        fine = fin.issue_fine(self.user("eho"), offence=Offence.objects.get(code="HLT-02"), offender_name="X", location="Y", account=self.acc)
        Bill.objects.filter(pk=fine.bill_id).update(due_date=timezone.localdate() - timedelta(days=60))
        created, _ = fin.run_late_penalties(treasurer, rate_pct=10, days_overdue=30)
        self.assertGreaterEqual(created, 1)
        pen = Bill.objects.get(revenue_head__code="PENALTY", description__startswith=f"Late payment penalty on {bill.number}")
        self.assertEqual(pen.amount, (bill.outstanding * Decimal("0.10")).quantize(Decimal("0.01")))
        self.assertFalse(Bill.objects.filter(revenue_head__code="PENALTY", description__contains=fine.bill.number).exists())
        self.assertEqual(fin.run_late_penalties(treasurer, rate_pct=10, days_overdue=30)[0], 0)   # same month again → nothing
        with self.assertRaises(PermissionDenied):
            fin.run_late_penalties(self.user("cashier"), rate_pct=10)


class CampfireTests(CouncilTestCase):
    def test_quota_hunt_billing_and_community_share(self):
        nro = self.user("natres.officer")
        q = HuntingQuota.objects.create(year=2031, species="LEOPARD", ward=29, quota=1, trophy_fee=Decimal("5000"))
        op = ClientAccount.objects.create(name="Test Safaris")
        hunt = sv.book_hunt(nro, quota=q, operator=op, client_name="A. Client")
        with self.assertRaises(ValidationError):
            sv.book_hunt(nro, quota=q, operator=op, client_name="Second client")                 # quota used up
        with self.assertRaises(PermissionDenied):
            sv.book_hunt(self.user("cashier"), quota=q, operator=op, client_name="x")
        sv.hunt_action(nro, hunt, "hunted", trophy_details="Male")
        hunt.refresh_from_db()
        self.assertEqual(hunt.status, TrophyHunt.Status.HUNTED)
        self.assertEqual(hunt.bill.amount, Decimal("5000.00"))
        self.assertEqual(hunt.community_share, Decimal("2750.00"))                                # 55 % to the ward
        fin.issue_receipt(self.user("cashier"), revenue_head=hunt.bill.revenue_head, amount="5000", account=op, bill=hunt.bill,
                          method="BANK", reference="RTGS-1")
        hunt.refresh_from_db()
        self.assertEqual(hunt.status, TrophyHunt.Status.PAID)
        row = next(r for r in sv.campfire_by_ward(2031) if r["ward"] == 29)
        self.assertEqual(row["community"], Decimal("2750.00"))


class NaturalResourceTests(CouncilTestCase):
    def test_permit_approve_pay_extract_limits(self):
        nro, head = self.user("natres.officer"), self.user("social.director")
        holder = ClientAccount.objects.create(name="Sand Co")
        today = timezone.localdate()
        p = ResourcePermit.objects.create(permit_type="SAND", holder=holder, location="River", unit="M3", quantity_allowed=Decimal("20"),
                                          unit_fee=Decimal("3"), valid_from=today, valid_to=today + timedelta(days=30), applied_by=nro)
        self.assertEqual(p.fee, Decimal("60"))
        with self.assertRaises(PermissionDenied):
            sv.decide_permit(nro, p, "approve")                                                  # captured it – someone else decides
        with self.assertRaises(ValidationError):
            sv.record_extraction(nro, p, quantity="5")                                           # not active yet
        sv.decide_permit(head, p, "approve", "ok")
        p.refresh_from_db()
        self.assertEqual(p.status, ResourcePermit.Status.APPROVED)
        fin.issue_receipt(self.user("cashier"), revenue_head=p.bill.revenue_head, amount="60", account=holder, bill=p.bill)
        p.refresh_from_db()
        self.assertEqual(p.status, ResourcePermit.Status.ACTIVE)                                 # active by itself when paid
        sv.record_extraction(nro, p, quantity="15", vehicle_reg="ABC 123")
        with self.assertRaises(ValidationError):
            sv.record_extraction(nro, p, quantity="6")                                           # over the permitted 20 m³
        self.assertEqual(p.quantity_left, Decimal("5"))


class FarmWaterWelfareTests(CouncilTestCase):
    def test_farm_register_feeds_farm_levy(self):
        owner = ClientAccount.objects.create(name="Farmer Moyo")
        farm = Farm.objects.create(name="Moyo plot", owner=owner, farm_number="T-77", location="Test scheme", hectares=Decimal("10"))
        self.assertEqual(farm.property.hectares, Decimal("10"))
        fin.run_levy_billing(self.user("treasurer"), RevenueHead.objects.get(code="FARM-LEVY"), 2032)
        self.assertEqual(farm.property.bills.get(period="2032").amount, Decimal("50.00"))
        farm.hectares = Decimal("12")
        farm.save()
        self.assertEqual(Property.objects.get(pk=farm.property_id).hectares, Decimal("12"))

    def test_welfare_and_sync_ops(self):
        so = self.user("social.officer")
        res = sync.push(so, [{"op_id": str(uuid.uuid4()), "type": "register.save",
                              "payload": {"register": "beneficiaries", "id": str(uuid.uuid4()),
                                          "fields": {"name": "Gogo Test", "ward": 3, "village": "Rimbi", "household_size": 2, "category": "ELDERLY",
                                                     "is_active": True}}}])[0]
        self.assertEqual(res["status"], "applied", res)
        b = Beneficiary.objects.get(name="Gogo Test")
        res = sync.push(so, [{"op_id": str(uuid.uuid4()), "type": "assistance.give",
                              "payload": {"beneficiary": str(b.pk), "kind": "FOOD", "description": "Maize 20 kg", "value": "12"}}])[0]
        self.assertEqual(res["status"], "applied", res)
        self.assertEqual(len(res["record"]["assistance"]), 1)
        res = sync.push(self.user("cashier"), [{"op_id": str(uuid.uuid4()), "type": "register.save",
                                                "payload": {"register": "water_points", "fields": {"name": "x", "village": "y"}}}])[0]
        self.assertEqual(res["status"], "rejected")                                              # Finance cannot edit water points
        res = sync.push(self.user("eho"), [{"op_id": str(uuid.uuid4()), "type": "register.save",
                                            "payload": {"register": "water_points", "fields": {"name": "New borehole", "village": "Rimbi",
                                                                                               "point_type": "BOREHOLE", "status": "WORKING",
                                                                                               "households_served": 30}}}])[0]
        self.assertEqual(res["status"], "applied", res)
        wp = WaterPoint.objects.get(name="New borehole")
        res = sync.push(self.user("eho"), [{"op_id": str(uuid.uuid4()), "type": "register.save",
                                            "payload": {"register": "water_points", "id": str(wp.pk), "fields": {"status": "BROKEN"}}}])[0]
        self.assertEqual(res["status"], "applied", res)
        wp.refresh_from_db()
        self.assertEqual((wp.status, wp.households_served), ("BROKEN", 30))                     # an edit keeps the other fields


class SocialAccessTests(CouncilTestCase):
    def test_pages_and_isolation(self):
        pages = ["/staff/social/wildlife/", "/staff/social/quotas/", "/staff/social/hunts/", "/staff/social/campfire/", "/staff/social/permits/",
                 "/staff/social/farms/", "/staff/social/water/", "/staff/social/welfare/", "/staff/finance/fines/", "/staff/finance/fines/offences/"]
        c = Client()
        c.force_login(self.user("social.director"))
        for url in pages[:-1]:
            self.assertEqual(c.get(url).status_code, 200, url)
        for name in ("hunts", "permits", "farms", "water", "wildlife"):
            for obj_url in [f"/staff/social/{name}/new/"]:
                self.assertEqual(c.get(obj_url).status_code, 200, obj_url)
        c.force_login(self.user("engineer"))
        self.assertEqual(c.get("/staff/social/wildlife/").status_code, 403)
        self.assertEqual(c.get("/staff/social/welfare/").status_code, 403)
        data = sync.staff_entities(self.user("engineer"))
        self.assertIsNone(data["wildlife"])
        self.assertIsNone(data["beneficiaries"])
        c.force_login(self.user("treasurer"))
        self.assertEqual(c.get("/staff/social/hunts/").status_code, 200)                          # Finance sees trophy fees
        self.assertEqual(c.get("/staff/finance/fines/offences/").status_code, 200)
        r = c.post("/staff/finance/billing-runs/", {"run": "penalty", "p-rate_pct": "10", "p-days_overdue": "30"})
        self.assertIn(r.status_code, (200, 302))
