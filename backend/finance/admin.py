from django.contrib import admin

from . import models

for m in [models.ExchangeRate, models.BudgetLine, models.RevenueHead, models.BankAccount, models.ClientAccount, models.Property,
          models.Supplier]:
    admin.site.register(m)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Financial transactions are created only through the controlled
    workflows; the admin site may view but never alter them."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for m in [models.Bill, models.Receipt, models.CashUp, models.Licence, models.Requisition, models.PurchaseOrder,
          models.PaymentVoucher, models.ApprovalRecord, models.OnlinePayment]:
    admin.site.register(m, ReadOnlyAdmin)
