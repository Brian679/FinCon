from django.contrib import admin
from .models import Invoice, Payment

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'client', 'amount', 'total_amount', 'status', 'issue_date', 'due_date']
    list_filter = ['status', 'issue_date']
    search_fields = ['invoice_number', 'client__username']
    raw_id_fields = ['client', 'service_request']

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'amount', 'payment_method', 'payment_date']
    list_filter = ['payment_method', 'payment_date']
    search_fields = ['invoice__invoice_number', 'transaction_id']
    raw_id_fields = ['invoice']
