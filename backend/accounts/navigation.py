"""Sidebar navigation built from the user's capabilities."""
from django.urls import NoReverseMatch, reverse

from core.models import Department


# Django-admin style "Add" links next to sidebar entries (list url name -> add url name)
ADD_LINKS = {
    "finance:receipts": ("finance:receipt_new", "receipt.create"), "finance:accounts": ("finance:account_new", "accounts.manage"),
    "finance:licences": ("finance:licence_new", "licence.manage"), "finance:vouchers": ("finance:voucher_new", "voucher.prepare"),
    "finance:suppliers": ("finance:supplier_new", "supplier.manage"), "finance:requisitions": ("finance:requisition_new", None),
    "finance:cashups": ("finance:cashup_new", "cashup.submit"), "finance:area_list": ("finance:area_new", "areas.manage"),
    "finance:leases": ("finance:lease_new", "leases.manage"), "finance:messages": ("finance:broadcast", "reminders.send"),
    "workflow:tasks": ("workflow:task_new", ("tasks.assign_any", "tasks.assign_department")), "workflow:complaints": ("workflow:complaint_new", ("complaints.manage", "complaints.department", "complaints.view_all")),
    "workflow:requests": ("workflow:request_new", None), "workflow:correspondence": ("workflow:correspondence_new", "correspondence.manage"),
    "departments:leave": ("departments:leave_new", None), "departments:stands": ("departments:stand_new", "stands.manage"),
    "departments:projects": ("departments:project_new", "projects.manage"), "departments:findings": ("departments:finding_new", "audit.findings_manage"),
    "departments:incidents": ("departments:incident_new", "incidents.manage"), "departments:activities": ("departments:activity_new", "activities.manage"),
    "departments:plans": ("departments:plan_new", "plans.review"), "departments:assets": ("departments:asset_new", "assets.manage"),
    "departments:risks": ("departments:risk_new", "risks.manage"), "departments:meetings": ("departments:meeting_new", "meetings.manage"),
    "departments:tickets": ("departments:ticket_new", None), "departments:policies": ("departments:policy_new", "policies.manage"),
    "accounts:users": ("accounts:user_new", "users.manage"),
    "finance:fines": ("finance:fine_new", "fines.issue"), "social:wildlife_list": ("social:wildlife_new", "wildlife.manage"),
    "social:hunts": ("social:hunt_new", "hunts.manage"), "social:permits": ("social:permit_new", "permits.manage"),
    "social:farms": ("social:farm_new", "farms.manage"), "social:water_list": ("social:water_new", "water.manage"),
    "social:beneficiaries": ("social:beneficiary_new", "welfare.manage"), "social:quotas": ("social:quota_new", "hunts.manage"),
    "workflow:memos": ("workflow:memo_new", None), "workflow:funds": ("workflow:fund_new", None),
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
    D = Department
    sees_all = user.sees_all_departments()
    dept = user.department
    sections = []

    # ---- The person's own department: its day-to-day work and its registers in one place.
    # (Personal things – profile, leave, payslips, notifications – are under the profile icon.)
    general = [_item("Dashboard", "core:dashboard")]
    if user.is_ceo or c("reports.executive"):
        general.append(_item("Executive overview", "core:executive"))
    if c("dept.overview", "dept.overview_all"):
        general.append(_item("Department overview", "departments:overview"))
    general += [
        _item("Tasks", "workflow:tasks"),
        _item("Memos to / from departments", "workflow:memos"),
        _item("Requests for funds & purchases", "workflow:funds") if c("funds.request") else None,
        _item("Purchase requisitions", "finance:requisitions") if c("requisition.create") else None,
        _item("Service requests / faults", "workflow:requests"),
        _item("ICT support", "departments:tickets"),
    ]
    if c("leave.approve"):
        general.append(_item("Leave applications to approve", "departments:leave"))
    if c("resolutions.update") and not c("meetings.view"):
        general.append(_item("Council resolutions for the department", "departments:resolutions"))
    sections.append({"title": user.get_department_display() or "My department", "items": general, "own": True})

    # ---- Complaints are confidential: customer care, the CEO, heads (their department) and officers given one.
    if c("complaints.view_all", "complaints.manage", "complaints.department"):
        sections.append({"title": "Customer care", "items": [_item("Complaints, compliments & suggestions", "workflow:complaints")]})
    else:
        from workflow.models import Complaint

        if Complaint.objects.alive().filter(assigned_to=user).exists():
            sections.append({"title": "Customer care", "items": [_item("Complaints given to me", "workflow:complaints")]})

    def show(code):
        return dept == code or sees_all

    # ---- Finance department
    if c("finance.view") and show(D.FINANCE):
        fin = []
        if c("receipt.create"):
            fin.append(_item("Receipting counter", "finance:receipt_new"))
        fin.append(_item("Receipts (income)", "finance:receipts"))
        if c("accounts.manage", "finance.view_all"):
            fin += [_item("Client accounts", "finance:accounts"), _item("Bills", "finance:bills")]
        if c("areas.view", "accounts.manage"):
            fin.append(_item("Areas overview – shops paid / owing", "finance:areas"))
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
        if c("budget.view", "budget.manage"):
            fin.append(_item("Budget vs actual", "finance:budget"))
        if c("bank.manage", "finance.view_all"):
            fin += [_item("Bank accounts & cashbook", "finance:banks"), _item("Exchange rates", "finance:rates")]
        if c("payments.online_view"):
            fin.append(_item("Online payments", "finance:online_payments"))
        if c("finance.reports"):
            fin.append(_item("Financial reports", "finance:reports"))
        if c("fines.view"):
            fin.append(_item("Fines & penalties", "finance:fines"))
        if c("hunts.view") and dept != D.SOCIAL_SERVICES:
            fin.append(_item("CAMPFIRE trophy fees", "social:hunts"))
        if c("permits.view") and dept != D.SOCIAL_SERVICES:
            fin.append(_item("Sand, mining & forestry permits", "social:permits"))
        if c("farms.view") and dept != D.SOCIAL_SERVICES:
            fin.append(_item("Farms register (farm levy)", "social:farms"))
        if c("payroll.view", "payroll.manage"):
            fin += [_item("Payroll", "payroll:payroll"), _item("Salaries", "payroll:salaries"), _item("Salaries owed to staff", "payroll:arrears"),
                    _item("PAYE tax tables", "payroll:tax")]
        sections.append({"title": "Finance", "items": fin})

    # ---- Procurement (Administration's procurement unit + Finance)
    proc = []
    if c("procurement.order", "finance.view_all"):
        proc.append(_item("Purchase orders", "finance:orders"))
    if c("supplier.manage", "finance.view_all"):
        proc.append(_item("Suppliers", "finance:suppliers"))
    if proc:
        sections.append({"title": "Procurement", "items": proc})

    # ---- Administration department
    if show(D.ADMINISTRATION) or (dept == D.EXECUTIVE and c("meetings.view")):
        admin_items = []
        if c("meetings.view"):
            admin_items += [_item("Council meetings", "departments:meetings"), _item("Council resolutions", "departments:resolutions")]
        if c("policies.view"):
            admin_items.append(_item("Policies & by-laws", "departments:policies"))
        if c("correspondence.manage"):
            admin_items.append(_item("Correspondence register", "workflow:correspondence"))
        if c("hr.view"):
            admin_items.append(_item("Staff directory", "departments:staff"))
        if admin_items:
            sections.append({"title": "Administration", "items": admin_items})

    # ---- Assets register (each department sees its own assets)
    if c("assets.view"):
        asset_label = "Assets & infrastructure" if (c("assets.manage") or sees_all) else "My department's assets"
        sections.append({"title": "Assets", "items": [_item(asset_label, "departments:assets")]})

    # ---- Social services
    if show(D.SOCIAL_SERVICES):
        social = []
        if c("stands.view"):
            social.append(_item("Housing & stand allocation", "departments:stands"))
        if c("incidents.view"):
            social.append(_item("Incidents & disasters", "departments:incidents"))
        if c("activities.manage", "activities.verify", "dept.overview_all") and (dept == D.SOCIAL_SERVICES or sees_all):
            social.append(_item("Community programmes & campaigns", "departments:activities"))
        if c("licence.inspect"):
            social.append(_item("Health certificate inspections", "finance:licences"))
        if c("welfare.view", "welfare.manage"):
            social.append(_item("Social welfare – vulnerable households", "social:beneficiaries"))
        if c("water.view", "water.manage"):
            social.append(_item("Water points (WASH)", "social:water_list"))
        if social:
            sections.append({"title": "Social services", "items": social})
        campfire = []
        if c("wildlife.view", "wildlife.manage"):
            campfire.append(_item("Wildlife database", "social:wildlife_list"))
        if c("hunts.view", "hunts.manage"):
            campfire += [_item("Hunting quotas", "social:quotas"), _item("Trophy hunts", "social:hunts"), _item("CAMPFIRE revenue by ward", "social:campfire")]
        if campfire:
            sections.append({"title": "CAMPFIRE (wildlife)", "items": campfire})
        natres = []
        if c("permits.view", "permits.manage"):
            natres.append(_item("Sand, mining & forestry permits", "social:permits"))
        if c("farms.view", "farms.manage"):
            natres.append(_item("Agricultural farms", "social:farms"))
        if natres:
            sections.append({"title": "Natural resources & agriculture", "items": natres})
    if c("fines.issue") and dept not in (D.FINANCE,) and not sees_all:
        sections.append({"title": "By-law enforcement", "items": [_item("Fines I have issued", "finance:fines")]})
    if dept == D.ADMINISTRATION and c("activities.manage"):
        sections.append({"title": "Staff development", "items": [_item("Trainings & staff activities", "departments:activities")]})

    # ---- Technical services
    if show(D.TECHNICAL_SERVICES):
        tech = []
        if c("projects.view"):
            tech.append(_item("Projects & infrastructure", "departments:projects"))
        if c("plans.view"):
            tech.append(_item("Building plans (development control)", "departments:plans"))
        if tech:
            sections.append({"title": "Technical services", "items": tech})

    # ---- Internal audit (audit findings addressed to my department for heads)
    audit_items = []
    if c("audit.findings_view") or c("audit.respond"):
        audit_items.append(_item("Internal audit findings" if c("audit.findings_view") else "Audit findings for my department", "departments:findings"))
    if c("risks.view", "risks.manage"):
        audit_items.append(_item("Risk register", "departments:risks"))
    if audit_items:
        own = dept == D.INTERNAL_AUDIT or sees_all
        sections.append({"title": "Internal audit" if own else "Audit & risks – my department", "items": audit_items})

    gov = []
    if c("audit.view_trail"):
        gov.append(_item("Audit trail", "core:audit_trail"))
    if c("users.manage", "users.view"):
        gov.append(_item("User management", "accounts:users"))
    if c("users.manage"):
        gov.append(_item("System administration (restricted)", "admin:index"))
    if gov:
        sections.append({"title": "Governance", "items": gov})

    for sec in sections:
        sec["items"] = [i for i in sec["items"] if i]
    # Everyone except the CEO / Internal Audit: fold their own department's registers into their department section.
    if not sees_all:
        own_titles = {D.FINANCE: ("Finance", "Procurement", "Assets"), D.ADMINISTRATION: ("Administration", "Procurement", "Assets", "Staff development"),
                      D.SOCIAL_SERVICES: ("Social services", "Assets"), D.TECHNICAL_SERVICES: ("Technical services", "Assets"),
                      D.INTERNAL_AUDIT: ("Internal audit",)}.get(dept, ())
        head = sections[0]
        rest = []
        for sec in sections[1:]:
            if sec["title"] in own_titles or sec["title"].startswith("Audit & risks"):
                head["items"] += [i for i in sec["items"] if i["url"] != head["items"][0]["url"]]
            else:
                rest.append(sec)
        sections = [head] + rest
    return [sec for sec in sections if sec["items"]]
