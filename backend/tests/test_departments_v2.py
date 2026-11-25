"""Two websites, shop/stand register, claims, leases & levies, reminders, and
the departmental registers (stage-by-stage workflows), plus their sync ops."""
import uuid
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import MessageLog
from departments import services as dept
from departments.models import Asset, BuildingPlan, CommunityActivity, Incident
from finance import services
from finance.models import AccountClaim, Bill, ClientAccount, Lease, Property, Requisition, RevenueHead, TradingArea

from .base import CouncilTestCase


@override_settings(CLIENT_HOSTS=["www.crdc.test"], STAFF_HOSTS=["staff.crdc.test"], ALLOWED_HOSTS=["*"])
class TwoWebsitesTests(CouncilTestCase):
    def test_client_site_has_no_staff_pages(self):
        c = Client(HTTP_HOST="www.crdc.test")
        self.assertEqual(c.get("/").status_code, 200)
        self.assertEqual(c.get("/portal/login/").status_code, 200)
        self.assertEqual(c.get("/staff/login/").status_code, 404)
        self.assertEqual(c.get("/system-admin/").status_code, 404)

    def test_staff_site_has_no_client_pages(self):
        c = Client(HTTP_HOST="staff.crdc.test")
        self.assertEqual(c.get("/staff/login/").status_code, 200)
        self.assertEqual(c.get("/portal/").status_code, 404)
        self.assertRedirects(c.get("/"), "/staff/", fetch_redirect_response=False)

    def test_each_login_rejects_the_other_kind_of_user(self):
        r = Client(HTTP_HOST="staff.crdc.test").post("/staff/login/", {"username": "resident", "password": "Chipinge@2026"})
        self.assertContains(r, "council staff only")
        r = Client(HTTP_HOST="www.crdc.test").post("/portal/login/", {"username": "treasurer", "password": "Chipinge@2026"})
        self.assertContains(r, "staff website")
        r = Client(HTTP_HOST="www.crdc.test").post("/portal/login/", {"username": "resident", "password": "Chipinge@2026"})
        self.assertRedirects(r, "/portal/", fetch_redirect_response=False)


class StandRegisterTests(CouncilTestCase):
    def test_claim_auto_approved_when_details_match(self):
        resident = self.user("resident")
        prop = Property.objects.get(stand_number="B14")
        resident.phone = prop.account.phone
        resident.save()
        claim = services.submit_claim(resident, stand_number="B14", area=prop.area)
        self.assertEqual(claim.status, AccountClaim.Status.APPROVED)
        self.assertTrue(prop.account.portal_users.filter(pk=resident.pk).exists())

    def test_unknown_stand_waits_for_verification_then_creates_account(self):
        resident = self.user("resident")
        area = TradingArea.objects.get(name="Chiriga Market")
        claim = services.submit_claim(resident, stand_number="M77", area=area, business_name="Moyo Veggies", claim_type="SHOP")
        self.assertEqual(claim.status, AccountClaim.Status.PENDING)
        with self.assertRaises(PermissionDenied):
            services.decide_claim(self.user("engineer"), claim, True, create_account=True)
        services.decide_claim(self.user("cashier"), claim, True, create_account=True, monthly_rates=Decimal("20"), note="ID seen")
        claim.refresh_from_db()
        self.assertEqual(claim.status, AccountClaim.Status.APPROVED)
        self.assertEqual(claim.account.properties.get().business_name, "Moyo Veggies")
        self.assertTrue(claim.account.portal_users.filter(pk=resident.pk).exists())

    def test_wrong_details_are_not_auto_linked(self):
        prop = Property.objects.get(stand_number="B14")
        claim = services.submit_claim(self.user("resident"), stand_number="B14", area=prop.area, phone="0000000000")
        self.assertEqual(claim.status, AccountClaim.Status.PENDING)
        self.assertEqual(claim.matched_property, prop)
        self.assertFalse(prop.account.portal_users.filter(username="resident").exists())

    def test_csv_import(self):
        rows = [
            {"area": "Chimanimani Turnoff", "ward": "9", "stand_number": "T1", "owner_name": "Paida Stores", "account_type": "BUS",
             "phone": "0779000111", "land_use": "COM", "business_name": "Paida Stores", "monthly_rates": "25"},
            {"area": "Chimanimani Turnoff", "ward": "9", "stand_number": "T2", "owner_name": "Kuda Ncube", "phone": "0779000222", "land_use": "RES"},
            {"area": "Chimanimani Turnoff", "stand_number": "", "owner_name": "x"},
        ]
        stats = services.import_register(self.user("cashier"), rows)
        self.assertEqual(stats["properties_new"], 2)
        self.assertEqual(len(stats["errors"]), 1)
        stats = services.import_register(self.user("cashier"), rows[:1])
        self.assertEqual(stats["properties_updated"], 1)
        self.assertEqual(TradingArea.objects.get(name="Chimanimani Turnoff").properties.count(), 2)


class LeviesLeasesRemindersTests(CouncilTestCase):
    def test_levy_and_lease_billing_are_idempotent(self):
        levy = RevenueHead.objects.get(code="DEV-LEVY")
        year = timezone.localdate().year
        area = TradingArea.objects.get(name="Checheche Growth Point")
        created, _ = services.run_levy_billing(self.user("treasurer"), levy, year, area=area)
        self.assertEqual(created, area.properties.count())
        self.assertEqual(services.run_levy_billing(self.user("treasurer"), levy, year, area=area)[0], 0)
        today = timezone.localdate()
        self.assertEqual(services.run_lease_billing(self.user("treasurer"), today.year, today.month)[0], 1)
        self.assertEqual(services.run_lease_billing(self.user("treasurer"), today.year, today.month)[0], 0)
        lease = Lease.objects.get()
        self.assertTrue(Bill.objects.filter(account=lease.lessee, revenue_head__code="RENT").exists())

    def test_compliance_and_reminders(self):
        area = TradingArea.objects.get(name="Checheche Growth Point")
        rows = [services.property_compliance(p) for p in area.properties.all()]
        self.assertTrue(all(not r["ok"] for r in rows))  # rates billed, no licences
        sent = services.send_compliance_reminders(self.user("cashier"), list(area.properties.all()), campaign="test")
        self.assertGreater(sent, 0)
        sms = MessageLog.objects.filter(channel="SMS", campaign="test").first()
        self.assertIn("Register free", sms.body)  # not on the app yet -> invitation
        with self.assertRaises(PermissionDenied):
            services.send_compliance_reminders(self.user("engineer"), list(area.properties.all()))

    def test_paid_up_shop_is_skipped(self):
        prop = Property.objects.get(stand_number="S2")
        lic = services.apply_licence(self.user("cashier"), account=prop.account, licence_type="BUSINESS", business_name="Selinda Grocers",
                                     premises="S2", property=prop)
        services.decide_licence(self.user("treasurer"), lic, True)
        services.issue_receipt(self.user("cashier"), revenue_head=self.rates, amount=str(prop.account.balance), account=prop.account)
        c = services.property_compliance(prop)
        self.assertEqual(c["licence"], "VALID")
        self.assertTrue(c["ok"])
        self.assertEqual(services.send_compliance_reminders(self.user("cashier"), [prop]), 0)

    def test_area_board_page(self):
        c = Client()
        c.force_login(self.user("treasurer"))
        area = TradingArea.objects.get(name="Checheche Growth Point")
        r = c.get(f"/staff/finance/areas/{area.pk}/")
        self.assertContains(r, "Tafara Hardware")
        self.assertContains(r, "OWING")


class DepartmentWorkflowTests(CouncilTestCase):
    def test_building_plan_stages(self):
        plan = BuildingPlan.objects.get(status="RECOMMEND")
        with self.assertRaises(PermissionDenied):  # reviewer can't approve
            dept.plan_action(self.user("tech.officer"), plan, "approve")
        dept.plan_action(self.user("engineer"), plan, "approve", "Approved subject to fire exits")
        plan.refresh_from_db()
        self.assertEqual(plan.status, "APPROVED")
        dept.plan_action(self.user("tech.officer"), plan, "inspect", "Foundations OK")
        dept.plan_action(self.user("tech.officer"), plan, "complete", "Final inspection passed")
        plan.refresh_from_db()
        self.assertEqual(plan.status, "COMPLETED")

    def test_client_plan_creates_fee_bill_and_approval_needs_payment(self):
        plan = dept.submit_building_plan(self.user("resident"), stand_number="101", location="Chipinge", development_type="ALT",
                                         description="Veranda")
        self.assertIsNotNone(plan.bill)
        dept.plan_action(self.user("tech.officer"), plan, "recommend", "ok")
        with self.assertRaises(ValidationError):
            dept.plan_action(self.user("engineer"), plan, "approve")

    def test_activity_report_verified_by_hod_only(self):
        act = CommunityActivity.objects.get(status="DONE")  # by the EHO
        with self.assertRaises(PermissionDenied):
            dept.verify_activity(self.user("social.officer"), act)
        dept.verify_activity(self.user("social.director"), act, True, "Good work")
        act.refresh_from_db()
        self.assertEqual(act.status, "VERIFIED")

    def test_incident_closed_only_by_director(self):
        inc = Incident.objects.get(incident_type="HWC")
        with self.assertRaises(PermissionDenied):
            dept.update_incident(self.user("social.officer"), inc, status="CLOSED")
        dept.update_incident(self.user("social.director"), inc, status="CLOSED", response="Herd moved back to the park")
        inc.refresh_from_db()
        self.assertEqual(inc.status, "CLOSED")

    def test_broken_borehole_alerts_head(self):
        b = Asset.objects.get(name="Borehole – Checheche clinic")
        dept.report_asset_condition(self.user("eho"), b, condition="BROKEN", note="Handle snapped")
        b.refresh_from_db()
        self.assertEqual(b.status, "REPAIR")
        self.assertTrue(self.user("social.director").notifications.filter(title__icontains="broken").exists())

    def test_department_overview_access(self):
        c = Client()
        c.force_login(self.user("social.director"))
        self.assertContains(c.get("/staff/department/"), "Social Services")
        c.force_login(self.user("ceo"))
        self.assertContains(c.get("/staff/department/?dept=TECH"), "Plans awaiting decision")
        c.force_login(self.user("social.officer"))
        self.assertEqual(c.get("/staff/department/").status_code, 403)


class SyncV2Tests(CouncilTestCase):
    def api(self, username, app="council"):
        c = APIClient()
        r = c.post("/api/v1/auth/login/", {"username": username, "password": "Chipinge@2026", "app": app}, format="json")
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        return c

    def push(self, c, op_type, payload):
        op = {"op_id": str(uuid.uuid4()), "type": op_type, "payload": payload}
        return c.post("/api/v1/sync/push/", {"operations": [op]}, format="json").data["results"][0]

    def test_scoped_entities(self):
        eng = self.api("engineer").post("/api/v1/sync/pull/", {"cursors": {}}, format="json").data["entities"]
        self.assertIn("building_plans", eng)
        self.assertNotIn("claims", eng)
        self.assertTrue(all(s["department"] == "TECH" for s in eng["staff"]["items"]))
        cashier = self.api("cashier").post("/api/v1/sync/pull/", {"cursors": {}}, format="json").data["entities"]
        self.assertIn("trading_areas", cashier)
        self.assertIn("claims", cashier)
        client = self.api("resident", "client").post("/api/v1/sync/pull/", {"cursors": {}}, format="json").data["entities"]
        self.assertNotIn("staff", client)
        self.assertIn("claims", client)

    def test_officer_requisition_from_phone_reaches_hod(self):
        r = self.push(self.api("tech.officer"), "requisition.create", {"id": str(uuid.uuid4()), "purpose": "Shovels",
                      "items": [{"description": "Shovel", "quantity": "10", "unit_cost": "8"}]})
        self.assertEqual(r["status"], "applied", r)
        req = Requisition.objects.get(pk=r["record"]["id"])
        self.assertEqual((req.status, req.total, req.department), ("SUBMITTED", Decimal("80.00"), "TECH"))
        r = self.push(self.api("engineer"), "requisition.decide", {"requisition": str(req.pk), "approve": True})
        self.assertEqual(r["record"]["status"], "HOD_OK")

    def test_hod_assigns_task_from_phone(self):
        officer = self.user("tech.officer")
        r = self.push(self.api("engineer"), "task.create", {"title": "Inspect culverts", "assigned_to": officer.pk})
        self.assertEqual(r["status"], "applied", r)
        r = self.push(self.api("engineer"), "task.create", {"title": "Out of my department", "assigned_to": self.user("cashier").pk})
        self.assertEqual(r["status"], "rejected")

    def test_client_claim_and_staff_decision_by_sync(self):
        area = TradingArea.objects.get(name="Chiriga Market")
        r = self.push(self.api("resident", "client"), "claim.create", {"id": str(uuid.uuid4()), "stand_number": "C9", "area": str(area.pk),
                                                                      "business_name": "Chiriga Tea Room", "claim_type": "SHOP"})
        self.assertEqual(r["record"]["status"], "PENDING")
        r = self.push(self.api("accountant"), "claim.decide", {"claim": r["record"]["id"], "approve": True, "create_account": True})
        self.assertEqual(r["record"]["status"], "APPROVED", r)
        self.assertTrue(ClientAccount.objects.filter(name__icontains="Johannes", portal_users__username="resident").exists())

    def test_reminders_from_phone(self):
        area = TradingArea.objects.get(name="Mount Selinda Business Centre")
        r = self.push(self.api("cashier"), "reminders.send", {"area": str(area.pk)})
        self.assertEqual(r["status"], "applied", r)
        self.assertGreater(r["info"]["sent"], 0)
