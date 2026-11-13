package ca.taram.meteo

import android.app.Application
import android.content.Context
import android.text.format.DateFormat
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.ProvideTextStyle
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.transformLatest
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import java.io.IOException
import java.text.NumberFormat
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import kotlin.time.Duration.Companion.minutes

private val REFETCH = 5.minutes
// Two missed hourly readings.
private val STALE = Duration.ofHours(3)
private val GREY = Color(0xFF888888)

// weather for timeseries, daily for aggregates; null while it couldn't be fetched.
data class Card(
    val sensor: SensorEntry,
    val fetchedAt: Instant,
    val weather: List<WeatherReading>? = null,
    val daily: List<AggregateReading>? = null,
)

data class DashboardState(val cards: List<Card> = emptyList(), val error: String? = null, val refreshing: Boolean = false)

class DashboardModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("shown", Context.MODE_PRIVATE)
    val shown = MutableStateFlow(prefs.getStringSet("shown", null).orEmpty().toSet())
    private val refreshes = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    private var last = DashboardState(refreshing = true)

    // Collected with the lifecycle, so polling stops in the background and refetches on return.
    @OptIn(ExperimentalCoroutinesApi::class)
    val state = shown.transformLatest { names ->
        if (names.isEmpty()) return@transformLatest emit(DashboardState().also { last = it })
        while (true) {
            emit(last.copy(refreshing = true))
            last = load(names)
            emit(last)
            withTimeoutOrNull(REFETCH) { refreshes.first() }
        }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(), last)

    fun refresh() {
        refreshes.tryEmit(Unit)
    }

    // ponytail: stand-in for the phase 3 picker, shows the first few sensors.
    fun choose() {
        viewModelScope.launch {
            try {
                val names = api.listSensors(limit = 5).sensors.filter { it.kind in KINDS }.map { it.name }.toSet()
                prefs.edit().putStringSet("shown", names).apply()
                shown.value = names
            } catch (e: IOException) {
                // Tap again.
            }
        }
    }

    private suspend fun load(names: Set<String>) = try {
        val sensors = api.listSensors(names = names.sorted()).sensors.filter { it.kind in KINDS }
        val now = Instant.now()
        DashboardState(coroutineScope { sensors.map { async { card(it, now) } }.awaitAll() })
    } catch (e: IOException) {
        DashboardState(error = e.describe())
    }

    private suspend fun card(sensor: SensorEntry, now: Instant) = try {
        if (sensor.kind == "timeseries") {
            Card(sensor, now, weather = api.getWeather(sensor.name, (now - Duration.ofHours(24)).toString()))
        } else {
            Card(sensor, now, daily = api.getWeatherAggregate(sensor.name, (now - Duration.ofDays(7)).toString()))
        }
    } catch (e: IOException) {
        Card(sensor, now)
    }
}

private fun IOException.describe() = "${javaClass.simpleName}: $message"

private fun num(value: Double?, digits: Int): String = value?.let {
    NumberFormat.getNumberInstance().apply {
        minimumFractionDigits = digits
        maximumFractionDigits = digits
    }.format(it)
} ?: "–"

private fun day(timestamp: String): String =
    DateTimeFormatter.ofPattern(DateFormat.getBestDateTimePattern(java.util.Locale.getDefault(), "dMMM"))
        .withZone(ZoneId.systemDefault()).format(instant(timestamp))

private val AGO = mapOf(
    ChronoUnit.MINUTES to R.string.card_ago_minutes,
    ChronoUnit.HOURS to R.string.card_ago_hours,
    ChronoUnit.DAYS to R.string.card_ago_days,
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Dashboard(model: DashboardModel = viewModel()) {
    val state by model.state.collectAsStateWithLifecycle()
    val shown by model.shown.collectAsStateWithLifecycle()
    PullToRefreshBox(state.refreshing, model::refresh, Modifier.fillMaxSize()) {
        // Messages sit in the list too, so they can be pulled to retry.
        LazyColumn(Modifier.fillMaxSize()) {
            state.error?.let { item { Message(it) } }
            items(state.cards, key = { it.sensor.name }) { SensorCard(it) }
            if (shown.isEmpty()) {
                item {
                    Button(model::choose, Modifier.fillMaxWidth().padding(24.dp)) { Text(stringResource(R.string.sensors_choose)) }
                }
            } else if (state.cards.isEmpty() && state.error == null && !state.refreshing) {
                item { Message(stringResource(R.string.dashboard_empty)) }
            }
        }
    }
}

@Composable
private fun Message(text: String) = Text(text, Modifier.fillMaxWidth().padding(16.dp), textAlign = TextAlign.Center)

@Composable
private fun SensorCard(card: Card) {
    Column(Modifier.fillMaxWidth().padding(16.dp)) {
        Text(card.sensor.name, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
        val data = if (card.sensor.kind == "timeseries") card.weather else card.daily
        when {
            data == null -> Time("…")
            data.isEmpty() -> Time(stringResource(R.string.card_no_data))
            card.weather != null -> TimeseriesBody(summarize(card.weather)!!, card.fetchedAt)
            else -> AggregateBody(card.daily!!.last())
        }
    }
    HorizontalDivider(color = Color(0xFFCCCCCC))
}

@Composable
private fun Time(text: String, color: Color = GREY) = Text(text, Modifier.padding(top = 2.dp), color = color, fontSize = 13.sp)

@Composable
private fun Line(content: @Composable RowScope.() -> Unit) =
    ProvideTextStyle(LocalTextStyle.current.copy(fontSize = 15.sp)) { Row(Modifier.padding(top = 4.dp), content = content) }

// Ages are relative to the last fetch, which refreshes every REFETCH.
@Composable
private fun TimeseriesBody(summary: Summary, now: Instant) {
    val latest = summary.latest
    val (unit, count) = age(latest.timestamp, now)
    val stale = Duration.between(instant(latest.timestamp), now) > STALE
    Time(stringResource(AGO.getValue(unit), count), if (stale) Color(0xFFC62828) else GREY)
    Line {
        Text("${num(latest.temperature, 1)} °C", Modifier.alignByBaseline(), fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
        TrendArrow(summary.temperatureTrend)
        Text("  " + stringResource(R.string.card_range, num(summary.min, 1), num(summary.max, 1)), Modifier.alignByBaseline())
    }
    Line {
        Text("${num(latest.humidity, 0)} % · ${num(latest.pressure, 0)} hPa", Modifier.alignByBaseline())
        TrendArrow(summary.pressureTrend)
    }
}

@Composable
private fun AggregateBody(reading: AggregateReading) {
    // Daily readings: the day matters, not the time.
    Time(day(reading.timestamp))
    Line {
        Text(
            stringResource(
                R.string.card_aggregate,
                num(reading.temperatureMin, 1), num(reading.temperatureAvg, 1), num(reading.temperatureMax, 1),
            ),
        )
    }
    Line { Text(stringResource(R.string.card_precipitation, num(reading.rain, 1), num(reading.snow, 1))) }
}

@Composable
private fun RowScope.TrendArrow(trend: Trend?) {
    if (trend == null) return
    val label = stringResource(if (trend == Trend.RISING) R.string.card_rising else R.string.card_falling)
    Text(if (trend == Trend.RISING) " ↑" else " ↓", Modifier.alignByBaseline().semantics { contentDescription = label })
}
