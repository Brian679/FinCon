import re

from django.core.exceptions import ValidationError

from core import audit
from core.models import AuditLog
from finance.models import ClientAccount


def _digits(s):
    return re.sub(r"\D", "", s or "")[-9:]


def link_account(user, account_number, verifier):
    """Link a ratepayer account to a client's portal profile. The client must
    prove ownership with the phone number or ID number held on the account."""
    account = ClientAccount.objects.alive().filter(account_number__iexact=account_number.strip()).first()
    v = (verifier or "").strip()
    ok = account is not None and v and (
        (account.phone and _digits(account.phone) == _digits(v) and len(_digits(v)) >= 9)
        or (account.id_number and account.id_number.replace("-", "").replace(" ", "").upper() == v.replace("-", "").replace(" ", "").upper())
    )
    if not ok:
        audit.log(AuditLog.Action.ACCESS_DENIED, user=user, message=f"Failed account link attempt for {account_number}")
        raise ValidationError("Account number and phone / ID number do not match our records. Visit council offices for help.")
    account.portal_users.add(user)
    audit.log(AuditLog.Action.UPDATE, account, user=user, message=f"Portal user {user.username} linked to account")
    return account
