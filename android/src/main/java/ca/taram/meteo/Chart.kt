package ca.taram.meteo

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
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
    val barWidth = (width - left) / points.size * 0.35f

    fun x(ms: Long) = left + pad + (ms - x0).toFloat() / span * (width - left - 2 * pad)
    fun y(v: Double) = ((hi - v) / (hi - lo) * (height - bottom)).toFloat()
    fun nearest(px: Float) = points.indices.minBy { abs(x(points[it].x) - px) }
}

private fun Density.frame(points: List<Point>, plot: Plot, size: Size) =
    Frame(points, plot == Plot.BARS, size.width, size.height, 36.dp.toPx(), 18.dp.toPx())

// Shows the latest point above the chart, or the held one while a finger stays on it.
@Composable
fun WeatherChart(title: String, hours: Int, points: List<Point>, plot: Plot, daily: Boolean, label: (Point) -> String) {
    var pressed by remember(points) { mutableStateOf<Int?>(null) }
    val shown = pressed?.let(points::getOrNull) ?: points.lastOrNull()
    val measurer = rememberTextMeasurer()
    val axis = TextStyle(fontSize = 11.sp, color = AXIS)
    Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
        Text(title, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
        val at = shown?.let { format(Instant.ofEpochMilli(it.x), if (daily) DAY else WHEN) }
        Text(shown?.let { "${label(it)} · $at" } ?: " ", Modifier.padding(top = 2.dp), color = AXIS, fontSize = 13.sp)
        if (points.isEmpty()) return@Column
        Canvas(
            Modifier.fillMaxWidth().padding(top = 8.dp).height(180.dp).pointerInput(points, plot) {
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
                drawLine(Color(0xFFE0E0E0), Offset(f.left, f.y(v)), Offset(size.width, f.y(v)))
                val text = measurer.measure(num(v, 0), axis)
                drawText(text, topLeft = Offset(0f, (f.y(v) - text.size.height / 2).coerceIn(0f, size.height - f.bottom)))
            }
            // Four time labels, kept inside the canvas.
            for (i in 0..3) {
                val ms = points.first().x + (points.last().x - points.first().x) * i / 3
                val text = measurer.measure(format(Instant.ofEpochMilli(ms), if (hours <= 24) TIME else DAY), axis)
                val x = (f.x(ms) - text.size.width / 2).coerceIn(f.left, size.width - text.size.width)
                drawText(text, topLeft = Offset(x, size.height - text.size.height))
            }
            when (plot) {
                Plot.LINE -> line(f, points, 0)
                Plot.BAND -> {
                    val band = points.filter { it.ys[1] != null && it.ys[2] != null }
                    val path = Path()
                    band.forEachIndexed { i, p -> if (i == 0) path.moveTo(f.x(p.x), f.y(p.ys[1]!!)) else path.lineTo(f.x(p.x), f.y(p.ys[1]!!)) }
                    band.asReversed().forEach { path.lineTo(f.x(it.x), f.y(it.ys[2]!!)) }
                    drawPath(path, COLOR.copy(alpha = 0.2f))
                    line(f, points, 0)
                }
                Plot.BARS -> for (p in points) {
                    p.ys.forEachIndexed { i, v ->
                        if (v == null) return@forEachIndexed
                        val x = f.x(p.x) + (i - 1) * f.barWidth
                        drawRect(if (i == 0) COLOR else SNOW, Offset(x, f.y(v)), Size(f.barWidth * 0.9f, f.y(0.0) - f.y(v)))
                    }
                }
            }
            shown?.takeIf { pressed != null }?.ys?.get(0)?.let { drawCircle(COLOR, 5.dp.toPx(), Offset(f.x(shown.x), f.y(it))) }
        }
    }
}

// Lines join across missing values.
private fun DrawScope.line(f: Frame, points: List<Point>, index: Int) {
    val path = Path()
    points.filter { it.ys[index] != null }.forEachIndexed { i, p ->
        if (i == 0) path.moveTo(f.x(p.x), f.y(p.ys[index]!!)) else path.lineTo(f.x(p.x), f.y(p.ys[index]!!))
    }
    drawPath(path, COLOR, style = Stroke(2.dp.toPx()))
}
