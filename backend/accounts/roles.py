"""Role-based access control.

Every staff user belongs to one department and holds one role. A role grants
a set of *capabilities*; views, API endpoints and the mobile sync scope all
check capabilities instead of role names, so access rules live in one place.
"""
from core.models import Department as D


class Level:
    EXECUTIVE = "EXEC"
    HEAD = "HEAD"
    OFFICER = "OFFICER"
    CLERK = "CLERK"


# code: (label, department, level)
ROLES = {
    "SYSADMIN": ("ICT / System Administrator", D.ADMINISTRATION, Level.OFFICER),
    "CEO": ("Chief Executive Officer", D.EXECUTIVE, Level.EXECUTIVE),
    "EXEC_ASSISTANT": ("Executive Assistant (Office of the CEO)", D.EXECUTIVE, Level.CLERK),
    # Administration
    "ADMIN_OFFICER": ("Administration Officer (Head of Administration)", D.ADMINISTRATION, Level.HEAD),
    "HR_OFFICER": ("Human Resources Officer", D.ADMINISTRATION, Level.OFFICER),
    "PROCUREMENT_OFFICER": ("Procurement Officer", D.ADMINISTRATION, Level.OFFICER),
    "RECORDS_CLERK": ("Records / Registry Clerk", D.ADMINISTRATION, Level.CLERK),
    # Finance
    "TREASURER": ("Treasurer (Head of Finance)", D.FINANCE, Level.HEAD),
    "ACCOUNTANT": ("Accountant", D.FINANCE, Level.OFFICER),
    "REVENUE_CLERK": ("Revenue Clerk / Cashier", D.FINANCE, Level.CLERK),
    "EXPENDITURE_CLERK": ("Expenditure Clerk", D.FINANCE, Level.CLERK),
    # Internal audit
    "CHIEF_AUDITOR": ("Chief Internal Auditor", D.INTERNAL_AUDIT, Level.HEAD),
    "AUDITOR": ("Internal Auditor", D.INTERNAL_AUDIT, Level.OFFICER),
    # Social services (incl. WASH, Natural Resources, Public Safety)
    "SOCIAL_HEAD": ("Director of Social Services", D.SOCIAL_SERVICES, Level.HEAD),
    "SOCIAL_OFFICER": ("Social Services Officer", D.SOCIAL_SERVICES, Level.OFFICER),
    "HEALTH_OFFICER": ("Environmental Health Officer (WASH)", D.SOCIAL_SERVICES, Level.OFFICER),
    "NATURAL_RESOURCES_OFFICER": ("Natural Resources Officer", D.SOCIAL_SERVICES, Level.OFFICER),
    "SAFETY_OFFICER": ("Public Safety & Disaster Risk Officer", D.SOCIAL_SERVICES, Level.OFFICER),
    # Technical services
    "ENGINEER": ("District Engineer (Head of Technical Services)", D.TECHNICAL_SERVICES, Level.HEAD),
    "TECHNICAL_OFFICER": ("Technical Officer", D.TECHNICAL_SERVICES, Level.OFFICER),
    "BUILDING_INSPECTOR": ("Building Inspector / Development Control", D.TECHNICAL_SERVICES, Level.OFFICER),
}

ROLE_CHOICES = [(code, label) for code, (label, _d, _l) in ROLES.items()]

# Capabilities every staff member has.
STAFF_BASE = {
    "dashboard",
    "tasks.view",
    "complaints.department",
    "requests.department",
    "requisition.create",
    "leave.apply",
}

HEAD_CAPS = {
    "tasks.assign_department",
    "requisition.hod_approve",
    "leave.approve",
    "audit.respond",
    "reports.department",
}

FINANCE_READ = {"finance.view", "finance.view_all", "finance.reports"}

ROLE_CAPS = {
    "SYSADMIN": {"users.manage", "audit.view_trail", "audit.view_all", "system.settings"},
    "CEO": HEAD_CAPS
    | FINANCE_READ
    | {
        "tasks.assign_any",
        "complaints.view_all",
        "requests.view_all",
        "requisition.authorise",
        "voucher.authorise",
        "audit.view_trail",
        "audit.view_all",
        "audit.findings_view",
        "reports.executive",
        "users.view",
        "stands.view",
        "projects.view",
        "budget.view",
        "licence.view",
        "hr.view",
    },
    "EXEC_ASSISTANT": {"complaints.view_all", "correspondence.manage", "tasks.assign_any"},
    # Administration
    "ADMIN_OFFICER": HEAD_CAPS
    | {"complaints.view_all", "correspondence.manage", "hr.manage", "hr.view", "users.view", "procurement.order"},
    "HR_OFFICER": {"hr.manage", "hr.view"},
    "PROCUREMENT_OFFICER": {"procurement.order", "supplier.manage", "finance.view"},
    "RECORDS_CLERK": {"correspondence.manage"},
    # Finance
    "TREASURER": HEAD_CAPS
    | FINANCE_READ
    | {
        "receipt.create",
        "receipt.void_approve",
        "accounts.manage",
        "billing.run",
        "licence.view",
        "licence.manage",
        "licence.approve",
        "supplier.manage",
        "voucher.prepare",
        "voucher.check",
        "voucher.approve",
        "voucher.pay",
        "requisition.finance_check",
        "requisition.approve",
        "procurement.order",
        "budget.manage",
        "budget.view",
        "bank.manage",
        "cashup.verify",
        "audit.view_trail",
        "payments.online_view",
    },
    "ACCOUNTANT": FINANCE_READ
    | {
        "receipt.create",
        "receipt.void_approve",
        "accounts.manage",
        "billing.run",
        "licence.view",
        "licence.manage",
        "supplier.manage",
        "voucher.prepare",
        "voucher.check",
        "requisition.finance_check",
        "procurement.order",
        "budget.view",
        "bank.manage",
        "cashup.verify",
        "payments.online_view",
    },
    "REVENUE_CLERK": {"finance.view", "receipt.create", "receipt.void_request", "accounts.manage", "licence.view", "licence.manage", "cashup.submit"},
    "EXPENDITURE_CLERK": {"finance.view", "supplier.manage", "voucher.prepare", "voucher.pay", "procurement.order", "budget.view"},
    # Internal audit - read everything, change nothing operational
    "CHIEF_AUDITOR": HEAD_CAPS
    | FINANCE_READ
    | {"audit.view_trail", "audit.view_all", "audit.findings_manage", "audit.findings_view", "complaints.view_all",
       "requests.view_all", "budget.view", "licence.view", "stands.view", "projects.view", "hr.view", "payments.online_view"},
    "AUDITOR": FINANCE_READ
    | {"audit.view_trail", "audit.view_all", "audit.findings_manage", "audit.findings_view", "budget.view", "licence.view",
       "stands.view", "projects.view", "payments.online_view"},
    # Social services
    "SOCIAL_HEAD": HEAD_CAPS | {"stands.manage", "stands.view", "stands.allocate", "licence.view", "licence.inspect"},
    "SOCIAL_OFFICER": {"stands.manage", "stands.view"},
    "HEALTH_OFFICER": {"licence.view", "licence.inspect"},
    "NATURAL_RESOURCES_OFFICER": set(),
    "SAFETY_OFFICER": set(),
    # Technical services
    "ENGINEER": HEAD_CAPS | {"projects.manage", "projects.view", "stands.view"},
    "TECHNICAL_OFFICER": {"projects.manage", "projects.view"},
    "BUILDING_INSPECTOR": {"projects.view", "licence.view", "licence.inspect", "stands.view"},
}

CLIENT_CAPS = {"portal.use"}


def role_label(code):
    return ROLES.get(code, (code or "", None, None))[0]


def role_department(code):
    return ROLES.get(code, (None, None, None))[1]


def role_level(code):
    return ROLES.get(code, (None, None, None))[2]


def capabilities_for(role):
    caps = set(STAFF_BASE)
    caps |= ROLE_CAPS.get(role, set())
    return caps
