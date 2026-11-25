# Chipinge RDC mobile apps (Kotlin Multiplatform)

Two apps share one Kotlin codebase and run on **Android and iOS**:

* **councilApp** – for council staff; the home screen is grouped by department and shows only what the role allows:
  * *General*: department overview for heads (staff, tasks, budget, everything waiting for the HOD), approvals, tasks,
    assign tasks (HODs/CEO), **raise purchase requisitions** (any officer → HOD → Accountant → Treasurer → CEO), notifications.
  * *Finance*: receipting (works offline), receipts, client accounts, **shops by area with paid/unpaid status and SMS reminders**,
    stand-registration approvals, leases, licences, budget vs actual.
  * *Social services*: stand applications (shortlist / allocate), incidents & disasters (report, response updates, Director closes),
    community programmes (plan, report, HOD verifies).
  * *Technical services*: projects (site progress updates), building plans (review → Engineer decision → inspections).
  * *Internal audit*: findings (HOD management responses), risk register.
  * *Administration*: council meetings & resolutions (progress updates), policies & by-laws, assets & infrastructure
    (field condition reports – e.g. a broken borehole), ICT helpdesk, leave.
  * Complaints and service requests for every department, Client Charter, Sync centre.
* **clientApp** – for residents and businesses: register, **register a stand / shop** (auto-linked or verified by council),
  link a council account, view balance and bills, **pay rates / levies / rent / licence fees** with EcoCash, OneMoney or InnBucks,
  payment history and receipts, apply for licences (linked to the shop's stand), **submit building plans**, report problems,
  complaints/compliments/suggestions, stand applications, notifications.

`shared/` contains the on-phone SQL database (SQLDelight), the API client (Ktor), the offline **sync engine**
and the common UI components. Business rules live on the server; the apps queue operations and the
server validates them (see the main README, section 2).

## Requirements
* JDK 17, Android Studio (Ladybug or newer) with the Kotlin Multiplatform plugin
* For iOS: a Mac with Xcode 15+ and [XcodeGen](https://github.com/yonaskolb/XcodeGen) (`brew install xcodegen`)

## Server address
* Android: the default comes from `councilServerUrl` in `gradle.properties` (`http://10.0.2.2:8000` = the
  development server on the computer running the Android emulator). Build for production with
  `./gradlew :councilApp:assembleRelease -PcouncilServerUrl=https://ems.chipingerdc.gov.zw`.
* iOS: `CRDCServerURL` in each `project.yml`.
* Users can also change it on the login screen under *Server settings*.

## Build & run
```bash
cd mobile
./gradlew :councilApp:installDebug      # council staff app on a connected device/emulator
./gradlew :clientApp:installDebug       # community app
```
iOS:
```bash
cd mobile/iosCouncilApp && xcodegen && open iosCouncilApp.xcodeproj   # or iosClientApp
```
The Xcode project's pre-build step compiles the Kotlin framework (`embedAndSignAppleFrameworkForXcode`).

## Offline behaviour in short
* Everything you can see is in the phone's database – it works with no signal.
* Changes are queued (outbox) and shown immediately with a "pending sync" note.
* Sync runs automatically (30 s while work is queued, otherwise every few minutes, plus Android background
  sync every 15 min and on reconnect). The coloured bar under the title shows the status; tap it to sync now.
* If the server rejects something (e.g. you no longer have permission, a budget is exhausted), the Sync centre
  shows the reason.
* Logging in as a different user on the same phone wipes the previous user's offline data.

## Verification done
The shared module and all screens of both apps were compiled for the JVM target, and the real sync engine was
run end-to-end against the Django server (login, role-scoped pull, offline receipt → queue → reconnect →
server receipt number, rejected operation handling, client login separation, online payment, offline
complaint, an officer's requisition raised on the phone and approved by the HOD on another phone, department-scoped
staff lists, the shop register for an area, reminders sent from the phone, and a client's stand registration). The Android and iOS targets are built by the GitHub Actions workflow (`.github/workflows/ci.yml`).
