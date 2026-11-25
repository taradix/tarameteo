package ca.taram.meteo

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.Application
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanResult
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts.RequestPermission
import androidx.activity.result.contract.ActivityResultContracts.StartActivityForResult
import androidx.activity.result.contract.ActivityResultContracts.StartIntentSenderForResult
import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenu
import androidx.compose.material3.ExposedDropdownMenuAnchorType
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.google.android.gms.maps.CameraUpdateFactory
import com.google.android.gms.maps.model.CameraPosition
import com.google.android.gms.maps.model.LatLng
import com.google.maps.android.compose.GoogleMap
import com.google.maps.android.compose.Marker
import com.google.maps.android.compose.rememberCameraPositionState
import com.google.maps.android.compose.rememberUpdatedMarkerState
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import java.io.IOException
import java.net.URI
import kotlin.math.roundToLong
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.seconds

// A station joins the WiFi, syncs the time and publishes within a minute of an ok.
private val FIRST_READING = 2.minutes
private val FIRST_READING_POLL = 5.seconds
// Street level, to tap the station's spot.
private const val PIN_ZOOM = 15f

// Below this, the station's WiFi tends to drop out; above STRONG, it has room to spare (dBm).
private const val WEAK = -80
private const val STRONG = -67

@StringRes
private fun signalOf(rssi: Int) = when {
    rssi >= STRONG -> R.string.setup_signal_strong
    rssi >= WEAK -> R.string.setup_signal_fair
    else -> R.string.setup_signal_weak
}

// Whole minutes, as the interval field shows them; one that isn't whole shows rounded until edited.
fun minutesOf(seconds: Int) = ((seconds + 30) / 60).coerceAtLeast(1).toString()

private val MINUTES = INTERVALS.first / 60..INTERVALS.last / 60

// What the port and minutes fields hold, or null when the station won't take it; the form says so under the field.
fun portOf(field: String): Int? = field.trim().toIntOrNull()?.takeIf { it in PORTS }
fun secondsOf(minutes: String): Int? = minutes.trim().toIntOrNull()?.takeIf { it in MINUTES }?.let { it * 60 }

// The server to send, or null when the fields hold the station's own (or no port), so it keeps it.
fun serverChange(station: MqttServer, host: String, port: String): MqttServer? =
    portOf(port)?.let { MqttServer(host.trim(), it) }?.takeIf { it != station }

// The interval to send, or null when the field still shows the station's, so one that isn't whole minutes stays.
fun intervalChange(station: Int, minutes: String): Int? = secondsOf(minutes)?.takeIf { minutes.trim() != minutesOf(station) }

// Whether this app sees the station's readings: the backend it reads gets them from the MQTT server on its own host.
fun readsHere(host: String, apiBase: String): Boolean = host.trim().equals(URI(apiBase).host, ignoreCase = true)

// Four decimals (about 10 m), like the backend's location tags.
private fun fourDecimals(x: Double) = (x * 10_000).roundToLong() / 10_000.0

// CONFIRM, RESETTING and RESET are the reset's, which skips the form.
enum class Step { START, CONNECTING, FORM, SENDING, WAITING, LATE, ELSEWHERE, CONFIRM, RESETTING, RESET }

// The fields under Advanced settings, which show it when they have a problem.
private val ADVANCED = setOf("server", "port", "interval")

// What a field shows under it for the problem, when the problem is about that field.
private fun fieldError(problem: Problem?, field: String): (@Composable () -> Unit)? =
    problem?.takeIf { it.field == field }?.let { { Text(stringResource(it.message)) } }

// What went wrong, as the message to show; the field it is about shows it, else the screen does.
data class Problem(@StringRes val message: Int, val field: String? = null)

// The station's error codes; the ones a field owns show under it.
private fun problemOf(error: IOException) = when (error) {
    is PairingFailed -> Problem(R.string.setup_pairing)
    is StalePairing -> Problem(R.string.setup_stale_pairing)
    is Rejected -> when (error.code) {
        "ssid" -> Problem(R.string.setup_ssid_rejected, "ssid")
        "password" -> Problem(R.string.setup_password_rejected, "password")
        "label" -> Problem(R.string.setup_label_rejected, "label")
        "server" -> Problem(R.string.setup_server_rejected, "server")
        "port" -> Problem(R.string.setup_port_rejected, "port")
        "interval" -> Problem(R.string.setup_interval_rejected, "interval")
        "wifi" -> Problem(R.string.setup_wifi_rejected, "password")
        "storage" -> Problem(R.string.setup_storage)
        else -> Problem(R.string.setup_other)
    }
    // Lost: out of range, or the window closed.
    else -> Problem(R.string.setup_lost)
}

class SetupModel(application: Application) : AndroidViewModel(application) {
    var step by mutableStateOf(Step.START)
    var problem by mutableStateOf<Problem?>(null)
    var id by mutableStateOf("")
    var ssid by mutableStateOf("")
    var password by mutableStateOf("")
    var label by mutableStateOf("")
    // What the station found when it powered on, strongest first.
    var networks by mutableStateOf<List<Network>>(emptyList())
    // Where the station stands: its last reading's spot, else where the user taps.
    var pin by mutableStateOf<LatLng?>(null)
    // Where the map starts when there is no pin yet.
    var here by mutableStateOf<LatLng?>(null)
    // Where the station sends its readings now, and how often. The fields start as its values, and only
    // what changed gets sent.
    private var stationServer: MqttServer? = null
    private var stationInterval: Int? = null
    var host by mutableStateOf("")
    var port by mutableStateOf("")
    var minutes by mutableStateOf("")
    var advanced by mutableStateOf(false)
    // Set once the station's first reading is in, for the screen to move on to the dashboard.
    var done by mutableStateOf(false)
    var asked = false
    // What the user came to do, picked before the chooser: reset the station rather than set it up.
    var resetting by mutableStateOf(false)
    private var station: Station? = null

    fun open(result: ScanResult) {
        val context = getApplication<Application>()
        // The chooser's job is done once it has picked.
        forget(context, result.device.address)
        @SuppressLint("MissingPermission") // The screen got BLUETOOTH_CONNECT before the chooser.
        val name = result.scanRecord?.deviceName ?: result.device.name
        id = name.orEmpty()
        problem = null
        step = Step.CONNECTING
        viewModelScope.launch {
            try {
                val opened = Station.open(context, result.device)
                station = opened
                if (resetting) {
                    step = Step.CONFIRM
                    return@launch
                }
                label = opened.label()
                val server = opened.mqttServer().also { stationServer = it }
                val interval = opened.interval().also { stationInterval = it }
                host = server.host
                port = server.port.toString()
                minutes = minutesOf(interval)
                advanced = false
                networks = opened.networks()
                // A station moving to a new WiFi keeps its spot; it can't say where that is, its readings can.
                val known = try {
                    api.listSensors(names = listOf(id)).sensors.firstOrNull()
                } catch (_: IOException) {
                    null
                }
                known?.let { pin = LatLng(it.latitude, it.longitude) }
                if (label.isEmpty()) label = known?.label.orEmpty()
                step = Step.FORM
            } catch (e: IOException) {
                fail(e)
            }
        }
    }

    fun notFound() {
        problem = Problem(R.string.setup_not_found)
    }

    fun refused() {
        problem = Problem(R.string.setup_permission)
    }

    // Only for the map's start: a coarse fix is a few streets off, so the user still taps the spot.
    fun locate(granted: Boolean) {
        if (!granted) return
        val context = getApplication<Application>()
        viewModelScope.launch {
            here = lastPosition(context) ?: withTimeoutOrNull(LOCATION_TIMEOUT) { currentPosition(context) }
        }
    }

    // Whether the advanced fields hold what the station takes; the form says what's wrong under each.
    val advancedValid get() = host.isNotBlank() && portOf(port) != null && secondsOf(minutes) != null

    fun send() {
        val at = pin ?: return
        val station = station ?: return
        val server = serverChange(stationServer ?: return, host, port)
        val interval = intervalChange(stationInterval ?: return, minutes)
        problem = null
        step = Step.SENDING
        viewModelScope.launch {
            try {
                val spot = LatLng(fourDecimals(at.latitude), fourDecimals(at.longitude))
                station.provision(WiFiCredentials(ssid, password), spot, label.trim(), server, interval)
            } catch (e: Rejected) {
                // The station saved nothing and still listens, so the form stays as it was.
                problem = problemOf(e)
                if (problem?.field in ADVANCED) advanced = true
                step = Step.FORM
                return@launch
            } catch (e: IOException) {
                fail(e)
                return@launch
            }
            close()
            // The server the station uses now, changed or not.
            if (!readsHere(host, BuildConfig.API_BASE)) {
                step = Step.ELSEWHERE
                return@launch
            }
            shown.show(id)
            step = Step.WAITING
            val arrived = withTimeoutOrNull(FIRST_READING) { while (!listed()) delay(FIRST_READING_POLL) } != null
            if (arrived) done = true else step = Step.LATE
        }
    }

    fun reset() {
        val station = station ?: return
        problem = null
        step = Step.RESETTING
        viewModelScope.launch {
            try {
                station.reset()
            } catch (e: Rejected) {
                // The station still listens, so the user can try again.
                problem = Problem(if (e.code == "storage") R.string.reset_storage else R.string.setup_other)
                step = Step.CONFIRM
                return@launch
            } catch (e: IOException) {
                fail(e)
                return@launch
            }
            close()
            step = Step.RESET
        }
    }

    fun cancel() {
        close()
        problem = null
        step = Step.START
    }

    // The sensor list has the station once a reading of it is in.
    private suspend fun listed() = try {
        api.listSensors(names = listOf(id)).sensors.isNotEmpty()
    } catch (_: IOException) {
        false
    }

    private fun fail(error: IOException) {
        close()
        problem = problemOf(error)
        step = Step.START
    }

    private fun close() {
        station?.close()
        station = null
    }

    override fun onCleared() = close()
}

@Composable
fun SetupScreen(onDone: () -> Unit, model: SetupModel = viewModel()) {
    LaunchedEffect(model.done) { if (model.done) onDone() }
    Column(Modifier.fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(16.dp)) {
        model.problem?.takeIf { it.field == null }?.let { Text(stringResource(it.message), color = WARNING) }
        when (model.step) {
            Step.START -> Start(model)
            Step.CONNECTING -> Busy(stringResource(R.string.setup_connecting))
            Step.FORM -> Form(model)
            Step.SENDING -> Busy(stringResource(R.string.setup_joining, model.ssid))
            Step.WAITING -> Busy(stringResource(R.string.setup_waiting))
            Step.LATE -> {
                Text(stringResource(R.string.setup_late), Modifier.padding(vertical = 8.dp))
                Button(onDone, Modifier.fillMaxWidth()) { Text(stringResource(R.string.setup_dashboard)) }
            }
            Step.ELSEWHERE -> {
                Text(stringResource(R.string.setup_elsewhere, model.host.trim()), Modifier.padding(vertical = 8.dp))
                Button(onDone, Modifier.fillMaxWidth()) { Text(stringResource(R.string.setup_dashboard)) }
            }
            Step.CONFIRM -> Confirm(model)
            Step.RESETTING -> Busy(stringResource(R.string.reset_busy))
            Step.RESET -> {
                Text(stringResource(R.string.reset_done, model.id), Modifier.padding(vertical = 8.dp))
                Button(onDone, Modifier.fillMaxWidth()) { Text(stringResource(R.string.setup_dashboard)) }
            }
        }
    }
}

@Composable
private fun Busy(text: String) = Column(Modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
    CircularProgressIndicator()
    Text(text, Modifier.padding(top = 16.dp))
}

// Permission, then Bluetooth on, then the chooser: each step's result starts the next.
@SuppressLint("MissingPermission") // ACTION_REQUEST_ENABLE runs only once BLUETOOTH_CONNECT is granted.
@Composable
private fun Start(model: SetupModel) {
    val context = LocalContext.current
    val adapter = remember { context.getSystemService(BluetoothManager::class.java)?.adapter }
    val supported = adapter != null && context.packageManager.hasSystemFeature(PackageManager.FEATURE_COMPANION_DEVICE_SETUP)
    val chooser = rememberLauncherForActivityResult(StartIntentSenderForResult()) { result ->
        // Backing out of the chooser is a choice, not a problem.
        if (result.resultCode == Activity.RESULT_OK) chosen(result.data)?.let(model::open)
    }
    val find = { chooseStation(context, { chooser.launch(IntentSenderRequest.Builder(it).build()) }, model::notFound) }
    val enable = rememberLauncherForActivityResult(StartActivityForResult()) { if (it.resultCode == Activity.RESULT_OK) find() }
    val ready = { if (adapter!!.isEnabled) find() else enable.launch(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE)) }
    val permission = rememberLauncherForActivityResult(RequestPermission()) { if (it) ready() else model.refused() }

    val start = { resetting: Boolean ->
        model.resetting = resetting
        val granted = Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
        if (granted) ready() else permission.launch(Manifest.permission.BLUETOOTH_CONNECT)
    }

    if (!supported) return Text(stringResource(R.string.setup_unsupported))
    Text(stringResource(R.string.setup_intro), Modifier.padding(vertical = 8.dp))
    Button({ start(false) }, Modifier.fillMaxWidth()) { Text(stringResource(R.string.setup_find)) }
    // Picked before connecting, so resetting is a choice and not a slip on the form.
    TextButton({ start(true) }, Modifier.fillMaxWidth().padding(top = 8.dp)) { Text(stringResource(R.string.setup_reset)) }
}

// The last chance to back out: a reset can't be undone, only followed by a new setup.
@Composable
private fun Confirm(model: SetupModel) {
    Text(stringResource(R.string.reset_confirm, model.id), Modifier.padding(vertical = 8.dp))
    Button(
        model::reset,
        Modifier.fillMaxWidth(),
        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
    ) { Text(stringResource(R.string.reset_send)) }
    TextButton(model::cancel, Modifier.fillMaxWidth()) { Text(stringResource(android.R.string.cancel)) }
}

@Composable
private fun Form(model: SetupModel) {
    val permission = rememberLauncherForActivityResult(RequestPermission(), model::locate)
    LaunchedEffect(Unit) {
        if (model.pin == null && !model.asked) {
            model.asked = true
            permission.launch(Manifest.permission.ACCESS_COARSE_LOCATION)
        }
    }
    var visible by remember { mutableStateOf(false) }
    fun error(field: String) = fieldError(model.problem, field)

    Text(stringResource(R.string.setup_station, model.id), Modifier.padding(bottom = 8.dp))
    Ssid(model, error("ssid"))
    OutlinedTextField(
        model.password,
        { model.password = it },
        Modifier.fillMaxWidth(),
        label = { Text(stringResource(R.string.setup_password)) },
        trailingIcon = {
            TextButton({ visible = !visible }) { Text(stringResource(if (visible) R.string.setup_hide else R.string.setup_show)) }
        },
        isError = error("password") != null,
        supportingText = error("password"),
        visualTransformation = if (visible) VisualTransformation.None else PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
        singleLine = true,
    )
    OutlinedTextField(
        model.label,
        { model.label = it },
        Modifier.fillMaxWidth(),
        label = { Text(stringResource(R.string.setup_label)) },
        isError = error("label") != null,
        supportingText = error("label") ?: { Text(stringResource(R.string.setup_label_hint, model.id)) },
        singleLine = true,
    )
    Text(stringResource(R.string.setup_pin), Modifier.padding(vertical = 8.dp))
    Pin(model)
    Advanced(model)
    Button(
        model::send,
        Modifier.fillMaxWidth().padding(top = 16.dp),
        enabled = model.ssid.isNotEmpty() && model.password.isNotEmpty() && model.pin != null &&
            model.advancedValid,
    ) { Text(stringResource(R.string.setup_send)) }
}

// Where the station sends its readings: folded away, since only someone running their own server changes it.
@Composable
private fun Advanced(model: SetupModel) {
    fun error(field: String) = fieldError(model.problem, field)

    TextButton({ model.advanced = !model.advanced }, Modifier.padding(top = 8.dp)) {
        Text(stringResource(if (model.advanced) R.string.setup_advanced_hide else R.string.setup_advanced))
    }
    if (!model.advanced) return
    Text(stringResource(R.string.setup_advanced_hint), Modifier.padding(bottom = 8.dp))
    OutlinedTextField(
        model.host,
        { model.host = it },
        Modifier.fillMaxWidth(),
        label = { Text(stringResource(R.string.setup_server)) },
        isError = error("server") != null || model.host.isBlank(),
        supportingText = error("server"),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
        singleLine = true,
    )
    OutlinedTextField(
        model.port,
        { model.port = it },
        Modifier.fillMaxWidth(),
        label = { Text(stringResource(R.string.setup_port)) },
        isError = error("port") != null || portOf(model.port) == null,
        supportingText = error("port") ?: { Text(stringResource(R.string.setup_port_hint)) },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        singleLine = true,
    )
    OutlinedTextField(
        model.minutes,
        { model.minutes = it },
        Modifier.fillMaxWidth(),
        label = { Text(stringResource(R.string.setup_interval)) },
        isError = error("interval") != null || secondsOf(model.minutes) == null,
        supportingText = error("interval") ?: { Text(stringResource(R.string.setup_interval_hint)) },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        singleLine = true,
    )
}

// The network name, typed or picked from what the station found; a hidden network has to be typed.
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Ssid(model: SetupModel, error: (@Composable () -> Unit)?) {
    var expanded by remember { mutableStateOf(false) }
    // Typing narrows the list, unless the field holds a pick already.
    val typed = model.ssid.takeIf { ssid -> model.networks.none { it.ssid == ssid } }.orEmpty()
    val shown = model.networks.filter { it.ssid.contains(typed, ignoreCase = true) }
    val weak = model.networks.find { it.ssid == model.ssid }?.takeIf { it.rssi < WEAK }
    val open = expanded && shown.isNotEmpty()
    ExposedDropdownMenuBox(open, { expanded = it }) {
        OutlinedTextField(
            model.ssid,
            {
                model.ssid = it
                expanded = true
            },
            Modifier.fillMaxWidth().menuAnchor(ExposedDropdownMenuAnchorType.PrimaryEditable, model.networks.isNotEmpty()),
            label = { Text(stringResource(R.string.setup_ssid)) },
            trailingIcon = model.networks.takeIf { it.isNotEmpty() }?.let { @Composable { ExposedDropdownMenuDefaults.TrailingIcon(open) } },
            isError = error != null,
            supportingText = error ?: weak?.let { @Composable { Text(stringResource(R.string.setup_signal_warning), color = WARNING) } },
            singleLine = true,
        )
        ExposedDropdownMenu(open, { expanded = false }) {
            shown.forEach { network ->
                DropdownMenuItem(
                    text = { Text(network.ssid) },
                    onClick = {
                        model.ssid = network.ssid
                        expanded = false
                    },
                    trailingIcon = { Text(stringResource(signalOf(network.rssi))) },
                )
            }
        }
    }
}

@Composable
private fun Pin(model: SetupModel) {
    val camera = rememberCameraPositionState {
        position = model.pin?.let { CameraPosition.fromLatLngZoom(it, PIN_ZOOM) } ?: HOME
    }
    // The fix comes late; recentre on it unless there is a pin to show already.
    LaunchedEffect(model.here) {
        val at = model.here ?: return@LaunchedEffect
        if (model.pin == null) camera.move(CameraUpdateFactory.newLatLngZoom(at, PIN_ZOOM))
    }
    GoogleMap(
        Modifier.fillMaxWidth().height(300.dp),
        cameraPositionState = camera,
        onMapClick = { model.pin = it },
    ) {
        model.pin?.let { Marker(state = rememberUpdatedMarkerState(it), contentDescription = model.id) }
    }
}
