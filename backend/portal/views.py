from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from django.contrib.auth import views as auth_views
from django.urls import reverse

from accounts.forms import ClientRegistrationForm, LoginForm
from core import audit
from core.crud import idempotent
from core.models import AuditLog
from departments.models import StandApplication
from finance import services as fin
from finance.models import Bill, ClientAccount, Licence, OnlinePayment, Receipt
from workflow import services as wf
from workflow.models import Complaint, ServiceRequest

from . import forms
from .services import link_account


def client_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path(), "portal:login")
        if not request.user.is_client:
            messages.info(request, "The client portal is for residents and businesses. Staff use the council system.")
            return redirect("accounts:home")
        return view(request, *args, **kwargs)

    return wrapper


class ClientLoginView(auth_views.LoginView):
    """Login for the public client website. Staff are sent to the staff website."""

    template_name = "portal/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        if form.get_user().is_staff_member:
            form.add_error(None, "Council staff must log in on the staff website.")
            return self.form_invalid(form)
        return super().form_valid(form)

    def get_default_redirect_url(self):
        return reverse("portal:dashboard")


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:home")
    form = ClientRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        audit.log(AuditLog.Action.CREATE, user, user=user, message="Client self-registration")
        login(request, user, backend="accounts.backends.LockoutModelBackend")
        d = form.cleaned_data
        if d.get("stand_number") and d.get("relationship", "NONE") != "NONE":
            claim = fin.submit_claim(user, stand_number=d["stand_number"], area=d.get("area"), location=d.get("location", ""),
                                     business_name=d.get("business_name", ""),
                                     claim_type=d["relationship"])
            if claim.status == claim.Status.APPROVED:
                messages.success(request, f"Welcome! Stand {claim.stand_number} matched our register and is now linked to your account.")
            else:
                messages.info(request, f"Welcome! Your stand {claim.stand_number} has been sent to the council for verification "
                                       f"(reference {claim.reference}). You will be notified once it is approved.")
            return redirect("portal:dashboard")
        messages.success(request, "Welcome! Link your council account or register your stand / shop.")
        return redirect("portal:claims")
    return render(request, "portal/register.html", {"form": form, "title": "Create client account"})


def my_accounts(user):
    return user.client_accounts.alive()


@client_required
def dashboard(request):
    accounts = my_accounts(request.user)
    return render(request, "portal/dashboard.html", {
        "title": "My council", "accounts": accounts,
        "unpaid": Bill.objects.alive().filter(account__in=accounts, status__in=[Bill.Status.UNPAID, Bill.Status.PART_PAID])[:10],
        "receipts": Receipt.objects.alive().filter(account__in=accounts).exclude(status=Receipt.Status.VOIDED)[:5],
        "licences": Licence.objects.alive().filter(Q(account__in=accounts) | Q(applicant=request.user)).distinct()[:5],
        "complaints": Complaint.objects.alive().filter(client=request.user)[:5],
        "requests": ServiceRequest.objects.alive().filter(reporter=request.user)[:5],
    })


@client_required
def accounts(request):
    return render(request, "portal/accounts.html", {"title": "My accounts", "accounts": my_accounts(request.user)})


@client_required
def account_detail(request, pk):
    account = get_object_or_404(my_accounts(request.user), pk=pk)
    return render(request, "portal/account_detail.html", {
        "title": str(account), "account": account, "bills": account.bills.alive().exclude(status=Bill.Status.CANCELLED),
        "receipts": account.receipts.alive().exclude(status=Receipt.Status.VOIDED), "properties": account.properties.alive(),
    })


@client_required
def link(request):
    form = forms.LinkAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            account = link_account(request.user, form.cleaned_data["account_number"], form.cleaned_data["verifier"])
            messages.success(request, f"Account {account.account_number} linked.")
            return redirect("portal:account", pk=account.pk)
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
    return render(request, "generic/form.html", {"form": form, "title": "Link my council account"})


@client_required
def pay(request):
    accounts = list(my_accounts(request.user))
    if not accounts:
        messages.info(request, "Link your council account first.")
        return redirect("portal:link")
    initial = {"phone": request.user.phone}
    bill = None
    if request.GET.get("bill"):
        bill = Bill.objects.alive().filter(pk=request.GET["bill"], account__in=accounts).first()
        if bill:
            initial.update(account=str(bill.account_id), revenue_head=bill.revenue_head_id, amount=bill.outstanding)
    elif accounts:
        initial.update(account=str(accounts[0].pk), amount=max(accounts[0].balance, 1))
    form = forms.PayForm(request.POST or None, initial=initial, accounts=accounts)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        account = next(a for a in accounts if str(a.pk) == d["account"])
        bill_id = request.POST.get("bill")
        bill = Bill.objects.alive().filter(pk=bill_id, account=account).first() if bill_id else None
        try:
            payment = fin.start_online_payment(request.user, account=account, amount=d["amount"], revenue_head=d["revenue_head"], bill=bill,
                                               method=d["method"], phone=d["phone"])
            return redirect("portal:payment", ref=payment.reference)
        except (ValidationError, PermissionDenied, RuntimeError) as exc:
            form.add_error(None, str(exc))
    return render(request, "portal/pay.html", {"form": form, "title": "Pay online", "bill": bill})


@client_required
def payment(request, ref):
    p = get_object_or_404(OnlinePayment, reference=ref, user=request.user)
    if request.method == "POST" and p.status == OnlinePayment.Status.PENDING:
        if p.provider == "simulated" and request.POST.get("confirm"):
            fin.confirm_online_payment(p, provider_reference=f"SIM{p.reference[-6:]}")
            messages.success(request, "Payment confirmed – your receipt has been issued.")
        elif request.POST.get("cancel"):
            p.status = OnlinePayment.Status.CANCELLED
            p.save()
        else:
            from finance.gateway import get_gateway

            status = get_gateway().check(p)
            if status in ("paid", "awaiting delivery", "delivered"):
                fin.confirm_online_payment(p, provider_reference=p.provider_reference)
            elif status in ("cancelled", "failed"):
                p.status = OnlinePayment.Status.FAILED
                p.save()
        return redirect("portal:payment", ref=ref)
    p.refresh_from_db()
    return render(request, "portal/payment.html", {"p": p, "title": f"Payment {p.reference}"})


@client_required
def receipts(request):
    qs = Receipt.objects.alive().filter(account__in=my_accounts(request.user)).exclude(status=Receipt.Status.VOIDED)
    return render(request, "portal/receipts.html", {"title": "Payment history", "receipts": qs})


@client_required
def receipt(request, pk):
    r = get_object_or_404(Receipt.objects.alive(), pk=pk, account__in=my_accounts(request.user))
    return render(request, "portal/receipt.html", {"r": r, "title": r.number})


@client_required
def licences(request):
    accounts = my_accounts(request.user)
    qs = Licence.objects.alive().filter(Q(account__in=accounts) | Q(applicant=request.user)).distinct()
    return render(request, "portal/licences.html", {"title": "My licences", "licences": qs})


@client_required
def licence_apply(request):
    accounts = list(my_accounts(request.user))
    if not accounts:
        messages.info(request, "Link (or ask council to open) a business account first.")
        return redirect("portal:link")
    form = forms.ClientLicenceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        account = next((a for a in accounts if str(a.pk) == request.POST.get("account")), accounts[0])
        d = form.cleaned_data
        lic = fin.apply_licence(request.user, account=account, licence_type=d["licence_type"], business_name=d["business_name"],
                                premises=d["premises"], business_activity=d["business_activity"], ward=d["ward"],
                                property=account.properties.alive().filter(pk=request.POST.get("property") or None).first())
        messages.success(request, f"Application {lic.number} submitted. We will process it within 30 working days.")
        return redirect("portal:licences")
    return render(request, "portal/licence_apply.html", {"form": form, "accounts": accounts, "title": "Apply for a licence"})


@client_required
def licence_certificate(request, pk):
    accounts = my_accounts(request.user)
    lic = get_object_or_404(Licence.objects.alive().filter(Q(account__in=accounts) | Q(applicant=request.user)).distinct(), pk=pk,
                            status=Licence.Status.ISSUED)
    return render(request, "finance/licence_certificate.html", {"lic": lic, "title": lic.number})


@client_required
def complaints(request):
    return render(request, "portal/list.html", {"title": "My complaints & feedback", "items": Complaint.objects.alive().filter(client=request.user),
                                                "new_url": "portal:complaint_new", "kind": "complaint"})


@client_required
@idempotent
def complaint_new(request):
    form = forms.ClientComplaintForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        c = wf.log_complaint(request.user, channel=Complaint.Channel.PORTAL, **form.cleaned_data)
        messages.success(request, f"Thank you. Reference {c.reference}. We will acknowledge within 48 hours.")
        return redirect("portal:complaints")
    return render(request, "generic/form.html", {"form": form, "title": "Complaint, compliment or suggestion", "offline_capable": True})


@client_required
def requests_list(request):
    return render(request, "portal/list.html", {"title": "My reported problems", "items": ServiceRequest.objects.alive().filter(reporter=request.user),
                                                "new_url": "portal:request_new", "kind": "request"})


@client_required
@idempotent
def request_new(request):
    form = forms.ClientRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        sr = wf.report_service_request(request.user, **form.cleaned_data)
        messages.success(request, f"Reported. Reference {sr.reference}.")
        return redirect("portal:requests")
    return render(request, "generic/form.html", {"form": form, "title": "Report a problem (water, roads, refuse …)", "offline_capable": True})


@client_required
def stands(request):
    return render(request, "portal/list.html", {"title": "My stand applications", "items": StandApplication.objects.alive().filter(applicant=request.user),
                                                "new_url": "portal:stand_new", "kind": "stand"})


@client_required
def stand_new(request):
    form = forms.ClientStandForm(request.POST or None, initial={"national_id": request.user.national_id, "phone": request.user.phone})
    if request.method == "POST" and form.is_valid():
        from departments.services import apply_for_stand

        d = form.cleaned_data
        st = apply_for_stand(request.user, stand_type=d["stand_type"], preferred_location=d["preferred_location"], ward=d.get("ward"))
        messages.success(request, f"Application {st.reference} received. " + (
            f"Pay the waiting-list fee (bill {st.fee_bill.number}) to join the waiting list." if st.fee_bill_id else "You are on the waiting list."))
        return redirect("portal:stands")
    return render(request, "generic/form.html", {"form": form, "title": "Apply for a stand"})


@client_required
def notifications(request):
    qs = request.user.notifications.alive().order_by("-created_at")[:100]
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, "portal/notifications.html", {"title": "Notifications", "items": qs})


@client_required
@idempotent
def claim_new(request):
    form = forms.ClaimForm(request.POST or None, initial={"phone": request.user.phone, "id_number": request.user.national_id})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        claim = fin.submit_claim(request.user, stand_number=d["stand_number"], area=d["area"], location=d["location"],
                                 business_name=d["business_name"], id_number=d["id_number"], phone=d["phone"], claim_type=d["claim_type"],
                                 notes=d["notes"])
        if claim.status == claim.Status.APPROVED:
            messages.success(request, f"Stand {claim.stand_number} matched the council register and is now linked to your account.")
        else:
            messages.info(request, f"Sent for verification (reference {claim.reference}). The council will check and approve it.")
        return redirect("portal:claims")
    return render(request, "generic/form.html", {"form": form, "title": "Register my stand / shop", "offline_capable": True})


@client_required
def claims(request):
    from finance.models import AccountClaim

    items = AccountClaim.objects.alive().filter(user=request.user)
    return render(request, "portal/claims.html", {"title": "My stands & shops", "items": items, "accounts": my_accounts(request.user)})


@client_required
def plans(request):
    from departments.models import BuildingPlan

    return render(request, "portal/list.html", {"title": "My building plans", "items": BuildingPlan.objects.alive().filter(applicant=request.user),
                                                "new_url": "portal:plan_new", "kind": "plan"})


@client_required
@idempotent
def plan_new(request):
    from departments import services as dept

    form = forms.ClientPlanForm(request.POST or None, initial={"phone": request.user.phone})
    if request.method == "POST" and form.is_valid():
        plan = dept.submit_building_plan(request.user, **form.cleaned_data)
        messages.success(request, f"Plan {plan.reference} submitted. Pay the plan fee to start the review (decision within 30 working days).")
        return redirect("portal:plans")
    return render(request, "generic/form.html", {"form": form, "title": "Submit a building plan for approval"})
