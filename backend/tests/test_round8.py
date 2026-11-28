import uuid
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import User
from api import sync
from core.models import MessageLog
from departments import services as dept
from departments.models import BuildingPlan
from finance import services as fin
from finance.models import Bill, Property
from workflow.models import Complaint

from .base import CouncilTestCase


class BillingScheduleTests(CouncilTestCase):
    def test_residential_annual_commercial_half_yearly_balance_brought_forward(self):
        treasurer = self.user("treasurer")
        house = Property.objects.get(stand_number="101")
        shop = Property.objects.get(stand_number="B12")
        fin.run_property_billing(treasurer, 2031, 1)
        fin.run_property_billing(treasurer, 2031, 2)
        house_bills = Bill.objects.filter(property=house, period__startswith="2031")
        self.assertEqual([(b.period, b.amount) for b in house_bills], [("2031", house.monthly_rates * 12)])        # one bill a year
        shop_bills = Bill.objects.filter(property=shop, period__startswith="2031").order_by("period")
        self.assertEqual([b.period for b in shop_bills], ["2031-H1", "2031-H2"])                                    # Jan–Jun, Jul–Dec
        self.assertEqual(shop_bills[0].amount, shop.monthly_rates * 6)
        h1 = shop_bills[0]
        self.assertEqual(shop_bills[1].brought_forward, sum((b.outstanding for b in Bill.objects.filter(
            property=shop, status__in=["UNPAID", "PART"]).exclude(pk=shop_bills[1].pk)), Decimal(0)))              # unpaid H1 carried forward
        self.assertGreaterEqual(shop_bills[1].brought_forward, h1.amount)
        self.assertEqual(fin.run_property_billing(treasurer, 2031, 2)[0], 0)                                         # idempotent
        farm = Property.objects.filter(hectares__gt=0).first()
        self.assertTrue(Bill.objects.filter(property=farm, period="2031", revenue_head__code="FARM-LEVY").exists())  # farms: annual levy


@override_settings(MEDIA_ROOT="/tmp/crdc-test-media")
class BuildingPlanTests(CouncilTestCase):
    def test_upload_plan_file_route_and_notify_on_decision(self):
        resident = User.objects.get(username="resident")
        res = sync.push(resident, [{"op_id": str(uuid.uuid4()), "type": "plan.create", "payload": {
            "id": str(uuid.uuid4()), "stand_number": "101", "location": "Chipinge Township", "development_type": "RES", "description": "3-room house",
            "floor_area": "80"}}])[0]
        plan = BuildingPlan.objects.get(pk=res["record"]["id"])
        c = APIClient()
        c.force_authenticate(resident)
        r = c.post(f"/api/v1/plans/{plan.pk}/drawing/", {"file": SimpleUploadedFile("plan.pdf", b"%PDF-1.4 test", content_type="application/pdf")},
                   format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["drawing_name"].split("_")[0].split(".")[0], "plan")
        r = c.post(f"/api/v1/plans/{plan.pk}/drawing/", {"file": SimpleUploadedFile("x.exe", b"MZ", content_type="application/octet-stream")},
                   format="multipart")
        self.assertEqual(r.status_code, 400)
        officer = self.user("tech.officer")
        engineer = self.user("engineer")
        fin.issue_receipt(self.user("cashier"), revenue_head=plan.bill.revenue_head, amount=plan.bill.amount, account=plan.bill.account, bill=plan.bill)
        plan.refresh_from_db()
        dept.plan_action(officer, plan, "recommend", note="Meets by-laws")
        dept.plan_action(engineer, plan, "approve", note="Approved – build as drawn")
        self.assertTrue(MessageLog.objects.filter(channel="SMS", subject__contains=plan.reference).exists())       # SMS as well as the app
        web = self.client
        web.force_login(officer)
        self.assertEqual(web.get(f"/staff/technical/plans/{plan.pk}/file/").status_code, 200)


class ProfileAndFeedbackTests(CouncilTestCase):
    def test_edit_my_details_and_send_a_message(self):
        u = User.objects.get(username="resident")
        c = APIClient()
        c.force_authenticate(u)
        r = c.post("/api/v1/me/", {"first_name": "Johannes", "last_name": "Mhlanga-Dube", "email": "jm@example.com", "phone": "0771234500", "ward": 4},
                   format="json")
        self.assertEqual(r.status_code, 200, r.content)
        u.refresh_from_db()
        self.assertEqual((u.last_name, u.phone, u.ward), ("Mhlanga-Dube", "0771234500", 4))
        self.assertEqual(c.post("/api/v1/me/", {"email": "not-an-email"}, format="json").status_code, 400)
        res = sync.push(u, [{"op_id": str(uuid.uuid4()), "type": "complaint.create", "payload": {
            "id": str(uuid.uuid4()), "details": "The street light at the bus stop has been off for a week."}}])[0]
        self.assertEqual(res["status"], "applied", res)
        msg = Complaint.objects.get(pk=res["record"]["id"])
        self.assertEqual((msg.kind, msg.department, msg.subject[:10]), ("ENQUIRY", "ADMIN", "The street"))
