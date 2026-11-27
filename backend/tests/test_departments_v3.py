from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.utils import timezone

from accounts.forms import StaffUserForm
from api import sync
from departments import leave
from departments import registers as rg
from departments.models import LeaveRequest, PublicLight, RecordFile, WorkOrder
from finance.models import ApprovalRecord
from core.models import Notification

from .base import CouncilTestCase


def nav_titles(user):
    return [s["title"] for s in user.nav_items()]


def nav_urls(user):
    return {i["url"] for s in user.nav_items() for i in s["items"]}


class LeaveFlowTests(CouncilTestCase):
    def _apply(self, who, start=20, days=2):
        today = timezone.localdate()
        lv = LeaveRequest.objects.create(employee=self.user(who), start_date=today + timedelta(days=start), end_date=today + timedelta(days=start + days),
                                         created_by=self.user(who))
        return leave.submit(lv)

    def test_officer_leave_goes_hod_then_hr_then_ceo(self):
        lv = self._apply("eho", start=100)
        self.assertEqual(lv.stage, "HOD")
        self.assertTrue(Notification.objects.filter(recipient=self.user("social.director"), title__startswith="Leave to approve").exists())
        with self.assertRaises(PermissionDenied):
            leave.decide(self.user("hr.officer"), lv, True)                     # not HR's turn yet
        with self.assertRaises(PermissionDenied):
            leave.decide(self.user("engineer"), lv, True)                       # another department's head
        lv = leave.decide(self.user("social.director"), lv, True, "OK")
        self.assertEqual((lv.status, lv.stage), ("PENDING", "HR"))
        self.assertTrue(Notification.objects.filter(recipient=self.user("eho"), title__contains="Head of Department").exists())
        lv = leave.decide(self.user("hr.officer"), lv, True, "Days available")
        self.assertEqual(lv.stage, "CEO")
        lv = leave.decide(self.user("ceo"), lv, True, "")
        self.assertEqual(lv.status, "APPROVED")
        self.assertEqual(ApprovalRecord.for_object(lv).count(), 3)
        self.assertTrue(Notification.objects.filter(recipient=self.user("eho"), title="Your leave is approved").exists())

    def test_rejection_needs_reason_and_ends_route(self):
        lv = self._apply("tech.officer", start=90)
        with self.assertRaises(ValidationError):
            leave.decide(self.user("engineer"), lv, False, "")
        lv = leave.decide(self.user("engineer"), lv, False, "Grading season – apply in January")
        self.assertEqual((lv.status, lv.stage), ("REJECTED", ""))

    def test_head_and_hr_own_leave_skip_themselves(self):
        lv = self._apply("engineer", start=110)                                             # a HOD: starts with HR
        self.assertEqual(lv.stage, "HR")
        lv = self._apply("hr.officer", start=120)
        self.assertEqual(lv.stage, "HOD")                                        # Administration Officer is the HOD
        lv = leave.decide(self.user("admin.officer"), lv, True)
        self.assertEqual(lv.stage, "CEO")                                        # the only other HR approver already approved
        with self.assertRaises(PermissionDenied):
            leave.decide(self.user("hr.officer"), lv, True)                      # never your own leave

    def test_leave_from_app_and_cancel(self):
        res = sync.push(self.user("cashier"), [{"op_id": "0b6c3f9e-1d2a-4c5b-9e8f-7a6b5c4d3e2f", "type": "leave.apply", "payload": {
            "start_date": str(timezone.localdate() + timedelta(days=60)), "end_date": str(timezone.localdate() + timedelta(days=61))}}])[0]
        self.assertEqual(res["status"], "applied", res)
        self.assertEqual(res["record"]["stage"], "HOD")
        self.assertEqual(res["record"]["approvers"], [self.user("treasurer").pk])
        lv = LeaveRequest.objects.get(pk=res["record"]["id"])
        leave.cancel(self.user("cashier"), lv)
        lv.refresh_from_db()
        self.assertEqual(lv.status, "CANCELLED")


class SocialRolesTests(CouncilTestCase):
    def test_each_officer_sees_own_functions(self):
        ema = nav_titles(self.user("natres.officer"))
        self.assertIn("Environment & natural resources", ema)
        self.assertIn("Agriculture", ema)
        self.assertNotIn("Public health & WASH", ema)
        self.assertNotIn("Community services", ema)
        eho = nav_titles(self.user("eho"))
        self.assertIn("Public health & WASH", eho)
        self.assertNotIn("Environment & natural resources", eho)
        self.assertNotIn("Agriculture", eho)
        com = nav_titles(self.user("social.officer"))
        self.assertIn("Community services", com)
        self.assertNotIn("Public health & WASH", com)
        self.assertNotIn("Environment & natural resources", com)
        hod = nav_titles(self.user("social.director"))
        for t in ("Community services", "Public health & WASH", "Environment & natural resources", "Agriculture"):
            self.assertIn(t, hod)
        c = Client()
        c.force_login(self.user("social.officer"))
        self.assertEqual(c.get("/staff/social/wildlife/").status_code, 403)
        self.assertEqual(c.get("/staff/social/inspections/").status_code, 403)
        self.assertEqual(c.get("/staff/social/facilities/").status_code, 200)
        c.force_login(self.user("eho"))
        self.assertEqual(c.get("/staff/social/inspections/").status_code, 200)
        self.assertEqual(c.get("/staff/social/welfare/").status_code, 403)
        self.assertIsNone(sync.staff_entities(self.user("eho"))["beneficiaries"])
        self.assertIsNone(sync.staff_entities(self.user("social.officer"))["health_inspections"])
        self.assertIn("Social Services", nav_titles(self.user("social.intern"))[0])


class GrowthPointTests(CouncilTestCase):
    def test_growth_point_manager_owns_housing_and_growth_points(self):
        gp = self.user("growthpoint")
        self.assertEqual(gp.department, "GROWTH")
        self.assertIn("Growth Points", nav_titles(gp))
        self.assertNotIn("Finance", nav_titles(gp))
        self.assertTrue(gp.has_cap("stands.allocate"))
        self.assertFalse(self.user("social.director").has_cap("stands.allocate"))
        c = Client()
        c.force_login(gp)
        for url in ("/staff/finance/areas/", "/staff/stands/" if False else "/staff/finance/leases/"):
            self.assertEqual(c.get(url).status_code, 200, url)
        self.assertEqual(c.get("/staff/finance/receipts/").status_code, 403)


class TechnicalAdminRegistersTests(CouncilTestCase):
    def test_work_order_flow_and_sign_off(self):
        eng, tech = self.user("engineer"), self.user("tech.officer")
        light = PublicLight.objects.filter(status="FAULTY").first()
        wo = WorkOrder.objects.create(kind="LIGHT", title="Fix", location="x", light=light, created_by=eng)
        rg.work_action(eng, wo, "assign", assigned_to=tech.pk)
        with self.assertRaises(PermissionDenied):
            rg.work_action(self.user("building.inspector") if False else self.user("cashier"), wo, "done")
        rg.work_action(tech, wo, "done", notes="Fixed", cost="50")
        with self.assertRaises(PermissionDenied):
            rg.work_action(tech, wo, "signoff")
        rg.work_action(eng, wo, "signoff", notes="Checked at night")
        light.refresh_from_db()
        self.assertEqual((wo.status, light.status), ("CLOSED", "WORKING"))

    def test_registry_loans_and_confidential_files(self):
        reg = self.user("registry")
        f = RecordFile.objects.get(file_number="ADM/HR/014")
        with self.assertRaises(PermissionDenied):
            rg.record_action(reg, f, "lend", borrower=self.user("cashier").pk)   # confidential HR file
        rg.record_action(reg, f, "lend", borrower=self.user("hr.officer").pk)
        self.assertEqual(f.status, "LOAN")
        with self.assertRaises(ValidationError):
            rg.record_action(reg, RecordFile.objects.get(file_number="FIN/STD/221"), "dispose")   # retention not over
        c = Client()
        c.force_login(self.user("tech.officer"))
        for url in ("/staff/technical/roads/", "/staff/technical/lights/", "/staff/technical/works/"):
            self.assertEqual(c.get(url).status_code, 200, url)
        self.assertEqual(c.get("/staff/admin/records/").status_code, 403)
        c.force_login(reg)
        self.assertEqual(c.get("/staff/admin/records/").status_code, 200)
