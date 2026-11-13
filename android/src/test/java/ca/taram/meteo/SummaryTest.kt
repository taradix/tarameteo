package ca.taram.meteo

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Instant
import java.time.temporal.ChronoUnit

class SummaryTest {
    private fun reading(hour: Int, temperature: Double, pressure: Double) =
        WeatherReading("s1", "2026-01-02T%02d:00:00+00:00".format(hour), temperature, 50.0, pressure)

    @Test
    fun summarizeTakesTheLatestReadingTemperatureRangeAnd3hTrends() {
        val readings = listOf(reading(0, 9.0, 1000.0), reading(1, 2.0, 1005.0), reading(3, 3.0, 1010.0), reading(4, 1.0, 1010.5))
        assertEquals(Summary(readings[3], 1.0, 9.0, Trend.FALLING, Trend.RISING), summarize(readings))
    }

    @Test
    fun summarizeTreatsSmallChangesAndMissingHistoryAsSteady() {
        val small = summarize(listOf(reading(0, 1.0, 1000.0), reading(3, 1.4, 1000.9)))!!
        assertEquals(null to null, small.temperatureTrend to small.pressureTrend)
        val short = summarize(listOf(reading(2, 1.0, 1000.0), reading(3, 9.0, 1020.0)))!!
        assertEquals(null to null, short.temperatureTrend to short.pressureTrend)
        assertNull(summarize(emptyList()))
    }

    @Test
    fun ageRoundsDownToTheLargestWholeUnit() {
        val now = Instant.parse("2026-01-03T00:00:00Z")
        assertEquals(ChronoUnit.MINUTES to 42L, age("2026-01-02T23:18:00Z", now))
        assertEquals(ChronoUnit.HOURS to 2L, age("2026-01-02T21:30:00Z", now))
        assertEquals(ChronoUnit.DAYS to 2L, age("2026-01-01T00:00:00Z", now))
        // Clock skew can put readings slightly in the future.
        assertEquals(ChronoUnit.MINUTES to 0L, age("2026-01-03T00:01:00Z", now))
    }
}
