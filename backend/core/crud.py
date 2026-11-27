"""Small generic list / form / detail framework shared by all departments so
each register is a few lines of configuration."""
from datetime import date, datetime
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.decorators import CapRequiredMixin

from . import audit
from .models import AuditLog, IdempotencyKey

BADGES = {
    "success": {"VALID", "PAID", "ISSUED", "APPROVED", "AUTHORISED", "VERIFIED", "RESOLVED", "CLOSED", "COMPLETED", "DONE",
                "ALLOCATED", "ACTIVE", "ORDERED", "DELIVERED", "RESPONDED", "INSPECTED", "FILED"},
    "danger": {"VOIDED", "REJECTED", "FAILED", "CANCELLED", "BLACKLISTED", "EXPIRED", "QUERIED", "URGENT", "CRITICAL", "SUSPENDED"},
    "warning": {"VOID_REQ", "PART", "PENDING", "INSPECTION", "SUBMITTED", "HOD_OK", "FIN_OK", "CHECKED", "PREPARED", "HIGH",
                "IN_PROGRESS", "ASSIGNED", "ACK", "OPEN", "SHORTLISTED", "UNPAID", "PROCUREMENT", "ONGOING", "IMPLEMENTING",
                "P_HOD", "P_ADMIN", "P_TREAS", "P_CEO", "P_PAY", "PAYING", "RETURNED", "SENT"},
}


def badge_class(value):
    for cls, values in BADGES.items():
        if value in values:
            return cls
    return "secondary"


def fmt(value):
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Decimal):
        return f"{value:,.2f}"
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime("%d %b %Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    return str(value)


def resolve(obj, accessor):
    """``"account.name"`` / ``"status"`` (uses get_status_display) / callable."""
    if callable(accessor):
        return accessor(obj)
    value = obj
    parts = accessor.split(".")
    for i, part in enumerate(parts):
        if value is None:
            return None
        display = getattr(value, f"get_{part}_display", None)
        if i == len(parts) - 1 and display is not None:
            return display()
        value = getattr(value, part, None)
        if callable(value) and not hasattr(value, "all"):
            value = value()
    return value


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, (forms.CheckboxInput,)):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs.setdefault("class", "form-select")
            else:
                w.attrs.setdefault("class", "form-control")
            if isinstance(w, forms.DateInput):
                w.input_type = "date"
                w.format = "%Y-%m-%d"      # browsers' date pickers only accept ISO dates when editing
            if isinstance(w, forms.Textarea):
                w.attrs.setdefault("rows", 3)


class BaseModelForm(BootstrapFormMixin, forms.ModelForm):
    pass


def date_widgets(*names):
    return {n: forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d") for n in names}


class GenericListView(CapRequiredMixin, ListView):
    template_name = "generic/list.html"
    paginate_by = 25
    title = ""
    columns = []  # [(label, accessor)]
    search_fields = []
    filter_field = "status"
    create_url_name = None
    create_caps = ()
    detail_url_name = None
    extra_buttons = []  # [(label, url_name, caps)]

    def scope(self, qs):
        return qs

    def base_queryset(self):
        qs = self.model.objects.all()
        if hasattr(qs, "alive"):
            qs = qs.alive()
        return qs

    def get_queryset(self):
        qs = self.scope(self.base_queryset())
        q = self.request.GET.get("q", "").strip()
        if q and self.search_fields:
            cond = Q()
            for f in self.search_fields:
                cond |= Q(**{f"{f}__icontains": q})
            qs = qs.filter(cond)
        fval = self.request.GET.get(self.filter_field or "", "")
        if self.filter_field and fval:
            qs = qs.filter(**{self.filter_field: fval})
        return qs

    def filter_choices(self):
        if not self.filter_field:
            return []
        try:
            return self.model._meta.get_field(self.filter_field).choices or []
        except Exception:
            return []

    def row_url(self, obj):
        return reverse(self.detail_url_name, args=[obj.pk]) if self.detail_url_name else None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rows = []
        for obj in ctx["object_list"]:
            cells = []
            for label, accessor in self.columns:
                raw = obj
                key = accessor if isinstance(accessor, str) else ""
                if key.endswith("status") or key in ("priority", "risk_rating"):
                    raw_val = getattr(obj, key.split(".")[-1], "")
                    text = fmt(resolve(obj, accessor))
                    cells.append({"text": text, "badge": "warning" if str(text).startswith("Awaiting") else badge_class(raw_val)})
                else:
                    val = resolve(raw, accessor)
                    cells.append({"text": fmt(val), "num": isinstance(val, Decimal)})
            rows.append({"cells": cells, "url": self.row_url(obj), "obj": obj})
        user = self.request.user
        ctx.update(
            title=self.title or self.model._meta.verbose_name_plural.title(),
            headers=[c[0] for c in self.columns],
            rows=rows,
            filter_field=self.filter_field,
            filter_choices=self.filter_choices(),
            current_filter=self.request.GET.get(self.filter_field or "", ""),
            q=self.request.GET.get("q", ""),
            searchable=bool(self.search_fields),
            create_url=reverse(self.create_url_name) if self.create_url_name and (not self.create_caps or user.has_cap(*self.create_caps)) else None,
            extra_buttons=[(lbl, reverse(n)) for lbl, n, caps in self.extra_buttons if not caps or user.has_cap(*caps)],
        )
        return ctx


class IdempotentFormMixin:
    """Supports offline-queued web forms: a replayed submission carrying an
    already-used ``idempotency_key`` is not saved twice."""

    def post(self, request, *args, **kwargs):
        key = request.POST.get("idempotency_key", "")
        if key:
            seen = IdempotencyKey.objects.filter(key=key).first()
            if seen:
                messages.info(request, "This form was already submitted.")
                return redirect(seen.redirect_to or "core:dashboard")
        response = super().post(request, *args, **kwargs)
        if key and response.status_code in (301, 302):
            IdempotencyKey.objects.get_or_create(key=key, defaults={"user": request.user, "redirect_to": response.url})
        return response


class GenericCreateView(IdempotentFormMixin, CapRequiredMixin, CreateView):
    template_name = "generic/form.html"
    title = ""
    detail_url_name = None
    success_message = "Saved successfully."
    offline_capable = False

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = self.title or f"New {self.model._meta.verbose_name}"
        ctx["offline_capable"] = self.offline_capable
        return ctx

    def prepare(self, obj):
        """Hook to set extra attributes before saving."""

    def form_valid(self, form):
        obj = form.save(commit=False)
        if hasattr(obj, "created_by_id") and not obj.created_by_id:
            obj.created_by = self.request.user
        self.prepare(obj)
        try:
            obj.save()
            form.save_m2m()
        except (ValidationError, ValueError) as exc:
            form.add_error(None, exc.messages if hasattr(exc, "messages") else str(exc))
            return self.form_invalid(form)
        self.object = obj
        self.after_save(obj)
        messages.success(self.request, self.success_message)
        return redirect(self.get_success_url())

    def after_save(self, obj):
        pass

    def get_success_url(self):
        if self.detail_url_name:
            return reverse(self.detail_url_name, args=[self.object.pk])
        return super().get_success_url()


class GenericUpdateView(CapRequiredMixin, UpdateView):
    template_name = "generic/form.html"
    title = ""
    detail_url_name = None

    def get_queryset(self):
        qs = self.model.objects.all()
        return qs.alive() if hasattr(qs, "alive") else qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = self.title or f"Edit {self.object}"
        return ctx

    def form_valid(self, form):
        resp = super().form_valid(form)
        messages.success(self.request, "Changes saved.")
        return resp

    def get_success_url(self):
        if self.detail_url_name:
            return reverse(self.detail_url_name, args=[self.object.pk])
        return super().get_success_url()


class GenericDetailView(CapRequiredMixin, DetailView):
    template_name = "generic/detail.html"
    fields = []  # [(label, accessor)]
    edit_url_name = None
    edit_caps = ()

    def get_queryset(self):
        qs = self.model.objects.all()
        if hasattr(qs, "alive"):
            qs = qs.alive()
        return self.scope(qs)

    def scope(self, qs):
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["title"] = str(obj)
        ctx["field_rows"] = [(label, fmt(resolve(obj, acc))) for label, acc in self.fields]
        status = getattr(obj, "status", None)
        if status:
            ctx["status_text"] = obj.get_status_display()
            ctx["status_badge"] = "warning" if ctx["status_text"].startswith("Awaiting") else badge_class(status)
        if self.edit_url_name and (not self.edit_caps or self.request.user.has_cap(*self.edit_caps)):
            ctx["edit_url"] = reverse(self.edit_url_name, args=[obj.pk])
        from finance.models import ApprovalRecord

        ctx["approvals"] = ApprovalRecord.for_object(obj)
        if self.request.user.has_cap("audit.view_trail"):
            ctx["history"] = AuditLog.objects.filter(model=obj._meta.label, object_id=str(obj.pk)).order_by("-timestamp")[:50]
        return ctx


def run_action(request, func, *args, success="Done.", **kwargs):
    """Run a service-layer action and convert rule violations to messages."""
    try:
        result = func(request.user, *args, **kwargs)
        messages.success(request, success)
        return result
    except PermissionDenied as exc:
        messages.error(request, str(exc) or "Permission denied.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except ValueError as exc:
        messages.error(request, str(exc))
    return None


class SafeCsvWriter:
    """csv.writer that neutralises cells a spreadsheet would run as a formula
    (a shop called "=HYPERLINK(...)" must not execute when the export is opened in Excel)."""

    def __init__(self, f):
        import csv

        self.w = csv.writer(f)

    @staticmethod
    def clean(v):
        if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + v
        return v

    def writerow(self, row):
        return self.w.writerow([self.clean(v) for v in row])

    def writerows(self, rows):
        for r in rows:
            self.writerow(r)


def log_export(request, what):
    audit.log(AuditLog.Action.EXPORT, message=f"Exported {what}", request=request)


def idempotent(view):
    """Function-view version of IdempotentFormMixin for offline-capable forms."""
    from functools import wraps

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        key = request.POST.get("idempotency_key", "") if request.method == "POST" else ""
        if key:
            seen = IdempotencyKey.objects.filter(key=key).first()
            if seen:
                messages.info(request, "This form was already submitted.")
                return redirect(seen.redirect_to or "/")
        response = view(request, *args, **kwargs)
        if key and response.status_code in (301, 302):
            IdempotencyKey.objects.get_or_create(key=key, defaults={"user": request.user if request.user.is_authenticated else None,
                                                                    "redirect_to": response.url})
        return response

    return wrapper
