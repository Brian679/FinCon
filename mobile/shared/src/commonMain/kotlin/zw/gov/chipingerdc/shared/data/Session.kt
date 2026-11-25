package zw.gov.chipingerdc.shared.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import zw.gov.chipingerdc.shared.model.AppJson
import zw.gov.chipingerdc.shared.model.Me
import kotlin.uuid.Uuid

/** Tokens, user profile and settings, persisted in the local database so the
 *  user stays signed in (and can keep working) while offline. */
class Session(private val store: LocalStore, defaultBaseUrl: String) {
    private val _user = MutableStateFlow(store.value(KEY_USER)?.let { runCatching { AppJson.decodeFromString(Me.serializer(), it) }.getOrNull() })
    val user: StateFlow<Me?> = _user.asStateFlow()

    var baseUrl: String = store.value(KEY_URL) ?: defaultBaseUrl
        set(value) {
            field = value.trim().trimEnd('/')
            store.setValue(KEY_URL, field)
        }

    val accessToken: String? get() = store.value(KEY_ACCESS)
    val refreshToken: String? get() = store.value(KEY_REFRESH)
    val isLoggedIn: Boolean get() = _user.value != null && refreshToken != null

    val deviceId: String = store.value(KEY_DEVICE) ?: Uuid.random().toString().also { store.setValue(KEY_DEVICE, it) }

    fun saveLogin(access: String, refresh: String, me: Me) {
        val previous = store.value(KEY_LAST_USER)
        if (previous != null && previous != me.username) {
            // Never show one officer's offline data to another officer.
            store.clearData()
        }
        store.setValue(KEY_ACCESS, access)
        store.setValue(KEY_REFRESH, refresh)
        store.setValue(KEY_USER, AppJson.encodeToString(Me.serializer(), me))
        store.setValue(KEY_LAST_USER, me.username)
        _user.value = me
    }

    fun updateTokens(access: String, refresh: String?) {
        store.setValue(KEY_ACCESS, access)
        if (refresh != null) store.setValue(KEY_REFRESH, refresh)
    }

    fun updateUser(me: Me) {
        store.setValue(KEY_USER, AppJson.encodeToString(Me.serializer(), me))
        _user.value = me
    }

    /** Sign out but keep unsynced work on the phone; it is uploaded at next login by the same user. */
    fun logout() {
        store.setValue(KEY_ACCESS, null)
        store.setValue(KEY_REFRESH, null)
        store.setValue(KEY_USER, null)
        _user.value = null
    }

    var lastSync: String?
        get() = store.value(KEY_LAST_SYNC)
        set(v) = store.setValue(KEY_LAST_SYNC, v)

    companion object {
        private const val KEY_URL = "base_url"
        private const val KEY_ACCESS = "access"
        private const val KEY_REFRESH = "refresh"
        private const val KEY_USER = "user"
        private const val KEY_LAST_USER = "last_user"
        private const val KEY_DEVICE = "device_id"
        private const val KEY_LAST_SYNC = "last_sync"
    }
}
