package ca.taram.meteo

import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test
import java.net.InetAddress
import java.net.ServerSocket
import kotlin.concurrent.thread

class ApiTest {
    @Volatile private var status = "200 OK"
    @Volatile private var body = "[]"
    private val requests = java.util.concurrent.CopyOnWriteArrayList<String>()

    // One request per connection is all HttpURLConnection needs when told to close.
    private val server = ServerSocket(0, 0, InetAddress.getLoopbackAddress())
    init {
        thread(isDaemon = true) {
            while (true) {
                val socket = runCatching { server.accept() }.getOrNull() ?: break
                socket.use {
                    val reader = it.getInputStream().bufferedReader()
                    requests += reader.readLine().split(" ")[1]
                    while (!reader.readLine().isNullOrEmpty()) continue
                    val bytes = body.toByteArray()
                    it.getOutputStream().write(
                        "HTTP/1.1 $status\r\nContent-Length: ${bytes.size}\r\nConnection: close\r\n\r\n".toByteArray() + bytes,
                    )
                }
            }
        }
    }

    private val api = Api("http://127.0.0.1:${server.localPort}")

    @After
    fun stop() = server.close()

    @Test
    fun getWeatherEncodesNameAndStart() = runBlocking {
        assertEquals(emptyList<WeatherReading>(), api.getWeather("a b", "2026-01-02T00:00:00+00:00"))
        assertEquals(listOf("/api/sensors/a%20b/weather?start=2026-01-02T00%3A00%3A00%2B00%3A00"), requests)
    }

    @Test
    fun getWeatherAggregateCallsTheAggregateEndpoint() = runBlocking {
        api.getWeatherAggregate("agg", "t")
        assertEquals(listOf("/api/sensors/agg/weather/aggregate?start=t"), requests)
    }

    @Test
    fun listSensorsRepeatsNamesEncodesValuesAndSkipsNulls() = runBlocking {
        body = """{"sensors": [{"name": "a b", "kind": "new-kind", "latitude": 1, "longitude": 2, "extra": 3}]}"""
        val list = api.listSensors(names = listOf("a b", "c"), q = "é&", limit = 5)
        assertEquals(listOf("/api/sensors?names=a%20b&names=c&q=%C3%A9%26&limit=5"), requests)
        // Unknown kinds and fields still parse, so the server can add them.
        assertEquals(SensorList(listOf(SensorEntry("a b", "new-kind", 1.0, 2.0))), list)
    }

    @Test
    fun listSensorsWithoutFilters() = runBlocking {
        body = """{"sensors": []}"""
        api.listSensors()
        assertEquals(listOf("/api/sensors"), requests)
    }

    @Test
    fun listClustersPassesBboxAndZoom() = runBlocking {
        body = """{"clusters": []}"""
        api.listClusters("-1.5,2,3,4", 6)
        assertEquals(listOf("/api/sensors/clusters?bbox=-1.5%2C2%2C3%2C4&zoom=6"), requests)
    }

    @Test
    fun nonOkResponsesThrowApiErrorWithTheStatus() {
        status = "404 Not Found"
        body = ""
        val error = assertThrows(ApiError::class.java) { runBlocking { api.listSensors() } }
        assertEquals(404, error.status)
        assertEquals("404 Not Found", error.message)
    }
}
