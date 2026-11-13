package ca.taram.meteo

import org.junit.Assert.assertEquals
import org.junit.Test

class PickerTest {
    @Test
    fun bboxRoundsToThreeDecimals() {
        assertEquals("-74.07,45.05,-73.17,45.95", bboxOf(-74.0700004, 45.05, -73.1699996, 45.95))
        assertEquals("0,-5,1.235,5", bboxOf(0.0, -5.0, 1.2346, 5.0))
    }

    @Test
    fun zoomHalvesTheSpanPerLevel() {
        // 100 km around Montréal: log2(360 / 0.9) ≈ 9.
        assertEquals(9, zoomOf(-74.07, -73.17))
        // Across the antimeridian, west > east: 10° wide.
        assertEquals(5, zoomOf(174.0, -176.0))
        assertEquals(0, zoomOf(-180.0, 180.0))
    }
}
