import uuid
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from accounts.models import User
from api import sync
from finance import services as fin
from finance.models import Bill, CertificateRequest, OnlinePayment, Property

from .base import CouncilTestCase


class PayEverythingTests(CouncilTestCase):
    def test_one_prompt_pays_every_bill_on_every_account(self):
        tsitsi = User.objects.get(username="tsitsi")
        bills = list(Bill.objects.filter(account__portal_users=tsitsi, status__in=["UNPAID", "PART"]))
        self.assertGreaterEqual(len({b.account_id for b in bills}), 2)                     # her own account and her company's
        total = sum(b.outstanding for b in bills)
        c = APIClient()
        c.force_authenticate(tsitsi)
        r = c.post("/api/v1/payments/", {"bills": [str(b.pk) for b in bills], "method": "ECOCASH", "phone": "0716000555"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Decimal(r.data["amount"]), total)
        r = c.post(f"/api/v1/payments/{r.data['reference']}/", {"action": "confirm"}, format="json")
        self.assertEqual(r.data["status"], "PAID", r.data)
        self.assertEqual(len(r.data["receipt_numbers"]), len(bills))                       # a receipt per bill
        self.assertFalse(Bill.objects.filter(pk__in=[b.pk for b in bills]).exclude(status="PAID").exists())
        from finance.models import Fine
        self.assertFalse(Fine.objects.filter(account__portal_users=tsitsi, status="ISSUED").exists())   # the fine is settled too

    def test_pay_part_of_the_balance_oldest_bills_first(self):
        tsitsi = User.objects.get(username="tsitsi")
        bills = sorted(Bill.objects.filter(account__portal_users=tsitsi, status="UNPAID"), key=lambda b: (b.due_date, b.created_at))
        with self.assertRaises(ValidationError):
            fin.start_bulk_payment(tsitsi, bills=bills, amount="100000")                     # more than is owing
        first = bills[0]
        p = fin.start_bulk_payment(tsitsi, bills=bills, amount=first.outstanding + Decimal("3"))
        fin.confirm_online_payment(p, provider_reference="SIM1")
        first.refresh_from_db()
        self.assertEqual(first.status, "PAID")                                               # oldest bill cleared first
        self.assertEqual(Bill.objects.filter(pk__in=[b.pk for b in bills], status="PART").count(), 1)   # the rest goes to the next one
        self.assertEqual(p.receipts.count(), 2)

    def test_cannot_pay_someone_elses_bills_in_a_batch(self):
        resident = User.objects.get(username="resident")
        other = Bill.objects.filter(status="UNPAID").exclude(account__portal_users=resident).first()
        with self.assertRaises(PermissionDenied):
            fin.start_bulk_payment(resident, bills=[other])


class CertificateTests(CouncilTestCase):
    def test_residence_letter_fee_then_office_then_issued(self):
        tsitsi = User.objects.get(username="tsitsi")
        c = CertificateRequest.objects.get(user=tsitsi, kind="RESIDENCE")
        self.assertEqual((c.status, c.fee_bill.amount), ("FEE_DUE", Decimal("5.00")))
        fin.issue_receipt(self.user("cashier"), revenue_head=c.fee_bill.revenue_head, amount="5", account=c.account, bill=c.fee_bill)
        c.refresh_from_db()
        self.assertEqual(c.status, "PROCESSING")
        with self.assertRaises(PermissionDenied):
            fin.certificate_action(self.user("cashier"), c, "issue")                          # finance does not issue residence letters
        admin = User.objects.filter(role="ADMIN_OFFICER").first()
        fin.certificate_action(admin, c, "issue")
        c.refresh_from_db()
        self.assertTrue(c.number.startswith("POR-"))
        self.assertIsNotNone(c.valid_until)
        web = self.client
        web.force_login(admin)
        self.assertContains(web.get(f"/staff/finance/certificates/{c.pk}/print/"), "resides at")
        web.force_login(self.user("cashier"))
        self.assertEqual(web.get(f"/staff/finance/certificates/{c.pk}/print/").status_code, 404)   # other offices do not see it

    def test_clearance_needs_a_clear_balance_and_your_own_stand(self):
        tsitsi = User.objects.get(username="tsitsi")
        shop = Property.objects.get(stand_number="C21")
        with self.assertRaises(ValidationError):
            fin.request_certificate(tsitsi, kind="CLEARANCE", property=shop, purpose="Selling the stand")      # owes rates and a fine
        with self.assertRaises(PermissionDenied):
            fin.request_certificate(tsitsi, kind="CLEARANCE", property=Property.objects.get(stand_number="101"))   # not hers
        for b in Bill.objects.filter(account=shop.account, status__in=["UNPAID", "PART"]):
            fin.issue_receipt(self.user("cashier"), revenue_head=b.revenue_head, amount=b.outstanding, account=b.account, bill=b)
        res = sync.push(tsitsi, [{"op_id": str(uuid.uuid4()), "type": "certificate.request", "payload": {
            "id": str(uuid.uuid4()), "kind": "CLEARANCE", "property": str(shop.pk), "purpose": "Selling the stand"}}])[0]
        self.assertEqual(res["status"], "applied", res)
        c = CertificateRequest.objects.get(pk=res["record"]["id"])
        fin.issue_receipt(self.user("cashier"), revenue_head=c.fee_bill.revenue_head, amount=c.fee_bill.amount, account=c.account, bill=c.fee_bill)
        c.refresh_from_db()
        ents = sync.entities_for(self.user("treasurer"))
        self.assertTrue(ents["certificates"][0].filter(pk=c.pk).exists())
        res = sync.push(self.user("treasurer"), [{"op_id": str(uuid.uuid4()), "type": "certificate.action", "payload": {
            "certificate": str(c.pk), "action": "issue"}}])[0]
        self.assertEqual(res["record"]["status"], "ISSUED", res)

    def test_burial_order_needs_the_details(self):
        tsitsi = User.objects.get(username="tsitsi")
        with self.assertRaises(ValidationError):
            fin.request_certificate(tsitsi, kind="BURIAL", other_party_name="T. Chiwara")
        c = fin.request_certificate(tsitsi, kind="BURIAL", other_party_name="T. Chiwara", event_date="2026-11-20", place="Gaza cemetery")
        self.assertEqual(c.account.portal_users.filter(pk=tsitsi.pk).count(), 1)


class WelfareTests(CouncilTestCase):
    def test_apply_assess_and_assist(self):
        from social import services as sv
        from social.models import Beneficiary

        tsitsi = User.objects.get(username="tsitsi")
        res = sync.push(tsitsi, [{"op_id": str(uuid.uuid4()), "type": "assistance.apply", "payload": {
            "id": str(uuid.uuid4()), "category": "CHRONIC", "need": "MEDICAL", "village": "Gaza", "household_size": 4, "children": 2,
            "reason": "Dialysis three times a week."}}])[0]
        self.assertEqual(res["status"], "applied", res)
        b = Beneficiary.objects.get(pk=res["record"]["id"])
        self.assertEqual((b.status, b.is_active), ("APPLIED", False))
        with self.assertRaises(ValidationError):
            sv.apply_for_assistance(tsitsi, category="CHRONIC", need="MEDICAL", village="Gaza", reason="again")      # one at a time
        with self.assertRaises(ValidationError):
            sv.give_assistance(self.user("social.director"), b, kind="MEDICAL", description="x")                     # not approved yet
        with self.assertRaises(PermissionDenied):
            sv.assess_beneficiary(self.user("cashier"), b, "approve")
        res = sync.push(self.user("social.director"), [{"op_id": str(uuid.uuid4()), "type": "beneficiary.assess", "payload": {
            "beneficiary": str(b.pk), "action": "approve", "note": "Visited"}}])[0]
        self.assertEqual(res["record"]["status"], "APPROVED", res)
        b.refresh_from_db()
        sv.give_assistance(self.user("social.director"), b, kind="MEDICAL", description="Transport to dialysis – November", value="35")
        ents = sync.entities_for(tsitsi)
        mine = ents["beneficiaries"][0]
        self.assertEqual(mine.count(), 1)
        self.assertEqual(ents["beneficiaries"][1](mine.first()).data["assistance_total"], "35.00")
        self.assertFalse(sync.entities_for(User.objects.get(username="resident"))["beneficiaries"][0].exists())   # others' records stay private


class StandBeneficiaryTests(CouncilTestCase):
    def test_owner_keeps_beneficiaries_council_sees_them_and_letter_for_a_son(self):
        from finance.models import StandBeneficiary

        tsitsi = User.objects.get(username="tsitsi")
        house = Property.objects.get(stand_number="612")
        self.assertEqual(StandBeneficiary.objects.filter(property=house, is_active=True).count(), 3)       # seeded: son, daughter, spouse
        res = sync.push(tsitsi, [{"op_id": str(uuid.uuid4()), "type": "stand_beneficiary.save", "payload": {
            "id": str(uuid.uuid4()), "property": str(house.pk), "full_name": "Gogo Mapfumo", "relationship": "PARENT", "national_id": "63-100200G63"}}])[0]
        self.assertEqual(res["status"], "applied", res)
        with self.assertRaises(PermissionDenied):                                                        # not her stand
            fin.save_stand_beneficiary(tsitsi, Property.objects.get(stand_number="101"), full_name="X", relationship="CHILD")
        with self.assertRaises(PermissionDenied):                                                        # staff without the right
            fin.save_stand_beneficiary(self.user("eho"), house, full_name="X", relationship="CHILD")
        staff = sync.entities_for(self.user("cashier"))["stand_beneficiaries"][0]
        self.assertEqual(staff.filter(property=house, is_active=True).count(), 4)                         # the council sees the same list
        self.assertFalse(sync.entities_for(User.objects.get(username="resident"))["stand_beneficiaries"][0].filter(property=house).exists())
        # proof of residence for someone typed in on the request: saved to the stand and named on the letter
        c = fin.request_certificate(tsitsi, kind="RESIDENCE", property=house, purpose="School", subject_name="Rutendo Mapfumo",
                                    subject_id="63-990011R63", subject_relationship="CHILD")
        self.assertEqual((c.subject_name, c.subject_id), ("Rutendo Mapfumo", "63-990011R63"))
        self.assertEqual(StandBeneficiary.objects.filter(property=house, full_name="Rutendo Mapfumo", is_active=True).count(), 2)  # new ID -> new record
        son = CertificateRequest.objects.get(user=tsitsi, kind="RESIDENCE", subject_name="Tafadzwa Mapfumo")
        fin.issue_receipt(self.user("cashier"), revenue_head=son.fee_bill.revenue_head, amount=son.fee_bill.amount, account=son.account, bill=son.fee_bill)
        son.refresh_from_db()
        admin = User.objects.filter(role="ADMIN_OFFICER").first()
        fin.certificate_action(admin, son, "issue")
        self.client.force_login(admin)
        page = self.client.get(f"/staff/finance/certificates/{son.pk}/print/")
        self.assertContains(page, "Tafadzwa Mapfumo")
        self.assertContains(page, "63-556677T63")
        self.client.force_login(self.user("cashier"))
        self.assertContains(self.client.get(f"/staff/finance/stands/{house.pk}/"), "Tafadzwa Mapfumo")
