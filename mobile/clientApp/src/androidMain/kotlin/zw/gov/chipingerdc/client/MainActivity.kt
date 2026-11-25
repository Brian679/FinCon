package zw.gov.chipingerdc.client

import android.app.Application
import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import zw.gov.chipingerdc.shared.CouncilSdk
import zw.gov.chipingerdc.shared.DatabaseDriverFactory
import zw.gov.chipingerdc.shared.model.AppKind
import java.util.concurrent.TimeUnit

class ClientApplication : Application() {
    lateinit var sdk: CouncilSdk
        private set

    override fun onCreate() {
        super.onCreate()
        sdk = CouncilSdk(DatabaseDriverFactory(this), AppKind.CLIENT, BuildConfig.SERVER_URL)
        SyncWorker.schedule(this)
    }
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val sdk = (application as ClientApplication).sdk
        setContent { ClientApp(sdk) }
    }

    override fun onStop() {
        super.onStop()
        // Make sure anything captured is uploaded as soon as a connection is available.
        SyncWorker.syncWhenOnline(this)
    }
}

/** Background sync: every 15 minutes, and once whenever connectivity returns with work queued. */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val sdk = (applicationContext as ClientApplication).sdk
        if (!sdk.session.isLoggedIn) return Result.success()
        val state = sdk.sync.sync()
        return if (state.online == false && sdk.store.pendingCount() > 0) Result.retry() else Result.success()
    }

    companion object {
        private val online = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

        fun schedule(context: Context) {
            val req = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES).setConstraints(online).build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork("crdc-client-sync", ExistingPeriodicWorkPolicy.KEEP, req)
        }

        fun syncWhenOnline(context: Context) {
            val req = OneTimeWorkRequestBuilder<SyncWorker>().setConstraints(online).build()
            WorkManager.getInstance(context).enqueueUniqueWork("crdc-client-sync-now", ExistingWorkPolicy.REPLACE, req)
        }
    }
}
