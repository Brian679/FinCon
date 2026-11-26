from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core import audit
from core.models import AuditLog
from finance.services import notify

from .models import Complaint, ServiceRequest, Task, TaskComment

User = get_user_model()


from .funds import funds_scope  # noqa: E402,F401  (re-exported for the sync API)
from .memos import memo_scope  # noqa: E402,F401


def can_assign_to(user, target_department):
    # Heads may also send a task to ANOTHER department - it goes to that
    # department's head, who passes it on (see create_task).
    return user.has_cap("tasks.assign_any", "tasks.assign_department")


@transaction.atomic
def create_task(user, **data):
    assignee = data.get("assigned_to")
    department = data.get("department") or (assignee.department if assignee else user.department)
    if not can_assign_to(user, department):
        raise PermissionDenied("Only heads of department can assign tasks.")
    if assignee and assignee.department != department:
        raise PermissionDenied("The assignee is not in that department.")
    if (department != user.department and not user.has_cap("tasks.assign_any") and assignee is not None and not assignee.is_head):
        raise PermissionDenied("A task for another department goes to its Head of Department - leave 'Assigned to' blank.")
    data["department"] = department
    task = Task.objects.create(assigned_by=user, created_by=user, **data)
    targets = [assignee] if assignee else [u for u in User.objects.filter(department=department, is_active=True) if u.is_head]
    notify(targets, f"New {task.get_kind_display().lower()} from {user.get_full_name() or user.username}: {task.title}", task.description[:200],
           f"/staff/tasks/{task.pk}/")
    return task


def can_view_task(user, task):
    return (user.has_cap("tasks.assign_any") or task.assigned_to_id == user.pk or task.assigned_by_id == user.pk
            or (user.is_head and task.department == user.department))


@transaction.atomic
def update_task(user, task, *, status=None, progress=None, comment=""):
    if not can_view_task(user, task):
        raise PermissionDenied("This task is not assigned to you.")
    if status:
        if status == Task.Status.CLOSED and task.assigned_by_id != user.pk and not user.has_cap("tasks.assign_any"):
            raise PermissionDenied("Only the person who assigned the task can close it.")
        task.status = status
        if status == Task.Status.DONE:
            task.completed_at = timezone.now()
            task.progress = 100
            notify([task.assigned_by], f"Task completed: {task.title}", comment, f"/staff/tasks/{task.pk}/")
            for memo in task.memos.all():
                notify([memo.sender], f"{memo.reference} done: {memo.subject}", comment, f"/staff/memos/{memo.pk}/")
    if progress is not None:
        task.progress = max(0, min(100, int(progress)))
        if task.status == Task.Status.OPEN and task.progress > 0:
            task.status = Task.Status.IN_PROGRESS
    task.save()
    if comment:
        TaskComment.objects.create(task=task, author=user, body=comment, created_by=user)
        others = {task.assigned_by, task.assigned_to} - {user}
        notify(others, f"Comment on {task.reference}: {task.title}", comment[:200], f"/staff/tasks/{task.pk}/")
    return task


def complaint_scope(user, qs):
    if user.is_client:
        return qs.filter(client=user)
    if user.has_cap("complaints.view_all") or user.sees_all_departments():
        return qs
    return qs.filter(department=user.department)


@transaction.atomic
def log_complaint(user, **data):
    if user is not None and user.is_authenticated and user.is_client:
        data.setdefault("client", user)
        data.setdefault("name", user.get_full_name())
        data.setdefault("phone", user.phone)
        data.setdefault("email", user.email)
    c = Complaint(created_by=user if user and user.is_authenticated else None, **data)
    c.save()
    heads = [u for u in User.objects.filter(department=c.department, is_active=True) if u.is_head]
    notify(heads, f"New {c.get_kind_display().lower()} {c.reference}: {c.subject}", "Acknowledge within 48 hours (Client Charter).",
           f"/staff/complaints/{c.pk}/")
    return c


@transaction.atomic
def act_on_complaint(user, c, action, *, note="", assignee=None, department=None):
    if not complaint_scope(user, Complaint.objects.filter(pk=c.pk)).exists() or user.is_client:
        raise PermissionDenied("This complaint is not in your department.")
    now = timezone.now()
    if action == "acknowledge":
        if c.acknowledged_at:
            raise ValidationError("Already acknowledged.")
        c.acknowledged_at = now
        c.status = Complaint.Status.ACKNOWLEDGED
        notify([c.client], f"We received your {c.get_kind_display().lower()} {c.reference}", note or "It is being attended to.")
    elif action == "assign":
        if assignee is None:
            raise ValidationError("Choose an officer.")
        c.assigned_to = assignee
        c.status = Complaint.Status.IN_PROGRESS
        c.acknowledged_at = c.acknowledged_at or now
        notify([assignee], f"Complaint assigned to you: {c.reference}", c.subject, f"/staff/complaints/{c.pk}/")
    elif action == "transfer":
        if not department:
            raise ValidationError("Choose a department.")
        c.department = department
        heads = [u for u in User.objects.filter(department=department, is_active=True) if u.is_head]
        notify(heads, f"Complaint transferred to your department: {c.reference}", c.subject, f"/staff/complaints/{c.pk}/")
    elif action == "resolve":
        if not note:
            raise ValidationError("Describe the resolution.")
        c.resolution = note
        c.resolved_at = now
        c.status = Complaint.Status.RESOLVED
        c.acknowledged_at = c.acknowledged_at or now
        notify([c.client], f"Resolved: {c.reference}", note)
    elif action == "close":
        c.status = Complaint.Status.CLOSED
    else:
        raise ValidationError("Unknown action.")
    c.save()
    audit.log(AuditLog.Action.UPDATE, c, user=user, message=f"Complaint {action}: {note}".strip())
    return c


def request_scope(user, qs):
    if user.is_client:
        return qs.filter(reporter=user)
    if user.has_cap("requests.view_all") or user.sees_all_departments():
        return qs
    return qs.filter(department=user.department)


@transaction.atomic
def report_service_request(user, **data):
    if user is not None and user.is_authenticated and user.is_client:
        data.setdefault("reporter", user)
        data.setdefault("reporter_name", user.get_full_name())
        data.setdefault("reporter_phone", user.phone)
    sr = ServiceRequest(created_by=user if user and user.is_authenticated else None, **data)
    sr.save()
    heads = [u for u in User.objects.filter(department=sr.department, is_active=True) if u.is_head]
    notify(heads, f"New service request {sr.reference}: {sr.get_category_display()}", f"{sr.location}. Due {timezone.localtime(sr.due_at):%d %b %H:%M}" if sr.due_at else sr.location,
           f"/staff/requests/{sr.pk}/")
    return sr


@transaction.atomic
def act_on_request(user, sr, action, *, note="", assignee=None):
    if user.is_client or not request_scope(user, ServiceRequest.objects.filter(pk=sr.pk)).exists():
        raise PermissionDenied("This request is not in your department.")
    if action == "assign":
        if assignee is None:
            raise ValidationError("Choose an officer.")
        sr.assigned_to = assignee
        sr.status = ServiceRequest.Status.ASSIGNED
        notify([assignee], f"Service request assigned: {sr.reference}", f"{sr.get_category_display()} at {sr.location}", f"/staff/requests/{sr.pk}/")
    elif action == "start":
        sr.status = ServiceRequest.Status.IN_PROGRESS
    elif action == "resolve":
        sr.status = ServiceRequest.Status.RESOLVED
        sr.resolution = note
        sr.resolved_at = timezone.now()
        notify([sr.reporter], f"Your report {sr.reference} has been resolved", note)
    elif action == "reject":
        sr.status = ServiceRequest.Status.REJECTED
        sr.resolution = note
        notify([sr.reporter], f"Update on {sr.reference}", note)
    elif action == "close":
        sr.status = ServiceRequest.Status.CLOSED
    else:
        raise ValidationError("Unknown action.")
    sr.save()
    audit.log(AuditLog.Action.UPDATE, sr, user=user, message=f"Service request {action}: {note}".strip())
    return sr
