package zw.gov.chipingerdc.shared.model

import kotlinx.serialization.Serializable

/** Entity names used by the sync protocol (must match the server's api/sync.py). */
object Entities {
    const val SERVICE_STANDARDS = "service_standards"
    const val REVENUE_HEADS = "revenue_heads"
    const val ACCOUNTS = "accounts"
    const val PROPERTIES = "properties"
    const val BILLS = "bills"
    const val RECEIPTS = "receipts"
    const val LICENCES = "licences"
    const val REQUISITIONS = "requisitions"
    const val VOUCHERS = "vouchers"
    const val BUDGET_LINES = "budget_lines"
    const val TASKS = "tasks"
    const val TASK_COMMENTS = "task_comments"
    const val COMPLAINTS = "complaints"
    const val SERVICE_REQUESTS = "service_requests"
    const val STANDS = "stands"
    const val PROJECTS = "projects"
    const val AUDIT_FINDINGS = "audit_findings"
    const val LEAVE = "leave"
    const val NOTIFICATIONS = "notifications"
    const val ONLINE_PAYMENTS = "online_payments"
    const val STAFF = "staff"
    const val TRADING_AREAS = "trading_areas"
    const val LEASES = "leases"
    const val CLAIMS = "claims"
    const val ASSETS = "assets"
    const val INCIDENTS = "incidents"
    const val ACTIVITIES = "activities"
    const val BUILDING_PLANS = "building_plans"
    const val RISKS = "risks"
    const val MEETINGS = "meetings"
    const val RESOLUTIONS = "resolutions"
    const val ICT_TICKETS = "ict_tickets"
    const val POLICIES = "policies"
    const val FUNDS_REQUESTS = "funds_requests"
    const val MEMOS = "memos"
    const val CASHUPS = "cashups"
    const val SUPPLIERS = "suppliers"
    const val PURCHASE_ORDERS = "purchase_orders"
    const val BANK_ACCOUNTS = "bank_accounts"
    const val CORRESPONDENCE = "correspondence"
    const val SALARY_PROFILES = "salary_profiles"
    const val PAYSLIPS = "payslips"
    const val TAX_TABLES = "tax_tables"
    const val OFFENCES = "offences"
    const val FINES = "fines"
    const val WILDLIFE = "wildlife"
    const val HUNTING_QUOTAS = "hunting_quotas"
    const val TROPHY_HUNTS = "trophy_hunts"
    const val RESOURCE_PERMITS = "resource_permits"
    const val FARMS = "farms"
    const val WATER_POINTS = "water_points"
    const val BENEFICIARIES = "beneficiaries"
}

@Serializable
data class ServiceStandard(val id: Long = 0, val code: String = "", val service: String = "", val standardText: String = "", val isDigital: Boolean = false)

@Serializable
data class RevenueHead(
    val id: String, val code: String = "", val name: String = "", val category: String = "", val categoryLabel: String = "",
    val defaultAmount: String = "0", val frequency: String = "", val payableOnline: Boolean = true, val isActive: Boolean = true,
)

@Serializable
data class ClientAccount(
    val id: String, val accountNumber: String = "", val accountType: String = "", val accountTypeLabel: String = "", val name: String = "",
    val idNumber: String = "", val phone: String = "", val email: String = "", val postalAddress: String = "", val ward: Int? = null,
    val status: String = "", val statusLabel: String = "", val balance: String = "0",
)

@Serializable
data class Property(
    val id: String, val account: String = "", val accountName: String = "", val accountNumber: String = "", val accountPhone: String = "",
    val registered: Boolean = false, val area: String? = null, val areaName: String = "", val standNumber: String = "", val businessName: String = "",
    val location: String = "", val ward: Int? = null, val landUse: String = "", val landUseLabel: String = "", val valuation: String = "0",
    val monthlyRates: String = "0", val hectares: String? = null, val isCouncilOwned: Boolean = false, val isActive: Boolean = true,
)

@Serializable
data class Bill(
    val id: String, val number: String = "", val account: String = "", val property: String? = null, val revenueHead: String = "",
    val revenueHeadCategory: String = "", val description: String = "",
    val period: String = "", val amount: String = "0", val amountPaid: String = "0", val outstanding: String = "0",
    val issueDate: String = "", val dueDate: String = "", val status: String = "", val statusLabel: String = "",
)

@Serializable
data class Receipt(
    val id: String, val number: String = "", val receivedBy: Long? = null, val voidRequestedBy: Long? = null, val voidReason: String = "",
    val account: String? = null, val accountNumber: String? = null, val payerName: String = "",
    val revenueHead: String = "", val revenueHeadName: String = "", val bill: String? = null, val description: String = "",
    val currency: String = "USD", val amount: String = "0", val baseAmount: String = "0", val method: String = "", val methodLabel: String = "",
    val reference: String = "", val channel: String = "", val channelLabel: String = "", val receivedByName: String? = null,
    val status: String = "", val statusLabel: String = "", val createdAt: String = "", val offlineCreatedAt: String? = null,
    val localNote: String? = null,
)

@Serializable
data class Licence(
    val id: String, val number: String = "", val licenceType: String = "", val licenceTypeLabel: String = "", val account: String = "",
    val property: String? = null,
    val accountNumber: String = "", val businessName: String = "", val businessActivity: String = "", val premises: String = "",
    val ward: Int? = null, val status: String = "", val statusLabel: String = "", val fee: String = "0", val bill: String? = null,
    val inspectionNotes: String = "", val rejectionReason: String = "", val issueDate: String? = null, val expiryDate: String? = null,
    val dueAt: String? = null, val createdAt: String = "", val localNote: String? = null,
    /** Shops: licence fee, lease and levy still owing – the licence is issued by itself once this is empty. */
    val stillToPay: List<Owing> = emptyList(),
)

@Serializable
data class Owing(val label: String = "", val amount: String = "0")

@Serializable
data class RequisitionItem(val description: String = "", val quantity: String = "", val unitCost: String = "", val total: String = "")

@Serializable
data class Requisition(
    val id: String, val number: String = "", val department: String = "", val departmentLabel: String = "", val requestedBy: Long? = null,
    val requestedByName: String = "", val needsCeo: Boolean = false,
    val purpose: String = "", val total: String = "0", val status: String = "", val statusLabel: String = "", val rejectionReason: String = "",
    val items: List<RequisitionItem> = emptyList(), val createdAt: String = "", val localNote: String? = null,
)

@Serializable
data class Voucher(
    val id: String, val number: String = "", val category: String = "", val categoryLabel: String = "", val payeeName: String = "",
    val department: String = "", val vote: String? = null, val description: String = "", val invoiceNumber: String = "",
    val currency: String = "USD", val amount: String = "0", val baseAmount: String = "0", val method: String = "", val methodLabel: String = "",
    val status: String = "", val statusLabel: String = "", val preparedBy: Long? = null, val preparedByName: String = "",
    val needsCeo: Boolean = false, val paymentReference: String = "",
    val paidAt: String? = null, val rejectionReason: String = "", val createdAt: String = "", val localNote: String? = null,
)

@Serializable
data class BudgetLine(
    val id: String, val financialYear: Int = 0, val voteCode: String = "", val description: String = "", val department: String = "",
    val kind: String = "", val kindLabel: String = "", val approvedAmount: String = "0", val revisedAmount: String? = null,
    val actual: String = "0", val committed: String = "0",
)

@Serializable
data class Task(
    val id: String, val reference: String = "", val kind: String = "", val kindLabel: String = "", val title: String = "",
    val description: String = "", val assignedByName: String = "", val assignedToName: String? = null, val department: String = "",
    val departmentLabel: String = "", val priority: String = "", val priorityLabel: String = "", val dueDate: String? = null,
    val status: String = "", val statusLabel: String = "", val progress: Int = 0, val localNote: String? = null,
)

@Serializable
data class TaskComment(val id: String, val task: String = "", val authorName: String = "", val body: String = "", val createdAt: String = "")

@Serializable
data class Complaint(
    val id: String, val reference: String = "", val kind: String = "", val kindLabel: String = "", val channel: String = "",
    val channelLabel: String = "", val name: String = "", val phone: String = "", val email: String = "", val ward: Int? = null,
    val department: String = "", val departmentLabel: String = "", val subject: String = "", val details: String = "",
    val status: String = "", val statusLabel: String = "", val acknowledgeDue: String? = null, val acknowledgedAt: String? = null,
    val responseDue: String? = null, val resolution: String = "", val resolvedAt: String? = null, val createdAt: String = "",
    val localNote: String? = null,
)

@Serializable
data class ServiceRequest(
    val id: String, val reference: String = "", val category: String = "", val categoryLabel: String = "", val department: String = "",
    val departmentLabel: String = "", val description: String = "", val location: String = "", val ward: Int? = null,
    val reporterName: String = "", val reporterPhone: String = "", val priority: String = "", val priorityLabel: String = "",
    val status: String = "", val statusLabel: String = "", val dueAt: String? = null, val resolution: String = "",
    val resolvedAt: String? = null, val createdAt: String = "", val localNote: String? = null,
)

@Serializable
data class StandApplication(
    val id: String, val reference: String = "", val applicantName: String = "", val nationalId: String = "", val phone: String = "",
    val standType: String = "", val standTypeLabel: String = "", val preferredLocation: String = "", val ward: Int? = null,
    val status: String = "", val statusLabel: String = "", val allocatedStand: String = "", val createdAt: String = "",
)

@Serializable
data class Project(
    val id: String, val code: String = "", val name: String = "", val category: String = "", val categoryLabel: String = "",
    val ward: Int? = null, val location: String = "", val budget: String = "0", val funder: String = "", val startDate: String? = null,
    val endDate: String? = null, val progress: Int = 0, val status: String = "", val statusLabel: String = "",
)

@Serializable
data class AuditFinding(
    val id: String, val reference: String = "", val auditType: String = "", val auditTypeLabel: String = "", val department: String = "",
    val departmentLabel: String = "", val title: String = "", val finding: String = "", val riskRating: String = "",
    val riskRatingLabel: String = "", val recommendation: String = "", val managementResponse: String = "",
    val implementationDate: String? = null, val status: String = "", val statusLabel: String = "",
)

@Serializable
data class LeaveRequest(
    val id: String, val employee: Long? = null, val employeeName: String = "", val employeeDepartment: String = "", val leaveType: String = "", val leaveTypeLabel: String = "", val startDate: String = "", val days: Int = 0,
    val endDate: String = "", val reason: String = "", val status: String = "", val statusLabel: String = "", val decisionComment: String = "",
    val localNote: String? = null,
)

@Serializable
data class AppNotification(val id: String, val title: String = "", val body: String = "", val link: String = "", val isRead: Boolean = false, val createdAt: String = "")

@Serializable
data class OnlinePayment(
    val id: String, val reference: String = "", val account: String = "", val bill: String? = null, val amount: String = "0", val provider: String = "",
    val currency: String = "USD", val method: String = "", val phone: String = "", val status: String = "", val statusLabel: String = "",
    val receipt: String? = null, val receiptNumber: String? = null, val paidAt: String? = null, val createdAt: String = "",
)

@Serializable
data class StaffMember(val id: String, val userId: Long = 0, val username: String = "", val fullName: String = "", val department: String = "",
                       val role: String = "", val roleLabel: String = "", val phone: String = "", val isActive: Boolean = true)

@Serializable
data class TradingArea(val id: String, val name: String = "", val kind: String = "", val kindLabel: String = "", val ward: Int? = null,
                       val isActive: Boolean = true)

@Serializable
data class Lease(val id: String, val number: String = "", val lessee: String = "", val lesseeName: String = "", val premises: String = "",
                 val premisesName: String = "", val purpose: String = "", val monthlyRent: String = "0", val deposit: String = "0",
                 val startDate: String = "", val endDate: String = "", val status: String = "", val statusLabel: String = "")

@Serializable
data class AccountClaim(val id: String, val reference: String = "", val userName: String = "", val claimType: String = "", val claimTypeLabel: String = "",
                        val standNumber: String = "", val area: String? = null, val areaName: String = "", val location: String = "",
                        val businessName: String = "", val idNumber: String = "", val phone: String = "", val notes: String = "", val status: String = "",
                        val statusLabel: String = "", val matchedProperty: String? = null, val matched: String = "", val accountNumber: String = "",
                        val decisionNote: String = "", val createdAt: String = "", val localNote: String? = null)

@Serializable
data class AssetHistory(val date: String = "", val workDone: String = "", val cost: String = "0", val condition: String = "")

@Serializable
data class Asset(val id: String, val assetNumber: String = "", val name: String = "", val category: String = "", val categoryLabel: String = "",
                 val department: String = "", val departmentLabel: String = "", val serialNumber: String = "", val location: String = "", val ward: Int? = null,
                 val acquisitionDate: String? = null, val cost: String = "0", val bookValue: String = "0", val custodianName: String = "",
                 val condition: String = "", val conditionLabel: String = "", val status: String = "", val statusLabel: String = "", val notes: String = "",
                 val history: List<AssetHistory> = emptyList(), val localNote: String? = null)

@Serializable
data class Incident(val id: String, val reference: String = "", val incidentType: String = "", val incidentTypeLabel: String = "", val title: String = "",
                    val description: String = "", val ward: Int? = null, val location: String = "", val occurredAt: String = "",
                    val householdsAffected: Int = 0, val peopleInjured: Int = 0, val deaths: Int = 0, val livestockLost: Int = 0,
                    val cropsHectares: String = "0", val response: String = "", val status: String = "", val statusLabel: String = "",
                    val leadOfficerName: String = "", val localNote: String? = null)

@Serializable
data class CommunityActivity(val id: String, val reference: String = "", val activityType: String = "", val activityTypeLabel: String = "",
                             val title: String = "", val department: String = "", val departmentLabel: String = "", val ward: Int? = null, val venue: String = "",
                             val date: String = "", val participants: Int = 0, val report: String = "", val status: String = "", val statusLabel: String = "",
                             val officerId: Long? = null, val officerName: String = "", val localNote: String? = null)

@Serializable
data class BuildingPlan(val id: String, val reference: String = "", val applicantName: String = "", val phone: String = "", val standNumber: String = "",
                        val location: String = "", val ward: Int? = null, val developmentType: String = "", val developmentTypeLabel: String = "",
                        val description: String = "", val floorArea: String = "0", val fee: String = "0", val bill: String? = null,
                        val billStatus: String? = null, val status: String = "", val statusLabel: String = "", val reviewedById: Long? = null,
                        val reviewNotes: String = "", val decisionNotes: String = "", val inspectionLog: String = "", val dueAt: String? = null,
                        val createdAt: String = "", val localNote: String? = null)

@Serializable
data class Risk(val id: String, val reference: String = "", val department: String = "", val departmentLabel: String = "", val title: String = "",
                val description: String = "", val category: String = "", val categoryLabel: String = "", val likelihood: Int = 0, val impact: Int = 0,
                val score: Int = 0, val rating: String = "", val existingControls: String = "", val mitigation: String = "", val ownerName: String = "",
                val reviewDate: String? = null, val status: String = "", val statusLabel: String = "")

@Serializable
data class CouncilMeeting(val id: String, val reference: String = "", val meetingType: String = "", val meetingTypeLabel: String = "", val title: String = "",
                          val date: String = "", val venue: String = "", val agenda: String = "", val minutes: String = "", val status: String = "",
                          val statusLabel: String = "")

@Serializable
data class Resolution(val id: String, val number: String = "", val meeting: String = "", val meetingTitle: String = "", val text: String = "",
                      val department: String = "", val departmentLabel: String = "", val responsibleId: Long? = null, val responsibleName: String = "",
                      val dueDate: String? = null, val status: String = "", val statusLabel: String = "", val progressNote: String = "",
                      val localNote: String? = null)

@Serializable
data class IctTicket(val id: String, val reference: String = "", val raisedById: Long? = null, val raisedByName: String = "", val department: String = "",
                     val category: String = "", val categoryLabel: String = "", val subject: String = "", val description: String = "",
                     val priority: String = "", val priorityLabel: String = "", val status: String = "", val statusLabel: String = "",
                     val resolution: String = "", val createdAt: String = "", val localNote: String? = null)

@Serializable
data class Policy(val id: String, val title: String = "", val kind: String = "", val kindLabel: String = "", val department: String = "",
                  val departmentLabel: String = "", val version: String = "", val summary: String = "", val status: String = "", val statusLabel: String = "",
                  val adoptedOn: String? = null, val reviewDate: String? = null)

@Serializable
data class FundsLine(val description: String = "", val quantity: String = "", val unitCost: String = "", val total: String = "")

/** One row of the "where is my request?" tracker. state: done | current | skipped | waiting | rejected | returned */
@Serializable
data class RouteStep(val label: String = "", val state: String = "", val who: String = "", val `when`: String = "", val note: String = "")

@Serializable
data class HistoryEntry(val stage: String = "", val decision: String = "", val user: String = "", val `when`: String = "", val comment: String = "")

/** Request for funds / purchase (travel & subsistence, advance, goods, fuel …). */
@Serializable
data class FundsRequest(
    val id: String, val reference: String = "", val requestType: String = "", val requestTypeLabel: String = "", val title: String = "",
    val purpose: String = "", val department: String = "", val departmentLabel: String = "", val requestedBy: Long? = null,
    val requestedByName: String = "", val destination: String = "", val departDate: String? = null, val returnDate: String? = null,
    val travellers: String = "", val currency: String = "USD", val total: String = "0", val neededBy: String? = null,
    val requiresPayment: Boolean = true, val payeeName: String = "", val paymentMethod: String = "", val paymentMethodLabel: String = "",
    val paymentDetails: String = "", val vote: String? = null, val status: String = "", val statusLabel: String = "",
    val submittedAt: String? = null, val stageSince: String? = null, val lastReminderAt: String? = null, val decisionNote: String = "",
    val voucherNumber: String? = null, val voucherStatus: String? = null, val completedAt: String? = null,
    val lines: List<FundsLine> = emptyList(), val route: List<RouteStep> = emptyList(), val history: List<HistoryEntry> = emptyList(),
    val whereNow: String = "", val daysWaiting: Int = 0, val deciders: List<Long> = emptyList(), val payeeDiffers: Boolean = false, val createdAt: String = "",
    val localNote: String? = null,
) {
    val isOpen get() = status in listOf("P_HOD", "P_ADMIN", "P_TREAS", "P_CEO", "P_PAY", "PAYING")
}

@Serializable
data class MemoReply(val author: String = "", val department: String = "", val body: String = "", val `when`: String = "")

/** Memo / request for action between departments. */
@Serializable
data class Memo(
    val id: String, val reference: String = "", val kind: String = "", val kindLabel: String = "", val sender: Long? = null,
    val senderName: String = "", val fromDepartment: String = "", val fromDepartmentLabel: String = "", val toDepartment: String = "",
    val toDepartmentLabel: String = "", val toUser: Long? = null, val toUserName: String? = null, val subject: String = "", val body: String = "",
    val priority: String = "", val priorityLabel: String = "", val status: String = "", val statusLabel: String = "", val readAt: String? = null,
    val taskReference: String? = null, val taskStatus: String? = null, val taskAssignee: String? = null,
    val replies: List<MemoReply> = emptyList(), val createdAt: String = "", val localNote: String? = null,
)

@Serializable
data class CashUp(val id: String, val cashierId: Long? = null, val cashierName: String = "", val date: String = "", val currency: String = "USD",
                  val expectedCash: String = "0", val declaredCash: String = "0", val expectedOther: String = "0", val variance: String = "0",
                  val status: String = "", val statusLabel: String = "", val notes: String = "", val verifiedByName: String? = null,
                  val verifiedAt: String? = null, val localNote: String? = null)

@Serializable
data class Supplier(val id: String, val code: String = "", val name: String = "", val category: String = "", val contactPerson: String = "",
                    val phone: String = "", val email: String = "", val status: String = "", val statusLabel: String = "")

@Serializable
data class PurchaseOrder(val id: String, val number: String = "", val requisition: String = "", val requisitionNumber: String = "",
                         val requisitionPurpose: String = "", val department: String = "", val supplier: String = "", val supplierName: String = "",
                         val amount: String = "0", val currency: String = "USD", val status: String = "", val statusLabel: String = "",
                         val expectedDelivery: String? = null, val deliveredAt: String? = null, val notes: String = "", val createdAt: String = "",
                         val localNote: String? = null)

@Serializable
data class BankAccount(val id: String, val name: String = "", val bank: String = "", val accountNumber: String = "", val currency: String = "USD",
                       val isActive: Boolean = true, val balance: String = "0")

@Serializable
data class Correspondence(val id: String, val reference: String = "", val sender: String = "", val senderContact: String = "", val subject: String = "",
                          val dateReceived: String = "", val department: String = "", val departmentLabel: String = "", val assignedTo: Long? = null,
                          val assignedToName: String? = null, val status: String = "", val statusLabel: String = "", val responseDue: String? = null,
                          val respondedAt: String? = null, val responseSummary: String = "", val fileReference: String = "", val localNote: String? = null)

@Serializable
data class SalaryProfile(val id: String, val employeeId: Long = 0, val employeeName: String = "", val department: String = "", val roleLabel: String = "",
                         val grade: String = "", val currency: String = "USD", val basicSalary: String = "0", val housingAllowance: String = "0",
                         val transportAllowance: String = "0", val otherAllowances: String = "0", val paye: String = "0", val nssa: String = "0",
                         val pension: String = "0", val medicalAid: String = "0", val otherDeductions: String = "0", val paymentMethod: String = "EFT",
                         val bankName: String = "", val bankAccount: String = "", val isActive: Boolean = true, val allowances: String = "0",
                         val gross: String = "0", val deductions: String = "0", val net: String = "0", val autoTax: Boolean = true,
                         val taxCredits: String = "0", val taxableIncome: String = "0", val incomeTax: String = "0", val aidsLevy: String = "0",
                         val localNote: String? = null)

@Serializable
data class SalaryPaymentLine(val amount: String = "0", val method: String = "", val reference: String = "", val paidOn: String = "", val paidBy: String = "")

@Serializable
data class Payslip(val id: String, val reference: String = "", val employeeId: Long = 0, val employeeName: String = "", val department: String = "",
                   val year: Int = 0, val month: Int = 0, val period: String = "", val currency: String = "USD", val grade: String = "",
                   val basicSalary: String = "0", val allowances: String = "0", val gross: String = "0", val paye: String = "0", val nssa: String = "0",
                   val taxableIncome: String = "0", val incomeTax: String = "0", val aidsLevy: String = "0", val taxTable: String = "",
                   val pension: String = "0", val otherDeductions: String = "0", val net: String = "0", val amountPaid: String = "0",
                   val balance: String = "0", val status: String = "", val statusLabel: String = "", val approvedAt: String? = null,
                   val payments: List<SalaryPaymentLine> = emptyList(), val localNote: String? = null)

/** Choice lists mirrored from the server so forms work offline. */
object Choices {
    val currencies = listOf("USD" to "US Dollar", "ZWG" to "Zimbabwe Gold")
    val fundsTypes = listOf("TRAVEL" to "Travel & subsistence allowance (T&S)", "ADVANCE" to "Cash advance / imprest",
        "PURCHASE" to "Purchase of goods or services", "FUEL" to "Fuel", "TRAINING" to "Training / workshop / conference fees",
        "REPAIRS" to "Repairs & maintenance", "OTHER" to "Other")
    val fundsPayment = listOf("EFT" to "Bank transfer", "CASH" to "Cash", "MOBILE" to "Mobile money (EcoCash / OneMoney)", "CHEQUE" to "Cheque")
    val voucherCategories = listOf("SUPPLIER" to "Supplier / contractor", "ALLOW" to "Allowances & subsistence", "SALARIES" to "Salaries & wages",
        "STATUTORY" to "Statutory (ZIMRA, NSSA, pension)", "UTILITIES" to "Utilities", "REFUND" to "Refund to client", "OTHER" to "Other")
    val voucherMethods = listOf("EFT" to "Bank transfer (RTGS / EFT)", "CHEQUE" to "Cheque", "CASH" to "Cash (petty cash)", "MOBILE" to "Mobile money")
    val correspondenceStatuses = listOf("RECEIVED" to "Received", "ASSIGNED" to "Assigned", "RESPONDED" to "Responded", "FILED" to "Filed (no response needed)")
    val memoKinds = listOf("MESSAGE" to "Message / memo", "ACTION" to "Request for action", "INFO" to "For information")
    val receiptMethods = listOf("CASH" to "Cash", "ECOCASH" to "EcoCash", "ONEMONEY" to "OneMoney", "INNBUCKS" to "InnBucks",
        "SWIPE" to "Card / swipe (POS)", "BANK" to "Bank transfer / deposit")
    val departments = listOf("EXEC" to "Office of the CEO", "ADMIN" to "Administration", "FINANCE" to "Finance",
        "AUDIT" to "Internal Audit", "SOCIAL" to "Social Services", "TECH" to "Technical Services")
    val complaintKinds = listOf("COMPLAINT" to "Complaint", "COMPLIMENT" to "Compliment", "SUGGESTION" to "Suggestion", "ENQUIRY" to "Enquiry")
    val complaintChannels = listOf("OFFICE" to "Council offices", "PHONE" to "Telephone", "CONSULT" to "Community consultation",
        "BOX" to "Suggestion box", "SOCIAL" to "Social media", "EMAIL" to "Email", "CEO" to "Chief Executive Officer")
    val serviceCategories = listOf("WATER_FAULT" to "Major water fault / burst pipe", "BOREHOLE" to "Borehole breakdown",
        "SEWER" to "Sewer blockage / ablutions", "REFUSE" to "Refuse not collected / illegal dumping", "HEALTH" to "Public health concern",
        "WILDLIFE" to "Human-wildlife conflict", "FIRE" to "Veld fire / fire incident", "DISASTER" to "Disaster / emergency",
        "ROAD" to "Road damage / pothole / bridge", "LIGHTING" to "Public lighting fault", "BUILDING" to "Illegal structure / development control",
        "BILLING" to "Billing / account query", "OTHER" to "Other")
    val licenceTypes = listOf("SHOP" to "Shop licence", "HAWKER" to "Hawker / vendor licence", "BUSINESS" to "General business licence",
        "LIQUOR" to "Liquor (council recommendation)", "HEALTH" to "Health / food handling certificate",
        "TRANSPORT" to "Public transport rank permit", "ADVERT" to "Advertising / billboard permit")
    val standTypes = listOf("RES" to "Residential", "COM" to "Commercial", "INST" to "Institutional / church / school", "IND" to "Industrial")
    val leaveTypes = listOf("ANNUAL" to "Annual / vacation", "SICK" to "Sick", "MATERNITY" to "Maternity", "COMPASS" to "Compassionate",
        "STUDY" to "Study", "UNPAID" to "Unpaid")
    val taskStatuses = listOf("IN_PROGRESS" to "In progress", "DONE" to "Completed - awaiting sign-off", "CLOSED" to "Closed")
    val mobileMoney = listOf("ECOCASH" to "EcoCash", "ONEMONEY" to "OneMoney", "INNBUCKS" to "InnBucks")
    val incidentTypes = listOf("FIRE" to "Veld / structure fire", "FLOOD" to "Flood", "STORM" to "Storm / cyclone", "DROUGHT" to "Drought",
        "HWC" to "Human-wildlife conflict", "DISEASE" to "Disease outbreak", "ACCIDENT" to "Accident", "COLLAPSE" to "Structure collapse", "OTHER" to "Other")
    val incidentStatuses = listOf("REPORTED" to "Reported", "RESPONDING" to "Response under way", "CONTAINED" to "Contained – recovery",
        "CLOSED" to "Closed (HOD signs off)")
    val activityTypes = listOf("HYGIENE" to "Hygiene promotion (WASH)", "HEALTH" to "Public health programme", "ENV" to "Environmental campaign",
        "CONSERVE" to "Natural resource conservation", "RECLAIM" to "Land reclamation", "FIRE" to "Fire management / fireguards",
        "SAFETY" to "Public safety awareness", "PREPARE" to "Emergency preparedness / drill", "SECURITY" to "Community security programme",
        "COMMUNITY" to "Community services", "CONSULT" to "Community consultation / WDC / village assembly", "TRAINING" to "Training")
    val devTypes = listOf("RES" to "Residential house", "COM" to "Commercial / shop", "IND" to "Industrial", "INST" to "Institutional",
        "ALT" to "Alteration / extension", "COU" to "Change of use / subdivision")
    val assetConditions = listOf("GOOD" to "Good / working", "FAIR" to "Fair", "POOR" to "Poor – needs repair", "BROKEN" to "Broken down / not working")
    val ictCategories = listOf("HW" to "Computer / hardware", "SW" to "Software / system", "NET" to "Network / internet", "ACCT" to "User account / password",
        "PRINT" to "Printer / scanner", "PHONE" to "Telephone / mobile app", "OTHER" to "Other")
    val priorities = listOf("LOW" to "Low", "NORMAL" to "Normal", "HIGH" to "High", "URGENT" to "Urgent")
    val resolutionStatuses = listOf("PENDING" to "Not started", "IN_PROGRESS" to "Being implemented", "DONE" to "Implemented")
    val projectStatuses = listOf("PLANNED" to "Planned", "PROCUREMENT" to "Procurement", "ONGOING" to "Ongoing", "COMPLETED" to "Completed", "SUSPENDED" to "Suspended")
    val taskKinds = listOf("TASK" to "Task / assignment", "REQUEST" to "Request for information / report", "MEMO" to "Memo / directive")
    val claimTypes = listOf("OWNER" to "I own / occupy this stand", "SHOP" to "I run a shop / business at this stand", "TENANT" to "I lease these council premises")
}
