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
                _item("My stands & shops", "portal:claims"),
                _item("Pay rates / levies", "portal:pay"),
                _item("Payment history", "portal:receipts"),
                _item("Licences", "portal:licences"),
                _item("Report a problem", "portal:request_new"),
                _item("Complaints & feedback", "portal:complaints"),
                _item("Stand applications", "portal:stands"),
                _item("Building plans", "portal:plans"),
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
        if c("areas.view", "accounts.manage"):
            fin.append(_item("Shops & stands by area (paid / unpaid)", "finance:areas"))
        if c("claims.review"):
            fin.append(_item("Stand registration requests", "finance:claims"))
        if c("leases.view", "leases.manage"):
            fin.append(_item("Leases", "finance:leases"))
        if c("billing.run"):
            fin.append(_item("Billing runs", "finance:billing_runs"))
        if c("messages.view", "reminders.send"):
            fin.append(_item("Messages & reminders", "finance:messages"))
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

    if c("dept.overview", "dept.overview_all"):
        general.insert(1, _item("My department (overview)", "departments:overview"))

    admin_items = [_item("Council meetings", "departments:meetings"), _item("Council resolutions", "departments:resolutions"),
                   _item("Policies & by-laws", "departments:policies")]
    if c("hr.view"):
        admin_items.append(_item("Staff directory", "departments:staff"))
    admin_items += [_item("Leave", "departments:leave"), _item("ICT helpdesk", "departments:tickets"), _item("Assets & infrastructure", "departments:assets")]
    sections.append({"title": "Administration & corporate", "items": admin_items})

    social = []
    if c("stands.view"):
        social.append(_item("Housing & stand allocation", "departments:stands"))
    if c("incidents.view"):
        social.append(_item("Incidents & disasters", "departments:incidents"))
    if c("activities.manage", "activities.verify", "dept.overview"):
        social.append(_item("Community programmes & campaigns", "departments:activities"))
    if social:
        sections.append({"title": "Social services", "items": social})

    tech = []
    if c("projects.view"):
        tech.append(_item("Projects & infrastructure", "departments:projects"))
    if c("plans.view"):
        tech.append(_item("Building plans (development control)", "departments:plans"))
    if tech:
        sections.append({"title": "Technical services", "items": tech})

    audit_items = []
    if c("audit.findings_view", "audit.respond"):
        audit_items.append(_item("Internal audit findings", "departments:findings"))
    if c("risks.view", "risks.manage"):
        audit_items.append(_item("Risk register", "departments:risks"))
    if audit_items:
        sections.append({"title": "Internal audit", "items": audit_items})

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
