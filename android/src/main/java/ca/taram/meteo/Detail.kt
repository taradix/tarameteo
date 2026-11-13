package ca.taram.meteo

import androidx.compose.foundation.layout.Arrangement
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
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.transformLatest
import kotlinx.coroutines.withTimeoutOrNull
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
    val error: String? = null,
    val refreshing: Boolean = false,
)

class DetailModel(private val name: String, val aggregate: Boolean) : ViewModel() {
    // Daily aggregates need longer ranges than hourly readings to show anything.
    val ranges = if (aggregate) listOf(7 * 24, 30 * 24, 90 * 24) else listOf(24, 7 * 24, 30 * 24)
    val hours = MutableStateFlow(ranges[0])
    private val refreshes = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    private var last = DetailState(refreshing = true)

    // Keeps the current charts on screen while another range loads.
    @OptIn(ExperimentalCoroutinesApi::class)
    val state = hours.transformLatest { h ->
        while (true) {
            emit(last.copy(refreshing = true))
            last = load(h)
            emit(last)
            withTimeoutOrNull(REFETCH) { refreshes.first() }
        }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(), last)

    fun refresh() {
        refreshes.tryEmit(Unit)
    }

    private suspend fun load(hours: Int) = try {
        val start = (Instant.now() - Duration.ofHours(hours.toLong())).toString()
        if (aggregate) DetailState(daily = api.getWeatherAggregate(name, start)) else DetailState(weather = api.getWeather(name, start))
    } catch (e: IOException) {
        DetailState(error = e.describe())
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SensorScreen(name: String, kind: String, model: DetailModel = viewModel { DetailModel(name, kind == "aggregate") }) {
    val state by model.state.collectAsStateWithLifecycle()
    val hours by model.hours.collectAsStateWithLifecycle()
    PullToRefreshBox(state.refreshing, model::refresh, Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (h in model.ranges) {
                    FilterChip(h == hours, { model.hours.value = h }, { Text(stringResource(RANGE_LABELS.getValue(h))) })
                }
            }
            val weather = state.weather
            val daily = state.daily
            when {
                state.error != null -> Message(state.error!!)
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
        Triple(R.string.chart_temperature, "°C", 1) to WeatherReading::temperature,
        Triple(R.string.chart_humidity, "%", 0) to WeatherReading::humidity,
        Triple(R.string.chart_pressure, "hPa", 0) to WeatherReading::pressure,
    )
    for ((info, field) in fields) {
        val (title, unit, digits) = info
        val points = readings.map { Point(instant(it.timestamp).toEpochMilli(), listOf(field(it))) }
        WeatherChart(stringResource(title), hours, points, Plot.LINE, daily = false) { "${num(it.ys[0], digits)} $unit" }
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
    WeatherChart(stringResource(R.string.chart_temperature), hours, temperatures, Plot.BAND, daily = true) {
        aggregate.format(num(it.ys[1], 1), num(it.ys[0], 1), num(it.ys[2], 1))
    }
    WeatherChart(stringResource(R.string.chart_precipitation), hours, precipitation, Plot.BARS, daily = true) {
        rainSnow.format(num(it.ys[0], 1), num(it.ys[1], 1))
    }
}
