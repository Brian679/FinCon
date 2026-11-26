"""Upload checks: only office documents and photos, and not too large."""
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

ALLOWED = ["pdf", "doc", "docx", "xls", "xlsx", "jpg", "jpeg", "png"]
MAX_BYTES = 5 * 1024 * 1024
_ext = FileExtensionValidator(ALLOWED)


def validate_document(f):
    _ext(f)
    if f.size and f.size > MAX_BYTES:
        raise ValidationError("The file is larger than 5 MB.")
    head = f.read(8)
    f.seek(0)
    name = f.name.lower()
    if name.endswith(".pdf") and not head.startswith(b"%PDF"):
        raise ValidationError("This is not a real PDF file.")
    if name.endswith((".jpg", ".jpeg")) and not head.startswith(b"\xff\xd8"):
        raise ValidationError("This is not a real JPEG photo.")
    if name.endswith(".png") and not head.startswith(b"\x89PNG"):
        raise ValidationError("This is not a real PNG image.")
