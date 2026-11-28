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
    "ADMIN_OFFICER": ("Human Resources & Administration Officer (Head of Administration)", D.ADMINISTRATION, Level.HEAD),
    "HR_OFFICER": ("Human Resources Officer", D.ADMINISTRATION, Level.OFFICER),
    "LIAISON_OFFICER": ("Community Liaison & Public Relations Officer", D.ADMINISTRATION, Level.OFFICER),
    "LAND_OFFICER": ("Land & Asset Management Officer", D.ADMINISTRATION, Level.OFFICER),
    "DATA_OFFICER": ("Data & Information Management Officer", D.ADMINISTRATION, Level.OFFICER),
    "PROCUREMENT_OFFICER": ("Procurement Officer", D.ADMINISTRATION, Level.OFFICER),
    "RECORDS_CLERK": ("Records Management / Registry Clerk", D.ADMINISTRATION, Level.CLERK),
    "RECEPTIONIST": ("Receptionist / Customer Care Officer", D.ADMINISTRATION, Level.CLERK),
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
    "NATURAL_RESOURCES_OFFICER": ("Environmental Management & Agricultural Officer", D.SOCIAL_SERVICES, Level.OFFICER),
    "SOCIAL_OFFICER": ("Community Development Officer", D.SOCIAL_SERVICES, Level.OFFICER),
    "HEALTH_OFFICER": ("Environmental Health Officer (public health & WASH)", D.SOCIAL_SERVICES, Level.OFFICER),
    "SAFETY_OFFICER": ("Public Safety & Disaster Risk Officer", D.SOCIAL_SERVICES, Level.OFFICER),
    # Technical services
    "ENGINEER": ("District Engineer (Head of Technical Services)", D.TECHNICAL_SERVICES, Level.HEAD),
    "TECHNICAL_OFFICER": ("Technical Officer (roads, lighting & engineering)", D.TECHNICAL_SERVICES, Level.OFFICER),
    "BUILDING_INSPECTOR": ("Building Inspector / Development Control", D.TECHNICAL_SERVICES, Level.OFFICER),
    # Growth points: housing, stands, shops and council premises at every growth point
    "GROWTH_POINT_MANAGER": ("Growth Point Manager", D.GROWTH_POINTS, Level.HEAD),
    # Any department: the department is chosen when the intern's account is created
    "INTERN": ("Intern / Attachment student", None, Level.CLERK),
}

# Roles that can be placed in any department (the role itself does not fix the department).
ANY_DEPARTMENT_ROLES = {"INTERN"}


ROLE_CHOICES = [(code, label) for code, (label, _d, _l) in ROLES.items()]

# Capabilities every staff member has. These are "self-service" and
# cross-department links only (my tasks, memos to other departments, my own
# requests for funds / purchases, leave, ICT help). Everything else belongs to
# a department and is granted only to that department's roles, so e.g. a
# Technical Services officer never sees Finance or Social Services registers.
STAFF_BASE = {
    "dashboard",
    "ict.raise",
    "tasks.view",
    "memos.send",
    "funds.request",
    "complaints.assigned",
    "requests.department",
    "requisition.create",
    "leave.apply",
}

HEAD_CAPS = {
    "dept.overview",
    "complaints.department",
    "funds.hod_approve",
    "risks.view",
    "resolutions.update",
    "activities.verify",
    "tasks.assign_department",
    "requisition.hod_approve",
    "leave.approve",
    "audit.respond",
    "reports.department",
}

FINANCE_READ = {"finance.view", "finance.view_all", "finance.reports", "fines.view"}

# Social Services registers: read access for oversight (CEO, internal audit)
SOCIAL_READ = {"wildlife.view", "hunts.view", "permits.view", "farms.view", "water.view", "health.view", "sanitation.view",
               "facilities.view"}
TECH_READ = {"roads.view", "lighting.view", "works.view"}
ADMIN_READ = {"records.view", "land.view", "engagements.view", "notices.view", "data.view"}
# Officers who enforce by-laws and may issue fines
FINE_ISSUERS = {"fines.issue", "fines.view"}

ROLE_CAPS = {
    "SYSADMIN": {"records.view", "ict.manage", "assets.manage", "assets.view", "meetings.view", "policies.view", "users.manage", "audit.view_trail", "audit.view_all", "system.settings"},
    "CEO": HEAD_CAPS
    | FINANCE_READ
    | {
        "tasks.assign_any",
        "complaints.view_all",
        "requests.view_all",
        "requisition.authorise",
        "voucher.authorise",
        "funds.ceo_approve",
        "funds.view_all",
        "payroll.view",
        "payroll.approve",
        "assets.view",
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
        "incidents.view",
        "plans.view",
        "meetings.manage",
        "meetings.view",
        "policies.manage",
        "policies.view",
        "areas.view",
        "leases.view",
        "messages.view",
        "fines.waive",
        "leave.ceo_approve",
        "auditplan.view",
        "notices.manage",
    }
    | SOCIAL_READ | TECH_READ | ADMIN_READ,
    "EXEC_ASSISTANT": {"meetings.manage", "meetings.view", "policies.view", "complaints.view_all", "correspondence.manage", "tasks.assign_any"},
    # Administration
    "ADMIN_OFFICER": HEAD_CAPS
    | {"complaints.view_all", "correspondence.manage", "hr.manage", "hr.view", "users.view", "procurement.order", "meetings.manage",
       "meetings.view", "policies.manage", "policies.view", "activities.manage", "assets.manage", "assets.view", "funds.admin_approve",
       "complaints.manage", "leave.hr_approve", "records.view", "records.manage"} | ADMIN_READ | {"notices.manage", "land.manage"},
    "HR_OFFICER": {"activities.manage", "hr.manage", "hr.view", "meetings.view", "policies.view", "leave.hr_approve"},
    # Community liaison & PR: WADCO / village assemblies, consultations, public notices to residents (client app)
    "LIAISON_OFFICER": {"engagements.manage", "engagements.view", "notices.manage", "notices.view", "activities.manage", "policies.view",
                        "meetings.view", "correspondence.manage"},
    # Land & asset management: council land bank, assets register, leases and stands information
    "LAND_OFFICER": {"land.manage", "land.view", "assets.manage", "assets.view", "leases.view", "areas.view", "stands.view", "plans.view"},
    # Data & information management (ICT services): statistics, data quality, exports, register imports
    "DATA_OFFICER": {"data.view", "data.manage", "records.view", "ict.raise", "users.view"},
    "PROCUREMENT_OFFICER": {"procurement.order", "supplier.manage", "meetings.view", "policies.view", "assets.view"},
    "RECORDS_CLERK": {"meetings.manage", "meetings.view", "policies.view", "correspondence.manage", "records.view", "records.manage"},
    # Front desk: receives every complaint, compliment, suggestion and enquiry and routes it to the right officer.
    "RECEPTIONIST": {"complaints.view_all", "complaints.manage", "correspondence.manage", "policies.view"},
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
        "funds.treasurer_approve",
        "funds.view_all",
        "payroll.manage",
        "payroll.approve",
        "payroll.pay",
        "payroll.view",
        "procurement.order",
        "budget.manage",
        "budget.view",
        "bank.manage",
        "cashup.verify",
        "audit.view_trail",
        "payments.online_view",
        "areas.view",
        "areas.manage",
        "leases.view",
        "leases.manage",
        "claims.review",
        "reminders.send",
        "messages.view",
        "assets.manage",
        "assets.view",
        "fines.issue",
        "fines.waive",
        "offences.manage",
        "hunts.view",
        "permits.view",
        "farms.view",
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
        "areas.view",
        "areas.manage",
        "leases.view",
        "leases.manage",
        "claims.review",
        "reminders.send",
        "messages.view",
        "assets.manage",
        "assets.view",
        "funds.view_all",
        "payroll.manage",
        "payroll.view",
        "fines.issue",
        "hunts.view",
        "permits.view",
        "farms.view",
    },
    "REVENUE_CLERK": {"fines.issue", "fines.view", "farms.view", "claims.review", "reminders.send", "areas.view", "leases.view", "finance.view", "receipt.create", "receipt.void_request", "accounts.manage", "licence.view", "licence.manage", "cashup.submit"},
    "EXPENDITURE_CLERK": {"payroll.pay", "payroll.view", "assets.manage", "assets.view", "funds.view_all", "finance.view", "supplier.manage", "voucher.prepare", "voucher.pay", "procurement.order", "budget.view"},
    # Internal audit - read everything, change nothing operational
    "CHIEF_AUDITOR": {"auditplan.manage", "auditplan.view"} | HEAD_CAPS
    | FINANCE_READ
    | {"audit.view_trail", "audit.view_all", "audit.findings_manage", "audit.findings_view", "complaints.view_all",
       "requests.view_all", "budget.view", "licence.view", "stands.view", "projects.view", "hr.view", "payments.online_view", "risks.manage",
       "incidents.view", "plans.view", "areas.view", "leases.view", "messages.view", "dept.overview_all", "assets.view",
       "meetings.view", "policies.view", "funds.view_all", "payroll.view"} | SOCIAL_READ | TECH_READ | ADMIN_READ,
    "AUDITOR": {"auditplan.manage", "auditplan.view"} | FINANCE_READ
    | {"audit.view_trail", "audit.view_all", "audit.findings_manage", "audit.findings_view", "budget.view", "licence.view",
       "stands.view", "projects.view", "payments.online_view", "risks.manage", "risks.view", "incidents.view", "plans.view", "areas.view",
       "leases.view", "assets.view", "meetings.view", "policies.view", "funds.view_all", "payroll.view"} | SOCIAL_READ | TECH_READ | ADMIN_READ,
    # Social services
    # Social Services – each officer works on their own functions; the Director sees and decides on everything
    "SOCIAL_HEAD": HEAD_CAPS | SOCIAL_READ | FINE_ISSUERS
    | {"stands.view", "licence.inspect", "activities.manage", "incidents.manage", "incidents.view", "assets.condition", "assets.view",
       "wildlife.manage", "hunts.manage", "permits.manage", "permits.approve", "farms.manage", "water.manage",
       "health.manage", "sanitation.manage", "facilities.manage"},
    # Natural resources & environment + agriculture: CAMPFIRE, human-wildlife conflict, fire management, land reclamation, permits, farms
    "NATURAL_RESOURCES_OFFICER": FINE_ISSUERS | {"activities.manage", "incidents.manage", "incidents.view", "wildlife.manage", "wildlife.view",
                                                 "hunts.manage", "hunts.view", "permits.manage", "permits.approve", "permits.view", "farms.manage",
                                                 "farms.view"},
    # Community services, schools & clinics development, disaster risk / public safety
    "SOCIAL_OFFICER": {"activities.manage", "incidents.manage", "incidents.view", "facilities.manage",
                       "facilities.view", "assets.condition", "assets.view"},
    # Public health and WASH: health inspections & certificates, water points, ablutions & waste, hygiene promotion
    "HEALTH_OFFICER": FINE_ISSUERS | {"licence.inspect", "activities.manage", "incidents.view", "assets.condition", "assets.view", "water.manage",
                                      "water.view", "health.manage", "health.view", "sanitation.manage", "sanitation.view"},
    "SAFETY_OFFICER": FINE_ISSUERS | {"activities.manage", "incidents.manage", "incidents.view"},
    # Technical services
    "ENGINEER": HEAD_CAPS | TECH_READ | {"roads.manage", "lighting.manage", "works.manage", "works.assign", "water.view", "projects.manage", "projects.view", "plans.view", "plans.review", "plans.approve", "assets.condition", "assets.view"},
    "TECHNICAL_OFFICER": TECH_READ | {"roads.manage", "lighting.manage", "works.manage", "projects.manage", "projects.view", "plans.view", "plans.review", "assets.condition", "assets.view"},
    "BUILDING_INSPECTOR": FINE_ISSUERS | {"works.view", "projects.view", "plans.view", "plans.review", "assets.view"},
    # Growth Points: oversees every growth point – housing & stand allocation, the houses / shops / stands there, council premises
    "GROWTH_POINT_MANAGER": HEAD_CAPS | FINE_ISSUERS
    | {"stands.view", "stands.manage", "stands.allocate", "areas.view", "areas.manage", "leases.view", "plans.view", "projects.view",
       "growth.manage", "reminders.send", "messages.view"},
}

# Letters & certificates for residents: each office issues its own kind (see finance.services.CERTIFICATES).
for _role in ("TREASURER", "ACCOUNTANT", "REVENUE_CLERK", "ADMIN_OFFICER", "LAND_OFFICER", "RECORDS_CLERK", "RECEPTIONIST", "SOCIAL_HEAD",
              "HEALTH_OFFICER", "GROWTH_POINT_MANAGER", "CEO"):
    ROLE_CAPS[_role] = set(ROLE_CAPS[_role]) | {"certificates.issue"}

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
