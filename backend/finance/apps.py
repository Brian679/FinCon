from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "finance"
    verbose_name = "Finance"

    def ready(self):
        from core import audit

        from . import models as m

        audit.register(m.ExchangeRate, m.BudgetLine, m.RevenueHead, m.BankAccount, m.ClientAccount, m.Property, m.Bill,
                       m.CashUp, m.Receipt, m.Licence, m.Supplier, m.Requisition, m.RequisitionItem, m.PurchaseOrder,
                       m.PaymentVoucher, m.OnlinePayment, m.TradingArea, m.Lease, m.AccountClaim, m.Offence, m.Fine, m.Tenancy, m.CertificateRequest)
