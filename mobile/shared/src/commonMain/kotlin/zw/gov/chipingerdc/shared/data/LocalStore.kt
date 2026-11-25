package zw.gov.chipingerdc.shared.data

import app.cash.sqldelight.coroutines.asFlow
import app.cash.sqldelight.coroutines.mapToList
import app.cash.sqldelight.coroutines.mapToOne
import app.cash.sqldelight.coroutines.mapToOneOrNull
import app.cash.sqldelight.db.SqlDriver
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonPrimitive
import zw.gov.chipingerdc.db.CouncilDatabase
import zw.gov.chipingerdc.db.Outbox
import zw.gov.chipingerdc.db.Record
import zw.gov.chipingerdc.shared.model.AppJson

/**
 * The phone's offline database. Everything the user can see is read from
 * here, so screens work identically with or without a connection.
 */
class LocalStore(driver: SqlDriver) {
    private val db = CouncilDatabase(driver)
    private val q = db.councilQueries
    private val io = Dispatchers.IO

    // ------------------------------------------------------------- records
    fun upsert(entity: String, obj: JsonObject, pending: Boolean = false) {
        val id = obj["id"]?.jsonPrimitive?.content ?: return
        val updated = (obj["updated_at"] as? JsonPrimitive)?.content ?: ""
        val deleted = (obj["is_deleted"] as? JsonPrimitive)?.booleanOrNull ?: false
        q.upsertRecord(entity, id, obj.toString(), updated, searchText(obj), if (deleted) 1 else 0, if (pending) 1 else 0)
    }

    fun upsertAll(entity: String, items: List<JsonObject>) = q.transaction { items.forEach { upsert(entity, it) } }

    fun delete(entity: String, id: String) = q.deleteRecord(entity, id)

    fun raw(entity: String, id: String): JsonObject? =
        q.recordById(entity, id).executeAsOneOrNull()?.let { AppJson.parseToJsonElement(it.json) as JsonObject }

    fun <T> get(entity: String, id: String, serializer: KSerializer<T>): T? =
        q.recordById(entity, id).executeAsOneOrNull()?.let { decode(it, serializer) }

    fun <T> list(entity: String, serializer: KSerializer<T>): List<T> =
        q.recordsByEntity(entity).executeAsList().mapNotNull { decode(it, serializer) }

    fun <T> observe(entity: String, serializer: KSerializer<T>): Flow<List<T>> =
        q.recordsByEntity(entity).asFlow().mapToList(io).map { rows -> rows.mapNotNull { decode(it, serializer) } }

    fun <T> observeSearch(entity: String, text: String, serializer: KSerializer<T>): Flow<List<T>> =
        q.searchRecords(entity, text.trim().lowercase()).asFlow().mapToList(io).map { rows -> rows.mapNotNull { decode(it, serializer) } }

    fun <T> observeOne(entity: String, id: String, serializer: KSerializer<T>): Flow<T?> =
        q.recordById(entity, id).asFlow().mapToOneOrNull(io).map { it?.let { r -> decode(r, serializer) } }

    fun isPending(entity: String, id: String): Boolean = q.recordById(entity, id).executeAsOneOrNull()?.local_pending == 1L

    private fun <T> decode(r: Record, serializer: KSerializer<T>): T? =
        runCatching { AppJson.decodeFromString(serializer, r.json) }.getOrNull()

    private fun searchText(obj: JsonObject): String {
        val sb = StringBuilder()
        fun walk(e: JsonElement) {
            when (e) {
                is JsonPrimitive -> if (e.isString) sb.append(e.content.lowercase()).append(' ')
                is JsonObject -> e.values.forEach(::walk)
                is JsonArray -> e.forEach(::walk)
                JsonNull -> Unit
            }
        }
        walk(obj)
        return sb.toString().take(2000)
    }

    // -------------------------------------------------------------- outbox
    fun addOp(opId: String, type: String, payload: JsonObject, createdAt: String, entity: String, localId: String, summary: String) =
        q.insertOp(opId, type, payload.toString(), createdAt, entity, localId, summary)

    fun pendingOps(limit: Long): List<Outbox> = q.pendingOps(limit).executeAsList()
    fun observeOps(): Flow<List<Outbox>> = q.allOps().asFlow().mapToList(io)
    fun observePendingCount(): Flow<Long> = q.pendingCount().asFlow().mapToOne(io)
    fun observeRejectedCount(): Flow<Long> = q.rejectedCount().asFlow().mapToOne(io)
    fun pendingCount(): Long = q.pendingCount().executeAsOne()
    fun rejectOp(opId: String, error: String) = q.markOpRejected(error, opId)
    fun bumpAttempt(opId: String) = q.bumpAttempt(opId)
    fun deleteOp(opId: String) = q.deleteOp(opId)

    // ------------------------------------------------------------- cursors
    fun cursors(): Map<String, String> = q.allCursors().executeAsList().associate { it.entity to it.cursor }
    fun setCursor(entity: String, cursor: String) = q.setCursor(entity, cursor)
    fun resetCursor(entity: String) = q.deleteCursor(entity)

    // ------------------------------------------------------------------ kv
    fun value(key: String): String? = q.getValue(key).executeAsOneOrNull()
    fun setValue(key: String, value: String?) = if (value == null) q.deleteValue(key) else q.setValue(key, value)

    /** Wipe all synced data (used when a different user logs in on the same phone). */
    fun clearData() = q.transaction {
        q.clearRecords()
        q.clearOutbox()
        q.clearCursors()
    }

    fun <R> transaction(block: () -> R): R = q.transactionWithResult { block() }
}
