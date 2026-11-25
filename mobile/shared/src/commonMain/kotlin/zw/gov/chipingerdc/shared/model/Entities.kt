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
    val id: String, val account: String = "", val standNumber: String = "", val location: String = "", val ward: Int? = null,
    val landUse: String = "", val landUseLabel: String = "", val valuation: String = "0", val monthlyRates: String = "0",
)

@Serializable
data class Bill(
    val id: String, val number: String = "", val account: String = "", val revenueHead: String = "", val description: String = "",
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
    val accountNumber: String = "", val businessName: String = "", val businessActivity: String = "", val premises: String = "",
    val ward: Int? = null, val status: String = "", val statusLabel: String = "", val fee: String = "0", val bill: String? = null,
    val inspectionNotes: String = "", val rejectionReason: String = "", val issueDate: String? = null, val expiryDate: String? = null,
    val dueAt: String? = null, val createdAt: String = "", val localNote: String? = null,
)

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
    val id: String, val employee: Long? = null, val employeeName: String = "", val employeeDepartment: String = "", val leaveType: String = "", val leaveTypeLabel: String = "", val startDate: String = "",
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

/** Choice lists mirrored from the server so forms work offline. */
object Choices {
    val currencies = listOf("USD" to "US Dollar", "ZWG" to "Zimbabwe Gold")
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
}
