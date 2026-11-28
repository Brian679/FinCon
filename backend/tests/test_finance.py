from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings

from finance import services
from finance.models import Bill, Property, BudgetLine, Licence, PaymentVoucher, Receipt, Requisition, RequisitionItem, Supplier

from .base import CouncilTestCase


class RevenueTests(CouncilTestCase):
    def test_receipt_reduces_balance_and_allocates_to_oldest_bill(self):
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.balance, Decimal("180.00"))  # demo residential levy: $15 a month x 12, billed once a year
        r = services.issue_receipt(self.user("cashier"), revenue_head=self.rates, amount="10", account=self.acc)
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.balance, Decimal("170.00"))
        bill = self.acc.bills.get()
        self.assertEqual(bill.status, Bill.Status.PART_PAID)
        self.assertTrue(r.number.startswith("RCT-"))
        self.assertEqual(r.received_by.username, "cashier")

    def test_foreign_currency_converted_to_usd(self):
        r = services.issue_receipt(self.user("cashier"), revenue_head=self.rates, amount="268", currency="ZWG",
                                   method="ECOCASH", reference="MP123", account=self.acc)
        self.assertEqual(r.base_amount, Decimal("10.00"))

    def test_non_cash_needs_reference(self):
        with self.assertRaises(ValidationError):
            services.issue_receipt(self.user("cashier"), revenue_head=self.rates, amount="5", payer_name="X", method="ECOCASH")

    def test_staff_without_capability_cannot_receipt(self):
        with self.assertRaises(PermissionDenied):
            services.issue_receipt(self.user("engineer"), revenue_head=self.rates, amount="5", payer_name="X")

    def test_void_needs_second_person(self):
        cashier = self.user("cashier")
        r = services.issue_receipt(cashier, revenue_head=self.rates, amount="15", account=self.acc)
        services.request_void(cashier, r, "Wrong account")
        with self.assertRaises(PermissionDenied):
            services.decide_void(cashier, r, True)
        services.decide_void(self.user("accountant"), r, True, "ok")
        r.refresh_from_db()
        self.acc.refresh_from_db()
        self.assertEqual(r.status, Receipt.Status.VOIDED)
        self.assertEqual(self.acc.balance, Decimal("180.00"))

    def test_billing_run_is_idempotent(self):
        from django.utils import timezone

        t = timezone.localdate()
        created, skipped = services.run_rates_billing(self.user("treasurer"), t.year, t.month)
        self.assertEqual(created, 0)                                   # already billed for this year / half-year
        self.assertGreaterEqual(skipped, Property.objects.filter(monthly_rates__gt=0).count())

    def test_cashup_variance(self):
        cashier = self.user("cashier")
        services.issue_receipt(cashier, revenue_head=self.rates, amount="20", payer_name="Walk in")
        cu = services.submit_cashup(cashier, currency="USD", declared_cash="18")
        self.assertEqual(cu.expected_cash, Decimal("20.00"))
        self.assertEqual(cu.variance, Decimal("-2.00"))
        with self.assertRaises(PermissionDenied):
            services.verify_cashup(cashier, cu, True)
        services.verify_cashup(self.user("accountant"), cu, False, "Short by $2")


class LicenceTests(CouncilTestCase):
    def test_shop_licence_needs_no_approval_and_is_issued_when_paid(self):
        client = self.user("resident")
        lic = services.apply_licence(client, account=self.acc, licence_type="SHOP", business_name="Mhlanga Tuckshop", premises="Stand 101")
        self.assertEqual(lic.status, Licence.Status.APPROVED)      # fee billed at once – no inspection, no Treasurer
        self.assertEqual(lic.bill.amount, Decimal("60.00"))
        self.assertIsNotNone(lic.due_at)
        services.issue_receipt(self.user("cashier"), revenue_head=self.shop, amount="240", account=self.acc)  # pays the house levy (180) + licence (60)
        lic.refresh_from_db()
        self.assertEqual(lic.status, Licence.Status.ISSUED)
        self.assertIsNotNone(lic.expiry_date)

    def test_shop_licence_waits_for_lease_and_levy(self):
        from finance.models import Lease, RevenueHead
        from datetime import date

        cashier, treasurer = self.user("cashier"), self.user("treasurer")
        prop = Property.objects.create(account=self.other_acc, location="Checheche", stand_number="TEST-1", business_name="Grace Butchery",
                                       land_use="COM")
        levy = RevenueHead.objects.get(code="DEV-LEVY")
        services.run_levy_billing(treasurer, levy, 2026, area=None, amount=Decimal("45"))
        services.create_lease(self.user("treasurer"), lessee=self.other_acc, premises=prop, start_date=date(2026, 1, 1), end_date=date(2027, 12, 31),
                              monthly_rent=Decimal("120"), deposit=Decimal("0"), purpose="Butchery")
        services.run_lease_billing(treasurer, 2026, 11)
        lic = services.apply_licence(cashier, account=self.other_acc, licence_type="SHOP", business_name="Grace Butchery", premises="TEST-1",
                                     property=prop)
        owing = dict(services.licence_outstanding(lic))
        self.assertEqual(owing, {"Licence fee": Decimal("60.00"), "Lease / rent": Decimal("120.00"), "Levy": Decimal("45.00")})
        services.issue_receipt(cashier, revenue_head=lic.bill.revenue_head, amount="60", account=self.other_acc, bill=lic.bill)
        lic.refresh_from_db()
        self.assertEqual(lic.status, Licence.Status.APPROVED)     # fee paid but lease and levy still owing
        for bill in prop.bills.filter(status="UNPAID"):
            services.issue_receipt(cashier, revenue_head=bill.revenue_head, amount=str(bill.amount), account=self.other_acc, bill=bill)
        lic.refresh_from_db()
        self.assertEqual(lic.status, Licence.Status.ISSUED)        # everything paid → issued by itself

    def test_health_certificate_still_inspected(self):
        lic = services.apply_licence(self.user("resident"), account=self.acc, licence_type="HEALTH", business_name="Mhlanga Tuckshop",
                                     premises="Stand 101")
        self.assertEqual(lic.status, Licence.Status.INSPECTION)
        with self.assertRaises(PermissionDenied):
            services.inspect_licence(self.user("cashier"), lic, True, "")
        services.inspect_licence(self.user("eho"), lic, True, "Clean premises")
        services.decide_licence(self.user("treasurer"), lic, True)
        lic.refresh_from_db()
        self.assertEqual(lic.status, Licence.Status.APPROVED)


class FarmLevyTests(CouncilTestCase):
    def test_farms_pay_per_hectare_and_not_flat_levies(self):
        from finance.models import ClientAccount, RevenueHead

        treasurer = self.user("treasurer")
        farm_acc = ClientAccount.objects.create(name="Test Farm", account_type="FARM")
        farm = Property.objects.create(account=farm_acc, location="Test farms", stand_number="F-1", land_use="AGR", hectares=Decimal("40"))
        head = RevenueHead.objects.get(code="FARM-LEVY")
        self.assertTrue(head.per_hectare)
        services.run_levy_billing(treasurer, head, 2030)
        bill = farm.bills.get(revenue_head=head)
        self.assertEqual(bill.amount, Decimal("200.00"))           # 40 ha × $5
        self.assertIn("40 ha", bill.description)
        stand_bills = Bill.objects.filter(revenue_head=head, property__hectares__isnull=True)
        self.assertFalse(stand_bills.exists())                     # stands / households don't pay the farm levy
        services.run_levy_billing(treasurer, RevenueHead.objects.get(code="DEV-LEVY"), 2030)
        self.assertFalse(farm.bills.filter(revenue_head__code="DEV-LEVY").exists())
        self.assertTrue(Bill.objects.filter(revenue_head__code="DEV-LEVY", period="2030", property__stand_number="101").exists())
        self.assertEqual(services.run_levy_billing(treasurer, head, 2030)[0], 0)   # idempotent


class InternTests(CouncilTestCase):
    def test_intern_works_on_department_tasks_only(self):
        from accounts.forms import StaffUserForm
        from workflow import services as wf

        intern = self.user("intern")
        self.assertEqual(intern.department, "TECH")
        self.assertTrue(intern.has_cap("tasks.view"))
        self.assertTrue(intern.has_cap("funds.request"))           # interns may request funds and raise requisitions
        self.assertTrue(intern.has_cap("requisition.create"))
        self.assertFalse(intern.has_cap("receipt.create"))
        task = wf.create_task(self.user("engineer"), title="Measure culverts", assigned_to=intern, department="TECH")
        wf.update_task(intern, task, status="IN_PROGRESS", progress=40, comment="Two of four done")
        task.refresh_from_db()
        self.assertEqual(task.progress, 40)
        with self.assertRaises(PermissionDenied):
            wf.create_task(self.user("treasurer"), title="x", assigned_to=intern, department="TECH")
        form = StaffUserForm(data={"username": "intern2", "first_name": "A", "last_name": "B", "role": "INTERN", "temporary_password": "Xy!12345abc",
                                   "is_active": True})
        self.assertFalse(form.is_valid())
        self.assertIn("department", form.errors)
        form = StaffUserForm(data={"username": "intern2", "first_name": "A", "last_name": "B", "role": "INTERN", "department": "FINANCE",
                                   "temporary_password": "Xy!12345abc", "is_active": True})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().department, "FINANCE")

    def test_client_cannot_apply_on_someone_elses_account(self):
        with self.assertRaises(PermissionDenied):
            services.apply_licence(self.user("resident"), account=self.other_acc, licence_type="HAWKER", business_name="x", premises="y")


class ExpenditureTests(CouncilTestCase):
    def _voucher(self, amount):
        return services.prepare_voucher(self.user("exp.clerk"), supplier=Supplier.objects.first(), description="Stationery",
                                        amount=Decimal(amount), budget_line=BudgetLine.objects.get(vote_code="E-210"), department="ADMIN")

    def test_small_voucher_workflow_without_ceo(self):
        self.fund_bank()
        v = self._voucher("500")
        with self.assertRaises(PermissionDenied):  # preparer cannot check own voucher
            services.decide_voucher(self.user("exp.clerk"), v, True)
        services.decide_voucher(self.user("accountant"), v, True)
        with self.assertRaises(PermissionDenied):  # the accountant cannot also approve
            services.decide_voucher(self.user("accountant"), v, True)
        services.decide_voucher(self.user("treasurer"), v, True)
        v.refresh_from_db()
        self.assertTrue(v.is_ready_for_payment)
        before = self.usd_bank.balance()
        services.pay_voucher(self.user("exp.clerk"), v, bank_account=self.usd_bank, payment_reference="RTGS001")
        v.refresh_from_db()
        self.assertEqual(v.status, PaymentVoucher.Status.PAID)
        self.assertEqual(before - self.usd_bank.balance(), Decimal("500.00"))
        self.assertEqual(BudgetLine.objects.get(vote_code="E-210").actual(), Decimal("500.00"))

    @override_settings(CEO_APPROVAL_THRESHOLD=1000)
    def test_large_voucher_needs_ceo(self):
        self.fund_bank()
        v = self._voucher("2500")
        services.decide_voucher(self.user("accountant"), v, True)
        services.decide_voucher(self.user("treasurer"), v, True)
        v.refresh_from_db()
        self.assertFalse(v.is_ready_for_payment)
        with self.assertRaises(ValidationError):
            services.pay_voucher(self.user("exp.clerk"), v, bank_account=self.usd_bank, payment_reference="X")
        services.decide_voucher(self.user("ceo"), v, True)
        v.refresh_from_db()
        self.assertEqual(v.status, PaymentVoucher.Status.AUTHORISED)

    def test_same_person_cannot_check_and_approve(self):
        v = self._voucher("50")
        services.decide_voucher(self.user("treasurer"), v, True)  # treasurer covers the checking stage
        with self.assertRaises(PermissionDenied):
            services.decide_voucher(self.user("treasurer"), v, True)

    def test_cannot_pay_more_than_bank_balance(self):
        v = self._voucher("100")
        services.decide_voucher(self.user("accountant"), v, True)
        services.decide_voucher(self.user("treasurer"), v, True)
        with self.assertRaises(ValidationError):
            services.pay_voucher(self.user("exp.clerk"), v, bank_account=self.usd_bank, payment_reference="X")

    def test_blacklisted_supplier_blocked(self):
        s = Supplier.objects.first()
        s.status = Supplier.Status.BLACKLISTED
        s.save()
        with self.assertRaises(ValidationError):
            self._voucher("10")


class ProcurementTests(CouncilTestCase):
    def test_requisition_to_purchase_order(self):
        officer = self.user("tech.officer")
        req = Requisition.objects.create(department="TECH", requested_by=officer, purpose="Road gravel",
                                         budget_line=BudgetLine.objects.get(vote_code="E-600"))
        RequisitionItem.objects.create(requisition=req, description="Gravel (m3)", quantity=10, unit_cost=20)
        services.submit_requisition(officer, req)
        self.assertEqual(req.status, Requisition.Status.SUBMITTED)
        with self.assertRaises(PermissionDenied):  # other department's head
            services.decide_requisition(self.user("social.director"), req, True)
        services.decide_requisition(self.user("engineer"), req, True)
        services.decide_requisition(self.user("accountant"), req, True)
        services.decide_requisition(self.user("treasurer"), req, True)
        req.refresh_from_db()
        self.assertTrue(req.is_ready_for_order)
        po = services.raise_purchase_order(self.user("procurement"), req, Supplier.objects.get(name__startswith="Eastern"))
        self.assertEqual(po.amount, Decimal("200.00"))
        services.receive_goods(self.user("procurement"), po)
        v = services.prepare_voucher(self.user("exp.clerk"), purchase_order=po, description="Gravel", amount=po.amount)
        self.assertEqual(v.budget_line.vote_code, "E-600")

    def test_budget_check_blocks_overspend(self):
        officer = self.user("auditor")
        line = BudgetLine.objects.get(vote_code="E-400")
        req = Requisition.objects.create(department="AUDIT", requested_by=officer, purpose="Laptops", budget_line=line)
        RequisitionItem.objects.create(requisition=req, description="Laptop", quantity=10, unit_cost=1000)
        services.submit_requisition(officer, req)
        services.decide_requisition(self.user("chief.auditor"), req, True)
        with self.assertRaises(ValidationError):
            services.decide_requisition(self.user("accountant"), req, True)
