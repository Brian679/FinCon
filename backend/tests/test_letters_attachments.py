"""Reception: scanned letters sent to the CEO / any officer, turned into department tasks; phone messages;
files (quotations, invoices, scans) on requests for funds and letters; purchase confirmed before payment."""
import shutil
import tempfile
import uuid
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Notification
from workflow import attachments as att
from workflow import funds as fr
from workflow import services as wf
from workflow.models import Attachment, Correspondence, FundsRequest, FundsRequestLine, PhoneMessage, Task

from .base import CouncilTestCase

PW = "Chipinge@2026"
MEDIA = tempfile.mkdtemp(prefix="crdc-test-media-")


def pdf(name="scan.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n% test\n", content_type="application/pdf")


@override_settings(MEDIA_ROOT=MEDIA)
class LettersAndCallsTests(CouncilTestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def api(self, username):
        c = APIClient()
        tok = c.post("/api/v1/auth/login/", {"username": username, "password": PW, "app": "council"}, format="json").data["access"]
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")
        return c

    def push(self, c, op_type, payload):
        return c.post("/api/v1/sync/push/", {"operations": [{"op_id": str(uuid.uuid4()), "type": op_type, "payload": payload}]},
                      format="json").data["results"][0]

    def letter(self, to="ceo"):
        return wf.log_correspondence(self.user("reception"), sender="Ministry of Local Government", subject="Budget consultation meeting",
                                     department="EXEC", addressed_to=self.user(to), routing_note="For the CEO's attention")

    def test_reception_scans_a_letter_and_sends_it_to_the_ceo(self):
        c = self.letter()
        att.add(self.user("reception"), "correspondence", c, pdf())
        self.assertEqual(att.for_object("correspondence", c).first().kind, Attachment.Kind.SCAN)
        self.assertTrue(Notification.objects.filter(recipient=self.user("ceo"), title__contains=c.reference).exists())
        self.assertIn(c, wf.in_tray(self.user("ceo")))
        # an officer it was not sent to cannot see it or its scan
        self.assertFalse(att.can_view(self.user("tech.officer"), "correspondence", c))

    def test_ceo_turns_the_letter_into_a_department_task(self):
        c = self.letter()
        with self.assertRaises(PermissionDenied):
            wf.route_letter(self.user("tech.officer"), c, "task", department="TECH")
        wf.route_letter(self.user("ceo"), c, "task", department="TECH", note="Prepare the ward 12 figures.")
        c.refresh_from_db()
        self.assertEqual(c.status, Correspondence.Status.TASKED)
        self.assertEqual(c.task.department, "TECH")
        self.assertEqual(c.task.assigned_to, self.user("engineer"))       # the head of the department
        self.assertTrue(Task.objects.filter(pk=c.task_id, description__contains="ward 12").exists())
        self.assertNotIn(c, wf.in_tray(self.user("ceo")))
        # the head of the department now sees the letter
        self.assertTrue(att.can_view(self.user("engineer"), "correspondence", c))

    def test_forward_file_and_respond(self):
        c = self.letter()
        wf.route_letter(self.user("ceo"), c, "forward", to_user=self.user("treasurer"), note="Please handle.")
        c.refresh_from_db()
        self.assertEqual(c.addressed_to, self.user("treasurer"))
        self.assertIn("Please handle.", c.routing_note)
        with self.assertRaises(ValidationError):
            wf.route_letter(self.user("treasurer"), c, "respond")
        wf.route_letter(self.user("treasurer"), c, "respond", note="Attendance confirmed.")
        c.refresh_from_db()
        self.assertEqual(c.status, Correspondence.Status.RESPONDED)

    def test_letters_from_the_app(self):
        r = self.push(self.api("reception"), "correspondence.create", {"id": str(uuid.uuid4()), "sender": "ZESA", "subject": "Power outage notice",
                                                                         "addressed_to": self.user("ceo").pk, "note": "Urgent"})
        self.assertEqual(r["status"], "applied", r)
        cid = r["record"]["id"]
        up = self.api("reception").post("/api/v1/attachments/", {"target_type": "correspondence", "target_id": cid, "kind": "SCAN",
                                                                  "file": pdf("zesa.pdf")}, format="multipart")
        self.assertEqual(up.status_code, 201, up.data)
        ceo = self.api("ceo")
        pulled = ceo.post("/api/v1/sync/pull/", {"cursors": {}}, format="json").data["entities"]["correspondence"]["items"]
        row = next(x for x in pulled if x["id"] == cid)
        self.assertEqual(len(row["attachments"]), 1)
        link = ceo.post(f"/api/v1/attachments/{up.data['id']}/link/").data["url"]
        self.assertEqual(self.client.get(link).status_code, 200)
        self.assertEqual(self.api("tech.officer").post(f"/api/v1/attachments/{up.data['id']}/link/").status_code, 403)
        r = self.push(ceo, "letter.route", {"id": cid, "action": "task", "department": "TECH"})
        self.assertEqual(r["status"], "applied", r)
        self.assertEqual(r["record"]["status"], "TASKED")

    def test_fake_files_are_refused(self):
        c = self.letter()
        with self.assertRaises(ValidationError):
            att.add(self.user("reception"), "correspondence", c, SimpleUploadedFile("x.pdf", b"MZ\x90\x00", content_type="application/pdf"))
        with self.assertRaises(ValidationError):
            att.add(self.user("reception"), "correspondence", c, SimpleUploadedFile("x.exe", b"MZ", content_type="application/octet-stream"))

    def test_phone_messages(self):
        with self.assertRaises(PermissionDenied):
            wf.take_phone_message(self.user("tech.officer"), caller_name="Mr Dube", message="Call me")
        m = wf.take_phone_message(self.user("reception"), caller_name="Mr Dube", caller_phone="0771234567", message="About the borehole",
                                  for_user=self.user("engineer"))
        self.assertTrue(Notification.objects.filter(recipient=self.user("engineer"), title__contains="Mr Dube").exists())
        self.assertFalse(wf.phone_message_scope(self.user("treasurer"), PhoneMessage.objects.filter(pk=m.pk)).exists())
        with self.assertRaises(PermissionDenied):
            wf.phone_message_done(self.user("treasurer"), m)
        wf.phone_message_done(self.user("engineer"), m, "Called back")
        m.refresh_from_db()
        self.assertEqual(m.status, PhoneMessage.Status.DONE)
        r = self.push(self.api("reception"), "phone_message.create", {"id": str(uuid.uuid4()), "caller_name": "Mrs Moyo", "message": "Rates query",
                                                                        "for_department": "FINANCE"})
        self.assertEqual(r["status"], "applied", r)


@override_settings(MEDIA_ROOT=MEDIA)
class PurchaseChainTests(CouncilTestCase):
    def make(self, user, kind="FUEL"):
        req = FundsRequest.objects.create(requested_by=user, created_by=user, request_type=kind, title="Fuel for the grader",
                                          purpose="Road works", requires_payment=True, depart_date=timezone.localdate())
        FundsRequestLine.objects.create(request=req, description="Diesel", quantity=100, unit_cost=Decimal("1.60"))
        return req

    def test_purchase_needs_quotation_then_invoice_before_payment(self):
        officer = self.user("tech.officer")
        req = self.make(officer)
        with self.assertRaises(ValidationError):
            fr.submit(officer, req)                                    # no quotation yet
        att.add(officer, "funds", req, pdf("quote.pdf"), "QUOTE")
        fr.submit(officer, req)
        self.assertEqual(req.status, FundsRequest.Status.PENDING_HOD)
        for who, nxt in (("engineer", "P_ADMIN"), ("admin.officer", "P_CEO"), ("ceo", "P_ACC"), ("accountant", "P_TREAS"),
                         ("treasurer", "P_CONF")):
            fr.decide(self.user(who), req, "approve")
            self.assertEqual(req.status, nxt, who)
        with self.assertRaises(ValidationError):
            fr.confirm_purchase(officer, req)                          # invoice missing
        with self.assertRaises(PermissionDenied):
            fr.confirm_purchase(self.user("social.officer"), req)
        att.add(officer, "funds", req, pdf("invoice.pdf"), "INVOICE")
        fr.confirm_purchase(officer, req, "Delivered")
        self.assertEqual(req.status, FundsRequest.Status.PENDING_PAYMENT)
        labels = [r["label"] for r in fr.route(req)]
        self.assertIn("Purchase confirmed – invoice / delivery note", labels)
        v = fr.prepare_payment(self.user("exp.clerk"), req)
        self.assertTrue(v.pk)

    def test_others_cannot_attach_to_a_request(self):
        req = self.make(self.user("tech.officer"))
        with self.assertRaises(PermissionDenied):
            att.add(self.user("social.officer"), "funds", req, pdf())


@override_settings(MEDIA_ROOT=MEDIA)
class WebPagesTests(CouncilTestCase):
    def web(self, username):
        from django.test import Client

        c = Client()
        c.login(username=username, password=PW)
        return c

    def test_reception_to_ceo_on_the_website(self):
        rec = self.web("reception")
        self.assertEqual(rec.get("/staff/correspondence/incoming/").status_code, 200)
        r = rec.post("/staff/correspondence/incoming/", {"sender": "Provincial Development Office", "subject": "Road plan", "date_received": "2026-11-27",
                                                         "addressed_to": self.user("ceo").pk, "routing_note": "Urgent", "scan": pdf("road.pdf")})
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        c = Correspondence.objects.get(subject="Road plan")
        self.assertEqual(att.for_object("correspondence", c).count(), 1)
        ceo = self.web("ceo")
        self.assertContains(ceo.get("/staff/incoming-mail/"), "Road plan")
        self.assertContains(ceo.get("/staff/"), "Incoming mail")
        page = ceo.get(f"/staff/correspondence/{c.pk}/view/")
        self.assertContains(page, "Give task")
        f = att.for_object("correspondence", c).first()
        self.assertEqual(ceo.get(f"/staff/files/{f.pk}/").status_code, 200)
        self.assertEqual(self.web("tech.officer").get(f"/staff/files/{f.pk}/").status_code, 403)
        ceo.post(f"/staff/correspondence/{c.pk}/view/", {"action": "task", "department": "TECH", "note": "Cost it"})
        c.refresh_from_db()
        self.assertEqual(c.status, Correspondence.Status.TASKED)

    def test_phone_messages_page(self):
        rec = self.web("reception")
        self.assertContains(rec.get("/staff/phone-messages/"), "Take a message")
        rec.post("/staff/phone-messages/", {"caller_name": "Mr Sithole", "message": "Water bill", "for_user": self.user("treasurer").pk, "call_back": "on"})
        m = PhoneMessage.objects.get(caller_name="Mr Sithole")
        t = self.web("treasurer")
        self.assertNotContains(t.get("/staff/phone-messages/"), "Take a message")
        t.post("/staff/phone-messages/", {"done": m.pk, "note": "Called"})
        m.refresh_from_db()
        self.assertEqual(m.status, PhoneMessage.Status.DONE)

    def test_files_and_confirm_on_the_request_page(self):
        officer = self.user("tech.officer")
        req = FundsRequest.objects.create(requested_by=officer, created_by=officer, request_type="REPAIRS", title="Grader tyres", purpose="Repairs",
                                          requires_payment=True)
        FundsRequestLine.objects.create(request=req, description="Tyre", quantity=2, unit_cost=Decimal("300"))
        w = self.web("tech.officer")
        self.assertContains(w.get(f"/staff/funds/{req.pk}/"), "Attach the quotation before submitting")
        w.post(f"/staff/files/funds/{req.pk}/add/", {"file": pdf("q.pdf"), "kind": "QUOTE", "next": f"/staff/funds/{req.pk}/"})
        w.post(f"/staff/funds/{req.pk}/action/", {"action": "submit"})
        req.refresh_from_db()
        self.assertEqual(req.status, FundsRequest.Status.PENDING_HOD)
        for who in ("engineer", "admin.officer", "ceo", "accountant", "treasurer"):
            fr.decide(self.user(who), req, "approve")
        self.assertContains(w.get(f"/staff/funds/{req.pk}/"), "Confirm purchase")
        w.post(f"/staff/files/funds/{req.pk}/add/", {"file": pdf("inv.pdf"), "kind": "INVOICE", "next": "/"})
        w.post(f"/staff/funds/{req.pk}/action/", {"action": "confirm", "comment": "Fitted"})
        req.refresh_from_db()
        self.assertEqual(req.status, FundsRequest.Status.PENDING_PAYMENT)


@override_settings(MEDIA_ROOT=MEDIA)
class ScanIsReadOnlyForRecipientTests(CouncilTestCase):
    def test_ceo_reads_the_scan_but_cannot_add_files(self):
        c = wf.log_correspondence(self.user("reception"), sender="ZESA", subject="Outage", department="EXEC", addressed_to=self.user("ceo"))
        att.add(self.user("reception"), "correspondence", c, pdf())
        self.assertTrue(att.can_view(self.user("ceo"), "correspondence", c))
        self.assertFalse(att.can_attach(self.user("ceo"), "correspondence", c))
        with self.assertRaises(PermissionDenied):
            att.add(self.user("ceo"), "correspondence", c, pdf())


@override_settings(MEDIA_ROOT=MEDIA)
class LetterActionPagesTests(CouncilTestCase):
    def test_letter_page_has_buttons_and_each_action_has_its_own_page(self):
        from django.test import Client

        c = wf.log_correspondence(self.user("reception"), sender="ZESA", subject="Outage", department="EXEC", addressed_to=self.user("ceo"))
        w = Client()
        w.login(username="ceo", password=PW)
        page = w.get(f"/staff/correspondence/{c.pk}/view/")
        self.assertContains(page, "Give task to a department")
        self.assertNotContains(page, "What must be done")
        for a in ("task", "respond", "forward"):
            self.assertEqual(w.get(f"/staff/correspondence/{c.pk}/{a}/").status_code, 200)
        w.post(f"/staff/correspondence/{c.pk}/view/", {"action": "respond", "note": "Noted, thank you."})
        c.refresh_from_db()
        self.assertEqual(c.status, Correspondence.Status.RESPONDED)
