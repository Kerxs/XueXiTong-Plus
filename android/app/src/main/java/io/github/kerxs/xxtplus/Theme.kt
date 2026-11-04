package io.github.kerxs.xxtplus

import android.content.Context
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.Easing
import androidx.compose.animation.core.FiniteAnimationSpec
import androidx.compose.animation.core.tween
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Same tokens as the desktop ui/qml/Theme.qml (light / dark). */
@Immutable
data class XColors(
    val dark: Boolean,
    val bg: Color, val pane: Color, val surface: Color, val surfaceAlt: Color, val sunken: Color,
    val border: Color, val borderStrong: Color,
    val text: Color, val muted: Color, val faint: Color,
    val accent: Color, val accentPressed: Color, val accentText: Color, val accentSoft: Color,
    val success: Color, val successSoft: Color, val warning: Color, val warningSoft: Color,
    val danger: Color, val dangerSoft: Color,
) {
    fun levelColor(level: String) = when (level) {
        "ERROR", "CRITICAL" -> danger
        "WARNING" -> warning
        "SUCCESS" -> success
        else -> muted
    }
}

val LightColors = XColors(
    dark = false,
    bg = Color(0xFFF3F4F8), pane = Color(0xFFECEEF4), surface = Color(0xFFFFFFFF), surfaceAlt = Color(0xFFF6F7FA),
    sunken = Color(0xFFEEF0F5), border = Color(0xFFE3E5EC), borderStrong = Color(0xFFD0D4DE),
    text = Color(0xFF1B1D24), muted = Color(0xFF616778), faint = Color(0xFF8C91A0),
    accent = Color(0xFF2563EB), accentPressed = Color(0xFF1847B5), accentText = Color(0xFFFFFFFF), accentSoft = Color(0xFFE6EEFF),
    success = Color(0xFF13865A), successSoft = Color(0xFFE2F5EB), warning = Color(0xFFA86200), warningSoft = Color(0xFFFFF2DB),
    danger = Color(0xFFC8323F), dangerSoft = Color(0xFFFDE8EA),
)

val DarkColors = XColors(
    dark = true,
    bg = Color(0xFF1C1C1F), pane = Color(0xFF202024), surface = Color(0xFF2A2A2F), surfaceAlt = Color(0xFF323238),
    sunken = Color(0xFF18181B), border = Color(0xFF3A3A41), borderStrong = Color(0xFF4A4A52),
    text = Color(0xFFF2F3F5), muted = Color(0xFFA2A6B2), faint = Color(0xFF757A87),
    accent = Color(0xFF6AA8FF), accentPressed = Color(0xFF5A96EC), accentText = Color(0xFF0B1530), accentSoft = Color(0xFF22324D),
    success = Color(0xFF5FD39B), successSoft = Color(0xFF1E3A2D), warning = Color(0xFFF2C45F), warningSoft = Color(0xFF3D331B),
    danger = Color(0xFFFF8A8A), dangerSoft = Color(0xFF45242A),
)

/** Desktop Theme.fast / normal / slow; all 0 when 界面动画 is off (like Theme.motion). */
@Immutable
data class Motion(val enabled: Boolean) {
    val fast get() = if (enabled) 140 else 0
    val normal get() = if (enabled) 240 else 0
    val slow get() = if (enabled) 380 else 0
    fun <T> fastSpec(): FiniteAnimationSpec<T> = tween(fast, easing = OutCubic)
    fun <T> normalSpec(): FiniteAnimationSpec<T> = tween(normal, easing = OutCubic)
    fun <T> slowSpec(): FiniteAnimationSpec<T> = tween(slow, easing = OutCubic)
}

val OutCubic: Easing = CubicBezierEasing(0.33f, 1f, 0.68f, 1f)
val OutBack: Easing = CubicBezierEasing(0.34f, 1.56f, 0.64f, 1f)

object Dimens {
    val radius = 8.dp
    val radiusLarge = 12.dp
    val gap = 12.dp
    val pad = 16.dp
}

val LocalXColors = staticCompositionLocalOf { LightColors }
val LocalMotion = staticCompositionLocalOf { Motion(true) }

object X {
    val colors: XColors @Composable get() = LocalXColors.current
    val motion: Motion @Composable get() = LocalMotion.current
}

/** UI preferences kept like the desktop QSettings: theme (system / light / dark) and 界面动画. */
object UiPrefs {
    var theme by mutableStateOf("system")
    var motion by mutableStateOf(true)
    var splash by mutableStateOf(true)          // 启动动画
    var alertOnFinish by mutableStateOf(true)   // 运行结束提醒
    var autoUpdate by mutableStateOf(true)      // 启动时检查更新

    fun load(ctx: Context) {
        val p = ctx.getSharedPreferences("app", Context.MODE_PRIVATE)
        theme = p.getString("theme", "system") ?: "system"
        motion = p.getBoolean("motion", true)
        splash = p.getBoolean("splash", true)
        alertOnFinish = p.getBoolean("alertOnFinish", true)
        autoUpdate = p.getBoolean("autoUpdate", true)
    }

    fun save(ctx: Context) {
        ctx.getSharedPreferences("app", Context.MODE_PRIVATE).edit()
            .putString("theme", theme).putBoolean("motion", motion).putBoolean("splash", splash)
            .putBoolean("alertOnFinish", alertOnFinish).putBoolean("autoUpdate", autoUpdate).apply()
    }
}

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    val dark = when (UiPrefs.theme) {
        "light" -> false
        "dark" -> true
        else -> isSystemInDarkTheme()
    }
    val c = if (dark) DarkColors else LightColors
    val base = if (dark) darkColorScheme() else lightColorScheme()
    val scheme = base.copy(
        primary = c.accent, onPrimary = c.accentText, primaryContainer = c.accentSoft, onPrimaryContainer = c.accent,
        secondary = c.accent, onSecondary = c.accentText, secondaryContainer = c.accentSoft, onSecondaryContainer = c.accent,
        background = c.bg, onBackground = c.text, surface = c.surface, onSurface = c.text,
        surfaceVariant = c.surfaceAlt, onSurfaceVariant = c.muted, surfaceContainer = c.surface,
        surfaceContainerLow = c.surface, surfaceContainerHigh = c.surfaceAlt, surfaceContainerHighest = c.sunken,
        outline = c.borderStrong, outlineVariant = c.border, error = c.danger, onError = Color.White,
        errorContainer = c.dangerSoft, onErrorContainer = c.danger,
    )
    // Desktop sizes (px) scaled a little for a phone held at reading distance.
    val type = Typography(
        titleLarge = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.Bold, color = c.text),
        titleMedium = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.SemiBold),
        titleSmall = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.SemiBold),
        bodyLarge = TextStyle(fontSize = 15.sp),
        bodyMedium = TextStyle(fontSize = 14.sp),
        bodySmall = TextStyle(fontSize = 12.sp),
        labelLarge = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.Medium),
        labelMedium = TextStyle(fontSize = 12.sp, fontWeight = FontWeight.SemiBold),
        labelSmall = TextStyle(fontSize = 11.sp),
    )
    CompositionLocalProvider(LocalXColors provides c, LocalMotion provides Motion(UiPrefs.motion)) {
        MaterialTheme(colorScheme = scheme, typography = type, content = content)
    }
}
