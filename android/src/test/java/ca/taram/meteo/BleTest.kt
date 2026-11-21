package ca.taram.meteo

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
        assertArrayEquals(bytes, location(1.0, -2.0))
    }

    @Test
    fun onlyOkAndErrorsAreVerdicts() {
        assertNull(verdict("idle"))
        assertNull(verdict("provisioning"))
        assertTrue(verdict("ok")!!.isSuccess)
        assertEquals("wifi", (verdict("error:wifi")!!.exceptionOrNull() as Rejected).code)
    }

    @Test
    fun uuidsMatchTheFirmware() {
        val header = File(System.getProperty("bleContract")!!).readText()
        val firmware = Regex("""constexpr const char \*(\w+) = "([0-9a-f-]+)"""").findAll(header)
            .associate { it.groupValues[1] to it.groupValues[2] }
        val app = mapOf(
            "SERVICE" to SERVICE, "SSID" to SSID, "PASSWORD" to PASSWORD, "LOCATION" to LOCATION,
            "COMMIT" to COMMIT, "STATUS" to STATUS, "LABEL" to LABEL,
        ).mapValues { it.value.toString() }
        assertEquals(firmware, app)
    }
}
