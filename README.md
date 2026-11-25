# Chipinge RDC – Council Management System

An integrated, offline-capable system for **Chipinge Rural District Council**, built around the
**Client Charter 2026–2030** ([photo](docs/client-charter-2026-2030.jpg)).

| Part | Technology | Who uses it |
|------|-----------|-------------|
| `backend/` – council website, client web portal, REST/sync API | Python 3.12+ · Django 5 · SQL (PostgreSQL in production, SQLite for development) | All council staff, residents, ratepayers, businesses |
| `mobile/councilApp` – **Council staff app** | Kotlin Multiplatform + Compose Multiplatform (Android & iOS) | Staff, role-based, works offline |
| `mobile/clientApp` – **Community app** | Kotlin Multiplatform + Compose Multiplatform (Android & iOS) | Residents & businesses: pay rates, licences, report problems |
| `mobile/shared` | Kotlin: SQLDelight (on-phone SQL database), Ktor (API), sync engine, UI kit | Used by both apps |

The Finance department is the most complete part, as requested. Every other department in the charter
has its core registers and workflows.

---

## 1. What the system does, per department

| Charter department / function | Implemented |
|---|---|
| **Office of the CEO** | Executive overview of all departments, charter-compliance scores (complaints acknowledged within 48h, requests resolved on time, correspondence answered within 7 working days), CEO authorisation of large payments/requisitions, assigning tasks / requests / memos to anyone, full audit-trail access |
| **Finance** – revenue collection | Receipting counter (USD & ZWG with exchange rates, cash/EcoCash/OneMoney/InnBucks/swipe/bank), receipts can never be edited or deleted – only voided through a request + second-person approval, automatic allocation of payments to the oldest bills, client (ratepayer) accounts & properties/stands, monthly rates billing run, bills/levies, statements (print & CSV), end-of-day **cash-ups** with variance reporting, online payments (Paynow / simulated test gateway) with immediate receipt |
| **Finance** – licences | Shop, hawker, business, liquor, health, transport, advertising licences: application (counter or client app) → health/building inspection → Treasurer approval → fee bill → **issued automatically when paid** → printable certificate → expiry |
| **Finance** – expenditure & procurement | Purchase requisitions from any department → HOD → Accountant funds check against the budget vote → Treasurer → CEO (≥ threshold) → purchase order → goods received → payment voucher → Accountant check → Treasurer approval → CEO authorisation (≥ threshold) → payment from a bank account. **Segregation of duties** is enforced (nobody approves their own document or two stages of the same document; blacklisted suppliers blocked; overspending a vote blocked; paying more than the bank balance blocked) |
| **Finance** – budgeting & reporting | Budget votes per department (income, expenditure, capital) with actual, committed and available; bank accounts & cashbook; exchange rates; revenue heads/tariffs; reports: income by revenue head / method / channel / cashier / ward, expenditure by vote & category, debtors age analysis, CSV exports |
| **Administration** | Staff user management (only by the ICT administrator), HR leave applications & approvals, staff directory, correspondence register (7-working-day standard), procurement officer role |
| **Internal Audit** | Read access to all finance data and the audit trail, audit findings (compliance, risk, systems, performance, cash) with risk ratings, management responses and close-out |
| **Social Services** (incl. WASH, Natural Resources, Public Safety) | Stand applications / allocation, water & borehole faults, refuse, public health, human-wildlife conflict, fires & disasters (service requests with charter deadlines), Environmental Health Officer licence inspections |
| **Technical Services** | Projects (roads, water, schools & clinics, lighting, housing) with budget and progress, road/lighting/building service requests, building-inspector licence inspections |
| **Clients' rights / Feedback & complaints** | Complaints, compliments, suggestions & enquiries from every channel on the charter (CEO, suggestion box, offices, email, phone, consultations, social media) plus portal & app; 48-hour acknowledgement clock, breach flags and CEO/HOD alerts |
| **Digital service delivery** | Electronic billing, e-payments, online enquiries, digital records, client web portal and app, notifications |

### Role-based access
Users log in with the account the ICT administrator created for them (there is **no staff self-registration**;
new staff must change their temporary password at first login; 5 wrong passwords lock the account for 15 minutes).
What a user sees and can do is decided by their **role**, which belongs to a department:

| Department | Roles |
|---|---|
| Office of the CEO | Chief Executive Officer, Executive Assistant |
| Administration | Administration Officer (HOD), HR Officer, Procurement Officer, Records Clerk, **ICT / System Administrator** |
| Finance | **Treasurer** (HOD – oversees everything in Finance), **Accountant**, Revenue Clerk / Cashier, Expenditure Clerk |
| Internal Audit | Chief Internal Auditor (HOD), Internal Auditor |
| Social Services | Director of Social Services (HOD), Social Services Officer, Environmental Health Officer, Natural Resources Officer, Public Safety Officer |
| Technical Services | District Engineer (HOD), Technical Officer, Building Inspector |

Roles map to *capabilities* in one file (`backend/accounts/roles.py`), so changing who may do what is a one-line change.
The same rules are enforced on the website, the API and the mobile sync.

### Restricted administration page
`/system-admin/` is the low-level administration site. Only the ICT / System Administrator (superuser) can open it –
even the CEO is refused. Financial transactions are **read-only** there; they can only be created through the
controlled workflows. Day-to-day staff registration is done on **User management** (`/accounts/users/`).

### Audit trail
Every create/update/void/approval/login/failed login/access-denied/export/mobile-sync is written to an
**append-only, hash-chained audit log** (who, what changed – old → new values, when, IP address, web/API/mobile).
Entries cannot be edited or deleted through the application, and any direct database tampering is detected by
*Audit trail → Verify chain* or `python manage.py verify_audit_chain`. Each financial document also shows its
approval history.

---

## 2. Offline-first design

**Mobile apps.** Each phone keeps its own SQL database (SQLDelight/SQLite) containing only the records the
user's role allows. Screens always read from that database, so the apps work the same with or without signal.
Work done offline (receipts, approvals, inspections, complaints, fault reports, task updates, leave, licence
applications…) is stored as *operations* in an outbox, shown immediately, and uploaded automatically:
every 30 s while work is queued, every 15 minutes in the background (Android WorkManager), whenever the
connection returns, and when the app returns to the foreground (iOS). Each operation carries a UUID, so a
retry after a dropped connection is never applied twice. The server re-checks every permission and business
rule at upload time; anything it rejects is shown in the **Sync centre** with the reason.
Online payments need a live connection (the mobile-money prompt is real-time).

**Website.** A service worker caches pages and assets: staff can open pages they have visited before
while offline, and forms marked *offline ready* (complaints, service requests, stand applications) are saved in
the browser and submitted automatically on reconnect (with idempotency keys to prevent duplicates).

---

## 3. Quick start (development)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_council --demo        # charter standards, revenue heads, budget, demo users & data
python manage.py runserver 0.0.0.0:8000
```

Open http://localhost:8000. Demo password for every demo user: **`Chipinge@2026`** (never use `--demo` in production).

| Username | Role |
|---|---|
| `ceo` | Chief Executive Officer |
| `ict.admin` | ICT / System Administrator (only user allowed into `/system-admin/`) |
| `treasurer`, `accountant`, `cashier`, `exp.clerk` | Finance |
| `admin.officer`, `hr.officer`, `procurement`, `registry` | Administration |
| `chief.auditor`, `auditor` | Internal Audit |
| `social.director`, `social.officer`, `eho` | Social Services |
| `engineer`, `tech.officer` | Technical Services |
| `resident` | Client portal / client app (linked to account of Johannes Mhlanga) |

Run the tests: `python manage.py test tests` (37 tests: workflows, segregation of duties, access control, lockout,
audit-chain tamper detection, charter deadlines, sync idempotency & scoping, online payments).

**Mobile apps** – see [`mobile/README.md`](mobile/README.md). In short: open `mobile/` in Android Studio and run
`councilApp` or `clientApp`; for iOS run `xcodegen` in `mobile/iosCouncilApp` / `mobile/iosClientApp` and open in Xcode.

## 4. Production

* Copy `backend/.env.example` to `backend/.env`, set a secret key, `DJANGO_DEBUG=False`, the host name and a
  PostgreSQL `DATABASE_URL`.
* `python manage.py migrate && python manage.py collectstatic --noinput`
* `python manage.py seed_council --admin-password '<strong password>'` creates the ICT administrator, who then
  registers all staff.
* Serve with `gunicorn crdc.wsgi` behind Nginx with HTTPS.
* Schedule `python manage.py daily_finance_jobs` daily (expires licences, raises monthly rates on the 1st,
  alerts on complaints that breached the 48-hour standard) and back up the database.
* Set `PAYMENT_GATEWAY=paynow` with the council's Paynow integration ID/key to take real payments.

## 5. Project layout

```
backend/
  crdc/          settings & URLs
  core/          audit trail, charter service standards, SLA/working-day calendar, dashboards, notifications
  accounts/      users, roles & capabilities, login lockout, user management
  finance/       revenue, accounts, bills, receipts, cash-ups, licences, budget, banks, procurement, vouchers, reports
  workflow/      tasks/memos, complaints & feedback, service requests, correspondence
  departments/   leave (HR), stand allocation, projects, internal-audit findings
  portal/        client web portal (pay, statements, licences, complaints, problems, stands)
  api/           JWT auth, offline sync (pull/push), payments
  tests/         automated tests
mobile/
  shared/        SQLDelight database, Ktor API client, sync engine, UI kit
  councilApp/    council staff app (Android + iOS)
  clientApp/     community app (Android + iOS)
  iosCouncilApp/ iosClientApp/   Xcode (XcodeGen) wrappers
docs/            client charter photo
```
