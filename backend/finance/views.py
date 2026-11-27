import csv
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import cap_required, staff_required
from core.crud import (
    SafeCsvWriter, GenericCreateView, GenericDetailView, GenericListView, GenericUpdateView, log_export, run_action,
)
from core.views import finance_kpis, pending_approvals

from . import forms, services
from .models import (
    ApprovalRecord, BankAccount, Bill, BudgetLine, CashUp, ClientAccount, ExchangeRate, Licence, OnlinePayment, PaymentVoucher,
    PurchaseOrder, Receipt, Requisition, RevenueHead, Supplier,
)

FIN_ALL = ("finance.view_all",)


@cap_required("finance.view")
def dashboard(request):
    """Old "Finance dashboard" address: everything is on the one dashboard now."""
    return redirect("core:dashboard")


def finance_dashboard_context(user):
    """Finance figures shown on the dashboard of Finance staff, the CEO and auditors."""
    today = timezone.localdate()
    receipts = Receipt.objects.alive().filter(status__in=Receipt.COUNTABLE)
    by_head = receipts.filter(created_at__date__gte=today.replace(day=1)).values("revenue_head__name").annotate(
        total=Sum("base_amount"), n=Count("id")).order_by("-total")[:8]
    last14 = receipts.filter(created_at__date__gte=today - timedelta(days=13)).annotate(d=TruncDate("created_at")).values("d").annotate(
        total=Sum("base_amount")).order_by("d")
    series = {r["d"]: r["total"] for r in last14}
    days = [(today - timedelta(days=i)) for i in range(13, -1, -1)]
    chart = [{"d": d, "total": series.get(d, Decimal(0))} for d in days]
    peak = max([c["total"] for c in chart] + [Decimal(1)])
    for c in chart:
        c["pct"] = int(c["total"] / peak * 100)
    mine = receipts.filter(received_by=user, cashup__isnull=True)
    sees_all = user.has_cap(*FIN_ALL)
    return {
        "fin": finance_kpis() if sees_all else None, "by_head": by_head if sees_all else [], "chart": chart if sees_all else [],
        "my_today": receipts.filter(received_by=user, created_at__date=today).aggregate(t=Sum("base_amount"), n=Count("id")),
        "my_uncashed": mine.values("currency").annotate(t=Sum("amount"), n=Count("id")),
        "banks": BankAccount.objects.alive().filter(is_active=True) if user.has_cap("bank.manage", "finance.view_all") else [],
        "recent": receipts.select_related("revenue_head")[:8] if sees_all else mine.select_related("revenue_head")[:8],
    }


# ----------------------------------------------------------------- receipts
@cap_required("receipt.create")
def receipt_new(request):
    initial = {"currency": "USD", "method": "CASH"}
    if request.GET.get("account"):
        initial["account"] = request.GET["account"]
    if request.GET.get("bill"):
        bill = Bill.objects.filter(pk=request.GET["bill"]).first()
        if bill:
            initial.update(account=bill.account_id, bill=bill.pk, revenue_head=bill.revenue_head_id, amount=bill.outstanding)
    form = forms.ReceiptForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        receipt = run_action(request, services.issue_receipt, revenue_head=d["revenue_head"], amount=d["amount"],
                             payer_name=d["payer_name"], account=d["account"], bill=d["bill"], currency=d["currency"],
                             method=d["method"], reference=d["reference"], bank_account=d["bank_account"],
                             description=d["description"], success="Receipt issued.")
        if receipt:
            return redirect("finance:receipt", pk=receipt.pk)
    rates = {r.currency: r.rate for r in ExchangeRate.objects.all()[:10]}
    return render(request, "finance/receipt_form.html", {"form": form, "title": "Receipting counter", "rates": rates})


class ReceiptList(GenericListView):
    model = Receipt
    required_caps = ("finance.view",)
    title = "Receipts – incoming money"
    columns = [("Receipt no.", "number"), ("Date", "created_at"), ("Payer", "payer_name"), ("Account", "account.account_number"),
               ("Revenue head", "revenue_head.name"), ("Cur.", "currency"), ("Amount", "amount"), ("Method", "method"),
               ("Channel", "channel"), ("Cashier", "received_by.username"), ("Status", "status")]
    search_fields = ["number", "payer_name", "account__account_number", "reference"]
    detail_url_name = "finance:receipt"
    create_url_name = "finance:receipt_new"
    create_caps = ("receipt.create",)

    def scope(self, qs):
        qs = qs.select_related("account", "revenue_head", "received_by")
        if not self.request.user.has_cap(*FIN_ALL):
            qs = qs.filter(received_by=self.request.user)
        return qs


class ReceiptDetail(GenericDetailView):
    model = Receipt
    required_caps = ("finance.view",)
    template_name = "finance/receipt_detail.html"

    def scope(self, qs):
        if not self.request.user.has_cap(*FIN_ALL):
            qs = qs.filter(received_by=self.request.user)
        return qs


@cap_required("receipt.void_request", "receipt.void_approve")
@require_POST
def receipt_void_request(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    run_action(request, services.request_void, receipt, request.POST.get("reason", "").strip(), success="Void requested – awaiting approval.")
    return redirect("finance:receipt", pk=pk)


@cap_required("receipt.void_approve")
@require_POST
def receipt_void_decide(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    run_action(request, services.decide_void, receipt, request.POST.get("decision") == "approve", request.POST.get("comment", ""),
               success="Decision recorded.")
    return redirect("finance:receipt", pk=pk)


# ------------------------------------------------------------- client accounts
class AccountList(GenericListView):
    model = ClientAccount
    required_caps = ("accounts.manage", "finance.view_all")
    title = "Client (ratepayer) accounts"
    columns = [("Account no.", "account_number"), ("Name", "name"), ("Type", "account_type"), ("Ward", "ward"), ("Phone", "phone"),
               ("Balance (USD)", "balance"), ("Status", "status")]
    search_fields = ["account_number", "name", "id_number", "phone", "properties__stand_number"]
    detail_url_name = "finance:account"
    create_url_name = "finance:account_new"
    create_caps = ("accounts.manage",)

    def scope(self, qs):
        if self.request.GET.get("debtors"):
            qs = qs.filter(balance__gt=0).order_by("-balance")
        return qs.distinct()


class AccountCreate(GenericCreateView):
    model = ClientAccount
    form_class = forms.ClientAccountForm
    required_caps = ("accounts.manage",)
    detail_url_name = "finance:account"
    title = "Open client account"


class AccountUpdate(GenericUpdateView):
    model = ClientAccount
    form_class = forms.ClientAccountForm
    required_caps = ("accounts.manage",)
    detail_url_name = "finance:account"


@cap_required("accounts.manage", "finance.view_all")
def account_detail(request, pk):
    account = get_object_or_404(ClientAccount.objects.alive(), pk=pk)
    bills = account.bills.alive().select_related("revenue_head")
    receipts = account.receipts.alive().select_related("revenue_head")
    # Statement: chronological list of debits (bills) and credits (receipts).
    lines = [(b.issue_date, b.created_at, f"Bill {b.number} – {b.description}", b.amount if b.status != "CANCELLED" else Decimal(0), Decimal(0)) for b in bills]
    lines += [(timezone.localtime(r.created_at).date(), r.created_at, f"Receipt {r.number} – {r.revenue_head.name}" + (" (VOID)" if r.status == "VOIDED" else ""),
               Decimal(0), r.base_amount if r.status != "VOIDED" else Decimal(0)) for r in receipts]
    lines.sort(key=lambda x: (x[0], x[1]))
    running = Decimal(0)
    statement = []
    for d, _ts, text, debit, credit in lines:
        running += debit - credit
        statement.append({"date": d, "text": text, "debit": debit, "credit": credit, "balance": running})
    return render(request, "finance/account_detail.html", {
        "title": str(account), "account": account, "bills": bills[:50], "receipts": receipts[:50], "statement": statement,
        "properties": account.properties.alive(), "licences": account.licences.alive(), "portal_users": account.portal_users.all(),
        "property_form": forms.PropertyForm(), "bill_form": forms.BillForm(),
    })


@cap_required("accounts.manage")
@require_POST
def property_add(request, pk):
    account = get_object_or_404(ClientAccount, pk=pk)
    form = forms.PropertyForm(request.POST)
    if form.is_valid():
        prop = form.save(commit=False)
        prop.account = account
        prop.created_by = request.user
        prop.save()
        messages.success(request, f"{prop} added.")
    else:
        messages.error(request, f"Property not saved: {form.errors.as_text()}")
    return redirect("finance:account", pk=pk)


@cap_required("billing.run")
@require_POST
def bill_add(request, pk):
    account = get_object_or_404(ClientAccount, pk=pk)
    form = forms.BillForm(request.POST)
    if form.is_valid():
        d = form.cleaned_data
        run_action(request, services.create_bill, account=account, revenue_head=d["revenue_head"], amount=d["amount"],
                   description=d["description"], due_date=d["due_date"], property=d["property"], success="Bill raised.")
    else:
        messages.error(request, f"Bill not saved: {form.errors.as_text()}")
    return redirect("finance:account", pk=pk)


@cap_required("accounts.manage", "finance.view_all")
def account_statement_csv(request, pk):
    account = get_object_or_404(ClientAccount, pk=pk)
    log_export(request, f"statement {account.account_number}")
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="statement-{account.account_number}.csv"'
    w = SafeCsvWriter(resp)
    w.writerow(["Date", "Type", "Number", "Description", "Amount USD"])
    for b in account.bills.alive().exclude(status="CANCELLED"):
        w.writerow([b.issue_date, "BILL", b.number, b.description, b.amount])
    for r in account.receipts.alive().exclude(status="VOIDED"):
        w.writerow([timezone.localtime(r.created_at).date(), "RECEIPT", r.number, r.description, -r.base_amount])
    w.writerow(["", "", "", "BALANCE", account.balance])
    return resp


class BillList(GenericListView):
    model = Bill
    required_caps = ("accounts.manage", "finance.view_all")
    title = "Bills / charges"
    columns = [("Bill no.", "number"), ("Issued", "issue_date"), ("Account", "account"), ("Revenue head", "revenue_head.name"),
               ("Period", "period"), ("Amount", "amount"), ("Paid", "amount_paid"), ("Due", "due_date"), ("Status", "status")]
    search_fields = ["number", "account__account_number", "account__name", "description"]
    extra_buttons = [("Billing runs (rates, levies, leases)", "finance:billing_runs", ("billing.run",))]

    def row_url(self, obj):
        return reverse("finance:account", args=[obj.account_id])

    def scope(self, qs):
        return qs.select_related("account", "revenue_head")


@cap_required("billing.run")
@require_POST
def bill_cancel(request, pk):
    bill = get_object_or_404(Bill, pk=pk)
    run_action(request, services.cancel_bill, bill, request.POST.get("reason", "Cancelled"), success="Bill cancelled.")
    return redirect("finance:account", pk=bill.account_id)


@cap_required("billing.run")
def billing_run(request):
    today = timezone.localdate()
    form = forms.BillingRunForm(request.POST or None, initial={"year": today.year, "month": today.month})
    if request.method == "POST" and form.is_valid():
        result = run_action(request, services.run_rates_billing, form.cleaned_data["year"], form.cleaned_data["month"], success="Billing run complete.")
        if result:
            messages.info(request, f"{result[0]} bills raised, {result[1]} properties were already billed for the period.")
            return redirect("finance:bills")
    return render(request, "generic/form.html", {"form": form, "title": "Monthly rates billing run"})


# ------------------------------------------------------------------- cash-ups
class CashUpList(GenericListView):
    model = CashUp
    required_caps = ("cashup.submit", "cashup.verify")
    title = "Cash-ups (end of day)"
    columns = [("Date", "date"), ("Cashier", "cashier"), ("Currency", "currency"), ("Expected cash", "expected_cash"),
               ("Declared", "declared_cash"), ("Variance", "variance"), ("Non-cash", "expected_other"), ("Status", "status")]
    detail_url_name = "finance:cashup"
    create_url_name = "finance:cashup_new"
    create_caps = ("cashup.submit", "receipt.create")

    def scope(self, qs):
        if not self.request.user.has_cap("cashup.verify"):
            qs = qs.filter(cashier=self.request.user)
        return qs.select_related("cashier")


@cap_required("cashup.submit", "receipt.create")
def cashup_new(request):
    form = forms.CashUpForm(request.POST or None, initial={"currency": "USD"})
    pending = Receipt.objects.alive().filter(received_by=request.user, cashup__isnull=True, status__in=Receipt.COUNTABLE)
    summary = pending.values("currency", "method").annotate(t=Sum("amount"), n=Count("id")).order_by("currency", "method")
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        cashup = run_action(request, services.submit_cashup, currency=d["currency"], declared_cash=d["declared_cash"], notes=d["notes"],
                            success="Cash-up submitted.")
        if cashup:
            return redirect("finance:cashup", pk=cashup.pk)
    return render(request, "finance/cashup_form.html", {"form": form, "summary": summary, "title": "Submit cash-up"})


class CashUpDetail(GenericDetailView):
    model = CashUp
    required_caps = ("cashup.submit", "cashup.verify")
    template_name = "finance/cashup_detail.html"
    fields = [("Cashier", "cashier"), ("Date", "date"), ("Currency", "currency"), ("Expected cash", "expected_cash"),
              ("Declared cash", "declared_cash"), ("Variance", "variance"), ("Non-cash receipts", "expected_other"),
              ("Notes", "notes"), ("Verified by", "verified_by"), ("Verified at", "verified_at")]

    def scope(self, qs):
        if not self.request.user.has_cap("cashup.verify"):
            qs = qs.filter(cashier=self.request.user)
        return qs


@cap_required("cashup.verify")
@require_POST
def cashup_verify(request, pk):
    cashup = get_object_or_404(CashUp, pk=pk)
    run_action(request, services.verify_cashup, cashup, request.POST.get("decision") == "verify", request.POST.get("comment", ""), success="Cash-up updated.")
    return redirect("finance:cashup", pk=pk)


# ------------------------------------------------------------------- licences
def licence_scope(user, qs):
    """Finance sees every licence; Social Services' health officers only see the
    shop inspections that are their job (no fees / accounts of other shops)."""
    if user.has_cap("licence.view"):
        return qs
    return qs.filter(Q(status=Licence.Status.INSPECTION) | Q(inspected_by=user))


class LicenceList(GenericListView):
    model = Licence
    required_caps = ("licence.view", "licence.inspect")
    title = "Licences (shop, hawker, business …)"
    columns = [("Licence no.", "number"), ("Type", "licence_type"), ("Business", "business_name"), ("Account", "account.account_number"),
               ("Premises", "premises"), ("Fee", "fee"), ("Expires", "expiry_date"), ("Status", "status")]
    search_fields = ["number", "business_name", "account__account_number", "account__name", "premises"]
    detail_url_name = "finance:licence"
    create_url_name = "finance:licence_new"
    create_caps = ("licence.manage",)

    def scope(self, qs):
        return licence_scope(self.request.user, qs.select_related("account"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not self.request.user.has_cap("licence.view"):
            ctx["title"] = "Shop health inspections"
        return ctx


@cap_required("licence.manage")
def licence_new(request):
    form = forms.LicenceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        lic = run_action(request, services.apply_licence, account=d["account"], licence_type=d["licence_type"], business_name=d["business_name"],
                         premises=d["premises"], business_activity=d["business_activity"], ward=d["ward"], property=d.get("property"),
                         success="Application captured.")
        if lic:
            return redirect("finance:licence", pk=lic.pk)
    return render(request, "generic/form.html", {"form": form, "title": "Capture licence application"})


class LicenceDetail(GenericDetailView):
    model = Licence
    required_caps = ("licence.view", "licence.inspect")

    def scope(self, qs):
        return licence_scope(self.request.user, qs)

    template_name = "finance/licence_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.object.status == Licence.Status.APPROVED:
            ctx["still_to_pay"] = services.licence_outstanding(self.object)
        return ctx

    fields = [("Type", "licence_type"), ("Business", "business_name"), ("Activity", "business_activity"), ("Account", "account"),
              ("Premises", "premises"), ("Ward", "ward"), ("Applicant", "applicant"), ("Fee (USD)", "fee"), ("Fee bill", "bill"),
              ("Inspected by", "inspected_by"), ("Inspection notes", "inspection_notes"), ("Approved by", "approved_by"),
              ("Issued", "issue_date"), ("Expires", "expiry_date"), ("Process by (charter)", "due_at"), ("Rejection reason", "rejection_reason")]


@cap_required("licence.inspect")
@require_POST
def licence_inspect(request, pk):
    lic = get_object_or_404(Licence, pk=pk)
    run_action(request, services.inspect_licence, lic, request.POST.get("decision") == "pass", request.POST.get("comment", ""), success="Inspection recorded.")
    return redirect("finance:licence", pk=pk)


@cap_required("licence.approve")
@require_POST
def licence_decide(request, pk):
    lic = get_object_or_404(Licence, pk=pk)
    fee = request.POST.get("fee") or None
    run_action(request, services.decide_licence, lic, request.POST.get("decision") == "approve", request.POST.get("comment", ""),
               fee=Decimal(fee) if fee else None, success="Decision recorded.")
    return redirect("finance:licence", pk=pk)


@cap_required("licence.view")
def licence_certificate(request, pk):
    lic = get_object_or_404(Licence, pk=pk, status=Licence.Status.ISSUED)
    log_export(request, f"licence certificate {lic.number}")
    return render(request, "finance/licence_certificate.html", {"lic": lic, "title": lic.number})


# ----------------------------------------------------------------- suppliers
class SupplierList(GenericListView):
    model = Supplier
    required_caps = ("supplier.manage", "finance.view_all")
    title = "Suppliers & contractors"
    columns = [("Code", "code"), ("Name", "name"), ("Category", "category"), ("Contact", "contact_person"), ("Phone", "phone"),
               ("Tax no.", "tax_number"), ("Status", "status")]
    search_fields = ["code", "name", "category", "tax_number"]
    detail_url_name = "finance:supplier_edit"
    create_url_name = "finance:supplier_new"
    create_caps = ("supplier.manage",)


class SupplierCreate(GenericCreateView):
    model = Supplier
    form_class = forms.SupplierForm
    required_caps = ("supplier.manage",)
    success_url = "/staff/finance/suppliers/"


class SupplierUpdate(GenericUpdateView):
    model = Supplier
    form_class = forms.SupplierForm
    required_caps = ("supplier.manage",)
    success_url = "/staff/finance/suppliers/"


# --------------------------------------------------------------- requisitions
class RequisitionList(GenericListView):
    model = Requisition
    required_caps = ("dashboard",)
    title = "Purchase requisitions"
    columns = [("Req. no.", "number"), ("Date", "created_at"), ("Department", "department"), ("Requested by", "requested_by"),
               ("Purpose", lambda r: r.purpose[:60]), ("Total (USD)", "total"), ("Status", "status")]
    search_fields = ["number", "purpose"]
    detail_url_name = "finance:requisition"
    create_url_name = "finance:requisition_new"

    def scope(self, qs):
        u = self.request.user
        if u.has_cap("finance.view_all", "procurement.order") or u.is_ceo:
            return qs
        if u.is_head:
            return qs.filter(department=u.department)
        return qs.filter(requested_by=u)


@staff_required
def requisition_form(request, pk=None):
    req = get_object_or_404(Requisition, pk=pk, requested_by=request.user, status=Requisition.Status.DRAFT) if pk else None
    form = forms.RequisitionForm(request.POST or None, instance=req, department=request.user.department)
    formset = forms.ItemFormSet(request.POST or None, instance=req or Requisition())
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            req = form.save(commit=False)
            if not req.pk or req._state.adding:
                req.requested_by = request.user
                req.department = request.user.department
                req.created_by = request.user
            req.save()
            formset.instance = req
            formset.save()
            req.recalc_total()
        if "submit" in request.POST:
            run_action(request, services.submit_requisition, req, success="Requisition submitted for approval.")
        else:
            messages.success(request, "Requisition saved as draft.")
        return redirect("finance:requisition", pk=req.pk)
    return render(request, "finance/requisition_form.html", {"form": form, "formset": formset, "title": "Purchase requisition"})


class RequisitionDetail(GenericDetailView):
    model = Requisition
    required_caps = ("dashboard",)
    template_name = "finance/requisition_detail.html"
    fields = [("Department", "department"), ("Requested by", "requested_by"), ("Date", "created_at"), ("Purpose", "purpose"),
              ("Budget vote", "budget_line"), ("Total (USD)", "total"), ("Needs CEO authorisation", "needs_ceo"),
              ("Rejection reason", "rejection_reason")]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        r = self.object
        u = self.request.user
        ctx["next_action"] = services.requisition_next_action(u, r) if r.requested_by_id != u.pk else None
        ctx["can_submit"] = r.status == Requisition.Status.DRAFT and r.requested_by_id == u.pk
        ctx["can_order"] = r.is_ready_for_order and u.has_cap("procurement.order")
        ctx["po_form"] = forms.PurchaseOrderForm(initial={"amount": r.total})
        ctx["po"] = getattr(r, "purchase_order", None)
        return ctx


@staff_required
@require_POST
def requisition_action(request, pk):
    req = get_object_or_404(Requisition, pk=pk)
    action = request.POST.get("action")
    if action == "submit":
        run_action(request, services.submit_requisition, req, success="Submitted.")
    elif action in ("approve", "reject"):
        run_action(request, services.decide_requisition, req, action == "approve", request.POST.get("comment", ""), success="Decision recorded.")
    elif action == "order":
        form = forms.PurchaseOrderForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            po = run_action(request, services.raise_purchase_order, req, d["supplier"], d["amount"], d["expected_delivery"], d["notes"],
                            success="Purchase order issued.")
            if po:
                return redirect("finance:order", pk=po.pk)
        else:
            messages.error(request, form.errors.as_text())
    return redirect("finance:requisition", pk=pk)


class OrderList(GenericListView):
    model = PurchaseOrder
    required_caps = ("procurement.order", "finance.view_all")
    title = "Purchase orders"
    columns = [("PO no.", "number"), ("Date", "created_at"), ("Supplier", "supplier.name"), ("Requisition", "requisition.number"),
               ("Amount", "amount"), ("Expected", "expected_delivery"), ("Status", "status")]
    search_fields = ["number", "supplier__name", "requisition__number"]
    detail_url_name = "finance:order"


class OrderDetail(GenericDetailView):
    model = PurchaseOrder
    required_caps = ("procurement.order", "finance.view_all", "voucher.prepare")
    template_name = "finance/order_detail.html"
    fields = [("Supplier", "supplier"), ("Requisition", "requisition"), ("Department", "requisition.department"),
              ("Amount", "amount"), ("Currency", "currency"), ("Expected delivery", "expected_delivery"), ("Delivered at", "delivered_at"),
              ("Received by", "received_by"), ("Notes", "notes")]


@cap_required("procurement.order", "voucher.prepare")
@require_POST
def order_receive(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    run_action(request, services.receive_goods, po, request.POST.get("comment", ""), success="Goods / services received.")
    return redirect("finance:order", pk=pk)


# ------------------------------------------------------------------ vouchers
class VoucherList(GenericListView):
    model = PaymentVoucher
    required_caps = ("voucher.prepare", "voucher.check", "voucher.approve", "voucher.authorise", "finance.view_all")
    title = "Payment vouchers – outgoing money"
    columns = [("PV no.", "number"), ("Date", "created_at"), ("Payee", "payee_name"), ("Category", "category"),
               ("Vote", "budget_line.vote_code"), ("Cur.", "currency"), ("Amount", "amount"), ("Prepared by", "prepared_by.username"),
               ("Status", "status")]
    search_fields = ["number", "payee_name", "description", "invoice_number", "payment_reference"]
    detail_url_name = "finance:voucher"
    create_url_name = "finance:voucher_new"
    create_caps = ("voucher.prepare",)


@cap_required("voucher.prepare")
def voucher_new(request):
    initial = {}
    if request.GET.get("po"):
        po = PurchaseOrder.objects.filter(pk=request.GET["po"]).first()
        if po:
            initial = {"purchase_order": po.pk, "supplier": po.supplier_id, "amount": po.amount, "budget_line": po.requisition.budget_line_id,
                       "department": po.requisition.department, "description": po.requisition.purpose}
    form = forms.VoucherForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = {k: v for k, v in form.cleaned_data.items() if v not in (None, "")}
        voucher = run_action(request, services.prepare_voucher, success="Payment voucher prepared and sent for checking.", **data)
        if voucher:
            return redirect("finance:voucher", pk=voucher.pk)
    return render(request, "generic/form.html", {"form": form, "title": "Prepare payment voucher"})


class VoucherDetail(GenericDetailView):
    model = PaymentVoucher
    required_caps = ("voucher.prepare", "voucher.check", "voucher.approve", "voucher.authorise", "finance.view_all", "voucher.pay")
    template_name = "finance/voucher_detail.html"
    fields = [("Payee", "payee_name"), ("Category", "category"), ("Supplier", "supplier"), ("Purchase order", "purchase_order"),
              ("Department", "department"), ("Budget vote", "budget_line"), ("Description", "description"), ("Supplier invoice", "invoice_number"),
              ("Amount", lambda v: f"{v.currency} {v.amount:,.2f}"), ("USD equivalent", "base_amount"), ("Method", "method"),
              ("Needs CEO authorisation", "needs_ceo"), ("Prepared by", "prepared_by"), ("Paid from", "bank_account"),
              ("Payment reference", "payment_reference"), ("Paid at", "paid_at"), ("Rejection reason", "rejection_reason")]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        v = self.object
        u = self.request.user
        ctx["next_action"] = services.voucher_next_action(u, v) if v.prepared_by_id != u.pk else None
        ctx["can_pay"] = v.is_ready_for_payment and u.has_cap("voucher.pay")
        ctx["pay_form"] = forms.PayVoucherForm()
        if v.budget_line_id:
            ctx["budget"] = {"available": v.budget_line.available(), "budget": v.budget_line.budget}
        return ctx


@staff_required
@require_POST
def voucher_action(request, pk):
    v = get_object_or_404(PaymentVoucher, pk=pk)
    action = request.POST.get("action")
    if action in ("approve", "reject"):
        run_action(request, services.decide_voucher, v, action == "approve", request.POST.get("comment", ""), success="Decision recorded.")
    elif action == "pay":
        form = forms.PayVoucherForm(request.POST)
        if form.is_valid():
            run_action(request, services.pay_voucher, v, bank_account=form.cleaned_data["bank_account"],
                       payment_reference=form.cleaned_data["payment_reference"], success="Payment recorded.")
        else:
            messages.error(request, form.errors.as_text())
    return redirect("finance:voucher", pk=pk)


# -------------------------------------------------------------------- budget
@cap_required("budget.view", "budget.manage")
def budget(request):
    year = int(request.GET.get("year") or timezone.localdate().year)
    lines = BudgetLine.objects.alive().filter(financial_year=year)
    if not (request.user.has_cap("finance.view_all") or request.user.is_ceo):
        lines = lines.filter(department=request.user.department)
    rows = []
    totals = {"INCOME": [Decimal(0)] * 3, "EXPENDITURE": [Decimal(0)] * 3, "CAPITAL": [Decimal(0)] * 3}
    for line in lines:
        actual, committed = line.actual(), line.committed()
        rows.append({"line": line, "actual": actual, "committed": committed, "available": line.budget - actual - committed,
                     "pct": line.utilisation_pct()})
        t = totals[line.kind]
        t[0] += line.budget
        t[1] += actual
        t[2] += committed
    return render(request, "finance/budget.html", {"title": f"Budget vs actual {year}", "rows": rows, "year": year, "totals": totals,
                                                   "can_manage": request.user.has_cap("budget.manage")})


class BudgetCreate(GenericCreateView):
    model = BudgetLine
    form_class = forms.BudgetLineForm
    required_caps = ("budget.manage",)
    success_url = "/staff/finance/budget/"


class BudgetUpdate(GenericUpdateView):
    model = BudgetLine
    form_class = forms.BudgetLineForm
    required_caps = ("budget.manage",)
    success_url = "/staff/finance/budget/"


# ----------------------------------------------------- banks, rates, revenue
class BankList(GenericListView):
    model = BankAccount
    required_caps = ("bank.manage", "finance.view_all")
    title = "Bank accounts"
    columns = [("Name", "name"), ("Bank", "bank"), ("Account no.", "account_number"), ("Currency", "currency"), ("Balance", "balance"), ("Active", "is_active")]
    detail_url_name = "finance:bank"
    create_url_name = "finance:bank_new"
    create_caps = ("bank.manage",)
    filter_field = None


class BankCreate(GenericCreateView):
    model = BankAccount
    form_class = forms.BankAccountForm
    required_caps = ("bank.manage",)
    detail_url_name = "finance:bank"


@cap_required("bank.manage", "finance.view_all")
def bank_detail(request, pk):
    bank = get_object_or_404(BankAccount.objects.alive(), pk=pk)
    entries = [(r.created_at, f"Receipt {r.number} {r.payer_name}", r.amount, Decimal(0)) for r in bank.receipts.alive().filter(status__in=Receipt.COUNTABLE)]
    entries += [(v.paid_at, f"PV {v.number} {v.payee_name} ({v.payment_reference})", Decimal(0), v.amount) for v in bank.vouchers.alive().filter(status="PAID")]
    entries.sort(key=lambda e: e[0])
    running = bank.opening_balance
    book = []
    for ts, text, dr, cr in entries:
        running += dr - cr
        book.append({"ts": ts, "text": text, "in": dr, "out": cr, "balance": running})
    return render(request, "finance/cashbook.html", {"title": f"Cashbook – {bank.name}", "bank": bank, "book": book[::-1]})


class RateList(GenericListView):
    model = ExchangeRate
    required_caps = ("bank.manage", "finance.view_all")
    title = "Exchange rates (units per 1 USD)"
    columns = [("Currency", "currency"), ("Rate", "rate"), ("Effective", "effective_date"), ("Set by", "set_by")]
    create_url_name = "finance:rate_new"
    create_caps = ("budget.manage",)
    filter_field = None


class RateCreate(GenericCreateView):
    model = ExchangeRate
    form_class = forms.ExchangeRateForm
    required_caps = ("budget.manage",)
    success_url = "/staff/finance/rates/"

    def prepare(self, obj):
        obj.set_by = self.request.user


class RevenueHeadList(GenericListView):
    model = RevenueHead
    required_caps = ("finance.view",)
    title = "Revenue heads (tariffs)"
    columns = [("Code", "code"), ("Name", "name"), ("Category", "category"), ("Default amount", "default_amount"), ("Frequency", "frequency"),
               ("Online", "payable_online"), ("Active", "is_active")]
    filter_field = "category"
    search_fields = ["code", "name"]
    detail_url_name = "finance:revenue_head_edit"
    create_url_name = "finance:revenue_head_new"
    create_caps = ("budget.manage",)


class RevenueHeadCreate(GenericCreateView):
    model = RevenueHead
    form_class = forms.RevenueHeadForm
    required_caps = ("budget.manage",)
    success_url = "/staff/finance/revenue-heads/"


class RevenueHeadUpdate(GenericUpdateView):
    model = RevenueHead
    form_class = forms.RevenueHeadForm
    required_caps = ("budget.manage",)
    success_url = "/staff/finance/revenue-heads/"


class OnlinePaymentList(GenericListView):
    model = OnlinePayment
    required_caps = ("payments.online_view",)
    title = "Online payments (portal & client app)"
    columns = [("Reference", "reference"), ("Date", "created_at"), ("Account", "account"), ("Amount", "amount"), ("Method", "method"),
               ("Provider ref.", "provider_reference"), ("Receipt", "receipt.number"), ("Channel", "channel"), ("Status", "status")]
    search_fields = ["reference", "account__account_number", "provider_reference"]


# ------------------------------------------------------------------- reports
@cap_required("finance.reports")
def reports(request):
    today = timezone.localdate()
    start = request.GET.get("from") or today.replace(day=1).isoformat()
    end = request.GET.get("to") or today.isoformat()
    receipts = Receipt.objects.alive().filter(status__in=Receipt.COUNTABLE, created_at__date__gte=start, created_at__date__lte=end)
    vouchers = PaymentVoucher.objects.alive().filter(status=PaymentVoucher.Status.PAID, paid_at__date__gte=start, paid_at__date__lte=end)
    ctx = {
        "title": "Financial reports", "start": start, "end": end,
        "income_total": receipts.aggregate(t=Sum("base_amount"))["t"] or 0,
        "expense_total": vouchers.aggregate(t=Sum("base_amount"))["t"] or 0,
        "by_head": receipts.values("revenue_head__code", "revenue_head__name").annotate(t=Sum("base_amount"), n=Count("id")).order_by("-t"),
        "by_method": receipts.values("method", "currency").annotate(t=Sum("amount"), n=Count("id")).order_by("method"),
        "by_channel": receipts.values("channel").annotate(t=Sum("base_amount"), n=Count("id")).order_by("-t"),
        "by_ward": receipts.filter(account__isnull=False).values("account__ward").annotate(t=Sum("base_amount")).order_by("account__ward"),
        "by_cashier": receipts.values("received_by__username").annotate(t=Sum("base_amount"), n=Count("id")).order_by("-t"),
        "by_vote": vouchers.values("budget_line__vote_code", "budget_line__description").annotate(t=Sum("base_amount"), n=Count("id")).order_by("-t"),
        "by_category": vouchers.values("category").annotate(t=Sum("base_amount")).order_by("-t"),
        "voided": Receipt.objects.alive().filter(status=Receipt.Status.VOIDED, voided_at__date__gte=start, voided_at__date__lte=end).count(),
    }
    ctx["net"] = ctx["income_total"] - ctx["expense_total"]
    # Debtors age analysis
    buckets = {"0-30": Decimal(0), "31-60": Decimal(0), "61-90": Decimal(0), "90+": Decimal(0)}
    for b in Bill.objects.alive().filter(status__in=[Bill.Status.UNPAID, Bill.Status.PART_PAID]).only("due_date", "amount", "amount_paid", "status"):
        age = (today - b.due_date).days
        key = "0-30" if age <= 30 else "31-60" if age <= 60 else "61-90" if age <= 90 else "90+"
        buckets[key] += b.outstanding
    ctx["ageing"] = buckets
    if request.GET.get("export") == "receipts":
        log_export(request, f"receipts {start} to {end}")
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="receipts-{start}-{end}.csv"'
        w = SafeCsvWriter(resp)
        w.writerow(["Number", "Date", "Payer", "Account", "Revenue head", "Currency", "Amount", "USD", "Method", "Reference", "Channel", "Cashier", "Status"])
        for r in receipts.select_related("account", "revenue_head", "received_by"):
            w.writerow([r.number, timezone.localtime(r.created_at).strftime("%Y-%m-%d %H:%M"), r.payer_name, r.account.account_number if r.account else "",
                        r.revenue_head.code, r.currency, r.amount, r.base_amount, r.method, r.reference, r.channel,
                        r.received_by.username if r.received_by else "", r.status])
        return resp
    if request.GET.get("export") == "payments":
        log_export(request, f"payments {start} to {end}")
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="payments-{start}-{end}.csv"'
        w = SafeCsvWriter(resp)
        w.writerow(["PV", "Paid at", "Payee", "Category", "Vote", "Currency", "Amount", "USD", "Reference"])
        for v in vouchers.select_related("budget_line"):
            w.writerow([v.number, timezone.localtime(v.paid_at).strftime("%Y-%m-%d %H:%M"), v.payee_name, v.category,
                        v.budget_line.vote_code if v.budget_line else "", v.currency, v.amount, v.base_amount, v.payment_reference])
        return resp
    return render(request, "finance/reports.html", ctx)


# ================================================================ areas
from .models import AccountClaim, Lease, Property, TradingArea  # noqa: E402


@cap_required("areas.view", "accounts.manage")
def areas_overview(request):
    """Every growth point / business centre / market on one page: how many shops are paid up,
    how many still owe and how much – the same rule as each area's shop board."""
    rows, total = services.area_overview()
    q = request.GET.get("q", "").strip().lower()
    if q:
        rows = [r for r in rows if q in r["area"].name.lower()]
    sort = request.GET.get("sort", "owed")
    keyf = {"name": lambda r: r["area"].name, "paid": lambda r: -r["pct"], "shops": lambda r: -r["shops"],
            "collected": lambda r: -r["collected"]}.get(sort, lambda r: -r["owed"])
    rows.sort(key=keyf)
    if request.GET.get("export") == "csv":
        log_export(request, "areas overview")
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="areas-overview.csv"'
        w = SafeCsvWriter(resp)
        w.writerow(["Area", "Type", "Ward", "Shops / stands", "Paid up", "Not paid up", "Owed (USD)", "No valid licence", "Not on app",
                    "Paid this year (USD)"])
        for r in rows:
            a = r["area"]
            w.writerow([a.name, a.get_kind_display(), a.ward or "", r["shops"], r["paid"], r["owing"], r["owed"], r["no_licence"], r["not_on_app"],
                        r["collected"]])
        return resp
    return render(request, "finance/areas_overview.html", {"title": "Areas overview – shops paid & owing", "rows": rows, "total": total,
                                                           "sort": sort, "q": q, "year": timezone.localdate().year})


class AreaList(GenericListView):
    model = TradingArea
    required_caps = ("areas.view", "accounts.manage")
    title = "Trading areas – shopping centres, growth points, townships, markets"
    columns = [("Name", "name"), ("Type", "kind"), ("Ward", "ward"), ("Stands / shops", lambda a: a.properties.alive().count()),
               ("Active", "is_active")]
    search_fields = ["name", "description"]
    filter_field = "kind"
    detail_url_name = "finance:area"
    create_url_name = "finance:area_new"
    create_caps = ("areas.manage",)
    extra_buttons = [("Import stands / shops (CSV)", "finance:register_import", ("accounts.manage",)),
                     ("Send message to clients", "finance:broadcast", ("reminders.send",))]


class AreaCreate(GenericCreateView):
    model = TradingArea
    form_class = forms.TradingAreaForm
    required_caps = ("areas.manage",)
    detail_url_name = "finance:area"


class AreaUpdate(GenericUpdateView):
    model = TradingArea
    form_class = forms.TradingAreaForm
    required_caps = ("areas.manage",)
    detail_url_name = "finance:area"


@cap_required("areas.view", "accounts.manage")
def area_detail(request, pk):
    """Shop / stand board: who has paid and who has not."""
    area = get_object_or_404(TradingArea.objects.alive(), pk=pk)
    rows = [services.property_compliance(p) for p in area.properties.alive().filter(is_active=True).select_related("account").order_by("stand_number")]
    show = request.GET.get("show", "")
    if show == "owing":
        rows = [r for r in rows if not r["ok"]]
    elif show == "paid":
        rows = [r for r in rows if r["ok"]]
    elif show == "unregistered":
        rows = [r for r in rows if not r["registered"]]
    if request.method == "POST":
        if not request.user.has_cap("reminders.send"):
            raise PermissionDenied
        ids = request.POST.getlist("selected")
        props = area.properties.alive().filter(pk__in=ids) if ids else area.properties.alive().filter(is_active=True)
        sent = run_action(request, services.send_compliance_reminders, props, campaign=f"Reminder – {area.name}",
                          extra=request.POST.get("extra", "").strip(), success="Reminders sent.")
        if sent is not None:
            messages.info(request, f"{sent} message(s) sent (app notification and SMS). Accounts that are fully paid were skipped.")
        return redirect("finance:area", pk=pk)
    all_rows = [services.property_compliance(p) for p in area.properties.alive().filter(is_active=True)]
    summary = {
        "stands": len(all_rows), "paid": sum(1 for r in all_rows if r["ok"]), "owing": sum(1 for r in all_rows if not r["ok"]),
        "amount": sum((r["total"] for r in all_rows), Decimal(0)), "unregistered": sum(1 for r in all_rows if not r["registered"]),
        "no_licence": sum(1 for r in all_rows if r["licence"] in ("NONE", "UNPAID", "EXPIRED")),
    }
    for r in rows:
        r["first_bill"] = r["property"].bills.alive().filter(status__in=[Bill.Status.UNPAID, Bill.Status.PART_PAID]).order_by("due_date").first()
    return render(request, "finance/area_detail.html", {"title": area.name, "area": area, "rows": rows, "summary": summary, "show": show,
                                                        "can_receipt": request.user.has_cap("receipt.create")})


@cap_required("accounts.manage")
def register_import(request):
    form = forms.ImportForm(request.POST or None, request.FILES or None)
    stats = None
    if request.method == "POST" and form.is_valid():
        import io

        raw = form.cleaned_data["file"].read().decode("utf-8-sig", errors="replace")
        rows = list(csv.DictReader(io.StringIO(raw)))
        stats = run_action(request, services.import_register, rows, success="Import finished.")
    return render(request, "finance/import.html", {"form": form, "stats": stats, "title": "Import stands & shops", "columns": services.IMPORT_COLUMNS})


@cap_required("accounts.manage")
def register_template(request):
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="crdc-stand-register-template.csv"'
    w = SafeCsvWriter(resp)
    w.writerow(services.IMPORT_COLUMNS)
    w.writerow(["Checheche Growth Point", 22, "B14", "Tafara Hardware (Pvt) Ltd", "BUS", "0772000001", "4455/2019", "", "COM",
                "Tafara Hardware", "40", "35000", "no"])
    w.writerow(["Chipinge Township", 1, "205", "Rumbidzai Moyo", "IND", "0713000002", "63-112233D63", "", "RES", "", "15", "15000", "no"])
    return resp


@cap_required("reminders.send")
def broadcast(request):
    form = forms.BroadcastForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        accs = ClientAccount.objects.alive().exclude(status="CLOSED")
        if d["area"]:
            accs = accs.filter(properties__area=d["area"]).distinct()
        if d["only_owing"]:
            accs = accs.filter(balance__gt=0)
        sent = run_action(request, services.broadcast, list(accs), d["subject"], d["message"], success="Message sent.")
        if sent is not None:
            messages.info(request, f"{sent} message(s) sent to {accs.count()} account(s).")
            return redirect("finance:messages")
    return render(request, "generic/form.html", {"form": form, "title": "Send message / notice to clients (app + SMS)"})


class MessageList(GenericListView):
    from core.models import MessageLog

    model = MessageLog
    required_caps = ("messages.view", "reminders.send")
    title = "Messages sent to clients (SMS, email, app)"
    columns = [("When", "created_at"), ("Channel", "channel"), ("To", "to"), ("Account", "account_number"), ("Campaign", "campaign"),
               ("Message", lambda m: m.body[:90]), ("Sent by", "sent_by"), ("Status", "status")]
    search_fields = ["to", "account_number", "body", "campaign"]
    filter_field = "channel"


# --------------------------------------------------------------- leases
class LeaseList(GenericListView):
    model = Lease
    required_caps = ("leases.view", "leases.manage")
    title = "Leases of council premises"
    columns = [("Lease no.", "number"), ("Lessee", "lessee.name"), ("Premises", "premises"), ("Purpose", "purpose"),
               ("Rent / month", "monthly_rent"), ("From", "start_date"), ("To", "end_date"), ("Status", "status")]
    search_fields = ["number", "lessee__name", "premises__stand_number", "purpose"]
    detail_url_name = "finance:lease"
    create_url_name = "finance:lease_new"
    create_caps = ("leases.manage",)


@cap_required("leases.manage")
def lease_new(request):
    form = forms.LeaseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        lease = run_action(request, services.create_lease, success="Lease registered.", **form.cleaned_data)
        if lease:
            return redirect("finance:lease", pk=lease.pk)
    return render(request, "generic/form.html", {"form": form, "title": "Register a lease"})


class LeaseDetail(GenericDetailView):
    model = Lease
    required_caps = ("leases.view", "leases.manage")
    template_name = "finance/lease_detail.html"
    fields = [("Lessee", "lessee"), ("Premises", "premises"), ("Purpose", "purpose"), ("Monthly rent (USD)", "monthly_rent"),
              ("Deposit", "deposit"), ("Start", "start_date"), ("End", "end_date"), ("Notes", "notes")]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["rent_bills"] = Bill.objects.alive().filter(property=self.object.premises, account=self.object.lessee,
                                                        revenue_head__code="RENT").order_by("-issue_date")[:24]
        return ctx


@cap_required("leases.manage")
@require_POST
def lease_status(request, pk):
    lease = get_object_or_404(Lease, pk=pk)
    new = request.POST.get("status")
    if new in (Lease.Status.TERMINATED, Lease.Status.EXPIRED):
        lease.status = new
        lease.notes = (lease.notes + "\n" + request.POST.get("note", "")).strip()
        lease.save()
        messages.success(request, f"Lease {lease.get_status_display().lower()}.")
    return redirect("finance:lease", pk=pk)


# --------------------------------------------------------------- claims
class ClaimList(GenericListView):
    model = AccountClaim
    required_caps = ("claims.review",)
    title = "Stand / shop registration requests from clients"
    columns = [("Ref.", "reference"), ("Date", "created_at"), ("Client", "user"), ("Type", "claim_type"), ("Stand", "stand_number"),
               ("Area", lambda c: c.area.name if c.area else c.location), ("Business", "business_name"),
               ("Matched in register", lambda c: str(c.matched_property) if c.matched_property else "No"), ("Status", "status")]
    search_fields = ["reference", "stand_number", "business_name", "user__first_name", "user__last_name", "phone"]
    detail_url_name = "finance:claim"


@cap_required("claims.review")
def claim_detail(request, pk):
    claim = get_object_or_404(AccountClaim.objects.alive(), pk=pk)
    initial = {"account": claim.matched_property.account_id if claim.matched_property else None}
    form = forms.ClaimDecisionForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        run_action(request, services.decide_claim, claim, request.POST.get("decision") == "approve", account=d["account"],
                   note=d["note"], create_account=d["create_account"], monthly_rates=d["monthly_rates"], land_use=d["land_use"] or "COM",
                   success="Decision recorded and the client notified.")
        return redirect("finance:claim", pk=pk)
    similar = Property.objects.alive().filter(stand_number__iexact=claim.stand_number).select_related("account", "area")[:10]
    return render(request, "finance/claim_detail.html", {"claim": claim, "form": form, "similar": similar, "title": str(claim),
                                                         "approvals": ApprovalRecord.for_object(claim)})


# ------------------------------------------------------- billing runs v2
@cap_required("billing.run")
def billing_runs(request):
    today = timezone.localdate()
    rates_form = forms.BillingRunForm(request.POST if request.POST.get("run") == "rates" else None, initial={"year": today.year, "month": today.month}, prefix="r")
    lease_form = forms.BillingRunForm(request.POST if request.POST.get("run") == "leases" else None, initial={"year": today.year, "month": today.month}, prefix="l")
    levy_form = forms.LevyRunForm(request.POST if request.POST.get("run") == "levy" else None, initial={"year": today.year}, prefix="v")
    penalty_form = forms.PenaltyRunForm(request.POST if request.POST.get("run") == "penalty" else None, prefix="p")
    result = None
    if request.method == "POST":
        run = request.POST.get("run")
        if run == "rates" and rates_form.is_valid():
            result = run_action(request, services.run_rates_billing, rates_form.cleaned_data["year"], rates_form.cleaned_data["month"], success="Rates billing done.")
        elif run == "leases" and lease_form.is_valid():
            result = run_action(request, services.run_lease_billing, lease_form.cleaned_data["year"], lease_form.cleaned_data["month"], success="Lease billing done.")
        elif run == "levy" and levy_form.is_valid():
            d = levy_form.cleaned_data
            result = run_action(request, services.run_levy_billing, d["revenue_head"], d["year"], area=d["area"], land_use=d["land_use"] or None,
                                amount=d["amount"], success="Levy billing done.")
        elif run == "penalty" and penalty_form.is_valid():
            d = penalty_form.cleaned_data
            result = run_action(request, services.run_late_penalties, rate_pct=d["rate_pct"], days_overdue=d["days_overdue"],
                                success="Late payment penalties charged.")
        if result:
            messages.info(request, f"{result[0]} bill(s) raised; {result[1]} were already billed for that period.")
            return redirect("finance:bills")
    return render(request, "finance/billing_runs.html", {"title": "Billing runs", "rates_form": rates_form, "lease_form": lease_form, "levy_form": levy_form,
                                                           "penalty_form": penalty_form})


# --------------------------------------------------------- fines & penalties
from departments.views import ActionDetail  # noqa: E402

from .models import Fine, Offence  # noqa: E402


class FineList(GenericListView):
    model = Fine
    required_caps = ("fines.view", "fines.issue")
    title = "Fines & penalties (by-law offences)"
    columns = [("Ref.", "reference"), ("Date", "date"), ("Offender", "offender_name"), ("Offence", "offence.name"), ("Location", "location"),
               ("Amount (USD)", "amount"), ("Issued by", "issued_by"), ("Status", "status")]
    search_fields = ["reference", "offender_name", "national_id", "phone", "vehicle_reg", "location"]
    detail_url_name = "finance:fine"
    create_url_name = "finance:fine_new"
    create_caps = ("fines.issue",)
    extra_buttons = [("Offence schedule", "finance:offences", ("fines.view", "offences.manage"))]

    def scope(self, qs):
        u = self.request.user
        return qs if u.has_cap("fines.view") and (u.has_cap("finance.view") or u.sees_all_departments() or u.is_head) else qs.filter(issued_by=u)


@cap_required("fines.issue")
def fine_new(request):
    form = forms.FineForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        fine = run_action(request, services.issue_fine, success="Fine issued – billed to the offender's account and sent by SMS.", **form.cleaned_data)
        if fine:
            return redirect("finance:fine", pk=fine.pk)
    return render(request, "generic/form.html", {"form": form, "title": "Issue a fine"})


class FineDetail(ActionDetail):
    model = Fine
    required_caps = ("fines.view", "fines.issue")
    action_url_name = "finance:fine_action"
    fields = [("Offence", "offence"), ("Offender", "offender_name"), ("National ID", "national_id"), ("Phone", "phone"), ("Vehicle", "vehicle_reg"),
              ("Account", "account"), ("Location", "location"), ("Ward", "ward"), ("Date", "date"), ("Amount (USD)", "amount"), ("Notes", "notes"),
              ("Bill", "bill"), ("Issued by", "issued_by"), ("Decided by", "decided_by"), ("Reason", "decision_reason")]

    def scope(self, qs):
        return FineList.scope(self, qs)

    def actions(self, obj):
        u = self.request.user
        acts = []
        if obj.status == Fine.Status.ISSUED and u.has_cap("fines.waive") and obj.issued_by_id != u.pk:
            acts.append({"title": "Waive the fine (Treasurer / CEO)", "fields": [("reason", "Reason", "textarea", None)],
                         "buttons": [("waive", "Waive", "outline-danger")]})
        if obj.status == Fine.Status.ISSUED and u.has_cap("fines.issue", "fines.waive"):
            acts.append({"title": "Not paid?", "fields": [("reason", "Note", "textarea", None)], "buttons": [("court", "Refer to court", "warning")]})
        return acts


@cap_required("fines.issue", "fines.waive")
@require_POST
def fine_action(request, pk):
    fine = get_object_or_404(Fine, pk=pk)
    run_action(request, services.decide_fine, fine, request.POST.get("action"), request.POST.get("reason", ""), success="Fine updated.")
    return redirect("finance:fine", pk=pk)


class OffenceList(GenericListView):
    model = Offence
    required_caps = ("fines.view", "offences.manage")
    title = "Offence schedule – standard fines"
    columns = [("Code", "code"), ("Offence", "name"), ("By-law", "by_law"), ("Fine (USD)", "default_fine"), ("Active", "is_active")]
    search_fields = ["code", "name", "by_law"]
    filter_field = None
    detail_url_name = "finance:offence_edit"
    create_url_name = "finance:offence_new"
    create_caps = ("offences.manage",)


class OffenceNew(GenericCreateView):
    model = Offence
    form_class = forms.OffenceForm
    required_caps = ("offences.manage",)
    title = "New offence"

    def get_success_url(self):
        return reverse("finance:offences")


class OffenceEdit(GenericUpdateView):
    model = Offence
    form_class = forms.OffenceForm
    required_caps = ("offences.manage",)

    def get_success_url(self):
        return reverse("finance:offences")
