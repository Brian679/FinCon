package zw.gov.chipingerdc.shared.sync

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.datetime.Clock
import kotlinx.serialization.json.JsonObject
import zw.gov.chipingerdc.shared.api.ApiClient
import zw.gov.chipingerdc.shared.api.ApiException
import zw.gov.chipingerdc.shared.api.AuthExpiredException
import zw.gov.chipingerdc.shared.data.LocalStore
import zw.gov.chipingerdc.shared.data.Session
import zw.gov.chipingerdc.shared.model.AppJson
import zw.gov.chipingerdc.shared.model.OperationDto

data class SyncState(
    val running: Boolean = false,
    val online: Boolean? = null,
    val lastSync: String? = null,
    val lastError: String? = null,
    val needsLogin: Boolean = false,
    val lastPushed: Int = 0,
    val lastPulled: Int = 0,
)

/**
 * Two-way synchronisation:
 *  1. PUSH every queued operation (oldest first). Each operation carries its own
 *     UUID so a retry after a dropped connection is never applied twice.
 *  2. PULL changes for every entity since the last cursor and store them locally.
 * A failure (no network) leaves the outbox untouched; the next attempt resumes.
 */
class SyncEngine(
    private val api: ApiClient,
    private val store: LocalStore,
    private val session: Session,
) {
    private val mutex = Mutex()
    private val _state = MutableStateFlow(SyncState(lastSync = session.lastSync))
    val state: StateFlow<SyncState> = _state.asStateFlow()
    private var autoJob: Job? = null

    suspend fun sync(): SyncState = mutex.withLock {
        if (!session.isLoggedIn) return _state.value
        _state.update { it.copy(running = true, lastError = null) }
        try {
            val pushed = pushAll()
            val pulled = pullAll()
            val now = Clock.System.now().toString()
            session.lastSync = now
            _state.update { it.copy(running = false, online = true, lastSync = now, lastError = null, needsLogin = false, lastPushed = pushed, lastPulled = pulled) }
        } catch (e: CancellationException) {
            _state.update { it.copy(running = false) }
            throw e
        } catch (e: AuthExpiredException) {
            _state.update { it.copy(running = false, online = true, needsLogin = true, lastError = e.message) }
        } catch (e: ApiException) {
            _state.update { it.copy(running = false, online = true, lastError = e.message) }
        } catch (e: Throwable) {
            // Most likely no connectivity - stay offline and keep the queue.
            _state.update { it.copy(running = false, online = false, lastError = "Offline – changes are saved on this phone and will sync automatically.") }
        }
        _state.value
    }

    private suspend fun pushAll(): Int {
        var total = 0
        repeat(50) {
            val batch = store.pendingOps(50)
            if (batch.isEmpty()) return total
            val ops = batch.map {
                OperationDto(it.op_id, it.type, AppJson.parseToJsonElement(it.payload) as JsonObject, it.created_at)
            }
            val response = api.push(session.deviceId, ops)
            val byId = response.results.associateBy { it.opId }
            store.transaction {
                for (op in batch) {
                    val r = byId[op.op_id]
                    if (r == null) {
                        store.bumpAttempt(op.op_id)
                        continue
                    }
                    if (r.status == "applied") {
                        val record = r.record
                        val entity = r.entity
                        if (op.local_id.isNotBlank() && op.entity.isNotBlank()) store.delete(op.entity, op.local_id)
                        if (record != null && entity != null) store.upsert(entity, record)
                        store.deleteOp(op.op_id)
                        total++
                    } else {
                        store.rejectOp(op.op_id, r.error.ifBlank { "Rejected by server" })
                        if (op.entity.isNotBlank() && op.local_id.isNotBlank()) {
                            if (op.type.endsWith(".create") || op.type.endsWith(".apply")) {
                                store.delete(op.entity, op.local_id)
                            } else {
                                // Restore the server's version of the record on the next pull.
                                store.resetCursor(op.entity)
                            }
                        }
                    }
                }
            }
        }
        return total
    }

    private suspend fun pullAll(): Int {
        var total = 0
        var cursors: Map<String, String> = store.cursors() + ("*" to "")
        repeat(30) {
            val resp = api.pull(cursors)
            val more = mutableMapOf<String, String>()
            store.transaction {
                for ((entity, page) in resp.entities) {
                    page.items.forEach { item ->
                        // Never overwrite a record that still has queued local changes.
                        val id = item["id"]?.toString()?.trim('"') ?: return@forEach
                        if (!store.isPending(entity, id)) store.upsert(entity, item)
                    }
                    total += page.items.size
                    page.cursor?.let { store.setCursor(entity, it) }
                    if (page.hasMore && page.cursor != null) more[entity] = page.cursor
                }
            }
            if (more.isEmpty()) return total
            cursors = more
        }
        return total
    }

    /** Keep syncing in the background while the app is open: quickly when work is queued, slowly otherwise. */
    fun startAuto(scope: CoroutineScope) {
        if (autoJob?.isActive == true) return
        autoJob = scope.launch {
            while (isActive) {
                if (session.isLoggedIn) sync()
                val waitMs = if (store.pendingCount() > 0) 30_000L else 180_000L
                delay(waitMs)
            }
        }
    }

    fun stopAuto() {
        autoJob?.cancel()
        autoJob = null
    }
}
