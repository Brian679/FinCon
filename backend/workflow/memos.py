"""Memos between departments: a message, a request for action or an item for
information. The receiving head of department can turn a request for action
into a task for one of their officers; the sender sees the progress."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core import audit
from core.models import AuditLog, Department, Notification

from .models import Memo, MemoReply, Task

User = get_user_model()


def heads_of(department):
    return [u for u in User.objects.filter(is_active=True, user_type=User.UserType.STAFF, department=department) if u.is_head]


def recipients(memo):
    return [memo.to_user] if memo.to_user_id else heads_of(memo.to_department)


def _note(users, title, body, memo):
    for u in {u for u in users if u is not None}:
        Notification.objects.create(recipient=u, title=title, body=body[:300], link=f"/staff/memos/{memo.pk}/")


def memo_scope(user, qs):
    if user.is_client:
        return qs.none()
    if user.sees_all_departments():
        return qs
    cond = Q(sender=user) | Q(to_user=user)
    if user.is_head:
        cond |= Q(to_department=user.department) | Q(from_department=user.department)
    else:
        cond |= Q(task__assigned_to=user)
    return qs.filter(cond)


def is_participant(user, memo):
    return memo_scope(user, Memo.objects.filter(pk=memo.pk)).exists()


def is_recipient(user, memo):
    if memo.to_user_id:
        return memo.to_user_id == user.pk or (user.is_head and user.department == memo.to_department)
    return user.is_head and user.department == memo.to_department


@transaction.atomic
def send(user, *, kind, to_department, subject, body, to_user=None, priority="NORMAL", memo_id=None):
    if user.is_client:
        raise PermissionDenied("Clients cannot send internal memos.")
    if to_department not in Department.values:
        raise ValidationError("Choose the department to send to.")
    if to_user is not None and (to_user.department != to_department or not to_user.is_active):
        raise ValidationError("That officer is not in the department you chose.")
    if not subject.strip() or not body.strip():
        raise ValidationError("Write a subject and a message.")
    extra = {"id": memo_id} if memo_id else {}
    memo = Memo.objects.create(sender=user, created_by=user, kind=kind, to_department=to_department, to_user=to_user, subject=subject.strip(),
                               body=body.strip(), priority=priority, **extra)
    _note(recipients(memo), f"{memo.get_kind_display()} from {memo.get_from_department_display()}: {memo.subject}",
          f"{user.get_full_name() or user.username}: {memo.body}", memo)
    return memo


def mark_read(user, memo):
    if memo.status == Memo.Status.SENT and is_recipient(user, memo):
        memo.status = Memo.Status.READ
        memo.read_at = timezone.now()
        memo.save(update_fields=["status", "read_at", "updated_at"])


@transaction.atomic
def reply(user, memo, body, *, close=False):
    if not is_participant(user, memo):
        raise PermissionDenied("You are not part of this memo.")
    if not body.strip() and not close:
        raise ValidationError("Write a reply.")
    if body.strip():
        MemoReply.objects.create(memo=memo, author=user, body=body.strip(), created_by=user)
    if close:
        if not (memo.sender_id == user.pk or is_recipient(user, memo)):
            raise PermissionDenied("Only the sender or the receiving department can close the memo.")
        memo.status = Memo.Status.CLOSED
    elif is_recipient(user, memo) and memo.status in (Memo.Status.SENT, Memo.Status.READ):
        memo.status = Memo.Status.IN_PROGRESS
    memo.save()
    others = [memo.sender] + recipients(memo)
    _note([u for u in others if u.pk != user.pk], f"Reply on {memo.reference}: {memo.subject}" + (" (closed)" if close else ""),
          f"{user.get_full_name() or user.username}: {body}", memo)
    return memo


@transaction.atomic
def to_task(user, memo, *, assigned_to, due_date=None, priority=None):
    """Receiving head turns a request for action into a task for an officer."""
    if not (user.is_head and user.department == memo.to_department):
        raise PermissionDenied("Only the head of the receiving department can assign this memo.")
    if memo.task_id:
        raise ValidationError(f"Already assigned as task {memo.task.reference}.")
    if assigned_to.department != memo.to_department:
        raise ValidationError("Assign it to an officer in your department.")
    task = Task.objects.create(kind=Task.Kind.REQUEST, title=memo.subject, description=f"From {memo.reference} "
                               f"({memo.get_from_department_display()}, {memo.sender.get_full_name()}):\n{memo.body}",
                               assigned_by=user, assigned_to=assigned_to, department=memo.to_department, priority=priority or memo.priority,
                               due_date=due_date, created_by=user)
    memo.task = task
    memo.status = Memo.Status.IN_PROGRESS
    memo.save()
    audit.log(AuditLog.Action.UPDATE, memo, user=user, message=f"Assigned as task {task.reference} to {assigned_to}")
    Notification.objects.create(recipient=assigned_to, title=f"New task from {memo.reference}: {task.title}", body=memo.body[:300],
                                link=f"/staff/tasks/{task.pk}/")
    _note([memo.sender], f"{memo.reference} assigned to {assigned_to.get_full_name()}",
          f"Your {memo.get_kind_display().lower()} is now task {task.reference}.", memo)
    return task
