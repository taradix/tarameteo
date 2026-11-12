package ca.taram.meteo

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

val COLOR = Color(0xFF1976D2)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = COLOR)) {
                Surface(Modifier.fillMaxSize().safeDrawingPadding()) { SensorNames() }
            }
        }
    }
}

// ponytail: placeholder proving the API works on the phone; the dashboard replaces it in phase 2.
@Composable
fun SensorNames() {
    val text by produceState("…") {
        value = try {
            api.listSensors(limit = 20).sensors.joinToString("\n") { it.name }
        } catch (e: java.io.IOException) {
            e.toString()
        }
    }
    Text(text, Modifier.padding(16.dp))
}
