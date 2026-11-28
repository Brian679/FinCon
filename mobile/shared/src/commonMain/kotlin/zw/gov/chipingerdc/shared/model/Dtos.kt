package zw.gov.chipingerdc.shared.model

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy
import kotlinx.serialization.json.JsonObject

/** JSON settings shared by the API client and the local store (server uses snake_case). */
val AppJson = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    isLenient = true
    coerceInputValues = true
    namingStrategy = JsonNamingStrategy.SnakeCase
}

enum class AppKind(val apiName: String) { COUNCIL("council"), CLIENT("client") }

@Serializable
data class Me(
    val id: Long = 0,
    val username: String = "",
    val fullName: String = "",
    val firstName: String = "",
    val lastName: String = "",
    val nationalId: String = "",
    val ward: Int? = null,
    val email: String = "",
    val phone: String = "",
    val userType: String = "",
    val department: String = "",
    val departmentLabel: String = "",
    val role: String = "",
    val roleLabel: String = "",
    val isHead: Boolean = false,
    val mustChangePassword: Boolean = false,
    val capabilities: List<String> = emptyList(),
    val employeeNumber: String? = null,
    val annualLeaveDays: Int = 22,
) {
    fun can(vararg caps: String) = caps.any { it in capabilities }
    val isClient get() = userType == "CLIENT"
    val isCeo get() = role == "CEO"
}

@Serializable
data class LoginRequest(val username: String, val password: String, val app: String)

@Serializable
data class LoginResponse(val access: String, val refresh: String, val user: Me)

@Serializable
data class RefreshRequest(val refresh: String)

@Serializable
data class RefreshResponse(val access: String, val refresh: String? = null)

@Serializable
data class PullRequest(val cursors: Map<String, String>, val limit: Int = 500)

@Serializable
data class EntityPage(val items: List<JsonObject> = emptyList(), val cursor: String? = null, val hasMore: Boolean = false)

@Serializable
data class PullResponse(val serverTime: String = "", val entities: Map<String, EntityPage> = emptyMap())

@Serializable
data class OperationDto(val opId: String, val type: String, val payload: JsonObject, val createdAt: String)

@Serializable
data class PushRequest(val deviceId: String, val operations: List<OperationDto>)

@Serializable
data class OpResult(
    val opId: String? = null,
    val status: String = "",
    val error: String = "",
    val duplicate: Boolean = false,
    val entity: String? = null,
    val record: JsonObject? = null,
)

@Serializable
data class PushResponse(val serverTime: String = "", val results: List<OpResult> = emptyList())

@Serializable
data class RegisterRequest(
    val firstName: String,
    val lastName: String,
    val username: String,
    val email: String,
    val phone: String,
    val nationalId: String,
    val ward: String = "",
    val password1: String,
    val password2: String,
    /** How the person is connected to a stand: NONE, OWNER, SHOP, RENT (renting from the owner) or TENANT (council premises). */
    val relationship: String = "NONE",
    val standNumber: String = "",
    val location: String = "",
    val businessName: String = "",
)
