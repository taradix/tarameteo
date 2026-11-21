package ca.taram.meteo

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ProvisionTest {
    private val station = MqttServer("meteo.taram.ca", 8883)

    @Test
    fun portsOutsideTheRangeAreRefused() {
        assertEquals(8883, portOf(" 8883 "))
        assertEquals(1, portOf("1"))
        assertEquals(65535, portOf("65535"))
        assertNull(portOf("0"))
        assertNull(portOf("65536"))
        assertNull(portOf("eighty"))
    }

    @Test
    fun minutesBecomeSecondsWithinADay() {
        assertEquals(60, secondsOf("1"))
        assertEquals(86400, secondsOf("1440"))
        assertNull(secondsOf("0"))
        assertNull(secondsOf("1441"))
    }

    @Test
    fun hugeMinutesAreRefusedNotWrapped() {
        // 71582790 minutes is 4294967400 s, which wraps to 104 s in an Int.
        assertNull(secondsOf("71582790"))
    }

    @Test
    fun intervalsShowAsRoundedMinutes() {
        assertEquals("60", minutesOf(3600))
        assertEquals("2", minutesOf(90))
        assertEquals("1", minutesOf(60))
    }

    @Test
    fun anUnchangedServerIsNotSent() {
        assertNull(serverChange(station, " meteo.taram.ca ", "8883"))
    }

    @Test
    fun aChangedHostOrPortSendsTheWholeServer() {
        assertEquals(MqttServer("mqtt.example", 8883), serverChange(station, "mqtt.example", "8883"))
        assertEquals(MqttServer("meteo.taram.ca", 1883), serverChange(station, "meteo.taram.ca", "1883"))
    }

    @Test
    fun anUnchangedIntervalIsNotSentEvenWhenNotWholeMinutes() {
        // 90 s shows as 2 minutes; sending that back would make it 120 s.
        assertNull(intervalChange(90, "2"))
        assertEquals(180, intervalChange(90, "3"))
    }

    @Test
    fun readingsShowHereOnlyFromTheAppsOwnHost() {
        assertTrue(readsHere("Meteo.Taram.ca", "https://meteo.taram.ca"))
        assertFalse(readsHere("192.168.1.20", "https://meteo.taram.ca"))
    }
}
