package ca.taram.meteo

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.location.LocationManager
import android.os.CancellationSignal
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts.RequestPermission
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.location.LocationManagerCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.google.android.gms.maps.CameraUpdateFactory
import com.google.android.gms.maps.model.BitmapDescriptorFactory
import com.google.android.gms.maps.model.LatLng
import com.google.android.gms.maps.model.LatLngBounds
import com.google.maps.android.compose.CameraPositionState
import com.google.maps.android.compose.GoogleMap
import com.google.maps.android.compose.MapProperties
import com.google.maps.android.compose.Marker
import com.google.maps.android.compose.MarkerComposable
import com.google.maps.android.compose.rememberCameraPositionState
import com.google.maps.android.compose.rememberUpdatedMarkerState
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.mapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import java.io.IOException
import java.math.BigDecimal
import java.math.RoundingMode
import kotlin.coroutines.resume
import kotlin.math.log2
import kotlin.math.roundToInt

// Enough to scroll through; past that, zooming in or searching beats scrolling.
private const val LIMIT = 50
// About 100 km across around you, and 20 km around a sensor picked from the list.
private const val NEARBY = 0.9
private const val FOCUS = 0.2

// The server takes west > east as crossing the antimeridian. Three decimals (about 100 m) keep requests steady.
fun bboxOf(west: Double, south: Double, east: Double, north: Double) = listOf(west, south, east, north)
    .joinToString(",") { BigDecimal(it).setScale(3, RoundingMode.HALF_UP).stripTrailingZeros().toPlainString() }

// Web map zoom: the world is 360° wide at zoom 0, and each level halves it.
fun zoomOf(west: Double, east: Double): Int {
    val span = if (east > west) east - west else east - west + 360
    return log2(360 / span).roundToInt().coerceIn(0, 22)
}

data class Viewport(val bbox: String, val zoom: Int)

private fun viewportOf(camera: CameraPositionState): Viewport? {
    val bounds = camera.projection?.visibleRegion?.latLngBounds ?: return null
    val (south, west) = bounds.southwest.let { it.latitude to it.longitude }
    val (north, east) = bounds.northeast.let { it.latitude to it.longitude }
    // ponytail: zoomed out this far the world repeats across the screen and the bounds can't say so; ask for all of it.
    if (camera.position.zoom < 1) return Viewport(bboxOf(-180.0, south, 180.0, north), 0)
    return Viewport(bboxOf(west, south, east, north), zoomOf(west, east))
}

private fun around(at: LatLng, span: Double) =
    LatLngBounds(LatLng(at.latitude - span / 2, at.longitude - span / 2), LatLng(at.latitude + span / 2, at.longitude + span / 2))

private fun round(x: Double) = Math.round(x * 100) / 100.0

// Two decimals (about 1 km) is enough to sort sensors, and all the server learns about the phone.
// ponytail: network provider only; GPS-only phones fall back to the world by name.
@SuppressLint("MissingPermission") // Only called once the permission is granted.
private suspend fun currentPosition(context: Context): LatLng? {
    val manager = context.getSystemService(LocationManager::class.java)
    if (!manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) return null
    return suspendCancellableCoroutine { continuation ->
        val signal = CancellationSignal()
        continuation.invokeOnCancellation { signal.cancel() }
        LocationManagerCompat.getCurrentLocation(
            manager, LocationManager.NETWORK_PROVIDER, signal, ContextCompat.getMainExecutor(context),
        ) { location -> continuation.resume(location?.let { LatLng(round(it.latitude), round(it.longitude)) }) }
    }
}

private suspend fun <T> attempt(block: suspend () -> T): Result<T> =
    try {
        Result.success(block())
    } catch (e: IOException) {
        Result.failure(e)
    }

@OptIn(FlowPreview::class, ExperimentalCoroutinesApi::class)
class PickerModel : ViewModel() {
    val query = MutableStateFlow("")
    val viewport = MutableStateFlow<Viewport?>(null)
    // Rounded; null when denied or off. located turns true once that is known.
    val here = MutableStateFlow<LatLng?>(null)
    val located = MutableStateFlow(false)
    var asked = false

    // Searching looks everywhere; otherwise the list follows the map.
    val sensors = combine(debouncedQuery(), viewport.filterNotNull(), here) { q, view, at ->
        Triple(q.ifEmpty { null }, if (q.isEmpty()) view.bbox else null, at)
    }.distinctUntilChanged().mapLatest { (q, bbox, at) ->
        attempt { api.listSensors(q = q, bbox = bbox, latitude = at?.latitude, longitude = at?.longitude, limit = LIMIT) }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    val clusters = viewport.filterNotNull().mapLatest { attempt { api.listClusters(it.bbox, it.zoom) } }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    // Searches once typing pauses, not on every keystroke.
    private fun debouncedQuery() = query.debounce(300).map { it.trim() }

    fun locate(context: Context, granted: Boolean) {
        viewModelScope.launch {
            here.value = if (granted) currentPosition(context) else null
            located.value = true
        }
    }
}

@Composable
fun Picker(model: PickerModel = viewModel()) {
    val context = LocalContext.current.applicationContext
    val permission = rememberLauncherForActivityResult(RequestPermission()) { model.locate(context, it) }
    LaunchedEffect(Unit) {
        if (!model.asked) {
            model.asked = true
            permission.launch(Manifest.permission.ACCESS_COARSE_LOCATION)
        }
    }
    val query by model.query.collectAsStateWithLifecycle()
    val here by model.here.collectAsStateWithLifecycle()
    val located by model.located.collectAsStateWithLifecycle()
    val sensors by model.sensors.collectAsStateWithLifecycle()
    val clusters by model.clusters.collectAsStateWithLifecycle()
    val names by shown.names.collectAsStateWithLifecycle()
    var selected by remember { mutableStateOf<SensorEntry?>(null) }
    var loaded by remember { mutableStateOf(false) }
    val camera = rememberCameraPositionState()
    val scope = rememberCoroutineScope()

    // Denied or failed (location off): start on the world, sorted by name. The list follows the map once it settles.
    LaunchedEffect(loaded, located) {
        if (!loaded || !located) return@LaunchedEffect
        here?.let { camera.move(CameraUpdateFactory.newLatLngBounds(around(it, NEARBY), 0)) }
        snapshotFlow { camera.isMoving }.filter { !it }.collect { model.viewport.value = viewportOf(camera) }
    }

    Column(Modifier.fillMaxSize().imePadding()) {
        OutlinedTextField(
            query,
            { model.query.value = it },
            Modifier.fillMaxWidth().padding(12.dp),
            placeholder = { Text(stringResource(R.string.sensors_search)) },
            singleLine = true,
        )
        Box(Modifier.weight(1f)) {
            if (located) {
                GoogleMap(
                    Modifier.fillMaxSize(),
                    cameraPositionState = camera,
                    properties = MapProperties(isMyLocationEnabled = here != null),
                    onMapLoaded = { loaded = true },
                    onMapClick = { selected = null },
                ) {
                    clusters?.getOrNull()?.clusters?.forEach { cluster ->
                        val sensor = cluster.sensor
                        val at = LatLng(cluster.latitude, cluster.longitude)
                        if (sensor == null) {
                            key(at) {
                                val label = pluralStringResource(R.plurals.sensors_cluster, cluster.count, cluster.count)
                                // Cells are a quarter of the view, so zooming in twice splits the cluster.
                                // ponytail: sensors sharing a spot stay one cluster at any zoom; spread them out if that happens.
                                MarkerComposable(
                                    cluster.count,
                                    state = rememberUpdatedMarkerState(at),
                                    contentDescription = label,
                                    onClick = {
                                        scope.launch { camera.animate(CameraUpdateFactory.newLatLngZoom(at, camera.position.zoom + 2)) }
                                        true
                                    },
                                ) { ClusterBubble(cluster.count) }
                            }
                        } else if (sensor.kind in KINDS) {
                            key(sensor.kind, sensor.name) {
                                Marker(
                                    state = rememberUpdatedMarkerState(LatLng(sensor.latitude, sensor.longitude)),
                                    contentDescription = sensor.name,
                                    icon = if (sensor.name in names) BitmapDescriptorFactory.defaultMarker(BitmapDescriptorFactory.HUE_AZURE) else null,
                                    onClick = {
                                        selected = sensor
                                        true
                                    },
                                )
                            }
                        }
                    }
                }
            }
            selected?.let {
                Surface(
                    Modifier.align(Alignment.BottomCenter).padding(8.dp).fillMaxWidth(),
                    shape = RoundedCornerShape(8.dp),
                    shadowElevation = 4.dp,
                ) { SensorRow(it, names) }
            }
        }
        LazyColumn(Modifier.weight(1f)) {
            if (located && here == null) item { Message(stringResource(R.string.sensors_no_location)) }
            (sensors?.exceptionOrNull() ?: clusters?.exceptionOrNull())?.let { item { Message(it.describe()) } }
            val list = sensors?.getOrNull()
            val entries = list?.sensors.orEmpty().filter { it.kind in KINDS }
            items(entries, key = { "${it.kind}:${it.name}" }) { sensor ->
                SensorRow(sensor, names) {
                    selected = sensor
                    val at = LatLng(sensor.latitude, sensor.longitude)
                    scope.launch { camera.animate(CameraUpdateFactory.newLatLngBounds(around(at, FOCUS), 0)) }
                }
            }
            if (list != null && entries.isEmpty()) item { Message(stringResource(R.string.dashboard_empty)) }
            if (list?.truncated == true) {
                item { Message(stringResource(if (here != null) R.string.sensors_truncated_near else R.string.sensors_truncated, LIMIT)) }
            }
        }
    }
}

@Composable
private fun ClusterBubble(count: Int) = Text(
    "$count",
    Modifier.background(COLOR, RoundedCornerShape(16.dp)).padding(horizontal = 10.dp, vertical = 6.dp),
    color = Color.White,
    fontWeight = FontWeight.SemiBold,
)

@Composable
private fun SensorRow(sensor: SensorEntry, names: Set<String>, onClick: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f).then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)) {
            Text(sensor.name, fontSize = 17.sp)
            sensor.distanceKm?.let { Time("${num(it, if (it < 10) 1 else 0)} km") }
        }
        val label = stringResource(R.string.sensors_toggle, sensor.name)
        Switch(sensor.name in names, { shown.toggle(sensor.name) }, Modifier.semantics { contentDescription = label })
    }
    HorizontalDivider(color = DIVIDER)
}
