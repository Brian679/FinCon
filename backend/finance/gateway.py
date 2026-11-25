"""Online payment gateways.

``simulated`` - for development, demos and training: payments are confirmed
               when the client presses "Confirm" on the simulated phone prompt.
``paynow``    - Paynow Zimbabwe (EcoCash / OneMoney / cards). Requires
               PAYNOW_INTEGRATION_ID / KEY. Implemented with the standard
               HTTP "initiate transaction" API so no extra package is needed.
"""
import hashlib
import urllib.parse
import urllib.request

from django.conf import settings


class SimulatedGateway:
    name = "simulated"

    def initiate(self, payment):
        payment.provider_reference = f"SIM-{payment.reference}"
        payment.save(update_fields=["provider_reference", "updated_at"])
        return payment

    def check(self, payment):
        return None  # confirmation comes from the simulated prompt


class PaynowGateway:
    name = "paynow"
    MOBILE_URL = "https://www.paynow.co.zw/interface/remotetransaction"

    def _hash(self, values):
        raw = "".join(str(v) for v in values) + settings.PAYNOW_INTEGRATION_KEY
        return hashlib.sha512(raw.encode()).hexdigest().upper()

    def initiate(self, payment):
        fields = {
            "id": settings.PAYNOW_INTEGRATION_ID,
            "reference": payment.reference,
            "amount": str(payment.amount),
            "additionalinfo": f"Chipinge RDC account {payment.account.account_number}",
            "returnurl": settings.PAYNOW_RETURN_URL,
            "resulturl": settings.PAYNOW_RESULT_URL,
            "authemail": payment.user.email or settings.DEFAULT_FROM_EMAIL,
            "phone": payment.phone,
            "method": payment.method.lower(),
            "status": "Message",
        }
        fields["hash"] = self._hash(fields.values())
        data = urllib.parse.urlencode(fields).encode()
        with urllib.request.urlopen(self.MOBILE_URL, data=data, timeout=30) as resp:  # noqa: S310
            reply = dict(urllib.parse.parse_qsl(resp.read().decode()))
        if reply.get("status", "").lower() != "ok":
            payment.status = payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            raise RuntimeError(reply.get("error", "Payment could not be initiated"))
        payment.poll_url = reply.get("pollurl", "")
        payment.provider_reference = reply.get("paynowreference", "")
        payment.save(update_fields=["poll_url", "provider_reference", "updated_at"])
        return payment

    def check(self, payment):
        if not payment.poll_url:
            return None
        with urllib.request.urlopen(payment.poll_url, data=b"", timeout=30) as resp:  # noqa: S310
            reply = dict(urllib.parse.parse_qsl(resp.read().decode()))
        return reply.get("status", "").lower()


def get_gateway():
    return PaynowGateway() if settings.PAYMENT_GATEWAY == "paynow" else SimulatedGateway()
