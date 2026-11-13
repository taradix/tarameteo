package ca.taram.meteo

import java.time.Duration
import java.time.Instant
import java.time.OffsetDateTime
import java.time.temporal.ChronoUnit

enum class Trend { RISING, FALLING }

private val TREND_WINDOW = Duration.ofHours(3)
// Changes smaller than this over TREND_WINDOW count as steady; tune to taste.
private const val TEMPERATURE_STEP = 0.5
private const val PRESSURE_STEP = 1.0

data class Summary(
    val latest: WeatherReading,
    val min: Double,
    val max: Double,
    val temperatureTrend: Trend?,
    val pressureTrend: Trend?,
)

// Instant.parse only takes "Z" before API 33; the API may send "+00:00".
fun instant(timestamp: String): Instant = OffsetDateTime.parse(timestamp).toInstant()

private fun trend(now: Double, then: Double?, step: Double): Trend? = when {
    then == null || Math.abs(now - then) < step -> null
    now > then -> Trend.RISING
    else -> Trend.FALLING
}

// Readings come sorted oldest first, as the API returns them.
fun summarize(readings: List<WeatherReading>): Summary? {
    val latest = readings.lastOrNull() ?: return null
    val cutoff = instant(latest.timestamp) - TREND_WINDOW
    val before = readings.lastOrNull { instant(it.timestamp) <= cutoff }
    return Summary(
        latest,
        readings.minOf { it.temperature },
        readings.maxOf { it.temperature },
        trend(latest.temperature, before?.temperature, TEMPERATURE_STEP),
        trend(latest.pressure, before?.pressure, PRESSURE_STEP),
    )
}

// Rounds down to the largest whole unit; readings slightly in the future (clock skew) are 0 minutes old.
fun age(timestamp: String, now: Instant): Pair<ChronoUnit, Long> {
    val minutes = maxOf(0, Duration.between(instant(timestamp), now).toMinutes())
    return when {
        minutes < 60 -> ChronoUnit.MINUTES to minutes
        minutes < 24 * 60 -> ChronoUnit.HOURS to minutes / 60
        else -> ChronoUnit.DAYS to minutes / (24 * 60)
    }
}
