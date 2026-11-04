package io.github.kerxs.xxtplus

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedContentTransitionScope
import androidx.compose.animation.ContentTransform
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.animateIntAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.outlined.Circle
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Desktop Card.qml: surface, 12 radius, 1 px border; fades in and lifts 14 px, staggered by [appearDelay]. */
@Composable
fun XCard(
    modifier: Modifier = Modifier,
    title: String = "",
    subtitle: String = "",
    appearDelay: Int = 0,
    padding: Dp = Dimens.pad,
    content: @Composable ColumnScope.() -> Unit,
) {
    val c = X.colors
    val m = X.motion
    val progress = remember { Animatable(if (m.enabled) 0f else 1f) }
    LaunchedEffect(Unit) {
        if (progress.value < 1f) {
            delay(appearDelay.toLong())
            progress.animateTo(1f, tween(m.slow, easing = OutCubic))
        }
    }
    val bgc by animateColorAsState(c.surface, m.slowSpec(), label = "card")
    Column(
        modifier
            .graphicsLayer { alpha = progress.value; translationY = (1f - progress.value) * 14.dp.toPx() }
            .clip(RoundedCornerShape(Dimens.radiusLarge))
            .background(bgc)
            .border(1.dp, c.border, RoundedCornerShape(Dimens.radiusLarge))
            .padding(padding),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        if (title.isNotEmpty()) {
            Column(verticalArrangement = Arrangement.spacedBy(1.dp)) {
                Text(title, color = c.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (subtitle.isNotEmpty()) Text(subtitle, color = c.muted, fontSize = 12.sp)
            }
            Spacer(Modifier.height(2.dp))
        }
        content()
    }
}

enum class Kind { Primary, Secondary, Danger, Warning, Ghost }

/** Desktop AppButton.qml: same kinds and colours, presses to 0.97, colours fade. */
@Composable
fun XButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    kind: Kind = Kind.Secondary,
    enabled: Boolean = true,
) {
    val c = X.colors
    val m = X.motion
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    val base = when (kind) {
        Kind.Primary -> c.accent
        Kind.Danger -> c.dangerSoft
        Kind.Warning -> c.warningSoft
        Kind.Ghost -> Color.Transparent
        Kind.Secondary -> c.surface
    }
    val press = when (kind) {
        Kind.Primary -> c.accentPressed
        Kind.Danger, Kind.Warning -> lerpDarker(base, c.dark)
        else -> c.sunken
    }
    val fg = when {
        !enabled -> c.faint
        kind == Kind.Primary -> c.accentText
        kind == Kind.Danger -> c.danger
        kind == Kind.Warning -> c.warning
        else -> c.text
    }
    val bgc by animateColorAsState(if (pressed) press else base, m.fastSpec(), label = "btn")
    val fgc by animateColorAsState(fg, m.fastSpec(), label = "btnFg")
    val scale by animateFloatAsState(if (pressed) 0.97f else 1f, m.fastSpec(), label = "btnScale")
    val alpha by animateFloatAsState(if (enabled) 1f else 0.55f, m.fastSpec(), label = "btnAlpha")
    Box(
        modifier
            .scale(scale)
            .alpha(alpha)
            .defaultMinSize(minHeight = 42.dp)
            .clip(RoundedCornerShape(Dimens.radius))
            .background(bgc)
            .then(if (kind == Kind.Secondary) Modifier.border(1.dp, c.border, RoundedCornerShape(Dimens.radius)) else Modifier)
            .clickable(interactionSource = source, indication = null, enabled = enabled, onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, color = fgc, fontSize = 14.sp,
            fontWeight = if (kind == Kind.Primary) FontWeight.SemiBold else FontWeight.Medium, maxLines = 1)
    }
}

private fun lerpDarker(color: Color, dark: Boolean): Color {
    val f = if (dark) 1.25f else 0.93f
    return Color((color.red * f).coerceIn(0f, 1f), (color.green * f).coerceIn(0f, 1f), (color.blue * f).coerceIn(0f, 1f), color.alpha)
}

/** Desktop StatusPill.qml: idle / running (green, pulsing dot) / paused (accent). */
@Composable
fun StatusPill(kind: String, text: String) {
    val c = X.colors
    val m = X.motion
    val fg = when (kind) { "running" -> c.success; "paused" -> c.accent; "error" -> c.danger; else -> c.muted }
    val bg = when (kind) { "running" -> c.successSoft; "paused" -> c.accentSoft; "error" -> c.dangerSoft; else -> c.surfaceAlt }
    val fgc by animateColorAsState(fg, m.normalSpec(), label = "pillFg")
    val bgc by animateColorAsState(bg, m.normalSpec(), label = "pillBg")
    val dotAlpha = if (kind == "running" && m.enabled) {
        rememberInfiniteTransition(label = "pulse").animateFloat(
            1f, 0.25f, infiniteRepeatable(tween(700), RepeatMode.Reverse), label = "dot",
        ).value
    } else 1f
    Row(
        Modifier.height(30.dp).clip(RoundedCornerShape(50)).background(bgc).padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(8.dp).alpha(dotAlpha).background(fgc, CircleShape))
        Spacer(Modifier.width(7.dp))
        AnimatedContent(text, transitionSpec = { fadeIn(tween(m.fast)) togetherWith fadeOut(tween(m.fast)) }, label = "pillText") {
            Text(it, color = fgc, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}

/** Desktop StatTile.qml: label + value, accent flash on change, counters roll to the new number. */
@Composable
fun StatTile(label: String, value: String, modifier: Modifier = Modifier, count: Int? = null, appearDelay: Int = 0) {
    val c = X.colors
    val m = X.motion
    val shown by animateIntAsState(count ?: 0, tween(if (m.enabled) 600 else 0, easing = OutCubic), label = "count")
    val flash = remember { Animatable(0f) }
    val key = count?.toString() ?: value
    var first by remember { mutableStateOf(true) }
    LaunchedEffect(key) {
        if (first) { first = false; return@LaunchedEffect }
        if (!m.enabled || key.isEmpty()) return@LaunchedEffect
        flash.animateTo(0.9f, tween(120))
        flash.animateTo(0f, tween(520, easing = OutCubic))
    }
    val empty = count == null && value.isEmpty()
    XCard(modifier, appearDelay = appearDelay, padding = 12.dp) {
        Box {
            Box(Modifier.matchParentSize().alpha(flash.value).background(c.accentSoft, RoundedCornerShape(Dimens.radius)))
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(label, color = c.muted, fontSize = 12.sp)
                Text(if (count != null) shown.toString() else value.ifEmpty { "—" },
                    color = if (empty) c.faint else c.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

/** Desktop Segmented.qml: a highlight that slides to the picked segment. */
@Composable
fun Segmented(options: List<Pair<String, String>>, current: String, onPick: (String) -> Unit, modifier: Modifier = Modifier) {
    val c = X.colors
    val m = X.motion
    val density = LocalDensity.current
    val xs = remember { mutableStateMapOf<Int, Float>() }
    val ws = remember { mutableStateMapOf<Int, Float>() }
    val index = options.indexOfFirst { it.first == current }
    val hx by animateDpAsState(with(density) { (xs[index] ?: 0f).toDp() }, m.normalSpec(), label = "segX")
    val hw by animateDpAsState(with(density) { (ws[index] ?: 0f).toDp() }, m.normalSpec(), label = "segW")
    Box(modifier.clip(RoundedCornerShape(Dimens.radius)).background(c.sunken).padding(3.dp)) {
        if (index >= 0 && ws[index] != null) {
            Box(Modifier.offset(x = hx).width(hw).height(34.dp)
                .clip(RoundedCornerShape(Dimens.radius - 2.dp)).background(c.surface)
                .border(1.dp, c.border, RoundedCornerShape(Dimens.radius - 2.dp)))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
            options.forEachIndexed { i, (value, label) ->
                val active = i == index
                val fg by animateColorAsState(if (active) c.text else c.muted, m.normalSpec(), label = "segFg")
                Box(
                    Modifier.weight(1f).height(34.dp)
                        .onGloballyPositioned { xs[i] = it.positionInParent().x; ws[i] = it.size.width.toFloat() }
                        .clip(RoundedCornerShape(Dimens.radius - 2.dp))
                        .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { onPick(value) },
                    contentAlignment = Alignment.Center,
                ) {
                    Text(label, color = fg, fontSize = 13.sp, fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal, maxLines = 1)
                }
            }
        }
    }
}

private fun androidx.compose.ui.layout.LayoutCoordinates.positionInParent() =
    parentLayoutCoordinates?.localPositionOf(this, androidx.compose.ui.geometry.Offset.Zero) ?: androidx.compose.ui.geometry.Offset.Zero

/** Progress bar: sunken track, accent fill that eases to the new value. */
@Composable
fun XProgress(fraction: Float, modifier: Modifier = Modifier, color: Color = X.colors.accent) {
    val m = X.motion
    val f by animateFloatAsState(fraction.coerceIn(0f, 1f), m.slowSpec(), label = "progress")
    Box(modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)).background(X.colors.sunken)) {
        Box(Modifier.fillMaxHeight().fillMaxWidth(f).clip(RoundedCornerShape(3.dp)).background(color))
    }
}

/** Small rounded label (题型 / 来源). */
@Composable
fun Badge(text: String, fg: Color, bg: Color, modifier: Modifier = Modifier) {
    val m = X.motion
    val bgc by animateColorAsState(bg, m.slowSpec(), label = "badge")
    Box(modifier.clip(RoundedCornerShape(4.dp)).background(bgc).padding(horizontal = 6.dp, vertical = 2.dp)) {
        Text(text, color = fg, fontSize = 11.sp)
    }
}

private val TYPE_LABELS = mapOf("single" to "单选题", "multiple" to "多选题", "judgement" to "判断题", "completion" to "填空题")

/** Desktop QuestionCard.qml: options light up when the answer is revealed; written answers type out. */
@Composable
fun QuestionCard(q: Question, pending: Boolean, revealDelay: Int) {
    val c = X.colors
    val m = X.motion
    var revealed by remember(q.index, q.answer) { mutableStateOf(!m.enabled) }
    LaunchedEffect(q.index, q.answer) {
        if (!revealed) { delay((revealDelay + 260).toLong()); revealed = true }
    }
    val answer = q.answer
    val options: List<Pair<String, Boolean>> = when (q.type) {
        "judgement" -> listOf("正确" to (answer == "true"), "错误" to (answer == "false"))
        "single", "multiple" -> q.options.lines().map { it.trim() }.filter { it.isNotEmpty() }
            .map { it to (answer.isNotEmpty() && it.take(1).uppercase() in answer.uppercase()) }
        else -> emptyList()
    }
    val fromBank = q.source == "cover"
    val fromAI = fromBank && q.origin == "ai"
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius)).background(c.surfaceAlt)
            .border(1.dp, c.border, RoundedCornerShape(Dimens.radius)).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("${q.index}.", color = c.text, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            Badge(TYPE_LABELS[q.type] ?: if (q.type.isEmpty()) "题目" else "简答题", c.accent, c.accentSoft)
            Spacer(Modifier.weight(1f))
            val (label, fg, bg) = when {
                pending -> Triple("查找中", c.muted, c.sunken)
                fromAI -> Triple("AI匹配", c.accent, c.accentSoft)
                fromBank -> Triple("题库匹配", c.success, c.successSoft)
                else -> Triple("随机作答", c.warning, c.warningSoft)
            }
            val a by animateFloatAsState(if (revealed) 1f else 0f, m.normalSpec(), label = "src")
            Badge(label, fg, bg, Modifier.alpha(a))
        }
        Text(q.title, color = c.text, fontSize = 14.sp)
        if (options.isNotEmpty()) {
            options.forEach { (text, selected) ->
                val marked = revealed && selected
                val bgc by animateColorAsState(if (marked) c.accentSoft else c.surface, m.slowSpec(), label = "opt")
                val bc by animateColorAsState(if (marked) c.accent else c.border, m.slowSpec(), label = "optB")
                val ic by animateColorAsState(if (marked) c.accent else c.faint, m.slowSpec(), label = "optI")
                val sc by animateFloatAsState(if (marked) 1f else 0.92f, tween(m.normal, easing = OutBack), label = "optS")
                Row(
                    Modifier.fillMaxWidth().heightIn(min = 36.dp).clip(RoundedCornerShape(6.dp)).background(bgc)
                        .border(1.dp, bc, RoundedCornerShape(6.dp)).padding(horizontal = 10.dp, vertical = 7.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Icon(if (marked) Icons.Filled.CheckCircle else Icons.Outlined.Circle, null, tint = ic,
                        modifier = Modifier.size(16.dp).scale(sc))
                    Text(text, color = c.text, fontSize = 13.sp)
                }
            }
        } else {
            var shown by remember(answer) { mutableIntStateOf(if (m.enabled) 0 else answer.length) }
            LaunchedEffect(answer, revealed) {
                if (!revealed) return@LaunchedEffect
                val step = (1200 / maxOf(1, answer.length)).coerceIn(16, 45).toLong()
                while (shown < answer.length) { delay(step); shown++ }
            }
            val border by animateColorAsState(if (answer.isNotEmpty() && shown > 0) c.accent else c.border, m.slowSpec(), label = "ans")
            Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(6.dp)).background(c.surface)
                .border(1.dp, border, RoundedCornerShape(6.dp)).padding(horizontal = 10.dp, vertical = 7.dp)) {
                Text(
                    if (answer.isEmpty()) (if (pending) "查找中…" else "（未填写）")
                    else answer.take(shown) + if (shown < answer.length) "▍" else "",
                    color = if (answer.isEmpty()) c.faint else c.text, fontSize = 13.sp,
                )
            }
        }
    }
}

/** Desktop page switch: the new page slides in 36 px from the side it is on and fades in. */
fun <T> pageTransition(index: (T) -> Int, motion: Motion, distPx: Int): AnimatedContentTransitionScope<T>.() -> ContentTransform = {
    val forward = index(targetState) >= index(initialState)
    (slideInHorizontally(tween(motion.slow, easing = OutCubic)) { if (forward) distPx else -distPx } +
        fadeIn(tween(motion.normal, easing = OutCubic))) togetherWith
        (slideOutHorizontally(tween(motion.slow, easing = OutCubic)) { if (forward) -distPx else distPx } +
            fadeOut(tween(motion.fast)))
}

/** AnimatedContent with the desktop page switch. */
@Composable
fun <T> PageSwitch(target: T, index: (T) -> Int, modifier: Modifier = Modifier, content: @Composable (T) -> Unit) {
    val m = X.motion
    val dist = with(LocalDensity.current) { 36.dp.roundToPx() }
    AnimatedContent(target, modifier, transitionSpec = pageTransition(index, m, dist), label = "page") { content(it) }
}
