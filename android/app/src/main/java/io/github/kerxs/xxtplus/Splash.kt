package io.github.kerxs.xxtplus

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.boundsInRoot
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlin.math.roundToInt
import kotlin.random.Random

/** Where the top-left brand icon is (root coordinates): the splash logo lands there. */
object Brand {
    var iconRect by mutableStateOf<Rect?>(null)
    var titleRect by mutableStateOf<Rect?>(null)
}

const val BRAND_TITLE = "学习通 PLUS"

/**
 * Top-left brand, like the desktop nav pane: icon + 学习通 PLUS.
 * While the splash logo flies in it is hidden; on landing the icon and title appear in the
 * same frame the identical flying copy disappears, so nothing flashes.
 */
@Composable
fun BrandRow(hidden: Boolean, modifier: Modifier = Modifier) {
    val c = X.colors
    val a = if (hidden) 0f else 1f
    Row(modifier.alpha(a), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Image(painterResource(R.drawable.brand_icon), null,
            Modifier.size(36.dp).onGloballyPositioned { Brand.iconRect = it.boundsInRoot() })
        Text(BRAND_TITLE, color = c.text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold,
            modifier = Modifier.onGloballyPositioned { Brand.titleRect = it.boundsInRoot() })
    }
}

private const val SPLASH_TEXT = "学习通 PLUS"
private val InOutCubic = CubicBezierEasing(0.65f, 0f, 0.35f, 1f)

enum class SplashPhase { Splash, Fly, Done }

/**
 * Desktop Splash.qml on the phone: the icon, "学习通 PLUS" typed out like streamed text, the real
 * loading status; then the logo moves from the centre to the brand row in the top-left.
 * [loaded] is when the app behind it is ready; [phase] drives what AppRoot shows underneath.
 */
@Composable
fun SplashOverlay(loaded: Boolean, status: String, phase: SplashPhase, onPhase: (SplashPhase) -> Unit) {
    val c = X.colors
    var shown by remember { mutableIntStateOf(0) }
    var logoRect by remember { mutableStateOf<Rect?>(null) }
    var textRect by remember { mutableStateOf<Rect?>(null) }
    val intro = remember { Animatable(0f) }

    LaunchedEffect(Unit) {
        intro.animateTo(1f, tween(240, easing = OutBack))
        while (shown < SPLASH_TEXT.length) {
            val next = SPLASH_TEXT[shown]
            delay(((if (next == ' ' || next in 'A'..'Z') 70 else 110) + Random.nextInt(50)).toLong())
            shown++
        }
    }
    LaunchedEffect(shown >= SPLASH_TEXT.length && loaded) {
        if (shown < SPLASH_TEXT.length || !loaded || phase != SplashPhase.Splash) return@LaunchedEffect
        delay(250)
        onPhase(SplashPhase.Fly)
    }
    // One clock (ms) for the whole flight: the icon arrives first, then the text, then P, L, U, S.
    val clock = remember { Animatable(0f) }
    LaunchedEffect(phase) {
        if (phase != SplashPhase.Fly) return@LaunchedEffect
        snapshotFlow { Brand.iconRect }.first { it != null }
        delay(16)  // one frame for the page underneath to lay out
        clock.animateTo(FLIGHT_END.toFloat(), tween(FLIGHT_END, easing = LinearEasing))
        onPhase(SplashPhase.Done)
    }
    if (phase == SplashPhase.Done) return

    // Splash backdrop: fades away as the logo starts to move, revealing the app underneath.
    val backdrop by animateFloatAsState(if (phase == SplashPhase.Splash) 1f else 0f, tween(260, easing = OutCubic), label = "backdrop")
    Box(Modifier.fillMaxSize()) {
        Box(Modifier.fillMaxSize().alpha(backdrop).background(c.bg)) {
            // Loading status only (no progress bar).
            Text(if (loaded) "准备就绪" else "$status…", color = c.muted, fontSize = 12.sp,
                modifier = Modifier.align(Alignment.BottomStart).navigationBarsPadding().padding(horizontal = 34.dp, vertical = 28.dp))
        }

        // The logo: measured at the centre, then flown with offset + scale (top-left origin).
        val start = logoRect
        val target = Brand.iconRect
        val t = clock.value
        val p = InOutCubic.transform((t / FLIGHT_MS).coerceIn(0f, 1f))
        val flying = start != null && target != null && phase == SplashPhase.Fly
        val dx = if (flying) (target!!.left - start!!.left) * p else 0f
        val dy = if (flying) (target!!.top - start!!.top) * p else 0f
        val s1 = if (flying) target!!.width / start!!.width else 1f
        val s = 1f + (s1 - 1f) * p
        // The wordmark (inside the scaled row) heads for the title and fades out as the pieces arrive.
        val title = Brand.titleRect
        val tr = textRect
        val (tx, ty) = if (flying && title != null && tr != null) {
            val finalX = target!!.left + (tr.left - start!!.left) * s1
            val finalY = target.top + (tr.top - start.top) * s1
            ((title.left - finalX) / s1) to ((title.top - finalY) / s1)
        } else 0f to 0f
        val wordmarkAlpha = if (flying) 1f - ((t - 200f) / 240f).coerceIn(0f, 1f) else 1f
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Row(
                Modifier.offset { IntOffset(dx.roundToInt(), dy.roundToInt()) }
                    .offset(y = (-12).dp)
                    .graphicsLayer {
                        scaleX = s; scaleY = s
                        transformOrigin = TransformOrigin(0f, 0f)
                        alpha = intro.value.coerceIn(0f, 1f)
                    },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Image(painterResource(R.drawable.brand_icon), null,
                    Modifier.size(96.dp)   // square, like the desktop icon
                        // Keep measuring while the text types (the centred row widens and the
                        // icon moves left); the flight starts from where it is at that moment.
                        .onGloballyPositioned { if (phase == SplashPhase.Splash) logoRect = it.boundsInRoot() })
                // 40 sp text and a 27 dp gap: scaled with the icon (96 -> 36 dp) they become the
                // brand's 15 sp title and 10 dp gap.
                Spacer(Modifier.width(27.dp))
                Box(Modifier.graphicsLayer { translationX = tx * p; translationY = ty * p }, contentAlignment = Alignment.CenterStart) {
                    Row(Modifier.alpha(wordmarkAlpha), verticalAlignment = Alignment.CenterVertically) {
                        Text(SPLASH_TEXT.take(shown), color = c.text, fontSize = 40.sp, fontWeight = FontWeight.Black)
                        // Hidden, not removed, once the flight starts: removing it would narrow the
                        // centred row and shift the icon off the start position measured for the flight.
                        Box(Modifier.alpha(if (phase == SplashPhase.Splash) 1f else 0f)) { Caret() }
                    }
                    // Invisible: only measured, as the pieces' start position.
                    Text(BRAND_TITLE, color = c.text, fontSize = 40.sp, fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.alpha(0f)
                            .onGloballyPositioned { if (phase == SplashPhase.Splash) textRect = it.boundsInRoot() })
                }
            }
        }
        if (flying && title != null && tr != null) TitlePieces(t, tr, title)
    }
}

private const val FLIGHT_MS = 560
// Characters that fly on their own (spaces only take up room): 学, 习, 通, P, L, U, S.
private val PIECE_STARTS = BRAND_TITLE.indices.filter { !BRAND_TITLE[it].isWhitespace() }
private fun pieceDelay(i: Int) = 90 + i * 45           // first one 90 ms after the icon, then every 45 ms
private val FLIGHT_END = FLIGHT_MS + pieceDelay(PIECE_STARTS.size - 1)

/**
 * The title one character at a time — 学, 习, 通, P, L, U, S — each flying on its own a little later
 * than the one before, its real font size going from 40 sp to 15 sp, so it ends as native text
 * exactly where BrandRow draws that character (positions from the full title's glyph positions).
 */
@Composable
private fun TitlePieces(t: Float, from: Rect, to: Rect) {
    val c = X.colors
    val measurer = rememberTextMeasurer()
    // Same base style as BrandRow's title (LocalTextStyle), so the line box — and the glyphs'
    // vertical position — match exactly when the pieces land.
    val base = LocalTextStyle.current
    fun style(size: Float) = base.merge(TextStyle(color = c.text, fontSize = size.sp, fontWeight = FontWeight.SemiBold))
    val big = remember(BRAND_TITLE) { measurer.measure(BRAND_TITLE, style(40f)) }
    val small = remember(BRAND_TITLE) { measurer.measure(BRAND_TITLE, style(15f)) }
    PIECE_STARTS.forEachIndexed { i, at ->
        val end = at + 1
        val delayMs = pieceDelay(i)
        val q = InOutCubic.transform(((t - delayMs) / FLIGHT_MS).coerceIn(0f, 1f))
        val alpha = ((t - (150f + delayMs / 2f)) / 240f).coerceIn(0f, 1f)
        val x0 = from.left + big.getHorizontalPosition(at, true)
        val x1 = to.left + small.getHorizontalPosition(at, true)
        val size = 40f + (15f - 40f) * q
        val piece = BRAND_TITLE.substring(at, end)
        // Baseline alignment: a lone Latin letter gets a shorter line box than the mixed CJK title,
        // so placing it by its top would sit it higher than in the real title.
        val pieceBig = remember(piece) { measurer.measure(piece, style(40f)) }
        val pieceSmall = remember(piece) { measurer.measure(piece, style(15f)) }
        val dy0 = big.firstBaseline - pieceBig.firstBaseline
        val dy1 = small.firstBaseline - pieceSmall.firstBaseline
        Text(piece, style = style(size), softWrap = false, maxLines = 1,
            modifier = Modifier.graphicsLayer {
                translationX = x0 + (x1 - x0) * q
                translationY = from.top + dy0 + (to.top + dy1 - from.top - dy0) * q
                this.alpha = alpha
            })
    }
}

@Composable
private fun Caret() {
    val a by rememberInfiniteTransition(label = "caret").animateFloat(1f, 0f,
        infiniteRepeatable(tween(420), RepeatMode.Reverse), label = "caretA")
    Box(Modifier.padding(start = 3.dp).width(3.dp).height(34.dp).alpha(a).background(X.colors.text, RoundedCornerShape(2.dp)))
}
