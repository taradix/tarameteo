package ca.taram.meteo

import kotlinx.serialization.SerializationException
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.IOException
import java.net.UnknownHostException

class UiTest {
    @Test
    fun errorsAreDescribedByWhatPeopleCanDoAboutThem() {
        assertEquals(R.string.error_network to emptyList<Any>(), reason(UnknownHostException("meteo.taram.ca")))
        assertEquals(R.string.error_status to listOf(503), reason(ApiError(503, "503 Service Unavailable")))
        assertEquals(R.string.error_response to emptyList<Any>(), reason(BadResponse(SerializationException("bad"))))
        assertEquals(R.string.error_other to listOf("SERVICE_NOT_AVAILABLE"), reason(IOException("SERVICE_NOT_AVAILABLE")))
    }
}
