package io.github.kerxs.xxtplus

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.CubicBezierEasing
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
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
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
import androidx.compose.ui.text.font.FontWeight
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
}

/** Top-left brand, like the desktop nav pane: icon + 学习通PLUS + 学习通课程助手. */
@Composable
fun BrandRow(hidden: Boolean, modifier: Modifier = Modifier) {
    val c = X.colors
    val a = if (hidden) 0f else 1f
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Image(painterResource(R.drawable.brand_icon), null,
            Modifier.size(36.dp).alpha(a).onGloballyPositioned { Brand.iconRect = it.boundsInRoot() })
        Column(Modifier.alpha(a)) {
            Text("学习通PLUS", color = c.text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Text("学习通课程助手", color = c.muted, fontSize = 11.sp)
        }
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
    val fly = remember { Animatable(0f) }
    val textAlpha = remember { Animatable(1f) }
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
    LaunchedEffect(phase) {
        if (phase != SplashPhase.Fly) return@LaunchedEffect
        snapshotFlow { Brand.iconRect }.first { it != null }
        delay(16)  // one frame for the page underneath to lay out
        coroutineScope {
            launch { delay(160); textAlpha.animateTo(0f, tween(320, easing = OutCubic)) }
            fly.animateTo(1f, tween(720, easing = InOutCubic))
        }
        onPhase(SplashPhase.Done)
    }
    if (phase == SplashPhase.Done) return

    // Splash backdrop: fades away as the logo starts to move, revealing the app underneath.
    val backdrop by animateFloatAsState(if (phase == SplashPhase.Splash) 1f else 0f, tween(260, easing = OutCubic), label = "backdrop")
    Box(Modifier.fillMaxSize()) {
        Box(Modifier.fillMaxSize().alpha(backdrop).background(c.bg)) {
            Column(Modifier.align(Alignment.BottomCenter).fillMaxWidth().navigationBarsPadding().padding(horizontal = 34.dp, vertical = 28.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(if (loaded) "准备就绪" else "$status…", color = c.muted, fontSize = 12.sp)
                XProgress(if (loaded) 1f else 0.6f, color = c.text)
            }
        }

        // The logo: measured once at the centre, then flown with offset + scale (top-left origin).
        val start = logoRect
        val target = Brand.iconRect
        val p = fly.value
        val dx = if (start != null && target != null && phase == SplashPhase.Fly) (target.left - start.left) * p else 0f
        val dy = if (start != null && target != null && phase == SplashPhase.Fly) (target.top - start.top) * p else 0f
        val s = if (start != null && target != null && phase == SplashPhase.Fly) 1f + (target.width / start.width - 1f) * p else 1f
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
                    Modifier.size(96.dp).clip(RoundedCornerShape(21.dp))
                        // Keep measuring while the text types (the centred row widens and the
                        // icon moves left); the flight starts from where it is at that moment.
                        .onGloballyPositioned { if (phase == SplashPhase.Splash) logoRect = it.boundsInRoot() })
                Spacer(Modifier.width(20.dp))
                Row(Modifier.alpha(textAlpha.value), verticalAlignment = Alignment.CenterVertically) {
                    Text(SPLASH_TEXT.take(shown), color = c.text, fontSize = 32.sp, fontWeight = FontWeight.Black)
                    Caret()
                }
            }
        }
    }
}

@Composable
private fun Caret() {
    val a by rememberInfiniteTransition(label = "caret").animateFloat(1f, 0f,
        infiniteRepeatable(tween(420), RepeatMode.Reverse), label = "caretA")
    Box(Modifier.padding(start = 3.dp).width(3.dp).height(34.dp).alpha(a).background(X.colors.text, RoundedCornerShape(2.dp)))
}
