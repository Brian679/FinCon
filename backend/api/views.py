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
