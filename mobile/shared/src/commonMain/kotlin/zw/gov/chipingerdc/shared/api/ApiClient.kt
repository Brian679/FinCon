package zw.gov.chipingerdc.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import zw.gov.chipingerdc.shared.data.Session
import zw.gov.chipingerdc.shared.model.AppJson
import zw.gov.chipingerdc.shared.model.AppKind
import zw.gov.chipingerdc.shared.model.LoginRequest
import zw.gov.chipingerdc.shared.model.LoginResponse
import zw.gov.chipingerdc.shared.model.Me
import zw.gov.chipingerdc.shared.model.OperationDto
import zw.gov.chipingerdc.shared.model.PullRequest
import zw.gov.chipingerdc.shared.model.PullResponse
import zw.gov.chipingerdc.shared.model.PushRequest
import zw.gov.chipingerdc.shared.model.PushResponse
import zw.gov.chipingerdc.shared.model.RefreshRequest
import zw.gov.chipingerdc.shared.model.RefreshResponse
import zw.gov.chipingerdc.shared.model.RegisterRequest

/** The server rejected the credentials / the session has expired: the user must log in again. */
class AuthExpiredException(message: String = "Your session has expired. Please log in again.") : Exception(message)

/** The server answered with an error the user should see (validation, permission ...). */
class ApiException(message: String, val status: Int) : Exception(message)

class ApiClient(private val session: Session, private val app: AppKind) {
    private val http = HttpClient {
        install(ContentNegotiation) { json(AppJson) }
        install(HttpTimeout) {
            requestTimeoutMillis = 60_000
            connectTimeoutMillis = 15_000
        }
        expectSuccess = false
    }

    private fun url(path: String) = "${session.baseUrl}/api/v1/$path"

    private fun HttpRequestBuilder.common() {
        header("X-Client-App", app.apiName)
        contentType(ContentType.Application.Json)
    }

    private suspend fun errorMessage(resp: HttpResponse): String {
        val text = runCatching { resp.bodyAsText() }.getOrDefault("")
        val obj = runCatching { AppJson.parseToJsonElement(text) as JsonObject }.getOrNull()
        val detail = obj?.get("detail")
        return when {
            detail != null -> runCatching { detail.jsonPrimitive.content }.getOrElse { detail.toString().trim('[', ']', '"') }
            obj?.get("errors") != null -> obj["errors"].toString()
            text.isNotBlank() && text.length < 300 -> text
            else -> "Server error (${resp.status.value})"
        }
    }

    /** Authenticated call with one automatic token refresh on 401. */
    private suspend fun authed(block: suspend (token: String) -> HttpResponse): HttpResponse {
        val token = session.accessToken ?: refresh()
        var resp = block(token)
        if (resp.status == HttpStatusCode.Unauthorized) {
            resp = block(refresh())
        }
        if (resp.status == HttpStatusCode.Unauthorized) throw AuthExpiredException()
        if (!resp.status.isSuccess()) throw ApiException(errorMessage(resp), resp.status.value)
        return resp
    }

    private suspend fun refresh(): String {
        val rt = session.refreshToken ?: throw AuthExpiredException()
        val resp = http.post(url("auth/refresh/")) { common(); setBody(RefreshRequest(rt)) }
        if (!resp.status.isSuccess()) throw AuthExpiredException()
        val body: RefreshResponse = resp.body()
        session.updateTokens(body.access, body.refresh)
        return body.access
    }

    suspend fun login(username: String, password: String): LoginResponse {
        val resp = http.post(url("auth/login/")) { common(); setBody(LoginRequest(username.trim(), password, app.apiName)) }
        if (!resp.status.isSuccess()) {
            val msg = errorMessage(resp)
            throw ApiException(if (resp.status.value == 401) "Incorrect username or password (accounts lock after 5 failed attempts)." else msg, resp.status.value)
        }
        return resp.body()
    }

    suspend fun register(req: RegisterRequest): Me {
        val resp = http.post(url("auth/register/")) { common(); setBody(req) }
        if (!resp.status.isSuccess()) throw ApiException(errorMessage(resp), resp.status.value)
        return resp.body()
    }

    suspend fun changePassword(old: String, new: String) {
        val resp = authed { t ->
            http.post(url("auth/password/")) { common(); bearer(t); setBody(kotlinx.serialization.json.buildJsonObject {
                put("old_password", kotlinx.serialization.json.JsonPrimitive(old)); put("new_password", kotlinx.serialization.json.JsonPrimitive(new)) }) }
        }
        if (!resp.status.isSuccess()) throw ApiException(errorMessage(resp), resp.status.value)
    }

    suspend fun me(): Me = authed { t -> http.get(url("me/")) { common(); bearer(t) } }.body()

    suspend fun pull(cursors: Map<String, String>, limit: Int = 500): PullResponse =
        authed { t -> http.post(url("sync/pull/")) { common(); bearer(t); setBody(PullRequest(cursors, limit)) } }.body()

    suspend fun push(deviceId: String, ops: List<OperationDto>): PushResponse =
        authed { t -> http.post(url("sync/push/")) { common(); bearer(t); setBody(PushRequest(deviceId, ops)) } }.body()

    suspend fun postJson(path: String, body: JsonObject): JsonObject =
        authed { t -> http.post(url(path)) { common(); bearer(t); setBody(body) } }.body()

    suspend fun getJson(path: String): JsonObject = authed { t -> http.get(url(path)) { common(); bearer(t) } }.body()

    private fun HttpRequestBuilder.bearer(token: String) = header(HttpHeaders.Authorization, "Bearer $token")
}
