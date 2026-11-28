from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core import audit
from core.models import AuditLog, Department
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
    for letter in task.letters.filter(is_deleted=False):
        letter.save(update_fields=["updated_at"])        # the letter shows the task's new status on the next sync
    if comment:
        TaskComment.objects.create(task=task, author=user, body=comment, created_by=user)
        others = {task.assigned_by, task.assigned_to} - {user}
        notify(others, f"Comment on {task.reference}: {task.title}", comment[:200], f"/staff/tasks/{task.pk}/")
    return task


def complaint_scope(user, qs):
    """Complaints are confidential: the front desk / customer care and the CEO see all of them,
    a head of department sees those about their department, and an officer only those assigned to them."""
    if user.is_client:
        return qs.filter(client=user)
    if user.has_cap("complaints.view_all") or user.sees_all_departments():
        return qs
    if user.has_cap("complaints.department"):
        from django.db.models import Q

        return qs.filter(Q(department=user.department) | Q(assigned_to=user))
    return qs.filter(assigned_to=user)


def complaint_handlers(department=None):
    """Who is told about a new complaint: customer care plus the head of the department concerned."""
    people = [u for u in User.objects.filter(is_active=True, user_type=User.UserType.STAFF) if u.has_cap("complaints.manage")]
    if department:
        people += [u for u in User.objects.filter(department=department, is_active=True) if u.is_head]
    return people


@transaction.atomic
def log_complaint(user, **data):
    if user is not None and user.is_authenticated and user.is_client:
        data.setdefault("client", user)
        data.setdefault("name", user.get_full_name())
        data.setdefault("phone", user.phone)
        data.setdefault("email", user.email)
    c = Complaint(created_by=user if user and user.is_authenticated else None, **data)
    c.save()
    notify(complaint_handlers(c.department), f"New {c.get_kind_display().lower()} {c.reference}: {c.subject}",
           "Acknowledge within 48 hours (Client Charter).", f"/staff/complaints/{c.pk}/")
    return c


@transaction.atomic
def act_on_complaint(user, c, action, *, note="", assignee=None, department=None):
    if not complaint_scope(user, Complaint.objects.filter(pk=c.pk)).exists() or user.is_client:
        raise PermissionDenied("This complaint has not been given to you.")
    if action in ("assign", "transfer") and not (user.has_cap("complaints.manage", "complaints.department") or user.sees_all_departments()):
        raise PermissionDenied("Only customer care or the head of department can assign or transfer a complaint.")
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



# ------------------------------------------------------------ correspondence
def _can_correspond(user, department=None):
    return user.has_cap("correspondence.manage") or (user.is_head and (department is None or department == user.department))


@transaction.atomic
def log_correspondence(user, *, sender, subject, department, sender_contact="", assigned_to=None, file_reference="", corr_id=None,
                       addressed_to=None, routing_note="", date_received=None):
    from .models import Correspondence

    if not _can_correspond(user, department):
        raise PermissionDenied("Only the registry or the head of the department can record correspondence.")
    extra = {"id": corr_id} if corr_id else {}
    if date_received:
        extra["date_received"] = date_received
    c = Correspondence.objects.create(sender=sender, sender_contact=sender_contact, subject=subject, department=department, assigned_to=assigned_to,
                                      file_reference=file_reference, status=Correspondence.Status.ASSIGNED if assigned_to else Correspondence.Status.RECEIVED,
                                      addressed_to=addressed_to, routing_note=routing_note, created_by=user, **extra)
    targets = [addressed_to] if addressed_to else [assigned_to] if assigned_to else [u for u in User.objects.filter(department=department, is_active=True) if u.is_head]
    notify(targets, f"Letter {c.reference} from {sender}: {subject}", (f"Received by {user.get_full_name()}. " + (routing_note + " " if routing_note else "") +
           (f"Reply due {timezone.localtime(c.response_due):%d %b %Y}" if c.response_due else "")).strip(), f"/staff/correspondence/{c.pk}/view/")
    return c


@transaction.atomic
def update_correspondence(user, c, *, status="", response_summary=""):
    from .models import Correspondence

    if not (_can_correspond(user, c.department) or c.assigned_to_id == user.pk):
        raise PermissionDenied("This letter is not assigned to you.")
    if status:
        if status not in Correspondence.Status.values:
            raise ValidationError("Unknown status.")
        c.status = status
        if status == Correspondence.Status.RESPONDED and not c.responded_at:
            c.responded_at = timezone.now()
    if response_summary:
        c.response_summary = response_summary
    c.save()
    audit.log(AuditLog.Action.UPDATE, c, user=user, message=f"Correspondence {c.reference}: {c.get_status_display()}")
    return c



# ------------------------------------------------------------ in-tray (incoming letters)
def letter_scope(user, qs):
    """Letters a user may see: reception / registry and the CEO see all; others the ones sent or assigned to them, heads their department's."""
    if user.has_cap("correspondence.manage") or user.sees_all_departments():
        return qs
    q = Q(addressed_to=user) | Q(assigned_to=user)
    if user.is_head:
        q |= Q(department=user.department)
    return qs.filter(q)


def in_tray(user):
    from .models import Correspondence

    open_ = [Correspondence.Status.RECEIVED, Correspondence.Status.ASSIGNED]
    return Correspondence.objects.alive().filter(status__in=open_).filter(Q(addressed_to=user) | Q(assigned_to=user, addressed_to__isnull=True))


@transaction.atomic
def route_letter(user, c, action, *, to_user=None, department="", title="", due_date=None, note=""):
    """What the person a letter was sent to does with it: give it to a department as a task, forward it, file it, or record the reply."""
    from .models import Correspondence

    if not (c.addressed_to_id == user.pk or c.assigned_to_id == user.pk or user.has_cap("correspondence.manage") or user.sees_all_departments()
            or (user.is_head and c.department == user.department)):
        raise PermissionDenied("This letter was not sent to you.")
    if action == "task":
        if to_user is None:
            raise ValidationError("Choose who will do the task.")
        dept = to_user.department or department or c.department
        task = create_task(user, title=(title or f"Letter {c.reference}: {c.subject}")[:200], department=dept, assigned_to=to_user,
                           description=f"Letter {c.reference} from {c.sender} (received {c.date_received:%d %b %Y}). {note}".strip() +
                           "\nThe scanned letter is on the letter page.", due_date=due_date or None)
        c.task, c.department, c.assigned_to, c.status = task, dept, to_user, Correspondence.Status.TASKED     # filed with the task
    elif action == "forward":
        if to_user is None:
            raise ValidationError("Choose who to send it to.")
        c.addressed_to = to_user
        c.department = to_user.department or c.department
        notify([to_user], f"Letter {c.reference} sent to you by {user.get_full_name()}", f"From {c.sender}: {c.subject}. {note}".strip(),
               f"/staff/correspondence/{c.pk}/view/")
    elif action == "file":
        c.status = Correspondence.Status.FILED
    elif action == "respond":
        if not note:
            raise ValidationError("Write what was replied.")
        c.status, c.responded_at, c.response_summary = Correspondence.Status.RESPONDED, timezone.now(), note
    else:
        raise ValidationError("Unknown action.")
    if note and action != "respond":
        c.routing_note = (c.routing_note + f"\n{timezone.localtime():%d %b %H:%M} {user.get_full_name()}: {note}").strip()
    c.save()
    audit.log(AuditLog.Action.UPDATE, c, user=user, message=f"Letter {c.reference}: {action}")
    return c


# ------------------------------------------------------------------ phone messages
@transaction.atomic
def take_phone_message(user, *, caller_name, message, caller_phone="", for_user=None, for_department="", call_back=True, msg_id=None):
    from .models import PhoneMessage

    if not user.has_cap("calls.log"):
        raise PermissionDenied("Only reception takes phone messages.")
    if not (caller_name and message):
        raise ValidationError("Enter who called and the message.")
    if for_user is None and not for_department:
        raise ValidationError("Choose who the message is for.")
    if for_department and for_department not in Department.values:
        raise ValidationError("Unknown department.")
    extra = {"id": msg_id} if msg_id else {}
    m = PhoneMessage.objects.create(caller_name=caller_name, caller_phone=caller_phone, for_user=for_user,
                                    for_department=for_department or (for_user.department if for_user else ""), message=message,
                                    call_back=call_back, taken_by=user, created_by=user, **extra)
    to = [for_user] if for_user else [u for u in User.objects.filter(department=for_department, is_active=True) if u.is_head]
    notify(to, f"Phone message from {caller_name}" + (f" ({caller_phone})" if caller_phone else ""),
           message + (" – please call back." if call_back else ""), "/staff/phone-messages/")
    return m


def phone_message_scope(user, qs):
    if user.has_cap("calls.log") or user.sees_all_departments():
        return qs
    q = Q(for_user=user)
    if user.is_head:
        q |= Q(for_user__isnull=True, for_department=user.department)
    return qs.filter(q)


@transaction.atomic
def phone_message_done(user, m, note=""):
    from .models import PhoneMessage

    if not phone_message_scope(user, PhoneMessage.objects.filter(pk=m.pk)).exists():
        raise PermissionDenied("This message is not for you.")
    m.status, m.done_at, m.done_note = PhoneMessage.Status.DONE, timezone.now(), note[:255]
    m.save()
    return m
