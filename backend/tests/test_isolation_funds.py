"""Department isolation, requests for funds / purchases (HOD -> Admin ->
Treasurer -> CEO -> payment) and memos between departments."""
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Notification
from finance import services as fin
from finance.models import PaymentVoucher
from workflow import funds as fr
from workflow import memos as mm
from workflow.models import FundsRequest, FundsRequestLine, Memo, Task

from .base import CouncilTestCase

PW = "Chipinge@2026"


def nav_titles(user):
    return [s["title"] for s in user.nav_items()]


def nav_urls(user):
    return {i["url"] for s in user.nav_items() for i in s["items"]}


class DepartmentIsolationTests(CouncilTestCase):
    def test_technical_staff_see_only_technical_and_shared_work(self):
        for name in ("engineer", "tech.officer"):
            titles = nav_titles(self.user(name))
            self.assertIn("Technical services", titles)
            for other in ("Finance", "Social services", "Administration", "Procurement"):
                self.assertNotIn(other, titles, f"{name} sees {other}")
            self.assertIn("My work", titles)

    def test_administration_staff_do_not_see_finance(self):
        for name in ("admin.officer", "hr.officer", "registry", "procurement"):
            titles = nav_titles(self.user(name))
            self.assertNotIn("Finance", titles, name)
            self.assertNotIn("Social services", titles, name)
            self.assertNotIn("Technical services", titles, name)
        self.assertIn("Administration", nav_titles(self.user("admin.officer")))

    def test_social_staff_do_not_see_finance_or_technical(self):
        for name in ("social.director", "social.officer", "eho"):
            titles = nav_titles(self.user(name))
            self.assertIn("Social services", titles)
            self.assertNotIn("Finance", titles)
            self.assertNotIn("Technical services", titles)
            self.assertNotIn("Administration", titles)

    def test_finance_staff_do_not_see_other_departments(self):
        titles = nav_titles(self.user("cashier"))
        self.assertIn("Finance", titles)
        for other in ("Social services", "Technical services", "Administration"):
            self.assertNotIn(other, titles)

    def test_ceo_sees_every_department(self):
        titles = nav_titles(self.user("ceo"))
        for d in ("Finance", "Social services", "Technical services", "Administration", "Internal audit"):
            self.assertIn(d, titles)

    def test_everyone_can_reach_other_departments_through_shared_links(self):
        for name in ("tech.officer", "eho", "hr.officer", "cashier"):
            urls = nav_urls(self.user(name))
            self.assertIn("/staff/memos/", urls)
            self.assertIn("/staff/funds/", urls)
            self.assertIn("/staff/finance/requisitions/", urls)

    def test_foreign_department_pages_are_refused(self):
        c = Client()
        c.login(username="tech.officer", password=PW)
        for url in ("/staff/finance/", "/staff/finance/receipts/", "/staff/social/incidents/", "/staff/meetings/", "/staff/policies/",
                    "/staff/social/stands/", "/staff/finance/licences/"):
            self.assertEqual(c.get(url).status_code, 403, url)
        self.assertEqual(c.get("/staff/technical/plans/").status_code, 200)
        c.login(username="hr.officer", password=PW)
        for url in ("/staff/finance/", "/staff/finance/vouchers/", "/staff/technical/projects/", "/staff/technical/plans/"):
            self.assertEqual(c.get(url).status_code, 403, url)

    def test_health_officer_only_sees_inspections_not_finance_licences(self):
        c = Client()
        c.login(username="eho", password=PW)
        r = c.get("/staff/finance/licences/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Shop health inspections")
        self.assertEqual(c.get("/staff/finance/").status_code, 403)

    def test_assets_are_scoped_to_department(self):
        from departments.models import Asset

        c = Client()
        c.login(username="tech.officer", password=PW)
        r = c.get("/staff/assets/")
        foreign = Asset.objects.exclude(department="TECH").first()
        if foreign:
            self.assertNotContains(r, foreign.asset_number)

    def test_sync_does_not_send_foreign_registers(self):
        api = APIClient()
        tok = api.post("/api/v1/auth/login/", {"username": "tech.officer", "password": PW, "app": "council"}, format="json").data["access"]
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")
        data = api.post("/api/v1/sync/pull/", {"cursors": {}}, format="json").data["entities"]
        for ent in ("licences", "stands", "incidents", "accounts", "receipts", "meetings", "policies"):
            self.assertNotIn(ent, data, ent)
        self.assertIn("funds_requests", data)
        self.assertIn("memos", data)


class FundsRequestFlowTests(CouncilTestCase):
    def make(self, user, *, payment=True, lines=((3, "30.00", "Subsistence – 3 days"), (2, "60.00", "Accommodation – 2 nights"))):
        req = FundsRequest.objects.create(requested_by=user, created_by=user, request_type="TRAVEL", title="Ward 12 water point inspection",
                                          purpose="Inspect boreholes", destination="Ward 12, Checheche", depart_date=timezone.localdate(),
                                          requires_payment=payment)
        for q, cost, desc in lines:
            FundsRequestLine.objects.create(request=req, description=desc, quantity=q, unit_cost=Decimal(cost))
        return req

    def test_full_route_with_payment_and_notifications(self):
        officer = self.user("tech.officer")
        req = self.make(officer)
        fr.submit(officer, req)
        req.refresh_from_db()
        self.assertEqual(req.total, Decimal("210.00"))
        self.assertEqual(req.status, FundsRequest.Status.PENDING_HOD)
        self.assertIn("Head of Department", fr.where_now(req))
        self.assertTrue(Notification.objects.filter(recipient=self.user("engineer"), title__contains=req.reference).exists())
        # other departments' heads cannot act at the HOD stage
        with self.assertRaises(PermissionDenied):
            fr.decide(self.user("social.director"), req, "approve")
        fr.decide(self.user("engineer"), req, "approve", "Needed")
        self.assertEqual(req.status, FundsRequest.Status.PENDING_ADMIN)
        self.assertTrue(Notification.objects.filter(recipient=officer, title__contains="Administration Officer").exists())
        fr.decide(self.user("admin.officer"), req, "approve")
        self.assertEqual(req.status, FundsRequest.Status.PENDING_TREASURER)
        fr.decide(self.user("treasurer"), req, "approve")
        self.assertEqual(req.status, FundsRequest.Status.PENDING_CEO)
        fr.decide(self.user("ceo"), req, "approve")
        self.assertEqual(req.status, FundsRequest.Status.PENDING_PAYMENT)
        self.assertTrue(Notification.objects.filter(recipient=officer, title__contains="fully approved").exists())
        # payment: voucher prepared, checked, approved again by Treasurer, paid
        v = fr.prepare_payment(self.user("exp.clerk"), req)
        req.refresh_from_db()
        self.assertEqual(req.status, FundsRequest.Status.PAYMENT_PROCESSING)
        self.assertIn("Accountant", fr.where_now(req))
        fin.decide_voucher(self.user("accountant"), v, True)
        req.refresh_from_db()
        self.assertIn("Treasurer", fr.where_now(req))
        fin.decide_voucher(self.user("treasurer"), v, True)
        self.fund_bank()
        v.refresh_from_db()
        fin.pay_voucher(self.user("exp.clerk"), v, bank_account=self.usd_bank, payment_reference="RTGS-1")
        req.refresh_from_db()
        self.assertEqual(req.status, FundsRequest.Status.PAID)
        self.assertTrue(Notification.objects.filter(recipient=officer, title__contains="has been paid").exists())
        states = [r["state"] for r in fr.route(req)]
        self.assertTrue(all(s in ("done", "skipped") for s in states), states)

    def test_no_payment_request_completes_after_ceo(self):
        officer = self.user("social.officer")
        req = self.make(officer, payment=False)
        fr.submit(officer, req)
        for name in ("social.director", "admin.officer", "treasurer", "ceo"):
            fr.decide(self.user(name), req, "approve")
        self.assertEqual(req.status, FundsRequest.Status.COMPLETED)

    def test_head_of_admin_and_treasurer_stages_are_not_repeated(self):
        hr = self.user("hr.officer")
        req = self.make(hr)
        fr.submit(hr, req)
        fr.decide(self.user("admin.officer"), req, "approve")  # as HOD
        self.assertEqual(req.status, FundsRequest.Status.PENDING_TREASURER)  # admin stage skipped
        acc = self.user("accountant")
        req2 = self.make(acc)
        fr.submit(acc, req2)
        fr.decide(self.user("treasurer"), req2, "approve")  # as HOD
        self.assertEqual(req2.status, FundsRequest.Status.PENDING_ADMIN)
        fr.decide(self.user("admin.officer"), req2, "approve")
        self.assertEqual(req2.status, FundsRequest.Status.PENDING_CEO)  # treasurer stage skipped

    def test_head_request_goes_straight_to_admin(self):
        eng = self.user("engineer")
        req = self.make(eng)
        fr.submit(eng, req)
        self.assertEqual(req.status, FundsRequest.Status.PENDING_ADMIN)
        with self.assertRaises(PermissionDenied):
            fr.decide(eng, req, "approve")

    def test_return_and_resubmit_then_reject(self):
        officer = self.user("tech.officer")
        req = self.make(officer)
        fr.submit(officer, req)
        with self.assertRaises(ValidationError):
            fr.decide(self.user("engineer"), req, "return", "")
        fr.decide(self.user("engineer"), req, "return", "Add the vehicle number")
        self.assertEqual(req.status, FundsRequest.Status.RETURNED)
        fr.submit(officer, req)
        self.assertEqual(req.status, FundsRequest.Status.PENDING_HOD)
        fr.decide(self.user("engineer"), req, "approve")
        fr.decide(self.user("admin.officer"), req, "reject", "No budget this quarter")
        self.assertEqual(req.status, FundsRequest.Status.REJECTED)
        self.assertTrue(Notification.objects.filter(recipient=officer, title__contains="rejected").exists())

    def test_reminder_goes_to_current_holder_with_cooldown(self):
        officer = self.user("tech.officer")
        req = self.make(officer)
        fr.submit(officer, req)
        fr.decide(self.user("engineer"), req, "approve")
        fr.remind(officer, req, "Workshop is on Monday")
        n = Notification.objects.filter(recipient=self.user("admin.officer"), title__startswith="Reminder").first()
        self.assertIsNotNone(n)
        self.assertIn("Workshop is on Monday", n.body)
        with self.assertRaises(ValidationError):
            fr.remind(officer, req)
        with self.assertRaises(PermissionDenied):
            fr.remind(self.user("cashier"), req)

    def test_visibility(self):
        officer = self.user("tech.officer")
        req = self.make(officer)
        fr.submit(officer, req)
        self.assertTrue(fr.can_view(self.user("engineer"), req))
        self.assertTrue(fr.can_view(self.user("admin.officer"), req))
        self.assertFalse(fr.can_view(self.user("social.officer"), req))
        self.assertFalse(fr.can_view(self.user("social.director"), req))

    def test_web_pages(self):
        c = Client()
        c.login(username="tech.officer", password=PW)
        r = c.post("/staff/funds/new/", {
            "request_type": "TRAVEL", "title": "Bridge inspection Ward 3", "purpose": "Inspect Musirizwi bridge", "destination": "Ward 3",
            "depart_date": timezone.localdate().isoformat(), "currency": "USD", "requires_payment": "on", "payment_method": "EFT",
            "lines-TOTAL_FORMS": "2", "lines-INITIAL_FORMS": "0", "lines-MIN_NUM_FORMS": "1", "lines-MAX_NUM_FORMS": "1000",
            "lines-0-description": "Subsistence", "lines-0-quantity": "2", "lines-0-unit_cost": "30", "lines-1-quantity": "1",
            "submit": "1"})
        self.assertEqual(r.status_code, 302)
        req = FundsRequest.objects.get(title="Bridge inspection Ward 3")
        self.assertEqual(req.status, FundsRequest.Status.PENDING_HOD)
        page = c.get(f"/staff/funds/{req.pk}/")
        self.assertContains(page, "Where is this request now?")
        self.assertContains(page, "Send reminder")
        c.login(username="engineer", password=PW)
        self.assertContains(c.get("/staff/funds/?box=awaiting"), req.reference)
        c.post(f"/staff/funds/{req.pk}/action/", {"action": "approve", "comment": "ok"})
        req.refresh_from_db()
        self.assertEqual(req.status, FundsRequest.Status.PENDING_ADMIN)
        c.login(username="cashier", password=PW)
        self.assertEqual(c.get(f"/staff/funds/{req.pk}/").status_code, 404)


class MemoTests(CouncilTestCase):
    def test_memo_to_another_department_becomes_a_task(self):
        eng = self.user("engineer")
        memo = mm.send(eng, kind="ACTION", to_department="SOCIAL", subject="Borehole at Ward 12 school", body="Please test the water quality.")
        self.assertTrue(Notification.objects.filter(recipient=self.user("social.director"), title__contains="Borehole").exists())
        self.assertFalse(mm.is_participant(self.user("cashier"), memo))
        with self.assertRaises(PermissionDenied):
            mm.to_task(eng, memo, assigned_to=self.user("eho"))
        task = mm.to_task(self.user("social.director"), memo, assigned_to=self.user("eho"))
        self.assertEqual(task.department, "SOCIAL")
        self.assertTrue(mm.is_participant(self.user("eho"), memo))
        from workflow import services as wf

        wf.update_task(self.user("eho"), task, status=Task.Status.DONE, comment="Water is safe")
        self.assertTrue(Notification.objects.filter(recipient=eng, title__contains="done").exists())
        mm.reply(eng, memo, "Thank you", close=True)
        memo.refresh_from_db()
        self.assertEqual(memo.status, Memo.Status.CLOSED)

    def test_heads_can_send_tasks_to_other_departments_head_only(self):
        from workflow import services as wf

        t = wf.create_task(self.user("engineer"), title="Clear drain at clinic", department="SOCIAL")
        self.assertIsNone(t.assigned_to)
        with self.assertRaises(PermissionDenied):
            wf.create_task(self.user("engineer"), title="x", department="SOCIAL", assigned_to=self.user("eho"))

    def test_memo_pages(self):
        c = Client()
        c.login(username="hr.officer", password=PW)
        r = c.post("/staff/memos/new/", {"kind": "MESSAGE", "to_department": "FINANCE", "priority": "NORMAL", "subject": "Payroll query",
                                         "body": "Please confirm overtime rates."})
        self.assertEqual(r.status_code, 302)
        memo = Memo.objects.get(subject="Payroll query")
        c.login(username="treasurer", password=PW)
        self.assertContains(c.get("/staff/memos/"), "Payroll query")
        self.assertEqual(c.get(f"/staff/memos/{memo.pk}/").status_code, 200)
        memo.refresh_from_db()
        self.assertEqual(memo.status, Memo.Status.READ)
        c.login(username="engineer", password=PW)
        self.assertEqual(c.get(f"/staff/memos/{memo.pk}/").status_code, 403)


class FundsSyncTests(CouncilTestCase):
    def api(self, username):
        c = APIClient()
        r = c.post("/api/v1/auth/login/", {"username": username, "password": PW, "app": "council"}, format="json")
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        return c

    def test_request_raised_and_approved_from_phones(self):
        import uuid

        rid = str(uuid.uuid4())
        officer = self.api("tech.officer")
        r = officer.post("/api/v1/sync/push/", {"operations": [{"op_id": str(uuid.uuid4()), "type": "funds.create", "payload": {
            "id": rid, "request_type": "TRAVEL", "title": "Culvert survey", "purpose": "Survey", "destination": "Ward 9",
            "depart_date": timezone.localdate().isoformat(), "lines": [{"description": "Subsistence", "quantity": "2", "unit_cost": "30"}]}}]},
            format="json")
        self.assertEqual(r.data["results"][0]["status"], "applied", r.data)
        rec = r.data["results"][0]["record"]
        self.assertEqual(rec["status"], "P_HOD")
        self.assertIn(self.user("engineer").pk, rec["deciders"])
        self.assertEqual(rec["route"][1]["state"], "current")
        eng = self.api("engineer")
        r = eng.post("/api/v1/sync/push/", {"operations": [{"op_id": str(uuid.uuid4()), "type": "funds.action",
                                                            "payload": {"id": rid, "action": "approve", "comment": "ok"}}]}, format="json")
        self.assertEqual(r.data["results"][0]["record"]["status"], "P_ADMIN")
        r = officer.post("/api/v1/sync/push/", {"operations": [{"op_id": str(uuid.uuid4()), "type": "funds.action",
                                                                "payload": {"id": rid, "action": "remind"}}]}, format="json")
        self.assertEqual(r.data["results"][0]["status"], "applied")
        # memo from phone
        r = officer.post("/api/v1/sync/push/", {"operations": [{"op_id": str(uuid.uuid4()), "type": "memo.create", "payload": {
            "id": str(uuid.uuid4()), "kind": "ACTION", "to_department": "FINANCE", "subject": "Fuel card", "body": "Please top up."}}]}, format="json")
        self.assertEqual(r.data["results"][0]["status"], "applied", r.data)


class PaymentsLinkTests(CouncilTestCase):
    """Council and client apps see the same money: a payment taken anywhere
    reaches the shop owner's phone with the balance left, and the area overview."""

    def test_counter_payment_notifies_owner_with_balance(self):
        from core.models import MessageLog
        from finance.models import Bill, ClientAccount

        resident = self.user("resident")
        acc = ClientAccount.objects.get(name="Johannes Mhlanga")
        self.assertTrue(acc.portal_users.filter(pk=resident.pk).exists())
        acc.recalculate()
        before = acc.balance
        bill = Bill.objects.alive().filter(account=acc, status__in=["UNPAID", "PART"]).first()
        r = fin.issue_receipt(self.user("cashier"), revenue_head=bill.revenue_head, amount=Decimal("5"), account=acc, bill=bill)
        n = Notification.objects.filter(recipient=resident, title__startswith="Payment received").latest("created_at")
        self.assertIn(r.number, n.body)
        self.assertIn(f"{before - Decimal('5'):,.2f}", n.body)
        self.assertTrue(MessageLog.objects.filter(channel="SMS", account_number=acc.account_number, campaign="Payment confirmation").exists())

    def test_field_payment_from_council_phone_reaches_client_phone(self):
        import uuid

        from finance.models import ClientAccount

        acc = ClientAccount.objects.get(name="Johannes Mhlanga")
        acc.recalculate()
        cashier = APIClient()
        tok = cashier.post("/api/v1/auth/login/", {"username": "cashier", "password": PW, "app": "council"}, format="json").data["access"]
        cashier.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")
        r = cashier.post("/api/v1/sync/push/", {"operations": [{"op_id": str(uuid.uuid4()), "type": "receipt.create", "payload": {
            "id": str(uuid.uuid4()), "account": str(acc.pk), "revenue_head": str(self.rates.pk), "amount": str(acc.balance), "method": "CASH"}}]},
            format="json").data["results"][0]
        self.assertEqual(r["status"], "applied", r)
        client = APIClient()
        tok = client.post("/api/v1/auth/login/", {"username": "resident", "password": PW, "app": "client"}, format="json").data["access"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")
        data = client.post("/api/v1/sync/pull/", {"cursors": {}}, format="json").data["entities"]
        mine = [a for a in data["accounts"]["items"] if a["id"] == str(acc.pk)][0]
        self.assertEqual(Decimal(mine["balance"]), Decimal("0.00"))
        self.assertTrue(all(b["status"] == "PAID" for b in data["bills"]["items"] if b["account"] == str(acc.pk)))
        self.assertTrue(any(n["title"].startswith("Payment received") for n in data["notifications"]["items"]))

    def test_area_overview_matches_shop_boards(self):
        from finance.models import Property, TradingArea

        rows, total = fin.area_overview()
        self.assertGreater(total["shops"], 0)
        for r in rows:
            board = [fin.property_compliance(p) for p in Property.objects.alive().filter(area=r["area"], is_active=True)]
            self.assertEqual(r["paid"], sum(1 for b in board if b["ok"]), r["area"].name)
            self.assertEqual(r["owed"], sum((b["total"] for b in board), Decimal("0")), r["area"].name)
        c = Client()
        c.login(username="treasurer", password=PW)
        page = c.get("/staff/finance/areas/")
        self.assertContains(page, "Areas overview")
        self.assertContains(page, TradingArea.objects.first().name)
        self.assertEqual(c.get("/staff/finance/areas/?export=csv")["Content-Type"], "text/csv")
        c.login(username="engineer", password=PW)
        self.assertEqual(c.get("/staff/finance/areas/").status_code, 403)

    def test_change_password_from_phone(self):
        api = APIClient()
        tok = api.post("/api/v1/auth/login/", {"username": "eho", "password": PW, "app": "council"}, format="json").data["access"]
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(api.post("/api/v1/auth/password/", {"old_password": "wrong", "new_password": "Borehole#2027"}, format="json").status_code, 400)
        self.assertEqual(api.post("/api/v1/auth/password/", {"old_password": PW, "new_password": "123"}, format="json").status_code, 400)
        self.assertEqual(api.post("/api/v1/auth/password/", {"old_password": PW, "new_password": "Borehole#2027"}, format="json").status_code, 200)
        self.assertTrue(self.user("eho").check_password("Borehole#2027"))

    def test_header_shows_profile_menu_not_welcome_text(self):
        c = Client()
        c.login(username="tech.officer", password=PW)
        page = c.get("/staff/")
        self.assertContains(page, 'id="profile-menu"')
        self.assertNotContains(page, "Welcome,")
        self.assertContains(page, "Change password")


class AreaBoardLinkTests(CouncilTestCase):
    def test_board_offers_record_payment_for_owing_shops(self):
        from finance.models import TradingArea

        c = Client()
        c.login(username="cashier", password=PW)
        area = TradingArea.objects.get(name="Checheche Growth Point")
        page = c.get(f"/staff/finance/areas/{area.pk}/")
        self.assertContains(page, "Record payment")
        self.assertContains(page, "/staff/finance/receipts/new/?account=")


class AppParityTests(CouncilTestCase):
    """Everything a finance / admin officer does on the website can be done from the council app."""

    def api(self, username):
        c = APIClient()
        tok = c.post("/api/v1/auth/login/", {"username": username, "password": PW, "app": "council"}, format="json").data["access"]
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")
        return c

    def push(self, c, op_type, payload):
        import uuid

        return c.post("/api/v1/sync/push/", {"operations": [{"op_id": str(uuid.uuid4()), "type": op_type, "payload": payload}]},
                      format="json").data["results"][0]

    def test_cashup_from_phone(self):
        cashier = self.api("cashier")
        acc = self.acc
        self.assertEqual(self.push(cashier, "receipt.create", {"account": str(acc.pk), "revenue_head": str(self.rates.pk), "amount": "10"})["status"], "applied")
        r = self.push(cashier, "cashup.submit", {"currency": "USD", "declared_cash": "10"})
        self.assertEqual(r["status"], "applied", r)
        self.assertEqual(Decimal(r["record"]["variance"]), Decimal("0"))
        r2 = self.push(self.api("accountant"), "cashup.verify", {"cashup": r["record"]["id"], "ok": True})
        self.assertEqual(r2["record"]["status"], "VERIFIED")

    def test_voucher_prepare_check_approve_pay_from_phones(self):
        from finance.models import Supplier

        self.fund_bank()
        sup = Supplier.objects.filter(status="ACTIVE").first()
        r = self.push(self.api("exp.clerk"), "voucher.prepare", {"supplier": str(sup.pk), "description": "Stationery", "amount": "120",
                                                                  "department": "ADMIN", "category": "SUPPLIER"})
        self.assertEqual(r["status"], "applied", r)
        vid = r["record"]["id"]
        self.push(self.api("accountant"), "voucher.decide", {"voucher": vid, "approve": True})
        self.push(self.api("treasurer"), "voucher.decide", {"voucher": vid, "approve": True})
        r = self.push(self.api("exp.clerk"), "voucher.pay", {"voucher": vid, "bank_account": str(self.usd_bank.pk), "payment_reference": "RTGS-77"})
        self.assertEqual(r["record"]["status"], "PAID", r)

    def test_purchase_order_from_phone(self):
        from finance.models import Requisition, RequisitionItem, Supplier

        officer = self.user("tech.officer")
        req = Requisition.objects.create(requested_by=officer, department="TECH", purpose="Cement", created_by=officer)
        RequisitionItem.objects.create(requisition=req, description="Cement bags", quantity=10, unit_cost=Decimal("12"))
        fin.submit_requisition(officer, req)
        for name in ("engineer", "accountant", "treasurer"):
            fin.decide_requisition(self.user(name), req, True)
        sup = Supplier.objects.filter(status="ACTIVE").first()
        r = self.push(self.api("procurement"), "po.create", {"requisition": str(req.pk), "supplier": str(sup.pk)})
        self.assertEqual(r["status"], "applied", r)
        r = self.push(self.api("procurement"), "po.receive", {"po": r["record"]["id"], "notes": "All bags delivered"})
        self.assertEqual(r["record"]["status"], "DELIVERED")

    def test_correspondence_from_phone(self):
        reg = self.api("registry")
        r = self.push(reg, "correspondence.create", {"sender": "Ministry of Local Government", "subject": "Budget circular",
                                                     "department": "FINANCE"})
        self.assertEqual(r["status"], "applied", r)
        r = self.push(self.api("treasurer"), "correspondence.update", {"id": r["record"]["id"], "status": "RESPONDED",
                                                                       "response_summary": "Acknowledged"})
        self.assertEqual(r["record"]["status"], "RESPONDED")
        self.assertEqual(self.push(self.api("tech.officer"), "correspondence.create", {"sender": "x", "subject": "y", "department": "FINANCE"})["status"],
                         "rejected")

    def test_reports_and_audit_trail_endpoints(self):
        self.assertEqual(self.api("treasurer").get("/api/v1/reports/finance/").status_code, 200)
        self.assertEqual(self.api("cashier").get("/api/v1/reports/finance/").status_code, 403)
        data = self.api("ceo").get("/api/v1/reports/executive/").data
        self.assertEqual(len(data["departments"]), 6)
        self.assertEqual(self.api("engineer").get("/api/v1/reports/executive/").status_code, 403)
        self.assertEqual(self.api("chief.auditor").get("/api/v1/audit/").status_code, 200)
        self.assertEqual(self.api("tech.officer").get("/api/v1/audit/").status_code, 403)


class LoopholeTests(CouncilTestCase):
    def login_api(self, username, password=PW, app="council"):
        c = APIClient()
        r = c.post("/api/v1/auth/login/", {"username": username, "password": password, "app": app}, format="json")
        return c, r

    def test_login_must_name_the_app(self):
        r = APIClient().post("/api/v1/auth/login/", {"username": "cashier", "password": PW}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_password_change_signs_out_other_devices(self):
        phone1, r1 = self.login_api("eho")
        phone2, r2 = self.login_api("eho")
        phone1.credentials(HTTP_AUTHORIZATION=f"Bearer {r1.data['access']}")
        phone2.credentials(HTTP_AUTHORIZATION=f"Bearer {r2.data['access']}")
        import time
        time.sleep(1.1)
        r = phone1.post("/api/v1/auth/password/", {"old_password": PW, "new_password": "Borehole#2027"}, format="json")
        self.assertEqual(r.status_code, 200)
        phone1.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        self.assertEqual(phone1.get("/api/v1/me/").status_code, 200)       # this phone keeps working
        self.assertEqual(phone2.get("/api/v1/me/").status_code, 401)       # the other phone is signed out
        self.assertEqual(APIClient().post("/api/v1/auth/refresh/", {"refresh": r2.data["refresh"]}, format="json").status_code, 401)

    def test_deactivated_user_is_locked_out_of_the_app(self):
        phone, r = self.login_api("cashier")
        phone.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        u = self.user("cashier")
        u.is_active = False
        u.save()
        self.assertEqual(phone.get("/api/v1/me/").status_code, 401)

    def test_receipt_is_booked_to_the_bills_revenue_head(self):
        from finance.models import Bill, RevenueHead

        bill = Bill.objects.alive().filter(account=self.acc, status="UNPAID").first()
        wrong = RevenueHead.objects.exclude(pk=bill.revenue_head_id).first()
        r = fin.issue_receipt(self.user("cashier"), revenue_head=wrong, amount=Decimal("1"), account=self.acc, bill=bill)
        self.assertEqual(r.revenue_head_id, bill.revenue_head_id)

    def test_voiding_the_fee_receipt_suspends_the_licence(self):
        from finance.models import Licence

        lic = fin.apply_licence(self.user("cashier"), account=self.other_acc, licence_type="SHOP", business_name="Grace Tuckshop", premises="Stand 9")
        if lic.status == Licence.Status.INSPECTION:
            lic = fin.inspect_licence(self.user("eho"), lic, True, "Clean")
        lic = fin.decide_licence(self.user("treasurer"), lic, True, fee=Decimal("60"))
        r = fin.issue_receipt(self.user("cashier"), revenue_head=lic.bill.revenue_head, amount=lic.bill.outstanding, account=lic.account, bill=lic.bill)
        lic.refresh_from_db()
        self.assertEqual(lic.status, Licence.Status.ISSUED)
        fin.request_void(self.user("cashier"), r, "Wrong account")
        fin.decide_void(self.user("accountant"), r, True)
        lic.refresh_from_db()
        self.assertEqual(lic.status, Licence.Status.APPROVED)

    def test_finance_cannot_pay_their_own_request(self):
        from workflow.models import FundsRequest, FundsRequestLine

        clerk = self.user("exp.clerk")
        req = FundsRequest.objects.create(requested_by=clerk, created_by=clerk, request_type="ADVANCE", title="Float", purpose="Petty cash float")
        FundsRequestLine.objects.create(request=req, description="Float", quantity=1, unit_cost=Decimal("50"))
        fr.submit(clerk, req)
        for name in ("treasurer", "admin.officer", "ceo"):
            if req.status in FundsRequest.PENDING:
                fr.decide(self.user(name), req, "approve")
        self.assertEqual(req.status, FundsRequest.Status.PENDING_PAYMENT)
        with self.assertRaises(PermissionDenied):
            fr.prepare_payment(clerk, req)
        v = fr.prepare_payment(self.user("accountant"), req)
        self.assertEqual(v.funds_requests.first().pk, req.pk)

    def test_payee_other_than_requester_is_flagged(self):
        from workflow.models import FundsRequest

        r = FundsRequest(requested_by=self.user("tech.officer"), payee_name="Zuva Petroleum")
        self.assertTrue(r.payee_differs)
        r.payee_name = "Prosper Mlambo"
        self.assertFalse(r.payee_differs)

    def test_csv_export_neutralises_formulas(self):
        import io

        from core.crud import SafeCsvWriter

        buf = io.StringIO()
        SafeCsvWriter(buf).writerow(['=HYPERLINK("http://x")', "Normal", 5])
        self.assertIn("'=HYPERLINK", buf.getvalue())

    def test_upload_must_be_a_real_document(self):
        from django.core.exceptions import ValidationError
        from django.core.files.uploadedfile import SimpleUploadedFile

        from core.validators import validate_document

        with self.assertRaises(ValidationError):
            validate_document(SimpleUploadedFile("quote.exe", b"MZ..."))
        with self.assertRaises(ValidationError):
            validate_document(SimpleUploadedFile("quote.pdf", b"not a pdf"))
        validate_document(SimpleUploadedFile("quote.pdf", b"%PDF-1.7 ..."))


class AllocationTests(CouncilTestCase):
    def test_payment_for_a_bill_pays_that_bill_first(self):
        from finance.models import Bill, RevenueHead

        old = Bill.objects.alive().filter(account=self.other_acc, status="UNPAID").first()
        fee = fin.create_bill(self.user("treasurer"), account=self.other_acc, revenue_head=RevenueHead.objects.get(code="LIC-SHOP"), amount=Decimal("60"))
        fin.issue_receipt(self.user("cashier"), revenue_head=fee.revenue_head, amount=Decimal("60"), account=self.other_acc, bill=fee)
        fee.refresh_from_db()
        self.assertEqual(fee.status, Bill.Status.PAID)
        if old:
            old.refresh_from_db()
            self.assertEqual(old.status, Bill.Status.UNPAID)

    def test_money_on_a_cancelled_bill_is_not_lost(self):
        from finance.models import RevenueHead

        bill = fin.create_bill(self.user("treasurer"), account=self.other_acc, revenue_head=RevenueHead.objects.get(code="MARKET"), amount=Decimal("10"))
        fin.issue_receipt(self.user("cashier"), revenue_head=bill.revenue_head, amount=Decimal("10"), account=self.other_acc, bill=bill)
        self.other_acc.refresh_from_db()
        before = self.other_acc.balance
        bill.status = "CANCELLED"
        bill.save()
        self.other_acc.recalculate()
        self.assertEqual(self.other_acc.balance, before - Decimal("10"))
