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

    app = serializers.ChoiceField(choices=["council", "client"], write_only=True,
                                  error_messages={"required": "Update the app: it must say whether it is the council or the client app."})

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
        fields = ["id", "username", "full_name", "first_name", "last_name", "national_id", "ward", "email", "phone", "user_type", "department",
                  "department_label", "role", "role_label", "is_head", "must_change_password", "capabilities", "employee_number", "annual_leave_days"]

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
                                         "stand_number", "business_name", "location", "ward", "land_use", "hectares", "valuation", "monthly_rates",
                                         "is_council_owned", "is_active"])

    def get_registered(self, obj):
        return obj.account.portal_users.exists()


class BillSerializer(SyncSerializer):
    outstanding = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    revenue_head_category = serializers.CharField(source="revenue_head.category", read_only=True)

    class Meta:
        model = Bill
        fields = _sync_fields(Bill, ["brought_forward"] + ["number", "account", "property", "revenue_head", "revenue_head_category", "description", "period", "amount",
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
    still_to_pay = serializers.SerializerMethodField()

    def get_still_to_pay(self, obj):
        if obj.status != Licence.Status.APPROVED:
            return []
        from finance.services import licence_outstanding

        return [{"label": label, "amount": str(amount)} for label, amount in licence_outstanding(obj)]

    class Meta:
        model = Licence
        fields = _sync_fields(Licence, ["number", "licence_type", "account", "property", "account_number", "business_name", "business_activity", "premises",
                                        "ward", "status", "fee", "bill", "inspection_notes", "rejection_reason", "issue_date", "expiry_date",
                                        "due_at", "still_to_pay"])


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
    waiting_position = serializers.IntegerField(read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True, default="")
    fee = serializers.DecimalField(source="fee_bill.amount", max_digits=14, decimal_places=2, read_only=True, default=None)
    deposit = serializers.DecimalField(source="deposit_bill.amount", max_digits=14, decimal_places=2, read_only=True, default=None)
    deposit_paid = serializers.SerializerMethodField()

    class Meta:
        model = StandApplication
        fields = _sync_fields(StandApplication, ["reference", "applicant_name", "national_id", "phone", "stand_type", "preferred_location", "ward",
                                                 "status", "allocated_stand", "account", "fee_bill", "fee", "deposit_bill", "deposit", "deposit_paid", "area", "area_name",
                                                 "waiting_position", "joined_waiting_list_at"])

    def get_deposit_paid(self, obj):
        return bool(obj.deposit_bill_id and obj.deposit_bill.status == "PAID")


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
    days = serializers.IntegerField(read_only=True)
    employee_department = serializers.CharField(source="employee.department", read_only=True)
    approvers = serializers.SerializerMethodField()
    route = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields = _sync_fields(LeaveRequest, ["employee", "employee_name", "employee_department", "leave_type", "start_date", "end_date", "days", "reason", "status",
                                             "stage", "decision_comment", "approvers", "route"])

    def get_approvers(self, obj):
        from departments import leave

        return [u.pk for u in leave.approvers(obj)]

    def get_route(self, obj):
        from departments import leave

        return [{"stage": r["stage"], "who": r["who"], "state": r["state"], "comment": r["comment"],
                 "when": r["when"].isoformat() if r["when"] else None} for r in leave.route(obj)]


class NotificationSerializer(SyncSerializer):
    class Meta:
        model = Notification
        fields = _sync_fields(Notification, ["title", "body", "link", "is_read"])


class OnlinePaymentSerializer(SyncSerializer):
    receipt_number = serializers.CharField(source="receipt.number", read_only=True, default="")
    receipt_numbers = serializers.SerializerMethodField()

    class Meta:
        model = OnlinePayment
        fields = _sync_fields(OnlinePayment, ["reference", "account", "bill", "revenue_head", "amount", "currency", "method", "phone", "provider", "status",
                                              "receipt", "receipt_number", "receipt_numbers", "paid_at"])

    def get_receipt_numbers(self, obj):
        nums = [r.number for r in obj.receipts.all()] if obj.pk else []
        return nums or ([obj.receipt.number] if obj.receipt_id else [])


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

    drawing_name = serializers.SerializerMethodField()

    def get_drawing_name(self, obj):
        return obj.drawing.name.rsplit("/", 1)[-1] if obj.drawing else ""

    class Meta:
        model = BuildingPlan
        fields = _sync_fields(BuildingPlan, ["reference", "applicant_name", "phone", "stand_number", "location", "ward", "development_type",
                                             "description", "floor_area", "fee", "drawing_name", "bill", "bill_status", "status", "reviewed_by_id", "review_notes",
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


# ------------------------------------------------- requests for funds & memos
from workflow import funds as _fr  # noqa: E402
from workflow import memos as _mm  # noqa: E402
from workflow.models import FundsRequest, Memo  # noqa: E402


def _s(v):
    if v is None:
        return ""
    if hasattr(v, "get_full_name"):
        return v.get_full_name() or v.username
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


class FundsRequestSerializer(SyncSerializer):
    requested_by_name = serializers.CharField(source="requested_by.get_full_name", read_only=True)
    lines = serializers.SerializerMethodField()
    route = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    where_now = serializers.SerializerMethodField()
    days_waiting = serializers.IntegerField(read_only=True)
    deciders = serializers.SerializerMethodField()
    payee_differs = serializers.BooleanField(read_only=True)
    voucher_number = serializers.CharField(source="voucher.number", read_only=True, default="")
    voucher_status = serializers.CharField(source="voucher.get_status_display", read_only=True, default="")
    vote = serializers.CharField(source="budget_line.vote_code", read_only=True, default="")

    class Meta:
        model = FundsRequest
        fields = _sync_fields(FundsRequest, ["reference", "request_type", "title", "purpose", "department", "requested_by", "requested_by_name",
                                             "destination", "depart_date", "return_date", "travellers", "currency", "total", "needed_by",
                                             "requires_payment", "payee_name", "payment_method", "payment_details", "vote", "status", "submitted_at",
                                             "stage_since", "last_reminder_at", "decision_note", "voucher_number", "voucher_status", "completed_at",
                                             "lines", "route", "history", "where_now", "days_waiting", "deciders", "payee_differs"])

    def get_lines(self, obj):
        return [{"description": ln.description, "quantity": str(ln.quantity), "unit_cost": str(ln.unit_cost), "total": str(ln.total)}
                for ln in obj.lines.all()]

    def get_route(self, obj):
        return [{"label": r["label"], "state": r["state"], "who": _s(r["who"]), "when": _s(r["when"]), "note": _s(r["note"])} for r in _fr.route(obj)]

    def get_history(self, obj):
        return [{"stage": a.stage, "decision": a.decision, "user": _s(a.user), "when": _s(a.timestamp), "comment": a.comment} for a in _fr.history(obj)]

    def get_where_now(self, obj):
        return _fr.where_now(obj)

    def get_deciders(self, obj):
        """Users who may decide now (the phone shows them the decision panel)."""
        if obj.status not in _fr.STAGE_LABEL:
            return []
        done = _fr._approved_this_round(obj)
        return [u.pk for u in _fr.eligible(obj) if u.pk != obj.requested_by_id and u.pk not in done]


class MemoSerializer(SyncSerializer):
    sender_name = serializers.CharField(source="sender.get_full_name", read_only=True)
    to_user_name = serializers.CharField(source="to_user.get_full_name", read_only=True, default="")
    task_reference = serializers.CharField(source="task.reference", read_only=True, default="")
    task_status = serializers.CharField(source="task.get_status_display", read_only=True, default="")
    task_assignee = serializers.CharField(source="task.assigned_to.get_full_name", read_only=True, default="")
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Memo
        fields = _sync_fields(Memo, ["reference", "kind", "sender", "sender_name", "from_department", "to_department", "to_user", "to_user_name",
                                     "subject", "body", "priority", "status", "read_at", "task_reference", "task_status", "task_assignee", "replies"])

    def get_replies(self, obj):
        return [{"author": _s(r.author), "department": r.author.get_department_display(), "body": r.body, "when": _s(r.created_at)}
                for r in obj.replies.all() if not r.is_deleted]


# ------------------------------------------- finance & admin registers for the apps
from finance.models import BankAccount, CashUp, PurchaseOrder, Supplier  # noqa: E402
from workflow.models import Correspondence  # noqa: E402


class CashUpSerializer(SyncSerializer):
    cashier_id = serializers.IntegerField(source="cashier.pk", read_only=True)
    cashier_name = serializers.CharField(source="cashier.get_full_name", read_only=True)
    verified_by_name = serializers.CharField(source="verified_by.get_full_name", read_only=True, default="")

    class Meta:
        model = CashUp
        fields = _sync_fields(CashUp, ["cashier_id", "cashier_name", "date", "currency", "expected_cash", "declared_cash", "expected_other",
                                       "variance", "status", "notes", "verified_by_name", "verified_at"])


class SupplierSerializer(SyncSerializer):
    class Meta:
        model = Supplier
        fields = _sync_fields(Supplier, ["code", "name", "category", "contact_person", "phone", "email", "status"])


class PurchaseOrderSerializer(SyncSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    requisition_number = serializers.CharField(source="requisition.number", read_only=True)
    requisition_purpose = serializers.CharField(source="requisition.purpose", read_only=True)
    department = serializers.CharField(source="requisition.department", read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = _sync_fields(PurchaseOrder, ["number", "requisition", "requisition_number", "requisition_purpose", "department", "supplier",
                                              "supplier_name", "amount", "currency", "status", "expected_delivery", "delivered_at", "notes"])


class BankAccountSerializer(SyncSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = BankAccount
        fields = _sync_fields(BankAccount, ["name", "bank", "account_number", "currency", "is_active", "balance"])

    def get_balance(self, obj):
        return str(obj.balance())


class CorrespondenceSerializer(SyncSerializer):
    assigned_to_name = serializers.CharField(source="assigned_to.get_full_name", read_only=True, default="")

    class Meta:
        model = Correspondence
        fields = _sync_fields(Correspondence, ["reference", "sender", "sender_contact", "subject", "date_received", "department", "assigned_to",
                                               "assigned_to_name", "status", "response_due", "responded_at", "response_summary", "file_reference"])



# ------------------------------------------------------------------ payroll
from payroll.models import Payslip, SalaryProfile  # noqa: E402


class SalaryProfileSerializer(SyncSerializer):
    employee_id = serializers.IntegerField(source="employee.pk", read_only=True)
    employee_name = serializers.CharField(source="employee.get_full_name", read_only=True)
    department = serializers.CharField(source="employee.department", read_only=True)
    role_label = serializers.CharField(source="employee.role_label", read_only=True)
    allowances = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    gross = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    deductions = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    net = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = SalaryProfile
        fields = _sync_fields(SalaryProfile, ["employee_id", "employee_name", "department", "role_label", "grade", "currency", "basic_salary",
                                              "housing_allowance", "transport_allowance", "other_allowances", "paye", "nssa", "pension", "medical_aid",
                                              "other_deductions", "payment_method", "bank_name", "bank_account", "is_active", "allowances", "gross",
                                              "deductions", "net", "auto_tax", "tax_credits", "taxable_income", "income_tax", "aids_levy"])


class PayslipSerializer(SyncSerializer):
    employee_id = serializers.IntegerField(source="employee.pk", read_only=True)
    employee_name = serializers.CharField(source="employee.get_full_name", read_only=True)
    department = serializers.CharField(source="employee.department", read_only=True)
    period = serializers.CharField(read_only=True)
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    payments = serializers.SerializerMethodField()

    class Meta:
        model = Payslip
        fields = _sync_fields(Payslip, ["reference", "employee_id", "employee_name", "department", "year", "month", "period", "currency", "grade",
                                        "basic_salary", "allowances", "gross", "paye", "taxable_income", "income_tax", "aids_levy", "tax_table", "nssa",
                                        "pension", "other_deductions", "net", "amount_paid",
                                        "balance", "status", "approved_at", "payments"])

    def get_payments(self, obj):
        return [{"amount": str(p.amount), "method": p.get_method_display(), "reference": p.reference, "paid_on": p.paid_on.isoformat(),
                 "paid_by": p.paid_by.get_full_name()} for p in obj.payments.all() if not p.is_deleted]



from payroll.models import TaxTable  # noqa: E402


class TaxTableSerializer(SyncSerializer):
    bands = serializers.SerializerMethodField()

    class Meta:
        model = TaxTable
        fields = _sync_fields(TaxTable, ["name", "currency", "effective_from", "aids_levy_rate", "nssa_rate", "nssa_ceiling", "pension_cap", "confirmed",
                                         "source", "bands"])

    def get_bands(self, obj):
        return [{"lower": str(b.lower), "upper": str(b.upper) if b.upper is not None else None, "rate": str(b.rate)} for b in obj.bands.all()]


# ------------------------------------------------- fines & social services
from finance.models import Fine, Offence  # noqa: E402
from social import models as sm  # noqa: E402


class _NamedFKSerializer(SyncSerializer):
    """Adds ``<fk>_name`` (the related object's name) for every foreign key in ``Meta.fields``."""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for f in instance._meta.concrete_fields:
            if f.is_relation and f.name in data:
                rel = getattr(instance, f.name)
                data[f"{f.name}_name"] = (rel.get_full_name() or rel.username) if hasattr(rel, "get_full_name") else (
                    getattr(rel, "name", None) or str(rel)) if rel else ""
        return data


class OffenceSerializer(SyncSerializer):
    class Meta:
        model = Offence
        fields = _sync_fields(Offence, ["code", "name", "by_law", "default_fine", "is_active"])


class FineSerializer(_NamedFKSerializer):
    class Meta:
        model = Fine
        fields = _sync_fields(Fine, ["reference", "offence", "account", "offender_name", "national_id", "phone", "vehicle_reg", "ward", "location",
                                     "date", "amount", "notes", "status", "bill", "issued_by", "decided_by", "decision_reason"])


class WildlifeSerializer(_NamedFKSerializer):
    class Meta:
        model = sm.WildlifeRecord
        fields = _sync_fields(sm.WildlifeRecord, ["reference", "species", "record_type", "date", "ward", "location", "count", "gps", "notes",
                                                  "recorded_by"])


class QuotaSerializer(_NamedFKSerializer):
    used = serializers.IntegerField(read_only=True)
    remaining = serializers.IntegerField(read_only=True)

    class Meta:
        model = sm.HuntingQuota
        fields = _sync_fields(sm.HuntingQuota, ["year", "species", "ward", "concession", "quota", "trophy_fee", "notes", "used", "remaining"])


class HuntSerializer(_NamedFKSerializer):
    species = serializers.CharField(source="quota.species", read_only=True)
    species_label = serializers.CharField(read_only=True)
    ward = serializers.IntegerField(source="quota.ward", read_only=True)
    community_share = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    council_share = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = sm.TrophyHunt
        fields = _sync_fields(sm.TrophyHunt, ["reference", "quota", "species", "species_label", "ward", "operator", "professional_hunter",
                                              "client_name", "client_nationality", "hunt_date", "trophy_fee", "community_share_pct", "community_share",
                                              "council_share", "trophy_details", "status", "bill", "recorded_by"])


class PermitSerializer(_NamedFKSerializer):
    quantity_extracted = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    quantity_left = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    extractions = serializers.SerializerMethodField()

    class Meta:
        model = sm.ResourcePermit
        fields = _sync_fields(sm.ResourcePermit, ["reference", "permit_type", "holder", "ward", "location", "gps", "unit", "quantity_allowed",
                                                  "unit_fee", "fee", "valid_from", "valid_to", "ema_reference", "conditions", "status", "bill",
                                                  "applied_by", "decided_by", "decision_note", "quantity_extracted", "quantity_left", "extractions"])

    def get_extractions(self, obj):
        return [{"date": str(e.date), "quantity": str(e.quantity), "vehicle_reg": e.vehicle_reg, "destination": e.destination,
                 "by": e.recorded_by.get_full_name() if e.recorded_by else ""} for e in obj.extractions.alive()]


class FarmSerializer(_NamedFKSerializer):
    class Meta:
        model = sm.Farm
        fields = _sync_fields(sm.Farm, ["reference", "name", "owner", "farm_number", "ward", "location", "hectares", "farm_type", "activity",
                                        "main_crops", "cattle", "goats_sheep", "irrigated_hectares", "water_source", "gps", "status", "notes"])


class WaterPointSerializer(_NamedFKSerializer):
    class Meta:
        model = sm.WaterPoint
        fields = _sync_fields(sm.WaterPoint, ["reference", "name", "point_type", "ward", "village", "households_served", "status", "last_serviced",
                                              "water_quality_ok", "committee_contact", "gps", "notes"])


# ------------------------------------------- charter registers (technical, admin, public health, community)
from departments import models as dm  # noqa: E402


def _reg_serializer(model, fields, extra=None):
    meta = type("Meta", (), {"model": model, "fields": _sync_fields(model, fields)})
    return type(f"{model.__name__}Serializer", (_NamedFKSerializer,), {"Meta": meta, **(extra or {})})


RoadSerializer = _reg_serializer(dm.Road, ["reference", "name", "road_number", "ward", "start_point", "end_point", "length_km", "surface", "condition",
                                           "last_graded", "bridges_culverts", "notes"])
LightSerializer = _reg_serializer(dm.PublicLight, ["reference", "light_type", "location", "ward", "pole_number", "status", "last_checked", "notes"])
WorkOrderSerializer = _reg_serializer(dm.WorkOrder, ["reference", "kind", "title", "location", "ward", "road", "light", "description", "assigned_to",
                                                     "due_date", "status", "materials", "labour_days", "cost", "completion_notes", "completed_at",
                                                     "signed_off_by"])
RecordFileSerializer = _reg_serializer(dm.RecordFile, ["file_number", "title", "department", "category", "location", "confidential", "opened_on",
                                                       "retain_until", "status", "borrowed_by", "borrowed_at", "due_back", "notes"])
InspectionSerializer = _reg_serializer(sm.HealthInspection, ["reference", "premises", "premises_type", "owner", "ward", "location", "date", "score",
                                                             "result", "findings", "follow_up_date", "inspector"])
SanitationSerializer = _reg_serializer(sm.SanitationFacility, ["reference", "name", "kind", "ward", "location", "status", "last_serviced",
                                                               "collection_days", "caretaker", "notes"])
FacilitySerializer = _reg_serializer(sm.SocialFacility, ["reference", "name", "kind", "ward", "location", "responsible_authority", "population_served",
                                                         "classrooms_or_beds", "condition", "needs", "contact"])
LandParcelSerializer = _reg_serializer(dm.LandParcel, ["parcel_number", "name", "ward", "location", "hectares", "land_use", "status", "survey_diagram",
                                                       "title_deed", "valuation", "stands_planned", "notes"])
EngagementSerializer = _reg_serializer(dm.Engagement, ["reference", "title", "kind", "date", "ward", "venue", "attendance", "issues_raised", "resolutions",
                                                       "status", "officer"])
NoticeSerializer = _reg_serializer(dm.PublicNotice, ["title", "category", "body", "ward", "publish_from", "expires_on", "is_published", "posted_by"])
AuditEngagementSerializer = _reg_serializer(dm.AuditEngagement, ["reference", "title", "audit_type", "department", "quarter", "auditor", "status", "scope",
                                                                 "conclusion"])


from finance.models import Tenancy  # noqa: E402


class TenancySerializer(SyncSerializer):
    stand_number = serializers.CharField(source="property.stand_number", read_only=True)
    location = serializers.CharField(source="property.location", read_only=True)
    area_name = serializers.CharField(source="property.area.name", read_only=True, default="")
    land_use = serializers.CharField(source="property.get_land_use_display", read_only=True)
    tenant_account_number = serializers.CharField(source="tenant.account_number", read_only=True)

    class Meta:
        model = Tenancy
        fields = _sync_fields(Tenancy, ["property", "tenant", "tenant_account_number", "stand_number", "location", "area_name", "land_use",
                                        "business_name", "start_date", "end_date", "is_active"])


from finance.models import CertificateRequest  # noqa: E402


class CertificateSerializer(SyncSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    stand_number = serializers.CharField(source="property.stand_number", read_only=True, default="")
    property_label = serializers.SerializerMethodField()
    account_number = serializers.CharField(source="account.account_number", read_only=True)
    account_balance = serializers.DecimalField(source="account.balance", max_digits=14, decimal_places=2, read_only=True)
    fee = serializers.DecimalField(source="fee_bill.amount", max_digits=14, decimal_places=2, read_only=True, default=None)
    fee_paid = serializers.SerializerMethodField()
    decided_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CertificateRequest
        fields = _sync_fields(CertificateRequest, ["reference", "number", "kind", "kind_label", "user", "account", "account_number", "account_balance",
                                                   "property", "stand_number", "property_label", "applicant_name", "national_id", "phone", "address",
                                                   "ward", "purpose", "other_party_name", "other_party_id", "event_date", "place", "beneficiary", "subject_name", "subject_id", "subject_phone",
                                                   "subject_relationship", "fee_bill", "fee",
                                                   "fee_paid", "status", "status_label", "decided_by_name", "decided_at", "decision_note", "valid_until",
                                                   "created_at"])

    def get_property_label(self, obj):
        return str(obj.property) if obj.property_id else ""

    def get_fee_paid(self, obj):
        return bool(obj.fee_bill_id and obj.fee_bill.status == "PAID")

    def get_decided_by_name(self, obj):
        return obj.decided_by.get_full_name() if obj.decided_by_id else ""


from finance.models import StandBeneficiary  # noqa: E402


class StandBeneficiarySerializer(SyncSerializer):
    relationship_label = serializers.CharField(source="get_relationship_display", read_only=True)
    stand_number = serializers.CharField(source="property.stand_number", read_only=True)
    property_label = serializers.SerializerMethodField()
    owner_name = serializers.CharField(source="property.account.name", read_only=True)
    account_number = serializers.CharField(source="property.account.account_number", read_only=True)
    added_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StandBeneficiary
        fields = _sync_fields(StandBeneficiary, ["property", "stand_number", "property_label", "owner_name", "account_number", "full_name", "relationship",
                                                 "relationship_label", "national_id", "date_of_birth", "phone", "lives_here", "notes", "added_by_name",
                                                 "is_active"])

    def get_property_label(self, obj):
        return str(obj.property)

    def get_added_by_name(self, obj):
        return obj.added_by.get_full_name() if obj.added_by_id else ""


from departments.models import AvailableStand  # noqa: E402


class AvailableStandSerializer(SyncSerializer):
    area_name = serializers.CharField(source="area.name", read_only=True)
    stand_type_label = serializers.CharField(source="get_stand_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    applicant_name = serializers.CharField(source="application.applicant_name", read_only=True, default="")

    class Meta:
        model = AvailableStand
        fields = _sync_fields(AvailableStand, ["stand_number", "area", "area_name", "stand_type", "stand_type_label", "size_sqm", "price", "status",
                                               "status_label", "application", "applicant_name", "notes"])
