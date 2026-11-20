package ca.taram.meteo

import android.app.Application
import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.core.content.edit
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.updateAndGet
import kotlinx.serialization.Serializable

// The theme's primary; screens read it from MaterialTheme.
private val BRAND_BLUE = Color(0xFF1976D2)

// The sensors picked for the dashboard; they stay on the phone.
class Shown(context: Context) {
    private val prefs = context.getSharedPreferences("shown", Context.MODE_PRIVATE)
    val names = MutableStateFlow(prefs.getStringSet("shown", null).orEmpty().toSet())

    fun toggle(name: String) {
        val picked = names.updateAndGet { if (name in it) it - name else it + name }
        prefs.edit { putStringSet("shown", picked) }
    }
}

lateinit var shown: Shown

class App : Application() {
    override fun onCreate() {
        super.onCreate()
        shown = Shown(this)
        push = Push(this)
    }
}

@Serializable object Home
@Serializable object Sensors
@Serializable object Alerts
// The card passes the kind so the screen doesn't wait on the sensor list.
@Serializable data class Detail(val name: String, val kind: String, val label: String? = null)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = BRAND_BLUE)) { Screens() }
        }
    }
}

// NOTE: no up arrow, the system back gesture covers it; add one with material-icons if wanted.
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Screens() {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val destination = entry?.destination
    val home = destination == null || destination.hasRoute<Home>()
    val pick = { nav.navigate(Sensors) { launchSingleTop = true } }
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        when {
                            destination?.hasRoute<Sensors>() == true -> stringResource(R.string.sensors_title)
                            destination?.hasRoute<Alerts>() == true -> stringResource(R.string.alerts_title)
                            destination?.hasRoute<Detail>() == true -> entry!!.toRoute<Detail>().let { it.label ?: it.name }
                            else -> stringResource(R.string.app_name)
                        },
                    )
                },
                actions = {
                    if (home) {
                        TextButton({ nav.navigate(Alerts) { launchSingleTop = true } }) {
                            Text(stringResource(R.string.alerts_title))
                        }
                        TextButton(pick) { Text(stringResource(R.string.sensors_title)) }
                    }
                },
            )
        },
    ) { padding ->
        NavHost(nav, Home, Modifier.padding(padding)) {
            composable<Home> { Dashboard(pick, { nav.navigate(Detail(it.name, it.kind, it.label)) }) }
            composable<Sensors> { Picker() }
            composable<Alerts> { AlertsScreen() }
            composable<Detail> {
                val route = it.toRoute<Detail>()
                SensorScreen(route.name, route.kind, route.label)
            }
        }
    }
}
