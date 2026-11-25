from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings

from finance import services
from finance.models import Bill, Property, BudgetLine, Licence, PaymentVoucher, Receipt, Requisition, RequisitionItem, Supplier

from .base import CouncilTestCase


class RevenueTests(CouncilTestCase):
    def test_receipt_reduces_balance_and_allocates_to_oldest_bill(self):
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.balance, Decimal("15.00"))  # demo rates bill
        r = services.issue_receipt(self.user("cashier"), revenue_head=self.rates, amount="10", account=self.acc)
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.balance, Decimal("5.00"))
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
        self.assertEqual(self.acc.balance, Decimal("15.00"))

    def test_billing_run_is_idempotent(self):
        from django.utils import timezone

        t = timezone.localdate()
        created, skipped = services.run_rates_billing(self.user("treasurer"), t.year, t.month)
        self.assertEqual(created, 0)
        self.assertEqual(skipped, Property.objects.filter(monthly_rates__gt=0).count())

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
    def test_shop_licence_lifecycle(self):
        client = self.user("resident")
        lic = services.apply_licence(client, account=self.acc, licence_type="SHOP", business_name="Mhlanga Tuckshop", premises="Stand 101")
        self.assertEqual(lic.status, Licence.Status.INSPECTION)
        self.assertIsNotNone(lic.due_at)
        with self.assertRaises(PermissionDenied):
            services.inspect_licence(self.user("cashier"), lic, True, "")
        services.inspect_licence(self.user("eho"), lic, True, "Clean premises")
        services.decide_licence(self.user("treasurer"), lic, True)
        lic.refresh_from_db()
        self.assertEqual(lic.status, Licence.Status.APPROVED)
        self.assertEqual(lic.bill.amount, Decimal("60.00"))
        services.issue_receipt(self.user("cashier"), revenue_head=self.shop, amount="75", account=self.acc)  # pays rates + licence
        lic.refresh_from_db()
        self.assertEqual(lic.status, Licence.Status.ISSUED)
        self.assertIsNotNone(lic.expiry_date)

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
        services.pay_voucher(self.user("exp.clerk"), v, bank_account=self.usd_bank, payment_reference="RTGS001")
        v.refresh_from_db()
        self.assertEqual(v.status, PaymentVoucher.Status.PAID)
        self.assertEqual(self.usd_bank.balance(), Decimal("99500.00"))
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
