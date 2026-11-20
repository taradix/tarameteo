package ca.taram.meteo

import androidx.compose.foundation.clickable
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import java.io.IOException
import java.time.Duration
import java.time.Instant
import java.time.temporal.ChronoUnit

// Two missed hourly readings.
private val STALE = Duration.ofHours(3)
// How far back a card looks; card_no_data_timeseries and card_no_data_aggregate name these.
private val TIMESERIES_WINDOW = Duration.ofHours(24)
private val AGGREGATE_WINDOW = Duration.ofDays(7)

// weather for timeseries, daily for aggregates, error when they couldn't be fetched.
data class Card(
    val sensor: SensorEntry,
    val fetchedAt: Instant,
    val weather: List<WeatherReading>? = null,
    val daily: List<AggregateReading>? = null,
    val error: IOException? = null,
)

data class DashboardState(val cards: List<Card> = emptyList(), val error: IOException? = null, val refreshing: Boolean = false)

class DashboardModel : ViewModel() {
    private val poll = Poll(viewModelScope, shown.names, DashboardState(refreshing = true), { it.copy(refreshing = true) }, ::load)
    val state = poll.state

    fun refresh() = poll.refresh()

    private suspend fun load(names: Set<String>) = try {
        // No names would list every sensor.
        if (names.isEmpty()) {
            DashboardState()
        } else {
            val sensors = api.listSensors(names = names.sorted()).sensors.filter { it.kind in KINDS }
            val now = Instant.now()
            DashboardState(coroutineScope { sensors.map { async { card(it, now) } }.awaitAll() })
        }
    } catch (e: IOException) {
        DashboardState(error = e)
    }

    private suspend fun card(sensor: SensorEntry, now: Instant) = try {
        if (sensor.kind == "timeseries") {
            Card(sensor, now, weather = api.getWeather(sensor.name, (now - TIMESERIES_WINDOW).toString()))
        } else {
            Card(sensor, now, daily = api.getWeatherAggregate(sensor.name, (now - AGGREGATE_WINDOW).toString()))
        }
    } catch (e: IOException) {
        Card(sensor, now, error = e)
    }
}

private val AGO = mapOf(
    ChronoUnit.MINUTES to R.string.card_ago_minutes,
    ChronoUnit.HOURS to R.string.card_ago_hours,
    ChronoUnit.DAYS to R.string.card_ago_days,
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Dashboard(onChoose: () -> Unit, onOpen: (SensorEntry) -> Unit, model: DashboardModel = viewModel()) {
    val state by model.state.collectAsStateWithLifecycle()
    val names by shown.names.collectAsStateWithLifecycle()
    PullToRefreshBox(state.refreshing, model::refresh, Modifier.fillMaxSize()) {
        // Messages sit in the list too, so they can be pulled to retry.
        LazyColumn(Modifier.fillMaxSize()) {
            state.error?.let { item { Message(describe(it)) } }
            items(state.cards, key = { it.sensor.name }) { SensorCard(it) { onOpen(it.sensor) } }
            if (names.isEmpty()) {
                item {
                    Button(onChoose, Modifier.fillMaxWidth().padding(24.dp)) { Text(stringResource(R.string.sensors_choose)) }
                }
            } else if (state.cards.isEmpty() && state.error == null && !state.refreshing) {
                item { Message(stringResource(R.string.dashboard_empty)) }
            }
        }
    }
}

@Composable
private fun SensorCard(card: Card, onClick: () -> Unit) {
    Column(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(16.dp)) {
        Text(card.sensor.title, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
        when {
            card.error != null -> Caption(describe(card.error), WARNING)
            card.weather != null ->
                summarize(card.weather)?.let { TimeseriesBody(it, card.fetchedAt) }
                    ?: Caption(stringResource(R.string.card_no_data_timeseries))
            card.daily != null ->
                card.daily.lastOrNull()?.let { AggregateBody(it) } ?: Caption(stringResource(R.string.card_no_data_aggregate))
        }
    }
    HorizontalDivider(color = DIVIDER)
}

@Composable
private fun Line(content: @Composable RowScope.() -> Unit) =
    ProvideTextStyle(LocalTextStyle.current.copy(fontSize = 15.sp)) { Row(Modifier.padding(top = 4.dp), content = content) }

// Ages are relative to the last fetch, which refreshes every REFETCH.
@Composable
private fun TimeseriesBody(summary: Summary, now: Instant) {
    val latest = summary.latest
    val (unit, count) = age(latest.timestamp, now)
    val stale = Duration.between(instant(latest.timestamp), now) > STALE
    Caption(stringResource(AGO.getValue(unit), count), if (stale) WARNING else GREY)
    Line {
        Text(Field.TEMPERATURE.format(latest.temperature), Modifier.alignByBaseline(), fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
        TrendArrow(summary.temperatureTrend)
        val digits = Field.TEMPERATURE.digits
        Text("  " + stringResource(R.string.card_range, num(summary.min, digits), num(summary.max, digits)), Modifier.alignByBaseline())
    }
    Line {
        Text("${Field.HUMIDITY.format(latest.humidity)} · ${Field.PRESSURE.format(latest.pressure)}", Modifier.alignByBaseline())
        TrendArrow(summary.pressureTrend)
    }
}

@Composable
private fun AggregateBody(reading: AggregateReading) {
    // Daily readings: the day matters, not the time.
    Caption(format(instant(reading.timestamp), DATE_SKELETON))
    val digits = Field.TEMPERATURE.digits
    Line {
        Text(
            stringResource(
                R.string.card_aggregate,
                num(reading.temperatureMin, digits), num(reading.temperatureAvg, digits), num(reading.temperatureMax, digits),
            ),
        )
    }
    Line { Text(stringResource(R.string.card_precipitation, num(reading.rain, Field.RAIN.digits), num(reading.snow, Field.SNOW.digits))) }
}

@Composable
private fun RowScope.TrendArrow(trend: Trend?) {
    if (trend == null) return
    val label = stringResource(if (trend == Trend.RISING) R.string.card_rising else R.string.card_falling)
    Text(if (trend == Trend.RISING) " ↑" else " ↓", Modifier.alignByBaseline().semantics { contentDescription = label })
}
