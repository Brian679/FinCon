package zw.gov.chipingerdc.council

import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.LeaveRequest
import zw.gov.chipingerdc.shared.model.Licence
import zw.gov.chipingerdc.shared.model.Me
import zw.gov.chipingerdc.shared.model.Receipt
import zw.gov.chipingerdc.shared.model.Requisition
import zw.gov.chipingerdc.shared.model.Voucher

data class Approval(val kind: String, val ref: String, val text: String, val stage: String, val screen: Screen?, val leave: LeaveRequest? = null, val receipt: Receipt? = null)

fun requisitionStage(me: Me, r: Requisition): String? {
    if (r.requestedBy == me.id || r.localNote != null) return null
    return when (r.status) {
        "SUBMITTED" -> if (me.can("requisition.hod_approve") && (r.department == me.department || me.isCeo)) "Head of Department" else null
        "HOD_OK" -> if (me.can("requisition.finance_check")) "Funds check" else null
        "FIN_OK" -> if (me.can("requisition.approve")) "Treasurer approval" else null
        "APPROVED" -> if (r.needsCeo && me.can("requisition.authorise")) "CEO authorisation" else null
        else -> null
    }
}

fun voucherStage(me: Me, v: Voucher): String? {
    if (v.preparedBy == me.id || v.localNote != null) return null
    return when (v.status) {
        "PREPARED" -> if (me.can("voucher.check")) "Checking" else null
        "CHECKED" -> if (me.can("voucher.approve")) "Treasurer approval" else null
        "APPROVED" -> if (v.needsCeo && me.can("voucher.authorise")) "CEO authorisation" else null
        else -> null
    }
}

fun licenceStage(me: Me, l: Licence): String? = when {
    l.localNote != null -> null
    l.status == "INSPECTION" && me.can("licence.inspect") -> "Inspection"
    l.status in listOf("APPLIED", "INSPECTED") && me.can("licence.approve") -> "Approval"
    else -> null
}

@Composable
fun rememberApprovals(ctx: Ctx): List<Approval> {
    val me = ctx.me
    val sdk = ctx.sdk
    val reqs by sdk.observe(Entities.REQUISITIONS, Requisition.serializer()).collectAsState(initial = emptyList())
    val vouchers by sdk.observe(Entities.VOUCHERS, Voucher.serializer()).collectAsState(initial = emptyList())
    val licences by sdk.observe(Entities.LICENCES, Licence.serializer()).collectAsState(initial = emptyList())
    val leave by sdk.observe(Entities.LEAVE, LeaveRequest.serializer()).collectAsState(initial = emptyList())
    val receipts by sdk.observe(Entities.RECEIPTS, Receipt.serializer()).collectAsState(initial = emptyList())
    return buildList {
        reqs.forEach { r -> requisitionStage(me, r)?.let { add(Approval("Requisition", r.number, "${r.departmentLabel} · $${r.total}", it, Screen.RequisitionDetail(r.id))) } }
        vouchers.forEach { v -> voucherStage(me, v)?.let { add(Approval("Payment voucher", v.number, "${v.payeeName} · ${v.currency} ${v.amount}", it, Screen.VoucherDetail(v.id))) } }
        licences.forEach { l -> licenceStage(me, l)?.let { add(Approval("Licence", l.number, l.businessName, it, Screen.LicenceDetail(l.id))) } }
        if (me.can("leave.approve")) leave.filter {
            it.status == "PENDING" && it.employee != me.id && it.localNote == null && (me.isCeo || it.employeeDepartment == me.department)
        }.forEach { add(Approval("Leave", it.employeeName, "${it.leaveTypeLabel} ${it.startDate} – ${it.endDate}", "Approval", null, leave = it)) }
        if (me.can("receipt.void_approve")) receipts.filter {
            it.status == "VOID_REQ" && it.voidRequestedBy != me.id && it.receivedBy != me.id && it.localNote == null
        }.forEach { add(Approval("Receipt void", it.number, it.voidReason, "Approve void", Screen.ReceiptDetail(it.id), receipt = it)) }
    }
}
