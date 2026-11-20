package ca.taram.meteo

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts.RequestPermission
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.mapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.io.IOException
import java.util.Locale

// The fields the API watches, in the order the web form lists them.
private val FIELDS = listOf(
    "temperature" to R.string.alerts_field_temperature,
    "humidity" to R.string.alerts_field_humidity,
    "pressure" to R.string.alerts_field_pressure,
    "rain" to R.string.alerts_field_rain,
    "snow" to R.string.alerts_field_snow,
    "offline" to R.string.alerts_field_offline,
)

private val UNITS = mapOf(
    "temperature" to "°C", "humidity" to "%", "pressure" to "hPa", "rain" to "mm", "snow" to "mm", "offline" to "h",
)

// The server won't look further back than this for a missing reading, and says so with a 422.
private const val OFFLINE_MAX = 30 * 24.0

// The alert's text comes from the server, written in the language the phone is set to.
private fun language() = if (Locale.getDefault().language == "fr") "fr" else "en"

data class AlertsState(val alerts: List<PushAlert>? = null, val error: String? = null, val busy: Boolean = false)

class AlertsModel : ViewModel() {
    val state = MutableStateFlow(AlertsState(busy = true))
    var asked = false

    // The dashboard's sensors by ID, for their titles; an ID is still readable if this fails.
    @OptIn(ExperimentalCoroutinesApi::class)
    val titles = shown.names.mapLatest { names ->
        // No names would list every sensor.
        if (names.isEmpty()) return@mapLatest emptyMap()
        try {
            api.listSensors(names = names.sorted()).sensors.associate { it.name to it.title }
        } catch (_: IOException) {
            emptyMap()
        }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyMap())

    init {
        reload()
    }

    fun reload() = act { state.value = AlertsState(api.listPushAlerts(push.token())) }

    fun create(rule: AlertRule) = act {
        api.createPushAlert(push.token(), rule)
        state.value = AlertsState(api.listPushAlerts(push.token()))
    }

    fun delete(alert: PushAlert) = act {
        api.deletePushAlert(push.token(), alert.id)
        state.value = state.value.copy(alerts = state.value.alerts?.minus(alert))
    }

    // Every call needs the token first, and asking FCM for it fails in as many ways as the request does.
    private fun act(block: suspend () -> Unit) {
        viewModelScope.launch {
            state.value = state.value.copy(error = null, busy = true)
            val failure = runCatching { block() }.exceptionOrNull()
            state.value = state.value.copy(error = failure?.describe(), busy = false)
        }
    }
}

// These alerts belong to the install, not to a person: the token in every request is their only name.
@Composable
fun AlertsScreen(model: AlertsModel = viewModel()) {
    val context = LocalContext.current
    val state by model.state.collectAsStateWithLifecycle()
    val names by shown.names.collectAsStateWithLifecycle()
    val titles by model.titles.collectAsStateWithLifecycle()
    // Before 33 there is nothing to ask for: notifications are granted at install.
    var allowed by remember {
        mutableStateOf(
            Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
                PackageManager.PERMISSION_GRANTED,
        )
    }
    val permission = rememberLauncherForActivityResult(RequestPermission()) { allowed = it }
    // Asking here is asking at the point of use: nothing else in the app notifies.
    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !allowed && !model.asked) {
            model.asked = true
            permission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    LazyColumn(Modifier.fillMaxSize().imePadding()) {
        if (!allowed) item { Message(stringResource(R.string.alerts_blocked)) }
        state.error?.let { item { Message(it) } }
        items(state.alerts.orEmpty(), key = { it.id }) { alert ->
            AlertRow(alert, titles) { model.delete(alert) }
        }
        if (state.alerts?.isEmpty() == true) item { Message(stringResource(R.string.alerts_none)) }
        item { NewAlert(names.sorted(), titles, state.busy, model::create) }
    }
}

// Reads like the alert's own text: "outdoor-north: temperature below -20 °C".
@Composable
private fun rule(alert: PushAlert, titles: Map<String, String>): String {
    val sensor = titles[alert.sensor] ?: alert.sensor
    val field = FIELDS.firstOrNull { it.first == alert.field }?.let { stringResource(it.second) } ?: alert.field
    val value = "${num(alert.threshold, if (alert.threshold % 1.0 == 0.0) 0 else 1)} ${UNITS[alert.field].orEmpty()}"
    if (alert.field == "offline") return "$sensor: $field $value"
    val condition = stringResource(if (alert.condition == "above") R.string.alerts_above else R.string.alerts_below)
    return "$sensor: $field $condition $value"
}

@Composable
private fun AlertRow(alert: PushAlert, titles: Map<String, String>, onDelete: () -> Unit) {
    val text = rule(alert, titles)
    Row(Modifier.fillMaxWidth().padding(start = 16.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f).padding(vertical = 16.dp)) {
            Text(text, fontSize = 17.sp)
            if (alert.triggered) Time(stringResource(R.string.alerts_triggered))
        }
        val label = stringResource(R.string.alerts_delete, text)
        TextButton(onDelete, Modifier.semantics { contentDescription = label }) { Text("✕", fontSize = 18.sp) }
    }
    HorizontalDivider(color = DIVIDER)
}

// The sensors on the dashboard are the ones worth alerting on, so the picker stays the one place to choose.
@Composable
private fun NewAlert(sensors: List<String>, titles: Map<String, String>, busy: Boolean, onCreate: (AlertRule) -> Unit) {
    if (sensors.isEmpty()) return Message(stringResource(R.string.alerts_no_sensors))
    var sensor by remember(sensors) { mutableStateOf(sensors.first()) }
    var field by remember { mutableStateOf(FIELDS.first().first) }
    var above by remember { mutableStateOf(false) }
    var threshold by remember { mutableStateOf("") }
    val offline = field == "offline"
    // A French keyboard offers the decimal comma, and thresholds go below zero.
    val value = threshold.replace(',', '.').toDoubleOrNull()

    Column(Modifier.padding(16.dp)) {
        Text(stringResource(R.string.alerts_new), fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
        Chips(sensors, sensor, { titles[it] ?: it }) { sensor = it }
        Chips(FIELDS, FIELDS.first { it.first == field }, { stringResource(it.second) }) { field = it.first }
        // An offline alert is always "more than N hours", so there is nothing to choose.
        if (!offline) {
            Chips(listOf(false, true), above, { stringResource(if (it) R.string.alerts_above else R.string.alerts_below) }) {
                above = it
            }
        }
        OutlinedTextField(
            threshold,
            { threshold = it },
            Modifier.fillMaxWidth().padding(top = 8.dp),
            label = { Text(stringResource(if (offline) R.string.alerts_hours else R.string.alerts_threshold)) },
            suffix = { Text(UNITS[field].orEmpty()) },
            // NOTE: the phone keypad is the only one with a minus sign; Compose has no signed number type.
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            singleLine = true,
        )
        Button(
            { onCreate(AlertRule(sensor, field, if (offline || above) "above" else "below", value!!, language())) },
            Modifier.fillMaxWidth().padding(top = 8.dp),
            enabled = !busy && value != null && (!offline || value in 1.0..OFFLINE_MAX),
        ) { Text(stringResource(R.string.alerts_create)) }
    }
}

@Composable
private fun <T> Chips(options: List<T>, selected: T, label: @Composable (T) -> String, onPick: (T) -> Unit) =
    FlowRow(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        for (option in options) {
            FilterChip(option == selected, { onPick(option) }, { Text(label(option)) })
        }
    }
