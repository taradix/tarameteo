package ca.taram.meteo

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

// Mirrors of backend/openapi.json schemas, with only the fields the app reads; ApiContractTest keeps them in sync.
@Serializable
data class SensorEntry(
    val name: String,
    val kind: String,
    val latitude: Double,
    val longitude: Double,
    @SerialName("distance_km") val distanceKm: Double? = null,
    val label: String? = null,
) {
    // What people see: the owner's label, else the ID.
    val title get() = label ?: name
}

// The latest firmware the backend offers a board.
@Serializable
data class FirmwareManifest(val version: String)

@Serializable
data class SensorList(val sensors: List<SensorEntry>, val truncated: Boolean = false)

@Serializable
data class WeatherReading(
    val sensor: String,
    val timestamp: String,
    val temperature: Double,
    val humidity: Double,
    val pressure: Double,
)

@Serializable
data class AggregateReading(
    val sensor: String,
    val timestamp: String,
    @SerialName("temperature_min") val temperatureMin: Double? = null,
    @SerialName("temperature_avg") val temperatureAvg: Double? = null,
    @SerialName("temperature_max") val temperatureMax: Double? = null,
    val rain: Double? = null,
    val snow: Double? = null,
)

@Serializable
data class PushTokenUpdate(@SerialName("push_token") val pushToken: String)

// What to watch for; the install is named by its token in the header, so the rule says nothing about who.
@Serializable
data class AlertRule(
    val sensor: String,
    val field: String,
    val condition: String,
    val threshold: Double,
    val language: String = "en",
)

@Serializable
data class PushAlert(
    val id: String,
    val sensor: String,
    val field: String,
    val condition: String,
    val threshold: Double,
    val language: String = "en",
    val triggered: Boolean = false,
)

@Serializable
data class Cluster(val latitude: Double, val longitude: Double, val count: Int, val sensor: SensorEntry? = null)

@Serializable
data class ClusterList(val clusters: List<Cluster>)

// Clients ignore sensor kinds they don't know (see CONTRIBUTING.rst).
val KINDS = setOf("timeseries", "aggregate")

class ApiError(val status: Int, message: String) : IOException(message)

// The server broke the contract; an IOException, so it fails like any other request instead of crashing.
class BadResponse(cause: Throwable) : IOException(cause.message, cause)

// Like encodeURIComponent: safe in a path segment as well as a query value.
private fun encode(value: Any) = URLEncoder.encode(value.toString(), "UTF-8").replace("+", "%20")

// Lists repeat the key (names=a&names=b), as FastAPI expects; nulls are left out.
private fun query(vararg params: Pair<String, Any?>): String {
    val pairs = params.flatMap { (key, value) ->
        when (value) {
            null -> emptyList()
            is List<*> -> value.map { "$key=${encode(it!!)}" }
            else -> listOf("$key=${encode(value)}")
        }
    }
    return if (pairs.isEmpty()) "" else pairs.joinToString("&", prefix = "?")
}

class Api(private val base: String = BuildConfig.API_BASE) {
    // Additive API changes add fields older apps don't know.
    private val json = Json { ignoreUnknownKeys = true }

    private suspend fun request(path: String, method: String = "GET", token: String? = null, body: String? = null) =
        withContext(Dispatchers.IO) {
            val connection = URL(base + path).openConnection() as HttpURLConnection
            try {
                connection.requestMethod = method
                // The push token both names an install and authorizes it, so it travels in a header, never in a URL.
                if (token != null) connection.setRequestProperty("X-Push-Token", token)
                if (body != null) {
                    connection.doOutput = true
                    connection.setRequestProperty("Content-Type", "application/json")
                    connection.outputStream.use { it.write(body.toByteArray()) }
                }
                val status = connection.responseCode
                if (status !in 200..299) throw ApiError(status, "$status ${connection.responseMessage}")
                if (status == 204) "" else connection.inputStream.bufferedReader().use { it.readText() }
            } finally {
                connection.disconnect()
            }
        }

    private suspend inline fun <reified T> get(path: String, token: String? = null): T =
        withContext(Dispatchers.IO) {
            val body = request(path, token = token)
            // SerializationException is an IllegalArgumentException, which decodeFromString also throws for invalid values.
            try {
                json.decodeFromString<T>(body)
            } catch (e: IllegalArgumentException) {
                throw BadResponse(e)
            }
        }

    private fun weather(name: String, suffix: String, start: String) =
        "/api/sensors/${encode(name)}/weather$suffix${query("start" to start)}"

    // latitude/longitude sort nearest first, within radius km when given; bbox is "west,south,east,north" in degrees.
    suspend fun listSensors(
        names: List<String>? = null,
        q: String? = null,
        bbox: String? = null,
        latitude: Double? = null,
        longitude: Double? = null,
        radius: Double? = null,
        limit: Int? = null,
    ): SensorList = get(
        "/api/sensors" + query(
            "names" to names, "q" to q, "bbox" to bbox,
            "latitude" to latitude, "longitude" to longitude, "radius" to radius, "limit" to limit,
        ),
    )

    suspend fun listClusters(bbox: String, zoom: Int): ClusterList =
        get("/api/sensors/clusters" + query("bbox" to bbox, "zoom" to zoom))

    suspend fun getWeather(name: String, start: String): List<WeatherReading> = get(weather(name, "", start))

    suspend fun getWeatherAggregate(name: String, start: String): List<AggregateReading> =
        get(weather(name, "/aggregate", start))

    suspend fun getFirmware(board: String): FirmwareManifest = get("/api/firmware/${encode(board)}")

    // Points this install's alerts at the token FCM replaced the old one with.
    suspend fun putPushToken(old: String, new: String) {
        request("/api/alerts/push", "PUT", old, json.encodeToString(PushTokenUpdate(new)))
    }

    suspend fun listPushAlerts(token: String): List<PushAlert> = get("/api/alerts/push", token)

    // Holding the token is the consent, so an alert starts sending right away: nothing to confirm.
    suspend fun createPushAlert(token: String, rule: AlertRule) {
        request("/api/alerts/push", "POST", token, json.encodeToString(rule))
    }

    suspend fun deletePushAlert(token: String, id: String) {
        request("/api/alerts/push/${encode(id)}", "DELETE", token)
    }
}

val api = Api()
