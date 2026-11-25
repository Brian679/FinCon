from django.db import connection
from django.test import Client

from core.models import AuditLog
from finance import services

from .base import CouncilTestCase


class AuditTrailTests(CouncilTestCase):
    def test_changes_are_logged_with_user(self):
        from core import audit

        token = audit.set_actor(self.user("accountant"))
        try:
            self.acc.phone = "0779999999"
            self.acc.save()
        finally:
            audit._actor.reset(token)
        entry = AuditLog.objects.filter(model="finance.ClientAccount", object_id=str(self.acc.pk), action="UPDATE").first()
        self.assertEqual(entry.username, "accountant")
        self.assertEqual(entry.changes["phone"][1], "0779999999")

    def test_audit_entries_are_immutable(self):
        entry = AuditLog.objects.first()
        with self.assertRaises(Exception):
            entry.message = "x"
            entry.save()
        with self.assertRaises(Exception):
            entry.delete()
        with self.assertRaises(Exception):
            AuditLog.objects.all().delete()

    def test_tampering_is_detected(self):
        services.issue_receipt(self.user("cashier"), revenue_head=self.rates, amount="5", payer_name="A")
        self.assertTrue(AuditLog.verify_chain()[0])
        victim = AuditLog.objects.filter(action="PAYMENT").first()
        with connection.cursor() as c:
            c.execute("UPDATE core_auditlog SET message = 'nothing to see' WHERE id = %s", [victim.id])
        ok, broken = AuditLog.verify_chain()
        self.assertFalse(ok)
        self.assertEqual(broken, victim.id)


class AccessControlTests(CouncilTestCase):
    def login(self, username):
        c = Client()
        c.force_login(self.user(username))
        return c

    def test_cashier_cannot_open_vouchers_or_audit_trail(self):
        c = self.login("cashier")
        self.assertEqual(c.get("/staff/finance/vouchers/").status_code, 403)
        self.assertEqual(c.get("/staff/audit-trail/").status_code, 403)
        self.assertEqual(c.get("/staff/finance/receipts/new/").status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="DENIED", username="cashier").exists())

    def test_treasurer_sees_finance_but_not_user_admin(self):
        c = self.login("treasurer")
        self.assertEqual(c.get("/staff/finance/reports/").status_code, 200)
        self.assertEqual(c.get("/accounts/users/").status_code, 403)

    def test_system_admin_site_only_for_ict_admin(self):
        self.assertEqual(self.login("ceo").get("/system-admin/").status_code, 302)
        self.assertEqual(self.login("ict.admin").get("/system-admin/").status_code, 200)

    def test_clients_cannot_reach_staff_pages(self):
        c = self.login("resident")
        self.assertEqual(c.get("/staff/finance/").status_code, 403)
        self.assertEqual(c.get("/portal/").status_code, 200)

    def test_ceo_executive_overview(self):
        self.assertEqual(self.login("ceo").get("/staff/executive/").status_code, 200)
        self.assertEqual(self.login("accountant").get("/staff/executive/").status_code, 403)

    def test_lockout_after_five_failures(self):
        c = Client()
        for _ in range(5):
            c.post("/accounts/login/", {"username": "cashier", "password": "wrong"})
        r = c.post("/accounts/login/", {"username": "cashier", "password": "Chipinge@2026"})
        self.assertEqual(r.status_code, 200)  # still on login page
        self.assertTrue(self.user("cashier").is_locked)

    def test_new_staff_must_change_password(self):
        admin = self.login("ict.admin")
        r = admin.post("/accounts/users/new/", {"username": "new.clerk", "first_name": "New", "last_name": "Clerk", "role": "REVENUE_CLERK",
                                                "temporary_password": "Temp#Pass123", "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        u = self.user("new.clerk")
        self.assertEqual(u.department, "FINANCE")
        self.assertTrue(u.must_change_password)
        c = Client()
        c.post("/accounts/login/", {"username": "new.clerk", "password": "Temp#Pass123"})
        self.assertRedirects(c.get("/staff/"), "/accounts/password/")


class CharterTests(CouncilTestCase):
    def test_complaint_due_in_48_hours(self):
        from workflow import services as wf

        c = wf.log_complaint(self.user("resident"), department="FINANCE", subject="Wrong bill", details="...")
        self.assertAlmostEqual((c.acknowledge_due - c.created_at).total_seconds(), 48 * 3600, delta=5)
        self.assertEqual(c.client.username, "resident")

    def test_working_days_skip_weekends(self):
        from datetime import date

        from core.sla import add_working_days

        self.assertEqual(add_working_days(date(2026, 11, 27), 1), date(2026, 11, 30))  # Fri -> Mon

    def test_water_fault_is_urgent_with_24h_deadline(self):
        from workflow import services as wf

        sr = wf.report_service_request(self.user("resident"), category="WATER_FAULT", description="Burst pipe", location="Main St")
        self.assertEqual(sr.priority, "URGENT")
        self.assertEqual(sr.department, "SOCIAL")
        self.assertAlmostEqual((sr.due_at - sr.created_at).total_seconds(), 24 * 3600, delta=5)
