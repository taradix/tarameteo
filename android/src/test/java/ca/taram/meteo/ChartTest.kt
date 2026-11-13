package ca.taram.meteo

import org.junit.Assert.assertEquals
import org.junit.Test

class ChartTest {
    @Test
    fun framesLinesBetweenWholeNumbersAndFindsTheNearestPoint() {
        val f = Frame(listOf(Point(0, listOf(0.4)), Point(10, listOf(9.6))), bars = false, 110f, 100f, left = 10f, bottom = 0f)
        assertEquals(0.0 to 10.0, f.lo to f.hi)
        assertEquals(10f to 110f, f.x(0) to f.x(10))
        assertEquals(100f to 0f, f.y(0.0) to f.y(10.0))
        assertEquals(1, f.nearest(80f))
    }

    @Test
    fun barsStartAtZeroAndGetASlotEach() {
        val f = Frame(listOf(Point(0, listOf(2.0, null)), Point(10, listOf(5.0, 1.0))), bars = true, 110f, 100f, left = 10f, bottom = 0f)
        assertEquals(0.0 to 5.0, f.lo to f.hi)
        // Two slots of 50: centres at 35 and 85.
        assertEquals(35f to 85f, f.x(0) to f.x(10))
    }
}
