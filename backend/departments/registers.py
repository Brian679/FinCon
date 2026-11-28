"""Charter registers added per department, built from one pattern (list, add, view, edit + stage actions):

* Technical Services – road network, public lighting, engineering work orders (job cards)
* Administration     – records management (registry files, loans, archiving)
* Social Services    – public health inspections, ablutions & waste (WASH), schools & clinics development
"""
from django import forms as djforms
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.forms import modelform_factory
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import cap_required
from core.crud import BootstrapFormMixin, GenericCreateView, GenericListView, GenericUpdateView, run_action
from finance.services import _record, notify
from social.models import HealthInspection, SanitationFacility, SocialFacility

from .models import AuditEngagement, AvailableStand, Engagement, LandParcel, PublicLight, PublicNotice, RecordFile, Road, WorkOrder
from .views import ActionDetail

DATE = {"type": "date"}


def _form(model, fields, dates=()):
    widgets = {d: djforms.DateInput(attrs=DATE, format="%Y-%m-%d") for d in dates}
    return modelform_factory(model, form=type("F", (BootstrapFormMixin, djforms.ModelForm), {}), fields=fields, widgets=widgets)


# key: model, url slug, title, view caps, manage caps, list columns, form fields, date fields, filter field, search
SPECS = {
    "available": (AvailableStand, "growth/available-stands", "Stands available for allocation (by area)", ("stands.view", "stands.manage"),
                  ("stands.manage",),
                  [("Stand", "stand_number"), ("Area", "area"), ("Type", "stand_type"), ("Size (m²)", "size_sqm"), ("Price (USD)", "price"),
                   ("Reserved for", "application"), ("Status", "status")],
                  ["stand_number", "area", "stand_type", "size_sqm", "price", "status", "notes"], (), "status", ["stand_number", "area__name"]),
    "roads": (Road, "technical/roads", "Road network – construction, rehabilitation & maintenance", ("roads.view", "roads.manage"), ("roads.manage",),
              [("Ref.", "reference"), ("Road", "name"), ("No.", "road_number"), ("Ward", "ward"), ("Length (km)", "length_km"), ("Surface", "surface"),
               ("Last graded", "last_graded"), ("Condition", "condition")],
              ["name", "road_number", "ward", "start_point", "end_point", "length_km", "surface", "condition", "last_graded", "bridges_culverts", "notes"],
              ("last_graded",), "condition", ["reference", "name", "road_number", "start_point", "end_point"]),
    "lights": (PublicLight, "technical/lights", "Public lighting – street & high-mast lights", ("lighting.view", "lighting.manage"), ("lighting.manage",),
               [("Ref.", "reference"), ("Type", "light_type"), ("Location", "location"), ("Ward", "ward"), ("Pole", "pole_number"),
                ("Last checked", "last_checked"), ("Status", "status")],
               ["light_type", "location", "ward", "pole_number", "status", "last_checked", "notes"], ("last_checked",), "status",
               ["reference", "location", "pole_number"]),
    "works": (WorkOrder, "technical/works", "Engineering services – work orders / job cards", ("works.view", "works.manage"), ("works.manage",),
              [("Ref.", "reference"), ("Type", "kind"), ("Work", "title"), ("Location", "location"), ("Assigned to", "assigned_to"), ("Due", "due_date"),
               ("Cost (USD)", "cost"), ("Status", "status")],
              ["kind", "title", "location", "ward", "road", "light", "description", "assigned_to", "due_date"], ("due_date",), "status",
              ["reference", "title", "location"]),
    "records": (RecordFile, "admin/records", "Records management – registry files", ("records.view", "records.manage"), ("records.manage",),
                [("File no.", "file_number"), ("Title", "title"), ("Department", "department"), ("Category", "category"), ("Location", "location"),
                 ("With", "borrowed_by"), ("Due back", "due_back"), ("Status", "status")],
                ["file_number", "title", "department", "category", "location", "confidential", "opened_on", "retain_until", "notes"],
                ("opened_on", "retain_until"), "status", ["file_number", "title", "category"]),
    "inspections": (HealthInspection, "social/inspections", "Public health inspections", ("health.view", "health.manage"), ("health.manage",),
                    [("Ref.", "reference"), ("Date", "date"), ("Premises", "premises"), ("Type", "premises_type"), ("Ward", "ward"), ("Score", "score"),
                     ("Follow-up", "follow_up_date"), ("Result", "result")],
                    ["premises", "premises_type", "owner", "ward", "location", "date", "score", "result", "findings", "follow_up_date"],
                    ("date", "follow_up_date"), "result", ["reference", "premises", "owner", "location"]),
    "sanitation": (SanitationFacility, "social/sanitation", "Public ablutions & waste management (WASH)", ("sanitation.view", "sanitation.manage"),
                   ("sanitation.manage",),
                   [("Ref.", "reference"), ("Name", "name"), ("Type", "kind"), ("Ward", "ward"), ("Location", "location"),
                    ("Last serviced", "last_serviced"), ("Collection days", "collection_days"), ("Status", "status")],
                   ["name", "kind", "ward", "location", "status", "last_serviced", "collection_days", "caretaker", "notes"], ("last_serviced",), "status",
                   ["reference", "name", "location"]),
    "facilities": (SocialFacility, "social/facilities", "Schools & clinics development", ("facilities.view", "facilities.manage"), ("facilities.manage",),
                   [("Ref.", "reference"), ("Name", "name"), ("Type", "kind"), ("Ward", "ward"), ("Learners / population", "population_served"),
                    ("Classrooms / beds", "classrooms_or_beds"), ("Condition", "condition")],
                   ["name", "kind", "ward", "location", "responsible_authority", "population_served", "classrooms_or_beds", "condition", "needs",
                    "contact"], (), "condition", ["reference", "name", "location", "needs"]),
    # ---- Administration: land & assets, community liaison
    "land": (LandParcel, "admin/land", "Council land bank – land parcels", ("land.view", "land.manage"), ("land.manage",),
             [("Parcel", "parcel_number"), ("Name", "name"), ("Ward", "ward"), ("Location", "location"), ("Hectares", "hectares"), ("Use", "land_use"),
              ("Stands planned", "stands_planned"), ("Status", "status")],
             ["parcel_number", "name", "ward", "location", "hectares", "land_use", "status", "survey_diagram", "title_deed", "valuation",
              "stands_planned", "notes"], (), "status", ["parcel_number", "name", "location", "survey_diagram"]),
    "engagements": (Engagement, "admin/engagements", "Stakeholder engagement – WADCO, village assemblies & consultations",
                    ("engagements.view", "engagements.manage"), ("engagements.manage",),
                    [("Ref.", "reference"), ("Date", "date"), ("Meeting", "title"), ("Type", "kind"), ("Ward", "ward"), ("Venue", "venue"),
                     ("Attendance", "attendance"), ("Status", "status")],
                    ["title", "kind", "date", "ward", "venue", "attendance", "issues_raised", "resolutions", "status"], ("date",), "status",
                    ["reference", "title", "venue", "issues_raised"]),
    "notices": (PublicNotice, "admin/notices", "Public notices (shown in the residents' app)", ("notices.view", "notices.manage"), ("notices.manage",),
                [("From", "publish_from"), ("Title", "title"), ("Type", "category"), ("Ward", "ward"), ("Until", "expires_on"), ("Published", "is_published")],
                ["title", "category", "body", "ward", "publish_from", "expires_on", "is_published"], ("publish_from", "expires_on"), "category",
                ["title", "body"]),
    # ---- Internal audit
    "audits": (AuditEngagement, "audit/plan", "Internal audit plan – audit engagements", ("auditplan.view", "auditplan.manage"), ("auditplan.manage",),
               [("Ref.", "reference"), ("Quarter", "quarter"), ("Audit", "title"), ("Type", "audit_type"), ("Department", "department"),
                ("Auditor", "auditor"), ("Status", "status")],
               ["title", "audit_type", "department", "quarter", "auditor", "status", "scope", "conclusion"], (), "status", ["reference", "title", "scope"]),
}
FORMS = {k: _form(v[0], v[6], v[7]) for k, v in SPECS.items()}


def form_for(key):
    return FORMS[key]


def works_scope(user, qs):
    if user.has_cap("works.view") or user.sees_all_departments():
        return qs
    return qs.filter(assigned_to=user)


def records_scope(user, qs):
    """Registry staff see every file; others see their department's non-confidential files."""
    if user.has_cap("records.manage") or user.sees_all_departments():
        return qs
    return qs.filter(department=user.department, confidential=False)


SCOPES = {"works": works_scope, "records": records_scope}


# ------------------------------------------------------------- stage actions
@transaction.atomic
def work_action(user, wo, action, *, assigned_to=None, notes="", materials="", labour_days=None, cost=None):
    if action == "assign":
        if not user.has_cap("works.assign"):
            raise PermissionDenied("Only the District Engineer assigns work orders.")
        wo.assigned_to = get_user_model().objects.get(pk=assigned_to)
        wo.status = WorkOrder.Status.OPEN
        notify([wo.assigned_to], f"Work order {wo.reference}: {wo.title}", wo.location, f"/staff/technical/works/{wo.pk}/")
    elif action in ("start", "done"):
        if wo.assigned_to_id != user.pk and not user.has_cap("works.assign"):
            raise PermissionDenied("This job card is assigned to someone else.")
        if wo.status in (WorkOrder.Status.DONE, WorkOrder.Status.CLOSED):
            raise ValidationError("The work has already been reported as done.")
        wo.status = WorkOrder.Status.IN_PROGRESS if action == "start" else WorkOrder.Status.DONE
        if action == "done":
            wo.completion_notes, wo.materials, wo.completed_at = notes, materials or wo.materials, timezone.now()
            if labour_days not in (None, ""):
                wo.labour_days = labour_days
            if cost not in (None, ""):
                wo.cost = cost
            notify([u for u in get_user_model().objects.filter(is_active=True) if u.has_cap("works.assign")],
                   f"Work done – sign off {wo.reference}", wo.title, f"/staff/technical/works/{wo.pk}/")
    elif action in ("signoff", "reopen"):
        if not user.has_cap("works.assign"):
            raise PermissionDenied("Only the District Engineer signs off work.")
        if wo.status != WorkOrder.Status.DONE:
            raise ValidationError("Only finished work can be signed off.")
        if wo.assigned_to_id == user.pk:
            raise PermissionDenied("Someone else must sign off work you did yourself.")
        wo.status = WorkOrder.Status.CLOSED if action == "signoff" else WorkOrder.Status.IN_PROGRESS
        wo.signed_off_by = user if action == "signoff" else None
        if wo.light_id and action == "signoff":
            PublicLight.objects.filter(pk=wo.light_id).update(status=PublicLight.Status.WORKING, last_checked=timezone.localdate(), updated_at=timezone.now())
        if wo.road_id and action == "signoff" and wo.kind == WorkOrder.Kind.ROAD:
            Road.objects.filter(pk=wo.road_id).update(last_graded=timezone.localdate(), updated_at=timezone.now())
        notify([wo.assigned_to], f"Work order {wo.reference} {'signed off' if action == 'signoff' else 'sent back'}", notes)
    else:
        raise ValidationError("Unknown action.")
    wo.save()
    _record(wo, "Work order", action.upper(), user, notes)
    return wo


@transaction.atomic
def record_action(user, rf, action, *, borrower=None, due_back=None, notes=""):
    if not user.has_cap("records.manage"):
        raise PermissionDenied("Only the registry can move files.")
    if action == "lend":
        if rf.status != RecordFile.Status.IN_REGISTRY:
            raise ValidationError("The file is not in the registry.")
        b = get_user_model().objects.get(pk=borrower)
        if rf.confidential and not (b.is_head or b.department == rf.department):
            raise PermissionDenied("Confidential file: only its department or a head of department may borrow it.")
        rf.status, rf.borrowed_by, rf.borrowed_at = RecordFile.Status.ON_LOAN, b, timezone.now()
        rf.due_back = due_back or timezone.localdate() + timezone.timedelta(days=7)
        notify([b], f"File {rf.file_number} lent to you", f"Please return it by {rf.due_back}.")
    elif action == "return":
        if rf.status != RecordFile.Status.ON_LOAN:
            raise ValidationError("The file is not out on loan.")
        rf.status, rf.borrowed_by, rf.borrowed_at, rf.due_back = RecordFile.Status.IN_REGISTRY, None, None, None
    elif action == "archive":
        rf.status = RecordFile.Status.ARCHIVED
    elif action == "dispose":
        if rf.retain_until and rf.retain_until > timezone.localdate():
            raise ValidationError(f"The file must be kept until {rf.retain_until}.")
        rf.status = RecordFile.Status.DISPOSED
    else:
        raise ValidationError("Unknown action.")
    rf.save()
    _record(rf, "Registry", action.upper(), user, notes)
    return rf


# ---------------------------------------------------------------- web views
def _views(key):
    model, slug, title, view_caps, manage_caps, columns, fields, dates, filt, search = SPECS[key]
    scope_fn = SCOPES.get(key)

    class List(GenericListView):
        pass

    List.model, List.required_caps, List.title, List.columns, List.filter_field, List.search_fields = model, view_caps, title, columns, filt, search
    List.detail_url_name, List.create_url_name, List.create_caps = f"registers:{key}", f"registers:{key}_new", manage_caps
    if scope_fn:
        List.scope = lambda self, qs: scope_fn(self.request.user, qs)

    class New(GenericCreateView):
        pass

    New.model, New.form_class, New.required_caps, New.title, New.detail_url_name = model, FORMS[key], manage_caps, f"New – {title}", f"registers:{key}"
    if key == "inspections":
        New.prepare = lambda self, obj: setattr(obj, "inspector", self.request.user)
    if key == "engagements":
        New.prepare = lambda self, obj: setattr(obj, "officer", self.request.user)
    if key == "notices":
        New.prepare = lambda self, obj: setattr(obj, "posted_by", self.request.user)

    class Edit(GenericUpdateView):
        pass

    Edit.model, Edit.form_class, Edit.required_caps, Edit.detail_url_name = model, FORMS[key], manage_caps, f"registers:{key}"

    class Detail(ActionDetail):
        pass

    Detail.model, Detail.required_caps = model, view_caps + (("works.view",) if key == "works" else ())
    Detail.fields = [(model._meta.get_field(f).verbose_name.capitalize(), f) for f in fields] + (
        [("Completion notes", "completion_notes"), ("Materials", "materials"), ("Labour (days)", "labour_days"), ("Cost (USD)", "cost"),
         ("Signed off by", "signed_off_by")] if key == "works" else [("With", "borrowed_by"), ("Due back", "due_back")] if key == "records"
        else [("Inspector", "inspector")] if key == "inspections" else [("Officer", "officer")] if key == "engagements"
        else [("Posted by", "posted_by")] if key == "notices" else [])
    Detail.edit_url_name, Detail.edit_caps = f"registers:{key}_edit", manage_caps
    if scope_fn:
        Detail.scope = lambda self, qs: scope_fn(self.request.user, qs)
    if key in ("works", "records"):
        Detail.action_url_name = f"registers:{key}_action"
        Detail.actions = _works_actions if key == "works" else _record_actions
    return slug, List, New, Edit, Detail


def _staff_choices(dept=None):
    User = get_user_model()
    qs = User.objects.filter(user_type=User.UserType.STAFF, is_active=True)
    if dept:
        qs = qs.filter(department=dept)
    return [(str(u.pk), u.get_full_name() or u.username) for u in qs.order_by("first_name")]


def _works_actions(self, obj):
    u, acts = self.request.user, []
    if obj.status in ("OPEN", "IN_PROGRESS") and u.has_cap("works.assign"):
        acts.append({"title": "Assign", "fields": [("assigned_to", "Give the job to", "select", _staff_choices("TECH"))], "buttons": [("assign", "Assign", "primary")]})
    if obj.status in ("OPEN", "IN_PROGRESS") and (obj.assigned_to_id == u.pk or u.has_cap("works.assign")):
        acts.append({"title": "Report progress", "fields": [("notes", "What was done", "textarea", None), ("materials", "Materials used", "text", None),
                                                           ("labour_days", "Labour (days)", "number", None), ("cost", "Cost (USD)", "number", None)],
                     "buttons": [("start", "Started", "secondary"), ("done", "Work done", "success")]})
    if obj.status == "DONE" and u.has_cap("works.assign") and obj.assigned_to_id != u.pk:
        acts.append({"title": "Sign off (District Engineer)", "fields": [("notes", "Comment", "textarea", None)],
                     "buttons": [("signoff", "Sign off", "success"), ("reopen", "Send back", "outline-danger")]})
    return acts


def _record_actions(self, obj):
    if not self.request.user.has_cap("records.manage"):
        return []
    if obj.status == "IN":
        return [{"title": "Lend the file", "fields": [("borrower", "To", "select", _staff_choices()), ("due_back", "Due back", "date", None)],
                 "buttons": [("lend", "Lend", "primary"), ("archive", "Archive", "secondary"), ("dispose", "Dispose", "outline-danger")]}]
    if obj.status == "LOAN":
        return [{"title": "File returned?", "fields": [], "buttons": [("return", "Returned to registry", "success")]}]
    return []


VIEWS = {k: _views(k) for k in SPECS}


@cap_required("works.manage", "works.view", "works.assign")
@require_POST
def works_action(request, pk):
    wo = get_object_or_404(WorkOrder, pk=pk)
    run_action(request, work_action, request.user, wo, request.POST.get("action"), assigned_to=request.POST.get("assigned_to"),
               notes=request.POST.get("notes", ""), materials=request.POST.get("materials", ""), labour_days=request.POST.get("labour_days") or None,
               cost=request.POST.get("cost") or None, success="Work order updated.")
    return redirect("registers:works", pk=pk)


@cap_required("records.manage")
@require_POST
def records_action(request, pk):
    rf = get_object_or_404(RecordFile, pk=pk)
    run_action(request, record_action, request.user, rf, request.POST.get("action"), borrower=request.POST.get("borrower"),
               due_back=request.POST.get("due_back") or None, success="Registry updated.")
    return redirect("registers:records", pk=pk)


app_name = "registers"
urlpatterns = []
for _k, (_slug, _L, _N, _E, _D) in VIEWS.items():
    urlpatterns += [path(f"{_slug}/", _L.as_view(), name=f"{_k}_list"), path(f"{_slug}/new/", _N.as_view(), name=f"{_k}_new"),
                    path(f"{_slug}/<uuid:pk>/", _D.as_view(), name=_k), path(f"{_slug}/<uuid:pk>/edit/", _E.as_view(), name=f"{_k}_edit")]
from .data import data_hub  # noqa: E402

urlpatterns += [path("admin/data/", data_hub, name="data_hub"),
                path("technical/works/<uuid:pk>/action/", works_action, name="works_action"),
                path("admin/records/<uuid:pk>/action/", records_action, name="records_action")]
