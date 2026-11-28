package zw.gov.chipingerdc.shared

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonObjectBuilder
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.db.Outbox
import zw.gov.chipingerdc.shared.api.ApiClient
import zw.gov.chipingerdc.shared.data.LocalStore
import zw.gov.chipingerdc.shared.data.Session
import zw.gov.chipingerdc.shared.model.AppKind
import zw.gov.chipingerdc.shared.model.Me
import zw.gov.chipingerdc.shared.model.RegisterRequest
import zw.gov.chipingerdc.shared.sync.SyncEngine
import kotlin.uuid.Uuid

/**
 * Entry point used by both apps: owns the local database, the session, the
 * API client and the sync engine.
 */
class CouncilSdk(driverFactory: DatabaseDriverFactory, val app: AppKind, defaultBaseUrl: String) {
    val store = LocalStore(driverFactory.createDriver(if (app == AppKind.COUNCIL) "crdc_council.db" else "crdc_client.db"))
    val session = Session(store, defaultBaseUrl)
    val api = ApiClient(session, app)
    val sync = SyncEngine(api, store, session)
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    val user get() = session.user
    val pendingCount: Flow<Long> = store.observePendingCount()
    val rejectedCount: Flow<Long> = store.observeRejectedCount()
    val outbox: Flow<List<Outbox>> = store.observeOps()

    // ------------------------------------------------------------ session
    suspend fun login(baseUrl: String, username: String, password: String): Me {
        session.baseUrl = baseUrl
        val resp = api.login(username, password)
        session.saveLogin(resp.access, resp.refresh, resp.user)
        scope.launch { sync.sync() }
        return resp.user
    }

    suspend fun register(baseUrl: String, req: RegisterRequest): Me {
        session.baseUrl = baseUrl
        return api.register(req)
    }

    fun logout() {
        sync.stopAuto()
        session.logout()
    }

    fun syncNow() = scope.launch { sync.sync() }

    // ------------------------------------------------------------- reads
    fun <T> observe(entity: String, serializer: KSerializer<T>) = store.observe(entity, serializer)
    fun <T> search(entity: String, text: String, serializer: KSerializer<T>) = store.observeSearch(entity, text, serializer)
    fun <T> observeOne(entity: String, id: String, serializer: KSerializer<T>) = store.observeOne(entity, id, serializer)
    fun <T> list(entity: String, serializer: KSerializer<T>) = store.list(entity, serializer)

    // ------------------------------------------------------------ writes
    /**
     * Queue an operation for the server. If [optimistic] is given, the record is
     * shown immediately (marked pending) so the user sees their work offline.
     */
    fun enqueue(type: String, summary: String, entity: String = "", localId: String = "", optimistic: JsonObject? = null,
                payload: JsonObjectBuilder.() -> Unit): String {
        val opId = Uuid.random().toString()
        val body = buildJsonObject(payload)
        val now = Clock.System.now().toString()
        store.transaction {
            store.addOp(opId, type, body, now, entity, localId, summary)
            if (optimistic != null && entity.isNotBlank()) store.upsert(entity, optimistic, pending = true)
        }
        syncNow()
        return opId
    }

    /** Mark an existing record as having a queued change, with a note shown in the UI. */
    fun markPending(entity: String, id: String, note: String, changes: Map<String, String> = emptyMap()) {
        val current = store.raw(entity, id) ?: return
        val updated = JsonObject(current + buildJsonObject {
            put("local_note", note)
            changes.forEach { (k, v) -> put(k, v) }
        })
        store.upsert(entity, updated, pending = true)
    }

    fun dismissRejected(opId: String) = store.deleteOp(opId)

    fun newId(): String = Uuid.random().toString()
    fun nowIso(): String = Clock.System.now().toString()

    // ---------------------------------------------------- online-only calls
    /** Needs a connection: the new password is checked against the council's password rules. */
    suspend fun changePassword(old: String, new: String) = api.changePassword(old, new)

    suspend fun postJson(path: String, body: JsonObject) = api.postJson(path, body)

    suspend fun uploadFile(path: String, field: String, fileName: String, bytes: ByteArray, mime: String, extra: Map<String, String> = emptyMap()) =
        api.uploadFile(path, field, fileName, bytes, mime, extra)

    /** Settings: save my own details on the server and keep the signed-in profile up to date. */
    suspend fun updateProfile(changes: JsonObject): zw.gov.chipingerdc.shared.model.Me {
        val me = zw.gov.chipingerdc.shared.model.AppJson.decodeFromJsonElement(zw.gov.chipingerdc.shared.model.Me.serializer(), api.postJson("me/", changes))
        session.updateUser(me)
        return me
    }
    suspend fun getJson(path: String) = api.getJson(path)
}
