package ca.taram.meteo

import com.google.android.gms.maps.model.LatLng
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class BleTest {
    @Test
    fun locationIsTwoLittleEndianFloats() {
        // 1.0f is 0x3f800000 and -2.0f is 0xc0000000, low byte first.
        val bytes = byteArrayOf(0x00, 0x00, 0x80.toByte(), 0x3f, 0x00, 0x00, 0x00, 0xc0.toByte())
        assertArrayEquals(bytes, location(LatLng(1.0, -2.0)))
    }

    @Test
    fun portAndIntervalAreLittleEndian() {
        assertArrayEquals(byteArrayOf(0xb3.toByte(), 0x22), uint16(8883))
        assertArrayEquals(byteArrayOf(0xff.toByte(), 0xff.toByte()), uint16(65535))
        assertArrayEquals(byteArrayOf(0x10, 0x0e, 0, 0), uint32(3600))
    }

    @Test
    fun mqttServerIsHostAndLittleEndianPort() {
        // 65535 is 0xffff: read as a signed short, it would come back as -1.
        val port = byteArrayOf(0xff.toByte(), 0xff.toByte())
        assertEquals(MqttServer("meteo.taram.ca", 65535), mqttServerOf("meteo.taram.ca".encodeToByteArray(), port))
    }

    @Test
    fun intervalIsLittleEndianSeconds() {
        assertEquals(86400, intervalOf(byteArrayOf(0x80.toByte(), 0x51, 0x01, 0x00)))
    }

    @Test
    fun onlyOkAndErrorsAreVerdicts() {
        assertNull(verdict("idle"))
        assertNull(verdict("provisioning"))
        assertTrue(verdict("ok")!!.isSuccess)
        assertEquals("wifi", (verdict("error:wifi")!!.exceptionOrNull() as Rejected).code)
    }

    @Test
    fun networksAreRssiLengthAndSsid() {
        val value = byteArrayOf(-40, 4) + "home".encodeToByteArray() + byteArrayOf(-85, 2) + "é".encodeToByteArray()
        assertEquals(listOf(Network("home", -40), Network("é", -85)), networksOf(value))
    }

    @Test
    fun aCutNetworkEndsTheList() {
        val value = byteArrayOf(-40, 1) + "a".encodeToByteArray() + byteArrayOf(-50, 5) + "bc".encodeToByteArray()
        assertEquals(listOf(Network("a", -40)), networksOf(value))
        assertEquals(emptyList<Network>(), networksOf(byteArrayOf(-40)))
    }

    @Test
    fun intervalBoundsMatchTheFirmware() {
        val header = File(System.getProperty("settingsContract")!!).readText()
        fun constant(name: String) =
            Regex("""static const uint32_t $name = (\d+);""").find(header)?.groupValues?.get(1)?.toInt()
                ?: error("$name not found in the firmware's CertificateManager.h")
        assertEquals(constant("MIN_INTERVAL")..constant("MAX_INTERVAL"), INTERVALS)
    }

    @Test
    fun uuidsMatchTheFirmware() {
        val header = File(System.getProperty("bleContract")!!).readText()
        val firmware = Regex("""constexpr const char \*(\w+) = "([0-9a-f-]+)"""").findAll(header)
            .associate { it.groupValues[1] to it.groupValues[2] }
        val app = mapOf(
            "SERVICE" to SERVICE, "SSID" to SSID, "PASSWORD" to PASSWORD, "LOCATION" to LOCATION,
            "COMMIT" to COMMIT, "STATUS" to STATUS, "LABEL" to LABEL, "NETWORKS" to NETWORKS,
            "SERVER" to SERVER, "PORT" to PORT, "INTERVAL" to INTERVAL,
        ).mapValues { it.value.toString() }
        assertEquals(firmware, app)
    }
}
