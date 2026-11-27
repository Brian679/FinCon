import uuid
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import Client
from rest_framework.test import APIClient

from api import sync
from finance import services as fin
from finance.models import Fine, Offence
from social import services as sv
from social.models import ResourcePermit

from .base import CouncilTestCase


def nav_labels(user):
    return [i["label"] for s in user.nav_items() for i in s["items"]]


class AdministrationRolesTests(CouncilTestCase):
    def test_each_admin_officer_sees_own_work(self):
        labels = {u: nav_labels(self.user(u)) for u in ("admin.officer", "liaison", "land.officer", "data.officer", "hr.officer", "admin.intern")}
        self.assertIn("Stakeholder engagement (WADCO, village assemblies)", labels["liaison"])
        self.assertIn("Public notices to residents", labels["liaison"])
        self.assertNotIn("Council land bank – land parcels", labels["liaison"])
        self.assertIn("Council land bank – land parcels", labels["land.officer"])
        self.assertIn("Assets & infrastructure", labels["land.officer"])
        self.assertNotIn("Public notices to residents", labels["land.officer"])
        self.assertIn("Data & information management", labels["data.officer"])
        self.assertNotIn("Staff directory", labels["data.officer"])
        for item in ("Council land bank – land parcels", "Stakeholder engagement (WADCO, village assemblies)", "Data & information management",
                     "Staff directory"):
            self.assertIn(item, labels["admin.officer"], item)          # HR & Administration Officer (HOD) oversees everything
        self.assertNotIn("Council land bank – land parcels", labels["admin.intern"])
        c = Client()
        c.force_login(self.user("land.officer"))
        self.assertEqual(c.get("/staff/admin/land/").status_code, 200)
        self.assertEqual(c.get("/staff/admin/engagements/").status_code, 403)
        c.force_login(self.user("data.officer"))
        r = c.get("/staff/admin/data/")
        self.assertContains(r, "Data quality")
        self.assertEqual(c.get("/staff/admin/data/?export=no-phone").status_code, 200)
        c.force_login(self.user("auditor"))
        self.assertEqual(c.get("/staff/audit/plan/").status_code, 200)
        c.force_login(self.user("cashier"))
        self.assertEqual(c.get("/staff/admin/data/").status_code, 403)


class ClientAppTests(CouncilTestCase):
    def api(self, user):
        c = APIClient()
        c.force_authenticate(self.user(user))
        return c

    def test_resident_finds_and_pays_a_fine(self):
        fine = fin.issue_fine(self.user("eho"), offence=Offence.objects.get(code="HLT-02"), offender_name="Johannes Visitor", national_id="77-123456X77",
                              phone="0779998877", location="Market")
        c = self.api("resident")
        self.assertEqual(c.post("/api/v1/fines/claim/", {"reference": fine.reference, "id_or_phone": "0711111111"}, format="json").status_code, 400)
        r = c.post("/api/v1/fines/claim/", {"reference": fine.reference.lower(), "id_or_phone": "0779 998 877"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        ents = sync.entities_for(self.user("resident"))
        self.assertTrue(ents["fines"][0].filter(pk=fine.pk).exists())
        pay = c.post("/api/v1/payments/", {"account": str(fine.account_id), "bill": str(fine.bill_id), "amount": str(fine.amount), "method": "ECOCASH",
                                           "phone": "0779998877"}, format="json")
        self.assertIn(pay.status_code, (200, 201), pay.content)
        c.post(f"/api/v1/payments/{pay.json()['reference']}/", {"action": "confirm"}, format="json")
        fine.refresh_from_db()
        self.assertEqual(fine.status, Fine.Status.PAID)

    def test_sand_collector_applies_pays_and_gets_permit(self):
        res = sync.push(self.user("resident"), [{"op_id": str(uuid.uuid4()), "type": "permit.apply", "payload": {
            "id": str(uuid.uuid4()), "permit_type": "SAND", "location": "Rusitu river", "quantity": "10", "ward": 12, "days": 14}}])[0]
        self.assertEqual(res["status"], "applied", res)
        p = ResourcePermit.objects.get(pk=res["record"]["id"])
        self.assertEqual((p.unit, p.unit_fee, p.fee, p.status), ("M3", Decimal("3"), Decimal("30"), "APPLIED"))
        sv.decide_permit(self.user("natres.officer"), p, "approve", "OK", unit_fee="2.50")
        p.refresh_from_db()
        self.assertEqual(p.fee, Decimal("25.00"))
        c = self.api("resident")
        pay = c.post("/api/v1/payments/", {"account": str(p.holder_id), "bill": str(p.bill_id), "amount": "25", "method": "ECOCASH", "phone": "0771234567"},
                     format="json")
        c.post(f"/api/v1/payments/{pay.json()['reference']}/", {"action": "confirm"}, format="json")
        p.refresh_from_db()
        self.assertEqual(p.status, "ACTIVE")

    def test_new_resident_without_account_gets_one_for_permit(self):
        from accounts.models import User

        u = User.objects.create_user("sandman", password="x", first_name="Simba", last_name="Collector", user_type=User.UserType.CLIENT, phone="0778880000")
        res = sync.push(u, [{"op_id": str(uuid.uuid4()), "type": "permit.apply", "payload": {"permit_type": "SAND", "location": "Save river", "quantity": 3}}])[0]
        self.assertEqual(res["status"], "applied", res)
        self.assertEqual(u.client_accounts.count(), 1)

    def test_notices_reach_residents(self):
        titles = [n.title for n in sync.entities_for(self.user("resident"))["public_notices"][0]]
        self.assertIn("Water interruption – Checheche, Friday", titles)
        with self.assertRaises(PermissionDenied):
            sync.op_register_save(self.user("cashier"), {"register": "public_notices", "fields": {"title": "x", "body": "y"}})
        res = sync.push(self.user("liaison"), [{"op_id": str(uuid.uuid4()), "type": "register.save", "payload": {
            "register": "public_notices", "id": str(uuid.uuid4()), "fields": {"title": "Ward 25 meeting", "category": "MEETING", "body": "Tuesday 10:00"}}}])[0]
        self.assertEqual(res["status"], "applied", res)
