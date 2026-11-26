"""Sidebar navigation built from the user's capabilities."""
from django.urls import NoReverseMatch, reverse


# Django-admin style "Add" links next to sidebar entries (list url name -> add url name)
ADD_LINKS = {
    "finance:receipts": ("finance:receipt_new", "receipt.create"), "finance:accounts": ("finance:account_new", "accounts.manage"),
    "finance:licences": ("finance:licence_new", "licence.manage"), "finance:vouchers": ("finance:voucher_new", "voucher.prepare"),
    "finance:suppliers": ("finance:supplier_new", "supplier.manage"), "finance:requisitions": ("finance:requisition_new", None),
    "finance:cashups": ("finance:cashup_new", "cashup.submit"), "finance:areas": ("finance:area_new", "areas.manage"),
    "finance:leases": ("finance:lease_new", "leases.manage"), "finance:messages": ("finance:broadcast", "reminders.send"),
    "workflow:tasks": ("workflow:task_new", ("tasks.assign_any", "tasks.assign_department")), "workflow:complaints": ("workflow:complaint_new", None),
    "workflow:requests": ("workflow:request_new", None), "workflow:correspondence": ("workflow:correspondence_new", "correspondence.manage"),
    "departments:leave": ("departments:leave_new", None), "departments:stands": ("departments:stand_new", "stands.manage"),
    "departments:projects": ("departments:project_new", "projects.manage"), "departments:findings": ("departments:finding_new", "audit.findings_manage"),
    "departments:incidents": ("departments:incident_new", "incidents.manage"), "departments:activities": ("departments:activity_new", "activities.manage"),
    "departments:plans": ("departments:plan_new", "plans.review"), "departments:assets": ("departments:asset_new", "assets.manage"),
    "departments:risks": ("departments:risk_new", "risks.manage"), "departments:meetings": ("departments:meeting_new", "meetings.manage"),
    "departments:tickets": ("departments:ticket_new", None), "departments:policies": ("departments:policy_new", "policies.manage"),
    "accounts:users": ("accounts:user_new", "users.manage"),
    "portal:complaints": ("portal:complaint_new", None), "portal:requests": ("portal:request_new", None), "portal:licences": ("portal:licence_apply", None),
    "portal:claims": ("portal:claim_new", None), "portal:plans": ("portal:plan_new", None), "portal:stands": ("portal:stand_new", None),
    "portal:accounts": ("portal:link", None),
}

_current_user = None


def _item(label, name, *args):
    try:
        item = {"label": label, "url": reverse(name, args=args)}
    except NoReverseMatch:
        return None
    add = ADD_LINKS.get(name)
    if add:
        caps = add[1]
        if caps is None or (_current_user is not None and _current_user.has_cap(*((caps,) if isinstance(caps, str) else caps))):
            try:
                item["add"] = reverse(add[0])
            except NoReverseMatch:
                pass
    return item


def build_nav(user):
    global _current_user
    _current_user = user
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
