from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from accounts.forms import ClientRegistrationForm
from core import audit
from core.models import AuditLog
from finance import services as fin
from finance.models import Bill, ClientAccount, OnlinePayment, RevenueHead
from portal.services import link_account

from . import serializers as s
from . import sync


class AuditActorMixin:
    """Attribute audit-trail entries to the JWT-authenticated user."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.user and request.user.is_authenticated:
            self._audit_token = audit.set_actor(request.user)

    def finalize_response(self, request, response, *args, **kwargs):
        token = getattr(self, "_audit_token", None)
        if token is not None:
            audit._actor.reset(token)
            self._audit_token = None
        return super().finalize_response(request, response, *args, **kwargs)


class LoginView(TokenObtainPairView):
    serializer_class = s.AppTokenSerializer
    throttle_classes = [AnonRateThrottle]


class MeView(AuditActorMixin, APIView):
    def get(self, request):
        return Response(s.MeSerializer(request.user).data)


class PasswordView(AuditActorMixin, APIView):
    """Change password from the phone (same rules as the website)."""

    def post(self, request):
        from django.contrib.auth.password_validation import validate_password

        user = request.user
        old, new = request.data.get("old_password", ""), request.data.get("new_password", "")
        if not user.check_password(old):
            return Response({"detail": "Your current password is wrong."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new, user)
        except ValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new)
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        audit.log(AuditLog.Action.UPDATE, user, user=user, message="Password changed (mobile app)")
        # Every other phone / computer is signed out; this device gets fresh tokens.
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(user)
        return Response({"detail": "Password changed. Other devices have been signed out.", "access": str(refresh.access_token), "refresh": str(refresh)})


class PullView(AuditActorMixin, APIView):
    def post(self, request):
        cursors = request.data.get("cursors") or {}
        limit = min(int(request.data.get("limit") or sync.PAGE), 1000)
        return Response(sync.pull(request.user, cursors, limit))


class PushView(AuditActorMixin, APIView):
    def post(self, request):
        ops = request.data.get("operations") or []
        if not isinstance(ops, list) or len(ops) > 200:
            return Response({"detail": "Send between 1 and 200 operations per batch."}, status=400)
        results = sync.push(request.user, ops, device_id=str(request.data.get("device_id", ""))[:64])
        applied = sum(1 for r in results if r["status"] == "applied")
        if ops:
            audit.log(AuditLog.Action.SYNC, user=request.user, message=f"Mobile sync: {len(ops)} operation(s), {applied} applied")
        return Response({"server_time": sync.timezone.now().isoformat(), "results": results})


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([AnonRateThrottle])
def register_client(request):
    form = ClientRegistrationForm(request.data)
    if not form.is_valid():
        return Response({"errors": form.errors}, status=400)
    user = form.save()
    audit.log(AuditLog.Action.CREATE, user, user=user, message="Client self-registration (mobile app)")
    return Response(s.MeSerializer(user).data, status=201)


class LinkAccountView(AuditActorMixin, APIView):
    def post(self, request):
        if not request.user.is_client:
            return Response({"detail": "Clients only."}, status=403)
        try:
            account = link_account(request.user, request.data.get("account_number", ""), request.data.get("verifier", ""))
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=400)
        return Response(s.ClientAccountSerializer(account).data)


class PaymentView(AuditActorMixin, APIView):
    """Online payments need a live connection (the mobile-money prompt is
    real-time), so they are a direct API call rather than a queued operation."""

    def post(self, request):
        user = request.user
        account = get_object_or_404(ClientAccount, pk=request.data.get("account"))
        bill = Bill.objects.filter(pk=request.data.get("bill"), account=account).first() if request.data.get("bill") else None
        head = RevenueHead.objects.filter(pk=request.data.get("revenue_head")).first() if request.data.get("revenue_head") else None
        try:
            p = fin.start_online_payment(user, account=account, amount=request.data.get("amount"), revenue_head=head, bill=bill,
                                         method=request.data.get("method", "ECOCASH"), phone=request.data.get("phone", ""),
                                         channel="CLIENT_APP")
        except (ValidationError, PermissionDenied, RuntimeError) as exc:
            msg = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            return Response({"detail": msg}, status=400)
        return Response(s.OnlinePaymentSerializer(p).data, status=201)


class PaymentStatusView(AuditActorMixin, APIView):
    def get(self, request, ref):
        p = get_object_or_404(OnlinePayment, reference=ref, user=request.user)
        return Response(s.OnlinePaymentSerializer(p).data)

    def post(self, request, ref):
        """``{"action": "confirm"}`` (simulated gateway only), ``"check"`` or ``"cancel"``."""
        p = get_object_or_404(OnlinePayment, reference=ref, user=request.user)
        action = request.data.get("action", "check")
        if p.status == OnlinePayment.Status.PENDING:
            if action == "confirm" and p.provider == "simulated":
                fin.confirm_online_payment(p, provider_reference=f"SIM{p.reference[-6:]}")
            elif action == "cancel":
                p.status = OnlinePayment.Status.CANCELLED
                p.save()
            elif action == "check":
                from finance.gateway import get_gateway

                st = get_gateway().check(p)
                if st in ("paid", "awaiting delivery", "delivered"):
                    fin.confirm_online_payment(p, provider_reference=p.provider_reference)
        p.refresh_from_db()
        return Response(s.OnlinePaymentSerializer(p).data)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def paynow_result(request):
    """Paynow server-to-server status callback."""
    ref = request.data.get("reference")
    p = OnlinePayment.objects.filter(reference=ref).first()
    if p and p.status == OnlinePayment.Status.PENDING:
        from finance.gateway import get_gateway

        st = get_gateway().check(p)  # never trust the callback body: re-poll Paynow
        if st in ("paid", "awaiting delivery", "delivered"):
            fin.confirm_online_payment(p, provider_reference=p.provider_reference)
    return Response(status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def health(request):
    return Response({"status": "ok", "time": sync.timezone.now().isoformat()})



class FinanceReportView(AuditActorMixin, APIView):
    """Financial summary for the apps (online): income by revenue head, payments by category,
    debtors ageing and bank balances for a period."""

    def get(self, request):
        from datetime import date

        from django.db.models import Count, Sum
        from django.utils import timezone

        from finance.models import BankAccount, PaymentVoucher, Receipt

        if not request.user.has_cap("finance.reports", "reports.executive"):
            return Response({"detail": "Financial reports are for the Treasurer, Accountant, CEO and auditors."}, status=403)
        today = timezone.localdate()
        try:
            start = date.fromisoformat(request.GET.get("from") or today.replace(day=1).isoformat())
            end = date.fromisoformat(request.GET.get("to") or today.isoformat())
        except ValueError:
            return Response({"detail": "Dates must be YYYY-MM-DD."}, status=400)
        rec = Receipt.objects.alive().filter(status__in=Receipt.COUNTABLE, created_at__date__gte=start, created_at__date__lte=end)
        pv = PaymentVoucher.objects.alive().filter(status=PaymentVoucher.Status.PAID, paid_at__date__gte=start, paid_at__date__lte=end)
        income = rec.aggregate(t=Sum("base_amount"))["t"] or 0
        spent = pv.aggregate(t=Sum("base_amount"))["t"] or 0
        ageing = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
        for b in Bill.objects.alive().filter(status__in=[Bill.Status.UNPAID, Bill.Status.PART_PAID]).only("due_date", "amount", "amount_paid", "status"):
            age = (today - b.due_date).days
            key = "0-30" if age <= 30 else "31-60" if age <= 60 else "61-90" if age <= 90 else "90+"
            ageing[key] += float(b.outstanding)
        audit.log(AuditLog.Action.EXPORT, message=f"Finance report {start} to {end} (mobile)", user=request.user)
        return Response({
            "from": start.isoformat(), "to": end.isoformat(), "income": str(income), "expenditure": str(spent), "net": str(income - spent),
            "receipts": rec.count(), "payments": pv.count(),
            "by_head": [{"label": r["revenue_head__name"], "amount": str(r["t"]), "count": r["n"]}
                        for r in rec.values("revenue_head__name").annotate(t=Sum("base_amount"), n=Count("id")).order_by("-t")],
            "by_channel": [{"label": r["channel"], "amount": str(r["t"]), "count": r["n"]}
                           for r in rec.values("channel").annotate(t=Sum("base_amount"), n=Count("id")).order_by("-t")],
            "by_category": [{"label": dict(PaymentVoucher.Category.choices).get(r["category"], r["category"]), "amount": str(r["t"]), "count": r["n"]}
                            for r in pv.values("category").annotate(t=Sum("base_amount"), n=Count("id")).order_by("-t")],
            "ageing": [{"label": k, "amount": f"{v:.2f}", "count": 0} for k, v in ageing.items()],
            "banks": [{"label": f"{b.name} ({b.currency})", "amount": str(b.balance()), "count": 0} for b in BankAccount.objects.alive().filter(is_active=True)]
            if request.user.has_cap("bank.manage", "finance.view_all") else [],
        })


class ExecutiveView(AuditActorMixin, APIView):
    """CEO's whole-council view for the apps: Client Charter compliance and every department."""

    def get(self, request):
        from datetime import timedelta

        from django.utils import timezone

        from core.models import Department
        from core.views import finance_kpis
        from departments.models import AuditFinding
        from workflow.models import Complaint, ServiceRequest, Task
        from workflow.models import FundsRequest

        if not request.user.has_cap("reports.executive"):
            return Response({"detail": "The executive overview is for the CEO."}, status=403)
        now = timezone.now()
        since = now - timedelta(days=90)
        comp = Complaint.objects.alive().filter(created_at__gte=since)
        acked = [c for c in comp.filter(acknowledged_at__isnull=False) if c.acknowledge_due and c.acknowledged_at <= c.acknowledge_due]
        reqs = ServiceRequest.objects.alive().filter(created_at__gte=since, resolved_at__isnull=False)
        in_time = [r for r in reqs if r.due_at and r.resolved_at <= r.due_at]

        def pct(a, b):
            return round(a * 100 / b) if b else None

        fin_k = finance_kpis()
        rows = []
        for code, label in Department.choices:
            open_tasks = Task.objects.alive().filter(department=code, status__in=["OPEN", "IN_PROGRESS"])
            rows.append({"code": code, "label": label, "tasks_open": open_tasks.count(),
                         "tasks_overdue": open_tasks.filter(due_date__lt=timezone.localdate()).count(),
                         "complaints_open": Complaint.objects.alive().filter(department=code).exclude(status__in=["RESOLVED", "CLOSED"]).count(),
                         "requests_open": ServiceRequest.objects.alive().filter(department=code).exclude(status__in=["RESOLVED", "CLOSED", "REJECTED"]).count(),
                         "findings_open": AuditFinding.objects.alive().filter(department=code).exclude(status="CLOSED").count(),
                         "funds_waiting": FundsRequest.objects.alive().filter(department=code, status__in=FundsRequest.OPEN).count()})
        return Response({
            "collected_today": str(fin_k["today"]["t"] or 0), "collected_month": str(fin_k["month"]["t"] or 0),
            "paid_out_month": str(fin_k["paid_out_month"]), "debtors": str(fin_k["debtors"]["t"] or 0), "overdue_bills": fin_k["overdue_bills"],
            "charter": [{"label": "Complaints acknowledged within 48 hours", "pct": pct(len(acked), comp.count()), "count": comp.count()},
                        {"label": "Service requests resolved within charter time", "pct": pct(len(in_time), reqs.count()), "count": reqs.count()}],
            "departments": rows,
        })


class AuditTrailView(AuditActorMixin, APIView):
    """Read-only audit trail for the apps (same scope as the website)."""

    def get(self, request):
        from django.db.models import Q

        from core.models import Department

        user = request.user
        if not user.has_cap("audit.view_trail"):
            return Response({"detail": "The audit trail is for auditors, the CEO, the Treasurer and ICT."}, status=403)
        qs = AuditLog.objects.all()
        if not user.has_cap("audit.view_all"):
            cond = Q(department=user.department)
            if user.department == Department.FINANCE:
                cond |= Q(model__startswith="finance.")
            qs = qs.filter(cond)
        q = request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(object_repr__icontains=q) | Q(message__icontains=q) | Q(username__icontains=q))
        if request.GET.get("action"):
            qs = qs.filter(action=request.GET["action"])
        page = max(1, int(request.GET.get("page") or 1))
        rows = qs.order_by("-timestamp", "-id")[(page - 1) * 50: page * 50]
        return Response({"page": page, "items": [
            {"when": r.timestamp.isoformat(), "user": r.username or "system", "action": r.get_action_display(), "object": r.object_repr,
             "model": r.model, "message": r.message, "channel": r.channel} for r in rows]})
