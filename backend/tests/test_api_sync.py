import uuid

from rest_framework.test import APIClient

from finance.models import ClientAccount, Receipt

from .base import CouncilTestCase


class SyncTests(CouncilTestCase):
    def api(self, username, app="council"):
        c = APIClient()
        r = c.post("/api/v1/auth/login/", {"username": username, "password": "Chipinge@2026", "app": app}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        return c

    def test_app_separation(self):
        c = APIClient()
        r = c.post("/api/v1/auth/login/", {"username": "resident", "password": "Chipinge@2026", "app": "council"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = c.post("/api/v1/auth/login/", {"username": "cashier", "password": "Chipinge@2026", "app": "client"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_pull_is_role_scoped(self):
        cashier = self.api("cashier").post("/api/v1/sync/pull/", {"cursors": {}}, format="json").data["entities"]
        self.assertIn("accounts", cashier)
        self.assertNotIn("vouchers", cashier)
        engineer = self.api("engineer").post("/api/v1/sync/pull/", {"cursors": {}}, format="json").data["entities"]
        self.assertNotIn("accounts", engineer)
        self.assertIn("projects", engineer)
        client = self.api("resident", "client").post("/api/v1/sync/pull/", {"cursors": {}}, format="json").data["entities"]
        self.assertEqual([a["name"] for a in client["accounts"]["items"]], ["Johannes Mhlanga"])
        self.assertEqual(len(client["bills"]["items"]), 1)

    def test_incremental_pull(self):
        c = self.api("cashier")
        first = c.post("/api/v1/sync/pull/", {"cursors": {"accounts": None}}, format="json").data["entities"]["accounts"]
        self.assertEqual(len(first["items"]), ClientAccount.objects.count())
        again = c.post("/api/v1/sync/pull/", {"cursors": {"accounts": first["cursor"]}}, format="json").data["entities"]["accounts"]
        self.assertLessEqual(len(again["items"]), 1)  # only the boundary record

    def test_offline_receipt_push_is_idempotent(self):
        c = self.api("cashier")
        op = {"op_id": str(uuid.uuid4()), "type": "receipt.create", "created_at": "2026-11-20T10:00:00Z",
              "payload": {"id": str(uuid.uuid4()), "account": str(self.acc.pk), "revenue_head": str(self.rates.pk), "amount": "15.00",
                          "currency": "USD", "method": "CASH", "captured_at": "2026-11-20T09:55:00Z"}}
        r1 = c.post("/api/v1/sync/push/", {"device_id": "phone-1", "operations": [op]}, format="json").data["results"][0]
        self.assertEqual(r1["status"], "applied", r1)
        r2 = c.post("/api/v1/sync/push/", {"device_id": "phone-1", "operations": [op]}, format="json").data["results"][0]
        self.assertTrue(r2["duplicate"])
        self.assertEqual(Receipt.objects.filter(pk=op["payload"]["id"]).count(), 1)
        rec = Receipt.objects.get(pk=op["payload"]["id"])
        self.assertEqual(rec.channel, "FIELD")
        self.assertIsNotNone(rec.offline_created_at)
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.balance, 0)

    def test_client_cannot_push_staff_operations(self):
        c = self.api("resident", "client")
        op = {"op_id": str(uuid.uuid4()), "type": "receipt.create", "payload": {"revenue_head": str(self.rates.pk), "amount": "1"}}
        r = c.post("/api/v1/sync/push/", {"operations": [op]}, format="json").data["results"][0]
        self.assertEqual(r["status"], "rejected")

    def test_client_offline_complaint_and_rejected_licence_on_foreign_account(self):
        c = self.api("resident", "client")
        ops = [
            {"op_id": str(uuid.uuid4()), "type": "complaint.create",
             "payload": {"id": str(uuid.uuid4()), "kind": "COMPLAINT", "department": "TECH", "subject": "Pothole", "details": "Big one"}},
            {"op_id": str(uuid.uuid4()), "type": "licence.apply",
             "payload": {"account": str(self.other_acc.pk), "licence_type": "SHOP", "business_name": "x", "premises": "y"}},
        ]
        res = c.post("/api/v1/sync/push/", {"operations": ops}, format="json").data["results"]
        self.assertEqual(res[0]["status"], "applied")
        self.assertEqual(res[0]["record"]["channel"], "APP")
        self.assertEqual(res[1]["status"], "rejected")

    def test_online_payment_issues_receipt(self):
        c = self.api("resident", "client")
        p = c.post("/api/v1/payments/", {"account": str(self.acc.pk), "amount": "15", "method": "ECOCASH", "phone": "0771234567"}, format="json")
        self.assertEqual(p.status_code, 201, p.content)
        done = c.post(f"/api/v1/payments/{p.data['reference']}/", {"action": "confirm"}, format="json").data
        self.assertEqual(done["status"], "PAID")
        self.assertTrue(done["receipt_number"].startswith("RCT-"))
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.balance, 0)

    def test_client_cannot_pay_into_foreign_account_via_link_guessing(self):
        c = self.api("resident", "client")
        r = c.post("/api/v1/client/link-account/", {"account_number": self.other_acc.account_number, "verifier": "0000000000"}, format="json")
        self.assertEqual(r.status_code, 400)
        p = c.post("/api/v1/payments/", {"account": str(self.other_acc.pk), "amount": "5"}, format="json")
        self.assertEqual(p.status_code, 400)
