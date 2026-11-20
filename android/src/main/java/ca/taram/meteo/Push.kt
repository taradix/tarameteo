package ca.taram.meteo

import android.content.Context
import android.util.Log
import androidx.core.content.edit
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import java.io.IOException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

// The app has no accounts: this install's FCM token is the only name its alerts have on the backend,
// which is also why it stays out of URLs and logs. Reinstalling loses the alerts with the token.
class Push(context: Context) {
    private val prefs = context.getSharedPreferences("push", Context.MODE_PRIVATE)

    /**
     * This install's token, moving its alerts along when FCM has replaced the one the backend knows.
     *
     * FCM only ever hands out the new token, so the old one has to be kept to say what moved. The new
     * one is stored only once the backend agrees, so a move that failed is retried on the next call.
     */
    suspend fun token(): String {
        val current = fetch()
        val known = prefs.getString("token", null)
        if (known != current) {
            if (known != null) api.putPushToken(known, current)
            prefs.edit { putString("token", current) }
            // Never the token itself: holding it is what owns the alerts.
            Log.i("Push", if (known == null) "Registered this install" else "Moved the alerts to a new token")
        }
        return current
    }

    // NOTE: FCM 25 deprecates tokens in favour of installation IDs (register()/onRegistered, and "fid"
    // instead of "token" in the send payload), which needs a manifest opt-in; tokens are still what the FCM
    // guide documents, so stay on them until the FID path is the default. Same for Messaging below.
    @Suppress("DEPRECATION")
    private suspend fun fetch(): String = suspendCancellableCoroutine { continuation ->
        // A build without google-services.json has no FirebaseApp, and getInstance() throws instead.
        val messaging = try {
            FirebaseMessaging.getInstance()
        } catch (e: IllegalStateException) {
            throw IOException(e.message, e)
        }
        // NOTE: hand-rolled await; kotlinx-coroutines-play-services is a dependency for these three lines.
        messaging.token
            .addOnSuccessListener { continuation.resume(it) }
            // An IOException, so callers handle FCM failing like the request failing.
            .addOnFailureListener { continuation.resumeWithException(it as? IOException ?: IOException(it.message, it)) }
    }
}

lateinit var push: Push

// A replaced token stops working right away, and pushes to it would make the backend drop the alerts
// it carried, so the move can't wait for the next launch.
class Messaging : FirebaseMessagingService() {
    @Suppress("OVERRIDE_DEPRECATION")
    override fun onNewToken(token: String) {
        // NOTE: one attempt, no WorkManager; Push.token() retries it when the app next needs the token.
        CoroutineScope(Dispatchers.IO).launch {
            try {
                push.token()
            } catch (e: IOException) {
                Log.w("Push", "Token move failed", e)
            }
        }
    }
}
