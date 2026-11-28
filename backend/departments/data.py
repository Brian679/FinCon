"""Data & Information Management (ICT services): council-wide statistics and data-quality checks.

The Data Officer sees how much is in every register and the records that need fixing (missing phone
numbers, duplicate ID numbers, stands without a ward, staff without employee numbers …) and can
download each list as CSV to correct it with the department concerned."""
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import cap_required
from core.crud import SafeCsvWriter, log_export


def _registers():
    from departments import models as dm
    from finance import models as fm
    from social import models as sm
    from workflow import models as wm

    User = get_user_model()
    return [
        ("Finance", [("Client accounts", fm.ClientAccount), ("Stands / shops / farms", fm.Property), ("Bills", fm.Bill), ("Receipts", fm.Receipt),
                     ("Licences", fm.Licence), ("Fines", fm.Fine)]),
        ("Administration", [("Staff", User.objects.filter(user_type="STAFF")), ("Registry files", dm.RecordFile), ("Land parcels", dm.LandParcel),
                            ("Assets", dm.Asset), ("Stakeholder meetings", dm.Engagement), ("Public notices", dm.PublicNotice)]),
        ("Social Services", [("Farms", sm.Farm), ("Wildlife records", sm.WildlifeRecord), ("Resource permits", sm.ResourcePermit),
                             ("Water points", sm.WaterPoint), ("Health inspections", sm.HealthInspection)]),
        ("Technical Services", [("Roads", dm.Road), ("Public lights", dm.PublicLight), ("Work orders", dm.WorkOrder), ("Projects", dm.Project)]),
        ("Growth Points", [("Stand applications", dm.StandApplication)]),
        ("Customer care", [("Complaints", wm.Complaint), ("Service requests / faults", wm.ServiceRequest)]),
    ]


def _count(src):
    qs = src if hasattr(src, "model") and not isinstance(src, type) else src.objects.all()
    return qs.filter(is_deleted=False).count() if hasattr(qs.model, "is_deleted") else qs.count()


def quality_checks():
    """[(key, title, department, queryset, columns)] – records that need fixing."""
    from finance.models import ClientAccount, Property

    User = get_user_model()
    accounts = ClientAccount.objects.alive()
    dup_ids = accounts.exclude(id_number="").values("id_number").annotate(n=Count("id")).filter(n__gt=1).values("id_number")
    return [
        ("no-phone", "Client accounts with no phone number (no SMS reminders / receipts)", "Finance",
         accounts.filter(Q(phone="") | Q(phone__isnull=True)), [("Account", "account_number"), ("Name", "name"), ("Ward", "ward")]),
        ("dup-id", "Client accounts sharing an ID number (possible duplicates)", "Finance",
         accounts.filter(id_number__in=dup_ids).order_by("id_number"), [("ID number", "id_number"), ("Account", "account_number"), ("Name", "name")]),
        ("no-ward", "Stands / shops / farms without a ward", "Finance",
         Property.objects.alive().filter(ward__isnull=True), [("Stand", "stand_number"), ("Location", "location"), ("Owner", "account.name")]),
        ("no-area", "Business stands not linked to a growth point / trading area", "Growth Points",
         Property.objects.alive().exclude(business_name="").filter(area__isnull=True), [("Stand", "stand_number"), ("Business", "business_name"),
                                                                                         ("Location", "location")]),
        ("no-empno", "Staff without an employee number", "Administration",
         User.objects.filter(user_type="STAFF", is_active=True).filter(Q(employee_number="") | Q(employee_number__isnull=True)),
         [("Username", "username"), ("Name", "get_full_name"), ("Department", "department")]),
        ("no-staff-phone", "Staff without a phone number", "Administration",
         User.objects.filter(user_type="STAFF", is_active=True, phone=""), [("Username", "username"), ("Name", "get_full_name"), ("Department", "department")]),
    ]


def overview():
    return {
        "registers": [(dept, [(label, _count(src)) for label, src in items]) for dept, items in _registers()],
        "checks": [(key, title, dept, qs.count()) for key, title, dept, qs, _cols in quality_checks()],
        "generated": timezone.now(),
    }


def _val(obj, accessor):
    v = obj
    for part in accessor.split("."):
        v = getattr(v, part, "") if v is not None else ""
    return v() if callable(v) else v


@cap_required("data.view", "data.manage")
def data_hub(request):
    key = request.GET.get("export")
    if key:
        for k, title, _dept, qs, cols in quality_checks():
            if k == key:
                resp = HttpResponse(content_type="text/csv")
                resp["Content-Disposition"] = f'attachment; filename="data-quality-{k}.csv"'
                w = SafeCsvWriter(resp)
                w.writerow([c for c, _ in cols])
                for obj in qs[:5000]:
                    w.writerow([_val(obj, a) for _, a in cols])
                log_export(request, f"Data quality: {title}")
                return resp
    ctx = overview()
    show = request.GET.get("show")
    if show:
        for k, title, _dept, qs, cols in quality_checks():
            if k == show:
                ctx["detail"] = {"title": title, "cols": [c for c, _ in cols], "rows": [[_val(o, a) for _, a in cols] for o in qs[:200]], "key": k}
    return render(request, "departments/data_hub.html", {"title": "Data & information management", **ctx})
