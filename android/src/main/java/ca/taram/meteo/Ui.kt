package ca.taram.meteo

import android.text.format.DateFormat
import androidx.annotation.StringRes
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.transformLatest
import kotlinx.coroutines.withTimeoutOrNull
import java.net.SocketException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.text.NumberFormat
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.time.Duration.Companion.minutes

// Sensors report hourly and MELCCFP daily; pull to refresh covers the impatient.
val REFETCH = 5.minutes
// Outlives a rotation, so turning the phone doesn't refetch; stops soon after the screen goes away.
val WHILE_SHOWN = SharingStarted.WhileSubscribed(5_000)

val GREY = Color(0xFF888888)
val WARNING = Color(0xFFC62828)
val DIVIDER = Color(0xFFCCCCCC)

// The fields a reading or an alert can be about, in the order the web alert form lists them.
enum class Field(val key: String, @StringRes val label: Int, val unit: String, val digits: Int) {
    TEMPERATURE("temperature", R.string.field_temperature, "°C", 1),
    HUMIDITY("humidity", R.string.field_humidity, "%", 0),
    PRESSURE("pressure", R.string.field_pressure, "hPa", 0),
    RAIN("rain", R.string.field_rain, "mm", 1),
    SNOW("snow", R.string.field_snow, "mm", 1),
    // Alerts only: hours without a reading.
    OFFLINE("offline", R.string.field_offline, "h", 0);

    fun format(value: Double?) = "${num(value, digits)} $unit"
}

/**
 * Loads [keys]' latest value, then again every REFETCH or on [refresh], keeping the last state on screen
 * (marked [refreshing]) while the next one loads. Collected with the lifecycle, so polling stops in the
 * background and refetches on return.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class Poll<K, S>(scope: CoroutineScope, keys: Flow<K>, initial: S, refreshing: (S) -> S, load: suspend (K) -> S) {
    private val refreshes = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    private var last = initial

    val state: StateFlow<S> = keys.transformLatest { key ->
        while (true) {
            emit(refreshing(last))
            last = load(key)
            emit(last)
            withTimeoutOrNull(REFETCH) { refreshes.first() }
        }
    }.stateIn(scope, WHILE_SHOWN, refreshing(initial))

    fun refresh() {
        refreshes.tryEmit(Unit)
    }
}

// What went wrong in words people can act on, as a string and its arguments.
fun reason(error: Throwable): Pair<Int, List<Any>> = when (error) {
    is ApiError -> R.string.error_status to listOf(error.status)
    is BadResponse -> R.string.error_response to emptyList()
    // SocketException covers refused and reset connections as well as unreachable networks.
    is UnknownHostException, is SocketException, is SocketTimeoutException -> R.string.error_network to emptyList()
    else -> R.string.error_other to listOf(error.message ?: error.javaClass.simpleName)
}

@Composable
fun describe(error: Throwable): String {
    val (id, args) = reason(error)
    return stringResource(id, *args.toTypedArray())
}

fun num(value: Double?, digits: Int): String = value?.let {
    NumberFormat.getNumberInstance().apply {
        minimumFractionDigits = digits
        maximumFractionDigits = digits
    }.format(it)
} ?: "–"

// Skeletons for format(): the locale picks the order and punctuation.
const val DATE_SKELETON = "dMMM"
const val TIME_SKELETON = "jjmm"
const val DATE_TIME_SKELETON = "dMMMjjmm"

fun format(at: Instant, skeleton: String): String =
    DateTimeFormatter.ofPattern(DateFormat.getBestDateTimePattern(Locale.getDefault(), skeleton))
        .withZone(ZoneId.systemDefault()).format(at)

@Composable
fun Message(text: String) = Text(text, Modifier.fillMaxWidth().padding(16.dp), textAlign = TextAlign.Center)

@Composable
fun Caption(text: String, color: Color = GREY) = Text(text, Modifier.padding(top = 2.dp), color = color, fontSize = 13.sp)
