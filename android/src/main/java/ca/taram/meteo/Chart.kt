package ca.taram.meteo

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.toSize
import java.time.Instant
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor

private val SNOW = Color(0xFF90A4AE)
private val AXIS = Color(0xFF555555)
private val GRID = Color(0xFFE0E0E0)

// Room left of the plot for the value labels, and below it for the time labels.
private val VALUE_LABELS_WIDTH = 36.dp
private val TIME_LABELS_HEIGHT = 18.dp
private val CHART_HEIGHT = 180.dp
private const val TIME_LABELS = 4
private val LINE_WIDTH = 2.dp
private val DOT_RADIUS = 5.dp
private const val BAND_ALPHA = 0.2f
// A bar takes this much of its point's slot, and fills this much of its width, leaving a gap between rain and snow.
private const val BAR_FRACTION = 0.35f
private const val BAR_FILL = 0.9f

// LINE plots ys[0]; BAND plots ys = [avg, min, max] as a min–max band under the avg line; BARS plots ys = [rain, snow].
enum class Plot { LINE, BAND, BARS }

// x in epoch milliseconds.
data class Point(val x: Long, val ys: List<Double?>)

// Maps data to pixels; left and bottom leave room for the axis labels. Points come sorted by x.
class Frame(private val points: List<Point>, bars: Boolean, val width: Float, val height: Float, val left: Float, val bottom: Float) {
    private val x0 = points.first().x
    private val span = (points.last().x - x0).coerceAtLeast(1)
    private val values = points.flatMap { it.ys }.filterNotNull()
    // Bars grow from zero; whole numbers keep the axis labels honest.
    val lo = floor(if (bars) minOf(0.0, values.minOrNull() ?: 0.0) else values.minOrNull() ?: 0.0)
    val hi = ceil(values.maxOrNull() ?: 1.0).let { if (it <= lo) lo + 1 else it }
    // Bars get one equal slot per point, so the first and last fit.
    private val pad = if (bars) (width - left) / (2 * points.size) else 0f
    val barWidth = (width - left) / points.size * BAR_FRACTION

    fun x(ms: Long) = left + pad + (ms - x0).toFloat() / span * (width - left - 2 * pad)
    fun y(v: Double) = ((hi - v) / (hi - lo) * (height - bottom)).toFloat()
    fun nearest(px: Float) = points.indices.minBy { abs(x(points[it].x) - px) }
}

private fun Density.frame(points: List<Point>, plot: Plot, size: Size) =
    Frame(points, plot == Plot.BARS, size.width, size.height, VALUE_LABELS_WIDTH.toPx(), TIME_LABELS_HEIGHT.toPx())

// Shows the latest point above the chart, or the held one while a finger stays on it.
@Composable
fun WeatherChart(title: String, hours: Int, points: List<Point>, plot: Plot, daily: Boolean, label: (Point) -> String) {
    var pressed by remember(points) { mutableStateOf<Int?>(null) }
    val shown = pressed?.let(points::getOrNull) ?: points.lastOrNull()
    val measurer = rememberTextMeasurer()
    val axis = TextStyle(fontSize = 11.sp, color = AXIS)
    val color = MaterialTheme.colorScheme.primary
    Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
        Text(title, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
        val at = shown?.let { format(Instant.ofEpochMilli(it.x), if (daily) DATE_SKELETON else DATE_TIME_SKELETON) }
        Text(shown?.let { "${label(it)} · $at" } ?: " ", Modifier.padding(top = 2.dp), color = AXIS, fontSize = 13.sp)
        if (points.isEmpty()) return@Column
        Canvas(
            Modifier.fillMaxWidth().padding(top = 8.dp).height(CHART_HEIGHT).pointerInput(points, plot) {
                val nearest = { offset: Offset -> frame(points, plot, size.toSize()).nearest(offset.x) }
                detectDragGesturesAfterLongPress(
                    onDragStart = { pressed = nearest(it) },
                    onDragEnd = { pressed = null },
                    onDragCancel = { pressed = null },
                    onDrag = { change, _ -> pressed = nearest(change.position) },
                )
            },
        ) {
            val f = frame(points, plot, size)
            // Gridlines and labels at the bottom and top of the range.
            for (v in listOf(f.lo, f.hi)) {
                drawLine(GRID, Offset(f.left, f.y(v)), Offset(size.width, f.y(v)))
                val text = measurer.measure(num(v, 0), axis)
                drawText(text, topLeft = Offset(0f, (f.y(v) - text.size.height / 2).coerceIn(0f, size.height - f.bottom)))
            }
            // Evenly spaced time labels, kept inside the canvas.
            for (i in 0 until TIME_LABELS) {
                val ms = points.first().x + (points.last().x - points.first().x) * i / (TIME_LABELS - 1)
                val text = measurer.measure(format(Instant.ofEpochMilli(ms), if (hours <= 24) TIME_SKELETON else DATE_SKELETON), axis)
                val x = (f.x(ms) - text.size.width / 2).coerceIn(f.left, size.width - text.size.width)
                drawText(text, topLeft = Offset(x, size.height - text.size.height))
            }
            when (plot) {
                Plot.LINE -> line(f, points, color)
                Plot.BAND -> {
                    band(f, points, color)
                    line(f, points, color)
                }
                Plot.BARS -> bars(f, points, color)
            }
            shown?.takeIf { pressed != null }?.ys?.get(0)?.let { drawCircle(color, DOT_RADIUS.toPx(), Offset(f.x(shown.x), f.y(it))) }
        }
    }
}

// Where ys[index] lands for each point that has one.
private fun Frame.offsets(points: List<Point>, index: Int) = points.mapNotNull { p -> p.ys[index]?.let { Offset(x(p.x), y(it)) } }

private fun path(offsets: List<Offset>) = Path().apply {
    offsets.forEachIndexed { i, o -> if (i == 0) moveTo(o.x, o.y) else lineTo(o.x, o.y) }
}

// Lines join across missing values.
private fun DrawScope.line(f: Frame, points: List<Point>, color: Color) =
    drawPath(path(f.offsets(points, 0)), color, style = Stroke(LINE_WIDTH.toPx()))

// Out along the minimums and back along the maximums, skipping days missing either.
private fun DrawScope.band(f: Frame, points: List<Point>, color: Color) {
    val band = points.filter { it.ys[1] != null && it.ys[2] != null }
    drawPath(path(f.offsets(band, 1) + f.offsets(band, 2).asReversed()), color.copy(alpha = BAND_ALPHA))
}

// Rain left of the day, snow right of it.
private fun DrawScope.bars(f: Frame, points: List<Point>, rain: Color) {
    for (p in points) {
        p.ys.forEachIndexed { i, v ->
            if (v == null) return@forEachIndexed
            val x = f.x(p.x) + (i - 1) * f.barWidth
            drawRect(if (i == 0) rain else SNOW, Offset(x, f.y(v)), Size(f.barWidth * BAR_FILL, f.y(0.0) - f.y(v)))
        }
    }
}
