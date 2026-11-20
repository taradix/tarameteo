package ca.taram.meteo

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.flow.MutableStateFlow
import java.io.IOException
import java.time.Duration
import java.time.Instant
import java.time.ZoneId

private val RANGE_LABELS = mapOf(
    24 to R.string.range_24,
    7 * 24 to R.string.range_168,
    30 * 24 to R.string.range_720,
    90 * 24 to R.string.range_2160,
)

data class DetailState(
    val weather: List<WeatherReading>? = null,
    val daily: List<AggregateReading>? = null,
    val error: IOException? = null,
    val refreshing: Boolean = false,
)

class DetailModel(private val name: String, val aggregate: Boolean) : ViewModel() {
    // Daily aggregates need longer ranges than hourly readings to show anything.
    val ranges = if (aggregate) listOf(7 * 24, 30 * 24, 90 * 24) else listOf(24, 7 * 24, 30 * 24)
    val hours = MutableStateFlow(ranges[0])

    // Keeps the current charts on screen while another range loads.
    private val poll = Poll(viewModelScope, hours, DetailState(refreshing = true), { it.copy(refreshing = true) }, ::load)
    val state = poll.state

    fun refresh() = poll.refresh()

    private suspend fun load(hours: Int) = try {
        val start = (Instant.now() - Duration.ofHours(hours.toLong())).toString()
        if (aggregate) DetailState(daily = api.getWeatherAggregate(name, start)) else DetailState(weather = api.getWeather(name, start))
    } catch (e: IOException) {
        DetailState(error = e)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SensorScreen(
    name: String,
    kind: String,
    label: String?,
    model: DetailModel = viewModel { DetailModel(name, kind == "aggregate") },
) {
    val state by model.state.collectAsStateWithLifecycle()
    val hours by model.hours.collectAsStateWithLifecycle()
    PullToRefreshBox(state.refreshing, model::refresh, Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            // The title bar shows the label, so the ID printed on the sticker goes here.
            if (label != null) Box(Modifier.padding(start = 16.dp, top = 8.dp)) { Caption(name) }
            Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (h in model.ranges) {
                    FilterChip(h == hours, { model.hours.value = h }, { Text(stringResource(RANGE_LABELS.getValue(h))) })
                }
            }
            val weather = state.weather
            val daily = state.daily
            val error = state.error
            when {
                error != null -> Message(describe(error))
                weather?.isEmpty() == true || daily?.isEmpty() == true -> Message(stringResource(R.string.chart_no_data))
                weather != null -> TimeseriesCharts(weather, hours)
                daily != null -> AggregateCharts(daily, hours)
            }
        }
    }
}

@Composable
private fun TimeseriesCharts(readings: List<WeatherReading>, hours: Int) {
    val fields = listOf(
        Field.TEMPERATURE to WeatherReading::temperature,
        Field.HUMIDITY to WeatherReading::humidity,
        Field.PRESSURE to WeatherReading::pressure,
    )
    for ((field, value) in fields) {
        val points = readings.map { Point(instant(it.timestamp).toEpochMilli(), listOf(value(it))) }
        WeatherChart(stringResource(field.label), hours, points, Plot.LINE, daily = false) { field.format(it.ys[0]) }
    }
}

@Composable
private fun AggregateCharts(readings: List<AggregateReading>, hours: Int) {
    // Each reading covers a local day; plot it at midnight, like the web dashboard.
    fun day(r: AggregateReading) =
        instant(r.timestamp).atZone(ZoneId.systemDefault()).toLocalDate().atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli()
    val temperatures = readings.map { Point(day(it), listOf(it.temperatureAvg, it.temperatureMin, it.temperatureMax)) }
    val precipitation = readings.map { Point(day(it), listOf(it.rain, it.snow)) }
    val aggregate = stringResource(R.string.card_aggregate)
    val rainSnow = stringResource(R.string.card_precipitation)
    val digits = Field.TEMPERATURE.digits
    WeatherChart(stringResource(Field.TEMPERATURE.label), hours, temperatures, Plot.BAND, daily = true) {
        aggregate.format(num(it.ys[1], digits), num(it.ys[0], digits), num(it.ys[2], digits))
    }
    WeatherChart(stringResource(R.string.chart_precipitation), hours, precipitation, Plot.BARS, daily = true) {
        rainSnow.format(num(it.ys[0], Field.RAIN.digits), num(it.ys[1], Field.SNOW.digits))
    }
}
