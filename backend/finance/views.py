import csv
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
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
    GenericCreateView, GenericDetailView, GenericListView, GenericUpdateView, log_export, run_action,
)
from core.views import finance_kpis, pending_approvals

from . import forms, services
from .models import (
    BankAccount, Bill, BudgetLine, CashUp, ClientAccount, ExchangeRate, Licence, OnlinePayment, PaymentVoucher,
    PurchaseOrder, Receipt, Requisition, RevenueHead, Supplier,
)

FIN_ALL = ("finance.view_all",)


@cap_required("finance.view")
def dashboard(request):
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
    mine = receipts.filter(received_by=request.user, cashup__isnull=True)
    ctx = {
        "title": "Finance dashboard", "fin": finance_kpis(), "by_head": by_head, "chart": chart,
        "approvals": pending_approvals(request.user),
        "my_uncashed": mine.values("currency").annotate(t=Sum("amount"), n=Count("id")),
        "banks": BankAccount.objects.alive().filter(is_active=True) if request.user.has_cap("bank.manage", "finance.view_all") else [],
        "recent": receipts.select_related("revenue_head")[:10] if request.user.has_cap(*FIN_ALL) else mine[:10],
    }
    return render(request, "finance/dashboard.html", ctx)


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
    w = csv.writer(resp)
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
    extra_buttons = [("Monthly rates billing run", "finance:billing_run", ("billing.run",))]

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
class LicenceList(GenericListView):
    model = Licence
    required_caps = ("licence.view",)
    title = "Licences (shop, hawker, business …)"
    columns = [("Licence no.", "number"), ("Type", "licence_type"), ("Business", "business_name"), ("Account", "account.account_number"),
               ("Premises", "premises"), ("Fee", "fee"), ("Expires", "expiry_date"), ("Status", "status")]
    search_fields = ["number", "business_name", "account__account_number", "account__name", "premises"]
    detail_url_name = "finance:licence"
    create_url_name = "finance:licence_new"
    create_caps = ("licence.manage",)


@cap_required("licence.manage")
def licence_new(request):
    form = forms.LicenceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        lic = run_action(request, services.apply_licence, account=d["account"], licence_type=d["licence_type"], business_name=d["business_name"],
                         premises=d["premises"], business_activity=d["business_activity"], ward=d["ward"], success="Application captured.")
        if lic:
            return redirect("finance:licence", pk=lic.pk)
    return render(request, "generic/form.html", {"form": form, "title": "Capture licence application"})


class LicenceDetail(GenericDetailView):
    model = Licence
    required_caps = ("licence.view",)
    template_name = "finance/licence_detail.html"
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
        w = csv.writer(resp)
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
        w = csv.writer(resp)
        w.writerow(["PV", "Paid at", "Payee", "Category", "Vote", "Currency", "Amount", "USD", "Reference"])
        for v in vouchers.select_related("budget_line"):
            w.writerow([v.number, timezone.localtime(v.paid_at).strftime("%Y-%m-%d %H:%M"), v.payee_name, v.category,
                        v.budget_line.vote_code if v.budget_line else "", v.currency, v.amount, v.base_amount, v.payment_reference])
        return resp
    return render(request, "finance/reports.html", ctx)
