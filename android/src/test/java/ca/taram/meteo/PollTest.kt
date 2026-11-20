package ca.taram.meteo

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class PollTest {
    // Collected the way a screen collects it, since an unwatched Poll doesn't load.
    private fun TestScope.shown(keys: Flow<String>, load: suspend (String) -> String) =
        Poll(backgroundScope, keys, "start", { "$it…" }, load).also { backgroundScope.launch { it.state.collect() } }

    @Test
    fun loadsWhenShownThenAgainEveryRefetch() = runTest {
        var loads = 0
        val poll = shown(MutableStateFlow("a")) { "$it${++loads}" }

        runCurrent()
        assertEquals("a1", poll.state.value)
        advanceTimeBy(REFETCH)
        runCurrent()

        assertEquals("a2", poll.state.value)
    }

    @Test
    fun refreshKeepsTheLastStateMarkedRefreshingUntilTheNextLoads() = runTest {
        val results = Channel<String>()
        val poll = shown(MutableStateFlow("a")) { results.receive() }
        runCurrent()
        results.send("a1")
        runCurrent()

        poll.refresh()
        runCurrent()
        assertEquals("a1…", poll.state.value)
        results.send("a2")
        runCurrent()

        assertEquals("a2", poll.state.value)
    }

    @Test
    fun aNewKeyLoadsAtOnce() = runTest {
        var loads = 0
        val keys = MutableStateFlow("a")
        val poll = shown(keys) { "$it${++loads}" }
        runCurrent()

        keys.value = "b"
        runCurrent()

        assertEquals("b2", poll.state.value)
    }
}
