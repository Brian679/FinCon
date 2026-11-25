from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from finance.models import BankAccount, ClientAccount, RevenueHead


class CouncilTestCase(TestCase):
    """Seeds charter data plus one user per demo role."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_council", "--demo", verbosity=0, stdout=open("/dev/null", "w"))
        cls.u = {u.username: u for u in User.objects.all()}
        cls.rates = RevenueHead.objects.get(code="RATES")
        cls.shop = RevenueHead.objects.get(code="LIC-SHOP")
        cls.usd_bank = BankAccount.objects.get(currency="USD")
        cls.acc = ClientAccount.objects.get(name="Johannes Mhlanga")
        cls.other_acc = ClientAccount.objects.get(name="Grace Chiwara")

    def user(self, name):
        return User.objects.get(username=name)

    def fund_bank(self, amount=Decimal("100000")):
        BankAccount.objects.filter(pk=self.usd_bank.pk).update(opening_balance=amount)
        self.usd_bank.refresh_from_db()
