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
    def test_area_fee_submits_then_approve_pay_price_stand_issued(self):
        from departments.models import AvailableStand
        from finance.models import TradingArea

        u = User.objects.create_user("applicant1", password="x", first_name="Rudo", last_name="Applicant", user_type=User.UserType.CLIENT,
                                     phone="0779001122", national_id="63-111000R63")
        area = TradingArea.objects.filter(available_stands__status="AVAILABLE", available_stands__stand_type="RES").distinct().first()
        self.assertIn(area, [a for a, _n in dept.stand_areas("RES")])                    # only areas with stands available are offered
        res = sync.push(u, [{"op_id": str(uuid.uuid4()), "type": "stand.create", "payload": {
            "id": str(uuid.uuid4()), "stand_type": "RES", "area": str(area.pk)}}])[0]
        self.assertEqual(res["status"], "applied", res)
        st = StandApplication.objects.get(pk=res["record"]["id"])
        self.assertEqual((st.status, st.fee_bill.amount), ("FEE_DUE", Decimal("20.00")))
        gp = self.user("growthpoint")
        self.assertFalse(sync.entities_for(gp)["stands"][0].filter(pk=st.pk).exists())   # not submitted to the council until the fee is paid
        with self.assertRaises(ValidationError):
            dept.stand_action(gp, st, "approve")
        fin.issue_receipt(self.user("cashier"), revenue_head=st.fee_bill.revenue_head, amount="20", account=st.account, bill=st.fee_bill)
        st.refresh_from_db()
        self.assertEqual(st.status, "RECEIVED")
        self.assertTrue(sync.entities_for(gp)["stands"][0].filter(pk=st.pk).exists())
        dept.stand_action(gp, st, "approve")                                               # a stand in the chosen area is reserved, its price billed
        st.refresh_from_db()
        av = AvailableStand.objects.get(application=st)
        self.assertEqual((st.status, av.status, st.deposit_bill.amount), ("APPROVED", "RESERVED", av.price))
        self.assertFalse(Property.objects.filter(stand_number=av.stand_number, account=st.account).exists())
        fin.issue_receipt(self.user("cashier"), revenue_head=st.deposit_bill.revenue_head, amount=av.price, account=st.account, bill=st.deposit_bill)
        st.refresh_from_db()
        av.refresh_from_db()
        self.assertEqual((st.status, av.status, st.allocated_stand), ("ALLOCATED", "SOLD", av.stand_number))
        self.assertTrue(Property.objects.filter(stand_number=av.stand_number, account=st.account, area=area).exists())   # on the applicant's account
        self.assertTrue(Notification.objects.filter(recipient=u, title=f"Stand {av.stand_number} is yours").exists())
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

    def test_registration_needs_no_stand_number(self):
        c = APIClient()
        r = c.post("/api/v1/auth/register/", {"first_name": "New", "last_name": "Person", "username": "newperson", "email": "", "phone": "0771112233",
                                              "national_id": "12-345678N12", "ward": 22, "password1": "Strong!Pass2026",
                                              "password2": "Strong!Pass2026"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertFalse(AccountClaim.objects.filter(user__username="newperson").exists())
        self.assertNotContains(Client().get("/portal/register/"), "Stand number")
