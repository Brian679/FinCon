import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import Client
from rest_framework.test import APIClient

from accounts.models import User
from api import sync
from core.models import Notification
from departments import services as dept
from departments.models import StandApplication
from finance import services as fin
from finance.models import AccountClaim, Property, Tenancy

from .base import CouncilTestCase


class StandWaitingListTests(CouncilTestCase):
    def test_fee_then_waiting_list_then_allocation_with_deposit(self):
        u = User.objects.create_user("applicant1", password="x", first_name="Rudo", last_name="Applicant", user_type=User.UserType.CLIENT,
                                     phone="0779001122", national_id="63-111000R63")
        res = sync.push(u, [{"op_id": str(uuid.uuid4()), "type": "stand.create", "payload": {
            "id": str(uuid.uuid4()), "stand_type": "RES", "preferred_location": "Checheche extension", "ward": 22}}])[0]
        self.assertEqual(res["status"], "applied", res)
        st = StandApplication.objects.get(pk=res["record"]["id"])
        self.assertEqual(st.status, "FEE_DUE")
        self.assertEqual(st.fee_bill.amount, Decimal("20.00"))
        self.assertEqual(u.client_accounts.count(), 1)                                    # own account opened to bill the fee
        gp = self.user("growthpoint")
        with self.assertRaises(ValidationError):
            dept.stand_action(gp, st, "allocate", stand="X1")                             # not on the waiting list until the fee is paid
        fin.issue_receipt(self.user("cashier"), revenue_head=st.fee_bill.revenue_head, amount="20", account=st.account, bill=st.fee_bill)
        st.refresh_from_db()
        self.assertEqual(st.status, "RECEIVED")
        self.assertIsNotNone(st.waiting_position)
        self.assertTrue(Notification.objects.filter(recipient=u, title__startswith="You are on the stand waiting list").exists())
        dept.stand_action(gp, st, "allocate", stand="CH-H40", deposit="150")
        st.refresh_from_db()
        self.assertEqual((st.status, st.deposit_bill.amount), ("ALLOCATED", Decimal("150.00")))
        self.assertTrue(Notification.objects.filter(recipient=u, title="Stand allocated to you: CH-H40").exists())
        with self.assertRaises(ValidationError):
            dept.apply_for_stand(User.objects.get(username="tenant"), stand_type="RES", preferred_location="again")   # already applied (seed)

class TenancyTests(CouncilTestCase):
    def test_renter_gets_own_account_not_the_owners(self):
        owner_shop = Property.objects.filter(business_name__gt="").exclude(account__phone="").first()
        renter = User.objects.create_user("renter1", password="x", first_name="Tino", last_name="Renter", user_type=User.UserType.CLIENT,
                                          phone=owner_shop.account.phone, national_id="99-000111T99")
        claim = fin.submit_claim(renter, stand_number=owner_shop.stand_number, area=owner_shop.area, business_name="Tino's Salon", claim_type="RENT")
        self.assertEqual(claim.status, AccountClaim.Status.PENDING)                      # renting is never auto-linked, even if the phone matches
        self.assertFalse(owner_shop.account.portal_users.filter(pk=renter.pk).exists())
        fin.decide_claim(self.user("cashier"), claim, True, note="Lease seen")
        claim.refresh_from_db()
        self.assertNotEqual(claim.account_id, owner_shop.account_id)
        t = Tenancy.objects.get(property=owner_shop, user=renter)
        self.assertEqual(t.tenant.portal_users.get(), renter)
        ents = sync.entities_for(renter)
        self.assertFalse(ents["bills"][0].filter(account=owner_shop.account).exists())   # never sees the owner's bills
        self.assertEqual(ents["tenancies"][0].count(), 1)
        res = sync.push(renter, [{"op_id": str(uuid.uuid4()), "type": "licence.apply", "payload": {
            "account": str(t.tenant_id), "property": str(owner_shop.pk), "licence_type": "SHOP", "business_name": "Tino's Salon",
            "premises": f"Stand {owner_shop.stand_number}"}}])[0]
        self.assertEqual(res["status"], "applied", res)                                   # licence for the rented shop on the renter's account

    def test_registration_asks_how_you_are_connected(self):
        c = APIClient()
        shop = Property.objects.filter(stand_number="B13").first()
        r = c.post("/api/v1/auth/register/", {"first_name": "New", "last_name": "Renter", "username": "newrenter", "email": "", "phone": "0771112233",
                                              "national_id": "12-345678N12", "ward": 22, "password1": "Strong!Pass2026", "password2": "Strong!Pass2026",
                                              "relationship": "RENT", "stand_number": "B13", "area": str(shop.area_id)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        claim = AccountClaim.objects.get(user__username="newrenter")
        self.assertEqual((claim.claim_type, claim.status), ("RENT", "PENDING"))
        r = c.post("/api/v1/auth/register/", {"first_name": "No", "last_name": "Stand", "username": "nostand", "phone": "0771112234",
                                              "national_id": "12-345679N12", "password1": "Strong!Pass2026", "password2": "Strong!Pass2026",
                                              "relationship": "OWNER"}, format="json")
        self.assertEqual(r.status_code, 400)                                              # owner must give the stand number
        w = Client()
        r = w.get("/portal/register/")
        self.assertContains(r, "I rent a house / shop from its owner")
