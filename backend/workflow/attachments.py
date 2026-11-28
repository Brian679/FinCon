"""Files attached to requests for funds (quotations, invoices, delivery notes, evidence) and to incoming letters (scans)."""
from django.core.exceptions import PermissionDenied, ValidationError

from core import audit
from core.models import AuditLog

from .models import Attachment, Correspondence, FundsRequest

MAX_BYTES = 15 * 1024 * 1024
TYPES = (".pdf", ".jpg", ".jpeg", ".png", ".webp", ".doc", ".docx", ".xls", ".xlsx")
TARGETS = {"funds": FundsRequest, "correspondence": Correspondence}


def target(kind, pk):
    model = TARGETS.get(kind)
    if model is None:
        raise ValidationError("Unknown item.")
    obj = model.objects.alive().filter(pk=pk).first()
    if obj is None:
        raise ValidationError("Not found.")
    return obj


def can_view(user, kind, obj):
    from . import funds as fr
    from .services import letter_scope

    if kind == "funds":
        return fr.can_view(user, obj)
    return letter_scope(user, Correspondence.objects.filter(pk=obj.pk)).exists()


def can_attach(user, kind, obj):
    if not can_view(user, kind, obj):
        return False
    if kind == "funds":
        return obj.requested_by_id == user.pk or user.has_cap("procurement.order", "voucher.prepare", "funds.accountant_approve")
    # letters: reception / registry scan them; the people the letter is sent to only read the scan
    return user.has_cap("correspondence.manage")


def add(user, kind, obj, upload, file_kind="", name=""):
    if not can_attach(user, kind, obj):
        raise PermissionDenied("You cannot add files here.")
    fname = (upload.name or "file").lower()
    if not fname.endswith(TYPES):
        raise ValidationError("Send a PDF, photo (JPG / PNG), Word or Excel file.")
    if upload.size > MAX_BYTES:
        raise ValidationError("The file is larger than 15 MB.")
    head = upload.read(8)
    upload.seek(0)
    if fname.endswith(".pdf") and not head.startswith(b"%PDF"):
        raise ValidationError("This is not a real PDF file.")
    if fname.endswith((".jpg", ".jpeg")) and not head.startswith(b"\xff\xd8"):
        raise ValidationError("This is not a real JPEG photo.")
    if fname.endswith(".png") and not head.startswith(b"\x89PNG"):
        raise ValidationError("This is not a real PNG image.")
    if file_kind not in Attachment.Kind.values:
        file_kind = Attachment.Kind.SCAN if kind == "correspondence" else Attachment.Kind.EVIDENCE
    a = Attachment(target_type=kind, target_id=obj.pk, name=(name or upload.name)[:200], kind=file_kind, size=upload.size, uploaded_by=user,
                   created_by=user)
    a.file.save(upload.name, upload, save=False)
    a.save()
    type(obj).objects.filter(pk=obj.pk).update(updated_at=a.created_at)      # apps pick up the new file on the next sync
    audit.log(AuditLog.Action.CREATE, obj, user=user, message=f"File attached: {a.name} ({a.get_kind_display()})")
    return a


def for_object(kind, obj):
    return Attachment.objects.alive().filter(target_type=kind, target_id=obj.pk).select_related("uploaded_by")


def as_list(kind, obj):
    return [{"id": str(a.pk), "name": a.name, "kind": a.kind, "kind_label": a.get_kind_display(), "size": a.size,
             "uploaded_by_name": a.uploaded_by.get_full_name() if a.uploaded_by_id else "", "created_at": a.created_at.isoformat()}
            for a in for_object(kind, obj)]
