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
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.updateAndGet
import kotlinx.serialization.Serializable

val COLOR = Color(0xFF1976D2)

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
    }
}

@Serializable object Home
@Serializable object Sensors

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = COLOR)) { Screens() }
        }
    }
}

// ponytail: no up arrow, the system back gesture covers it; add one with material-icons if wanted.
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Screens() {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val picking = entry?.destination?.hasRoute<Sensors>() == true
    val pick = { nav.navigate(Sensors) { launchSingleTop = true } }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(if (picking) R.string.sensors_title else R.string.app_name)) },
                actions = { if (!picking) TextButton(pick) { Text(stringResource(R.string.sensors_title)) } },
            )
        },
    ) { padding ->
        NavHost(nav, Home, Modifier.padding(padding)) {
            composable<Home> { Dashboard(pick) }
            composable<Sensors> { Picker() }
        }
    }
}
