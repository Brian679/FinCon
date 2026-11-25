"""Outgoing messages to clients: in-app notification, SMS and email.

SMS_BACKEND = "console" logs the SMS only (development / no gateway yet);
"http" posts JSON {to, message, sender} with a bearer token to SMS_HTTP_URL,
which suits most Zimbabwean bulk-SMS providers' REST APIs.
"""
import json
import logging
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

from .models import MessageLog, Notification

log = logging.getLogger("crdc.messaging")


def _send_sms(to, message):
    if settings.SMS_BACKEND == "http" and settings.SMS_HTTP_URL:
        req = urllib.request.Request(
            settings.SMS_HTTP_URL,
            data=json.dumps({"to": to, "message": message, "sender": settings.SMS_SENDER_ID}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {settings.SMS_HTTP_TOKEN}"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
            if resp.status >= 300:
                raise RuntimeError(f"SMS gateway returned {resp.status}")
    else:
        log.info("SMS to %s: %s", to, message)


def notify_client(*, users=(), phone="", email="", subject, body, account_number="", sent_by=None, campaign="", link=""):
    """Reach a client on every channel available. Returns the number of messages sent."""
    sent = 0
    for u in {u for u in users if u is not None}:
        Notification.objects.create(recipient=u, title=subject, body=body, link=link)
        MessageLog.objects.create(channel=MessageLog.Channel.APP, recipient=u, to=u.username, account_number=account_number,
                                  subject=subject, body=body, sent_by=sent_by, campaign=campaign)
        sent += 1
    if phone:
        entry = MessageLog(channel=MessageLog.Channel.SMS, to=phone, account_number=account_number, subject=subject,
                           body=f"{subject}. {body}"[:459], sent_by=sent_by, campaign=campaign)
        try:
            _send_sms(phone, entry.body)
        except Exception as exc:  # noqa: BLE001 - delivery failure is recorded, not fatal
            entry.status, entry.error = "FAILED", str(exc)[:255]
        entry.save()
        sent += 1
    if email:
        entry = MessageLog(channel=MessageLog.Channel.EMAIL, to=email, account_number=account_number, subject=subject, body=body,
                           sent_by=sent_by, campaign=campaign)
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        except Exception as exc:  # noqa: BLE001
            entry.status, entry.error = "FAILED", str(exc)[:255]
        entry.save()
        sent += 1
    return sent
