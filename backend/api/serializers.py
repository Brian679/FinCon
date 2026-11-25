from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.models import Notification, ServiceStandard
from departments.models import AuditFinding, LeaveRequest, Project, StandApplication
from finance.models import (
    Bill, BudgetLine, ClientAccount, Licence, OnlinePayment, PaymentVoucher, Property, Receipt, Requisition, RevenueHead,
)
from workflow.models import Complaint, ServiceRequest, Task, TaskComment

User = get_user_model()


class AppTokenSerializer(TokenObtainPairSerializer):
    """JWT login. The ``app`` field stops staff from logging into the client app
    and clients from logging into the council app."""

    app = serializers.ChoiceField(choices=["council", "client"], required=False, write_only=True)

    def validate(self, attrs):
        app = attrs.pop("app", None)
        data = super().validate(attrs)
        user = self.user
        if app == "council" and not user.is_staff_member:
            raise serializers.ValidationError({"detail": "This app is for council staff. Please use the Chipinge RDC client app."})
        if app == "client" and not user.is_client:
            raise serializers.ValidationError({"detail": "Staff must use the council app."})
        data["user"] = MeSerializer(user).data
        return data


class MeSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name")
    role_label = serializers.CharField()
    department_label = serializers.CharField(source="get_department_display")
    capabilities = serializers.SerializerMethodField()
    is_head = serializers.BooleanField()

    class Meta:
        model = User
        fields = ["id", "username", "full_name", "email", "phone", "user_type", "department", "department_label", "role", "role_label",
                  "is_head", "must_change_password", "capabilities"]

    def get_capabilities(self, obj):
        return sorted(obj.capabilities)


def _sync_fields(model, extra=()):
    return ["id", "created_at", "updated_at", "is_deleted"] + [f for f in extra]


class SyncSerializer(serializers.ModelSerializer):
    """Base: emits display labels for choice fields as ``<field>_label``."""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for f in instance._meta.concrete_fields:
            if f.choices and f.name in data:
                data[f"{f.name}_label"] = getattr(instance, f"get_{f.name}_display")()
        return data


class RevenueHeadSerializer(SyncSerializer):
    class Meta:
        model = RevenueHead
        fields = _sync_fields(RevenueHead, ["code", "name", "category", "default_amount", "frequency", "payable_online", "is_active"])


class ServiceStandardSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceStandard
        fields = ["id", "code", "service", "standard_text", "is_digital", "updated_at"]


class ClientAccountSerializer(SyncSerializer):
    class Meta:
        model = ClientAccount
        fields = _sync_fields(ClientAccount, ["account_number", "account_type", "name", "id_number", "phone", "email", "postal_address", "ward",
                                              "status", "balance"])


class PropertySerializer(SyncSerializer):
    area_name = serializers.CharField(source="area.name", read_only=True, default="")
    account_name = serializers.CharField(source="account.name", read_only=True)
    account_number = serializers.CharField(source="account.account_number", read_only=True)
    account_phone = serializers.CharField(source="account.phone", read_only=True)
    registered = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = _sync_fields(Property, ["account", "account_name", "account_number", "account_phone", "registered", "area", "area_name",
                                         "stand_number", "business_name", "location", "ward", "land_use", "valuation", "monthly_rates",
                                         "is_council_owned", "is_active"])

    def get_registered(self, obj):
        return obj.account.portal_users.exists()


class BillSerializer(SyncSerializer):
    outstanding = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    revenue_head_category = serializers.CharField(source="revenue_head.category", read_only=True)

    class Meta:
        model = Bill
        fields = _sync_fields(Bill, ["number", "account", "property", "revenue_head", "revenue_head_category", "description", "period", "amount",
                                     "amount_paid", "outstanding",
                                     "issue_date", "due_date", "status"])


class ReceiptSerializer(SyncSerializer):
    revenue_head_name = serializers.CharField(source="revenue_head.name", read_only=True)
    account_number = serializers.CharField(source="account.account_number", read_only=True, default="")
    received_by_name = serializers.CharField(source="received_by.username", read_only=True, default="")

    class Meta:
        model = Receipt
        fields = _sync_fields(Receipt, ["number", "received_by", "void_requested_by", "void_reason", "account", "account_number", "payer_name", "revenue_head", "revenue_head_name", "bill",
                                        "description", "currency", "amount", "base_amount", "method", "reference", "channel",
                                        "received_by_name", "status", "offline_created_at"])


class LicenceSerializer(SyncSerializer):
    account_number = serializers.CharField(source="account.account_number", read_only=True)

    class Meta:
        model = Licence
        fields = _sync_fields(Licence, ["number", "licence_type", "account", "property", "account_number", "business_name", "business_activity", "premises",
                                        "ward", "status", "fee", "bill", "inspection_notes", "rejection_reason", "issue_date", "expiry_date",
                                        "due_at"])


class RequisitionSerializer(SyncSerializer):
    requested_by_name = serializers.CharField(source="requested_by.get_full_name", read_only=True)
    items = serializers.SerializerMethodField()
    needs_ceo = serializers.BooleanField(read_only=True)

    class Meta:
        model = Requisition
        fields = _sync_fields(Requisition, ["number", "department", "requested_by", "requested_by_name", "purpose", "total", "status",
                                            "rejection_reason", "items", "needs_ceo"])

    def get_items(self, obj):
        return [{"description": i.description, "quantity": str(i.quantity), "unit_cost": str(i.unit_cost), "total": str(i.total)} for i in obj.items.all()]


class VoucherSerializer(SyncSerializer):
    prepared_by_name = serializers.CharField(source="prepared_by.get_full_name", read_only=True)
    vote = serializers.CharField(source="budget_line.vote_code", read_only=True, default="")
    needs_ceo = serializers.BooleanField(read_only=True)

    class Meta:
        model = PaymentVoucher
        fields = _sync_fields(PaymentVoucher, ["number", "category", "payee_name", "department", "vote", "description", "invoice_number",
                                               "currency", "amount", "base_amount", "method", "status", "prepared_by", "prepared_by_name", "needs_ceo",
                                               "payment_reference", "paid_at", "rejection_reason"])


class BudgetLineSerializer(SyncSerializer):
    actual = serializers.SerializerMethodField()
    committed = serializers.SerializerMethodField()

    class Meta:
        model = BudgetLine
        fields = _sync_fields(BudgetLine, ["financial_year", "vote_code", "description", "department", "kind", "approved_amount", "revised_amount",
                                           "actual", "committed"])

    def get_actual(self, obj):
        return str(obj.actual())

    def get_committed(self, obj):
        return str(obj.committed())


class TaskSerializer(SyncSerializer):
    assigned_by_name = serializers.CharField(source="assigned_by.get_full_name", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.get_full_name", read_only=True, default="")

    class Meta:
        model = Task
        fields = _sync_fields(Task, ["reference", "kind", "title", "description", "assigned_by", "assigned_by_name", "assigned_to",
                                     "assigned_to_name", "department", "priority", "due_date", "status", "progress", "completed_at"])


class TaskCommentSerializer(SyncSerializer):
    author_name = serializers.CharField(source="author.get_full_name", read_only=True)

    class Meta:
        model = TaskComment
        fields = _sync_fields(TaskComment, ["task", "author", "author_name", "body"])


class ComplaintSerializer(SyncSerializer):
    class Meta:
        model = Complaint
        fields = _sync_fields(Complaint, ["reference", "kind", "channel", "name", "phone", "email", "ward", "department", "subject", "details",
                                          "status", "assigned_to", "acknowledge_due", "acknowledged_at", "response_due", "resolution",
                                          "resolved_at"])


class ServiceRequestSerializer(SyncSerializer):
    class Meta:
        model = ServiceRequest
        fields = _sync_fields(ServiceRequest, ["reference", "category", "department", "description", "location", "ward", "latitude", "longitude",
                                               "reporter_name", "reporter_phone", "priority", "status", "assigned_to", "due_at", "resolution",
                                               "resolved_at"])


class StandApplicationSerializer(SyncSerializer):
    class Meta:
        model = StandApplication
        fields = _sync_fields(StandApplication, ["reference", "applicant_name", "national_id", "phone", "stand_type", "preferred_location", "ward",
                                                 "status", "allocated_stand"])


class ProjectSerializer(SyncSerializer):
    class Meta:
        model = Project
        fields = _sync_fields(Project, ["code", "name", "category", "department", "ward", "location", "budget", "funder", "start_date",
                                        "end_date", "progress", "status"])


class AuditFindingSerializer(SyncSerializer):
    class Meta:
        model = AuditFinding
        fields = _sync_fields(AuditFinding, ["reference", "audit_type", "department", "title", "finding", "risk_rating", "recommendation",
                                             "management_response", "implementation_date", "status"])


class LeaveRequestSerializer(SyncSerializer):
    employee_name = serializers.CharField(source="employee.get_full_name", read_only=True)
    employee_department = serializers.CharField(source="employee.department", read_only=True)

    class Meta:
        model = LeaveRequest
        fields = _sync_fields(LeaveRequest, ["employee", "employee_name", "employee_department", "leave_type", "start_date", "end_date", "reason", "status",
                                             "decision_comment"])


class NotificationSerializer(SyncSerializer):
    class Meta:
        model = Notification
        fields = _sync_fields(Notification, ["title", "body", "link", "is_read"])


class OnlinePaymentSerializer(SyncSerializer):
    receipt_number = serializers.CharField(source="receipt.number", read_only=True, default="")

    class Meta:
        model = OnlinePayment
        fields = _sync_fields(OnlinePayment, ["reference", "account", "bill", "revenue_head", "amount", "currency", "method", "phone", "provider", "status",
                                              "receipt", "receipt_number", "paid_at"])


# ------------------------------------------------------------- new registers
from departments.models import (  # noqa: E402
    Asset, BuildingPlan, CommunityActivity, CouncilMeeting, ICTTicket, Incident, Policy, Resolution, Risk,
)
from finance.models import AccountClaim, Lease, TradingArea  # noqa: E402


class StaffSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name")
    role_label = serializers.CharField()
    updated_at = serializers.DateTimeField(source="date_joined")

    class Meta:
        model = User
        fields = ["id", "username", "full_name", "department", "role", "role_label", "phone", "email", "is_active", "updated_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["id"] = str(instance.pk)
        data["user_id"] = instance.pk
        return data


class TradingAreaSerializer(SyncSerializer):
    class Meta:
        model = TradingArea
        fields = _sync_fields(TradingArea, ["name", "kind", "ward", "description", "is_active"])


class LeaseSerializer(SyncSerializer):
    lessee_name = serializers.CharField(source="lessee.name", read_only=True)
    premises_name = serializers.CharField(source="premises.__str__", read_only=True)

    class Meta:
        model = Lease
        fields = _sync_fields(Lease, ["number", "lessee", "lessee_name", "premises", "premises_name", "purpose", "monthly_rent", "deposit",
                                      "start_date", "end_date", "status"])


class ClaimSerializer(SyncSerializer):
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True, default="")
    matched = serializers.SerializerMethodField()
    account_number = serializers.CharField(source="account.account_number", read_only=True, default="")

    class Meta:
        model = AccountClaim
        fields = _sync_fields(AccountClaim, ["reference", "user_name", "claim_type", "stand_number", "area", "area_name", "location", "business_name",
                                             "id_number", "phone", "notes", "status", "matched_property", "matched", "account", "account_number",
                                             "decision_note"])

    def get_matched(self, obj):
        p = obj.matched_property
        return f"{p} – {p.account.name} ({p.account.phone})" if p else ""


class AssetSerializer(SyncSerializer):
    book_value = serializers.SerializerMethodField()
    custodian_name = serializers.CharField(source="custodian.get_full_name", read_only=True, default="")
    history = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = _sync_fields(Asset, ["asset_number", "name", "category", "department", "serial_number", "location", "ward", "acquisition_date",
                                      "cost", "book_value", "custodian_name", "condition", "status", "notes", "history"])

    def get_book_value(self, obj):
        return str(obj.book_value())

    def get_history(self, obj):
        return [{"date": str(m.date), "work_done": m.work_done, "cost": str(m.cost), "condition": m.get_condition_after_display()}
                for m in obj.maintenance.alive()[:10]]


class IncidentSerializer(SyncSerializer):
    lead_officer_name = serializers.CharField(source="lead_officer.get_full_name", read_only=True, default="")

    class Meta:
        model = Incident
        fields = _sync_fields(Incident, ["reference", "incident_type", "title", "description", "ward", "location", "occurred_at",
                                         "households_affected", "people_injured", "deaths", "livestock_lost", "crops_hectares", "response", "status",
                                         "lead_officer_name"])


class ActivitySerializer(SyncSerializer):
    officer_id = serializers.IntegerField(source="officer.pk", read_only=True, default=None)
    officer_name = serializers.CharField(source="officer.get_full_name", read_only=True, default="")

    class Meta:
        model = CommunityActivity
        fields = _sync_fields(CommunityActivity, ["reference", "activity_type", "title", "department", "ward", "venue", "date", "participants",
                                                  "report", "status", "officer_id", "officer_name"])


class BuildingPlanSerializer(SyncSerializer):
    reviewed_by_id = serializers.IntegerField(source="reviewed_by.pk", read_only=True, default=None)
    bill_status = serializers.CharField(source="bill.status", read_only=True, default="")

    class Meta:
        model = BuildingPlan
        fields = _sync_fields(BuildingPlan, ["reference", "applicant_name", "phone", "stand_number", "location", "ward", "development_type",
                                             "description", "floor_area", "fee", "bill", "bill_status", "status", "reviewed_by_id", "review_notes",
                                             "decision_notes", "inspection_log", "due_at"])


class RiskSerializer(SyncSerializer):
    score = serializers.IntegerField(read_only=True)
    rating = serializers.CharField(read_only=True)
    owner_name = serializers.CharField(source="owner.get_full_name", read_only=True, default="")

    class Meta:
        model = Risk
        fields = _sync_fields(Risk, ["reference", "department", "title", "description", "category", "likelihood", "impact", "score", "rating",
                                     "existing_controls", "mitigation", "owner_name", "review_date", "status"])


class MeetingSerializer(SyncSerializer):
    class Meta:
        model = CouncilMeeting
        fields = _sync_fields(CouncilMeeting, ["reference", "meeting_type", "title", "date", "venue", "agenda", "minutes", "status"])


class ResolutionSerializer(SyncSerializer):
    responsible_id = serializers.IntegerField(source="responsible.pk", read_only=True, default=None)
    responsible_name = serializers.CharField(source="responsible.get_full_name", read_only=True, default="")
    meeting_title = serializers.CharField(source="meeting.title", read_only=True)

    class Meta:
        model = Resolution
        fields = _sync_fields(Resolution, ["number", "meeting", "meeting_title", "text", "department", "responsible_id", "responsible_name",
                                           "due_date", "status", "progress_note"])


class TicketSerializer(SyncSerializer):
    raised_by_id = serializers.IntegerField(source="raised_by.pk", read_only=True)
    raised_by_name = serializers.CharField(source="raised_by.get_full_name", read_only=True)

    class Meta:
        model = ICTTicket
        fields = _sync_fields(ICTTicket, ["reference", "raised_by_id", "raised_by_name", "department", "category", "subject", "description",
                                          "priority", "status", "resolution"])


class PolicySerializer(SyncSerializer):
    class Meta:
        model = Policy
        fields = _sync_fields(Policy, ["title", "kind", "department", "version", "summary", "status", "adopted_on", "review_date"])
