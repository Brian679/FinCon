"""Sidebar navigation built from the user's capabilities."""
from django.urls import NoReverseMatch, reverse


def _item(label, name, *args):
    try:
        return {"label": label, "url": reverse(name, args=args)}
    except NoReverseMatch:
        return None


def build_nav(user):
    if user.is_client:
        return [
            {"title": "My council", "items": [
                _item("Dashboard", "portal:dashboard"),
                _item("My accounts & bills", "portal:accounts"),
                _item("Pay rates / levies", "portal:pay"),
                _item("Payment history", "portal:receipts"),
                _item("Licences", "portal:licences"),
                _item("Report a problem", "portal:request_new"),
                _item("Complaints & feedback", "portal:complaints"),
                _item("Stand applications", "portal:stands"),
            ]},
        ]
    c = user.has_cap
    sections = []
    general = [_item("Dashboard", "core:dashboard"), _item("Notifications", "core:notifications"), _item("My tasks", "workflow:tasks")]
    if user.is_ceo or c("reports.executive"):
        general.insert(1, _item("Executive overview", "core:executive"))
    sections.append({"title": "General", "items": general})

    if c("finance.view"):
        fin = [_item("Finance dashboard", "finance:dashboard")]
        if c("receipt.create"):
            fin.append(_item("Receipting counter", "finance:receipt_new"))
        fin.append(_item("Receipts (income)", "finance:receipts"))
        if c("accounts.manage", "finance.view_all"):
            fin += [_item("Client accounts", "finance:accounts"), _item("Bills", "finance:bills")]
        if c("cashup.submit", "cashup.verify"):
            fin.append(_item("Cash-ups", "finance:cashups"))
        if c("licence.view"):
            fin.append(_item("Licences", "finance:licences"))
        if c("voucher.prepare", "voucher.check", "voucher.approve", "voucher.authorise", "finance.view_all"):
            fin.append(_item("Payment vouchers (expenditure)", "finance:vouchers"))
        if c("supplier.manage", "finance.view_all"):
            fin.append(_item("Suppliers", "finance:suppliers"))
        if c("procurement.order", "finance.view_all"):
            fin.append(_item("Purchase orders", "finance:orders"))
        if c("budget.view", "budget.manage"):
            fin.append(_item("Budget vs actual", "finance:budget"))
        if c("bank.manage", "finance.view_all"):
            fin += [_item("Bank accounts & cashbook", "finance:banks"), _item("Exchange rates", "finance:rates")]
        if c("payments.online_view"):
            fin.append(_item("Online payments", "finance:online_payments"))
        if c("finance.reports"):
            fin.append(_item("Financial reports", "finance:reports"))
        sections.append({"title": "Finance", "items": fin})
    elif c("licence.view"):
        sections.append({"title": "Finance", "items": [_item("Licences / inspections", "finance:licences")]})

    proc = [_item("Requisitions", "finance:requisitions")]
    sections.append({"title": "Procurement", "items": proc})

    services = [_item("Complaints & feedback", "workflow:complaints"), _item("Service requests / faults", "workflow:requests")]
    if c("correspondence.manage") or user.is_head:
        services.append(_item("Correspondence register", "workflow:correspondence"))
    sections.append({"title": "Client service (Charter)", "items": services})

    dept = []
    if c("stands.view"):
        dept.append(_item("Stand allocation", "departments:stands"))
    if c("projects.view"):
        dept.append(_item("Projects & infrastructure", "departments:projects"))
    if c("audit.findings_view", "audit.respond"):
        dept.append(_item("Internal audit findings", "departments:findings"))
    dept.append(_item("Leave", "departments:leave"))
    if c("hr.view"):
        dept.append(_item("Staff directory", "departments:staff"))
    sections.append({"title": "Departments", "items": dept})

    gov = []
    if c("audit.view_trail"):
        gov.append(_item("Audit trail", "core:audit_trail"))
    if c("users.manage", "users.view"):
        gov.append(_item("User management", "accounts:users"))
    if c("users.manage"):
        gov.append(_item("System administration (restricted)", "admin:index"))
    if gov:
        sections.append({"title": "Governance", "items": gov})

    for s in sections:
        s["items"] = [i for i in s["items"] if i]
    return sections
