package io.github.kerxs.xxtplus

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextFieldColors
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlin.math.roundToInt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/**
 * config.ini values, edited with the field list from ui/advanced.py (shared with the desktop
 * settings page) plus the basic account / run fields; read and written by Python.
 */
object SettingsModel {
    var loaded by mutableStateOf(false)
    var schema: JSONObject = JSONObject()
        private set
    val values = mutableStateMapOf<String, String>()
    /** 更多 AI 选项 unfolded (fields marked "more" in ui/advanced.py); folded each time the app starts. */
    var moreOpen by mutableStateOf(false)

    suspend fun load(ctx: Context) = withContext(Dispatchers.IO) {
        val s = JSONObject(PythonBridge.settingsSchema(ctx))
        val v = JSONObject(PythonBridge.loadSettings(ctx))
        withContext(Dispatchers.Main) {
            schema = s
            values.clear()
            v.keys().forEach { values[it] = v.optString(it) }
            loaded = true
        }
    }

    private fun json() = JSONObject(values.toMap()).toString()

    suspend fun save(ctx: Context) = withContext(Dispatchers.IO) { PythonBridge.saveSettings(ctx, json()) }

    /** Why 开始运行 cannot start ("" = ready). Same rule and wording as the desktop (core/settings.py). */
    suspend fun problem(ctx: Context): String = withContext(Dispatchers.IO) { PythonBridge.setupProblem(ctx, json()) }

    /** The guide's 答题来源 step (stricter: 题库 needs its token / address). */
    suspend fun guideProblem(ctx: Context): String = withContext(Dispatchers.IO) { PythonBridge.guideProblem(ctx, json()) }

    fun basic(): List<JSONObject> = schema.optJSONArray("basic").objects()
    fun group(id: String): JSONObject? = schema.optJSONArray("groups").objects().firstOrNull { it.optString("id") == id }
    fun groups(): List<JSONObject> = schema.optJSONArray("groups").objects()
}

fun JSONArray?.objects(): List<JSONObject> = if (this == null) emptyList() else (0 until length()).map { getJSONObject(it) }

private fun split(value: String?) = (value ?: "").split(",").map { it.trim() }.filter { it.isNotEmpty() }

/** Same rules as the desktop AdvancedOptions.qml ("show" in ui/advanced.py). */
private fun visible(field: JSONObject, values: Map<String, String>): Boolean {
    val show = field.opt("show") ?: return true
    val conds = when (show) {
        is JSONArray -> show.objects()
        is JSONObject -> listOf(show)
        else -> return true
    }
    return conds.all { c ->
        val v = values[c.optString("key")] ?: ""
        when {
            c.has("has") -> {
                val wanted = when (val h = c.get("has")) {
                    is JSONArray -> (0 until h.length()).map { h.getString(it) }
                    else -> listOf(h.toString())
                }
                split(v).any { it in wanted }
            }
            c.has("eq") -> v == c.optString("eq")
            c.has("ne") -> v != c.optString("ne")
            c.has("on") -> (v.lowercase() in listOf("true", "1", "yes", "on")) == c.optBoolean("on")
            else -> true
        }
    }
}

// ---------------------------------------------------------------- desktop-coloured controls

@Composable
fun fieldColors(): TextFieldColors {
    val c = X.colors
    return OutlinedTextFieldDefaults.colors(
        focusedBorderColor = c.accent, unfocusedBorderColor = c.border, focusedLabelColor = c.accent,
        unfocusedLabelColor = c.muted, focusedContainerColor = c.surface, unfocusedContainerColor = c.surface,
        cursorColor = c.accent, focusedTextColor = c.text, unfocusedTextColor = c.text,
        focusedSupportingTextColor = c.muted, unfocusedSupportingTextColor = c.muted,
        unfocusedPlaceholderColor = c.faint, focusedPlaceholderColor = c.faint,
        focusedSuffixColor = c.muted, unfocusedSuffixColor = c.muted, errorBorderColor = c.danger,
        errorSupportingTextColor = c.danger, errorLabelColor = c.danger,
    )
}

@Composable
fun switchColors() = X.colors.let { c ->
    SwitchDefaults.colors(checkedTrackColor = c.accent, checkedThumbColor = c.accentText,
        uncheckedTrackColor = c.sunken, uncheckedThumbColor = c.muted, uncheckedBorderColor = c.borderStrong)
}

@Composable
fun checkboxColors() = X.colors.let { c ->
    CheckboxDefaults.colors(checkedColor = c.accent, uncheckedColor = c.borderStrong, checkmarkColor = c.accentText)
}

@Composable
private fun chipColors() = X.colors.let { c ->
    FilterChipDefaults.filterChipColors(containerColor = c.surface, labelColor = c.text,
        selectedContainerColor = c.accentSoft, selectedLabelColor = c.accent)
}

@Composable
private fun chipBorder(selected: Boolean) = X.colors.let { c ->
    FilterChipDefaults.filterChipBorder(enabled = true, selected = selected, borderColor = c.border, selectedBorderColor = c.accent)
}

// ---------------------------------------------------------------- cards

@Composable
fun SettingsGroupCard(group: JSONObject, appearDelay: Int = 0) {
    XCard(Modifier.fillMaxWidth(), title = group.optString("title"), subtitle = group.optString("subtitle"),
        appearDelay = appearDelay) {
        group.optJSONArray("fields").objects().forEach { f -> AnimatedField(f) }
    }
}

@Composable
fun BasicFields(ids: List<String>? = null) {
    SettingsModel.basic().filter { ids == null || it.optString("id") in ids }.forEach { AnimatedField(it) }
}

/** Dependent fields appear / disappear the way the desktop AdvancedOptions does (fade + height). */
@Composable
private fun AnimatedField(f: JSONObject) {
    val m = X.motion
    AnimatedVisibility(visible(f, SettingsModel.values) && (!f.optBoolean("more") || SettingsModel.moreOpen),
        enter = fadeIn(tween(m.normal)) + expandVertically(tween(m.normal)),
        exit = fadeOut(tween(m.fast)) + shrinkVertically(tween(m.normal))) {
        FieldView(f)
    }
}

@Composable
private fun Hint(text: String) {
    if (text.isNotEmpty()) Text(text, color = X.colors.muted, fontSize = 12.sp)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FieldView(f: JSONObject) {
    val c = X.colors
    val id = f.optString("id")
    val values = SettingsModel.values
    val value = values[id] ?: f.optString("default")
    val label = f.optString("label")
    val hint = f.optString("hint")
    when (f.optString("type")) {
        "heading" -> Text(label, color = c.text, fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(top = 4.dp))
        "switch" -> SwitchRow(label, hint, value.lowercase() == "true") { values[id] = if (it) "true" else "false" }
        "percent" -> Column {
            val v = value.toFloatOrNull() ?: 0f
            Row {
                Text(label, color = c.text, fontSize = 14.sp, modifier = Modifier.weight(1f))
                Text("${(v * 100).roundToInt()}%", color = c.accent, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            }
            Slider(value = v, onValueChange = { values[id] = String.format(java.util.Locale.US, "%.2f", (it * 20).roundToInt() / 20f) },
                valueRange = 0f..1f, steps = 19,
                colors = SliderDefaults.colors(thumbColor = c.accent, activeTrackColor = c.accent, inactiveTrackColor = c.sunken,
                    activeTickColor = c.accentText.copy(alpha = 0.4f), inactiveTickColor = c.borderStrong))
            Hint(hint)
        }
        "number" -> {
            val decimals = f.optInt("decimals", 0)
            val min = f.optDouble("min"); val max = f.optDouble("max")
            val n = value.toDoubleOrNull()
            val bad = n == null || (!min.isNaN() && n < min) || (!max.isNaN() && n > max)
            OutlinedTextField(
                value = value, onValueChange = { values[id] = it.trim() },
                label = { Text(label) }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(Dimens.radius), colors = fieldColors(),
                suffix = { Text(f.optString("suffix")) },
                keyboardOptions = KeyboardOptions(keyboardType = if (decimals > 0) KeyboardType.Decimal else KeyboardType.Number),
                supportingText = { Text(if (bad) "范围 ${fmt(min)} – ${fmt(max)}" else hint) },
                isError = bad,
            )
        }
        "choice" -> Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(label, color = c.text, fontSize = 14.sp)
            val options = f.optJSONArray("options").objects().map { it.optString("value") to it.optString("label") }
            if (options.size <= 3) {
                Segmented(options, value, { values[id] = it }, Modifier.fillMaxWidth())
            } else {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    options.forEach { (v, l) ->
                        FilterChip(selected = value == v, onClick = { values[id] = v }, label = { Text(l) },
                            colors = chipColors(), border = chipBorder(value == v))
                    }
                }
            }
            Hint(hint)
        }
        "text", "secret" -> OutlinedTextField(
            value = value, onValueChange = { values[id] = it }, label = { Text(label) },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(Dimens.radius), colors = fieldColors(),
            visualTransformation = if (f.optString("type") == "secret") PasswordVisualTransformation() else VisualTransformation.None,
            supportingText = { if (hint.isNotEmpty()) Text(hint) },
        )
        "providers" -> ProvidersField(f)
        "aiprovider" -> AiProviderField(label)
        "modelpicker" -> ModelPicker()
        "backupproviders" -> BackupProvidersField()
        "more" -> MoreRow(label, hint)
        "aitest" -> AiTestRow()
        else -> Unit  // display-only types the phone does not use
    }
}

private fun fmt(d: Double) = if (d.isNaN()) "" else if (d == d.toLong().toDouble()) d.toLong().toString() else d.toString()

/** 答题方式: mode (none / 题库 / AI / both) + the providers of those kinds, 题库 first (ui/advanced.py). */
@Composable
private fun ProvidersField(f: JSONObject) {
    val c = X.colors
    val id = f.optString("id")
    val values = SettingsModel.values
    val options = f.optJSONArray("options").objects()
    val kindOf = options.associate { it.optString("value") to it.optString("kind") }
    val picked = split(values[id])
    val kinds = picked.map { kindOf[it] ?: "tiku" }.toSet()
    val mode = when { kinds.isEmpty() -> "none"; kinds == setOf("tiku") -> "tiku"; kinds == setOf("ai") -> "ai"; else -> "both" }

    fun store(list: List<String>) {
        val tiku = list.filter { (kindOf[it] ?: "tiku") == "tiku" }
        val ai = list.filter { kindOf[it] == "ai" }
        values[id] = (tiku + ai).joinToString(",")
    }

    fun applyMode(m: String) {
        val tiku = picked.filter { (kindOf[it] ?: "tiku") == "tiku" }
        val ai = picked.filter { kindOf[it] == "ai" }
        val parts = mutableListOf<String>()
        if (m == "tiku" || m == "both") parts += tiku.ifEmpty { listOf("TikuYanxi") }
        if (m == "ai" || m == "both") parts += ai.ifEmpty { listOf("AI") }
        store(parts)
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(f.optString("label"), color = c.text, fontSize = 14.sp)
        val modes = f.optJSONArray("modes").objects()
        Segmented(modes.map { it.optString("value") to it.optString("label") }, mode, { applyMode(it) }, Modifier.fillMaxWidth())
        modes.firstOrNull { it.optString("value") == mode }?.let { Hint(it.optString("hint")) }
        val shownKinds = when (mode) { "tiku" -> setOf("tiku"); "ai" -> setOf("ai"); "both" -> setOf("tiku", "ai"); else -> emptySet() }
        val choices = options.filter { it.optString("kind") in shownKinds && (!it.optBoolean("legacy") || it.optString("value") in picked) }
        val aiOnly = mode == "ai" && choices.size == 1 && choices[0].optString("value") in picked
        if (!aiOnly) choices.forEach { o ->
            val v = o.optString("value")
            val index = picked.indexOf(v)
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius)).clickable {
                store(if (index >= 0) picked - v else picked + v)
            }.padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = index >= 0, onCheckedChange = null, colors = checkboxColors())
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f)) {
                    Text(o.optString("label") + if (index >= 0 && picked.size > 1) "（第 ${index + 1} 个查询）" else "",
                        color = c.text, fontSize = 14.sp)
                    Hint(o.optString("hint"))
                }
            }
        }
        if (!aiOnly && mode != "none") Hint(f.optString("hint"))
    }
}

private const val CUSTOM_PROVIDERS = "tiku.custom_providers"

/** Saved 自定义服务商 (ui/cloudmodels.py): [{name, endpoint}] as JSON in tiku.custom_providers. */
private fun customProviders(saved: String): List<Pair<String, String>> = runCatching {
    JSONArray(saved.ifBlank { "[]" }).objects().map { it.optString("name") to it.optString("endpoint") }
        .filter { it.first.isNotBlank() && it.second.isNotBlank() }
}.getOrDefault(emptyList())

/** One service in the picker: a built-in company or a saved custom one. */
private data class Service(val name: String, val endpoint: String, val console: String, val custom: Boolean)

/**
 * 模型服务商: one row with the service in use; tapping it opens 选择服务商, a two-level menu
 * (国内 / 海外 / 自定义 → the services of that category) like the desktop ProviderPickerDialog.
 */
@Composable
private fun AiProviderField(label: String) {
    val ctx = LocalContext.current
    val c = X.colors
    val values = SettingsModel.values
    val endpoint = (values["tiku.endpoint"] ?: "").trim().trimEnd('/')
    val saved = values[CUSTOM_PROVIDERS] ?: ""
    val custom = remember(saved) { customProviders(saved) }
    val builtIn = SettingsModel.schema.optJSONArray("aiProviders").objects()
    val current = builtIn.firstOrNull { it.optString("endpoint") == endpoint }
    val currentName = current?.optString("name") ?: custom.firstOrNull { it.second == endpoint }?.first ?: ""
    var picking by remember { mutableStateOf(false) }

    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, color = c.text, fontSize = 14.sp)
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius))
            .border(1.dp, c.border, RoundedCornerShape(Dimens.radius)).background(c.surface)
            .clickable { picking = true }.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(currentName.ifEmpty { if (endpoint.isEmpty()) "未选择" else "请重新选择" },
                    color = if (currentName.isNotEmpty()) c.text else c.muted, fontSize = 15.sp, fontWeight = FontWeight.Medium)
                Text(endpoint.ifEmpty { "国内、海外常用服务，或你自己的服务" }, color = c.muted, fontSize = 12.sp,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Text("更换", color = c.muted, fontSize = 13.sp)
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = c.faint)
        }
        val console = current?.optString("console").orEmpty()
        if (console.isNotEmpty()) Text("获取 API Key ↗", color = c.accent, fontSize = 13.sp,
            modifier = Modifier.clip(RoundedCornerShape(6.dp)).clickable { openLink(ctx, console) }.padding(vertical = 4.dp))
    }

    if (picking) ProviderPicker(endpoint, builtIn, custom, saved) { picking = false }
}

private fun openLink(ctx: Context, url: String) {
    runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
}

/** 选择服务商: full screen; first the categories, then the services of the chosen one. */
@Composable
private fun ProviderPicker(
    endpoint: String, builtIn: List<JSONObject>, custom: List<Pair<String, String>>, saved: String,
    onPick: ((String) -> Unit)? = null, onClose: () -> Unit,
) {
    val ctx = LocalContext.current
    val c = X.colors
    val scope = rememberCoroutineScope()
    val values = SettingsModel.values
    val regions = SettingsModel.schema.optJSONArray("aiRegions").objects()
        .map { it.optString("id") to it.optString("label") } + ("custom" to "自定义服务")
    fun servicesOf(id: String): List<Service> =
        if (id == "custom") custom.map { Service(it.first, it.second, "", true) }
        else builtIn.filter { it.optString("region") == id }
            .map { Service(it.optString("name"), it.optString("endpoint"), it.optString("console"), false) }
    var category by remember { mutableStateOf("") }
    var adding by remember { mutableStateOf(false) }
    var removing by remember { mutableStateOf<Service?>(null) }

    fun back() { if (category.isEmpty()) onClose() else category = "" }
    // onPick: 备用服务商 — the address goes to that dialog, the primary service stays as it is
    fun pick(e: String) { if (onPick != null) onPick(e) else values["tiku.endpoint"] = e; onClose() }

    Dialog(onDismissRequest = { back() }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Column(Modifier.fillMaxSize().background(c.bg).padding(Dimens.pad).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(Dimens.gap)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(40.dp).clip(RoundedCornerShape(Dimens.radius)).clickable { back() },
                    contentAlignment = Alignment.Center) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, "返回", tint = c.text)
                }
                Spacer(Modifier.size(6.dp))
                PageHeader(regions.firstOrNull { it.first == category }?.second?.substringBefore("（") ?: "选择服务商")
            }
            if (category.isEmpty()) {
                XCard(Modifier.fillMaxWidth(), padding = 6.dp) {
                    regions.forEachIndexed { i, (id, title) ->
                        val inUse = servicesOf(id).any { it.endpoint == endpoint }
                        PickerRow(title.substringBefore("（"), when {
                            inUse -> "正在使用：" + servicesOf(id).first { it.endpoint == endpoint }.name
                            id == "custom" && custom.isEmpty() -> "中转站、公司网关等，自己添加"
                            else -> "${servicesOf(id).size} 个服务"
                        }, divider = i < regions.size - 1, chevron = true) { category = id }
                    }
                }
                Text("都需要兼容 OpenAI 接口。海外服务在国内通常需要网络代理。", color = c.muted, fontSize = 12.sp)
            } else {
                val list = servicesOf(category)
                if (list.isNotEmpty()) XCard(Modifier.fillMaxWidth(), padding = 6.dp) {
                    list.forEachIndexed { i, s ->
                        PickerRow(s.name, s.endpoint, divider = i < list.size - 1, selected = s.endpoint == endpoint,
                            onRemove = if (s.custom) ({ removing = s }) else null) { pick(s.endpoint) }
                    }
                }
                if (category == "custom") {
                    if (list.isEmpty()) Text("还没有自定义服务。中转站、公司内部网关等兼容 OpenAI 接口的服务，可以在这里添加。",
                        color = c.muted, fontSize = 13.sp)
                    XButton("添加自定义服务", { adding = true }, Modifier.fillMaxWidth(), Kind.Primary)
                } else {
                    Text("选好后到“API Key”里填写这个服务的密钥。", color = c.muted, fontSize = 12.sp)
                }
            }
        }
    }

    if (adding) {
        var name by remember { mutableStateOf("") }
        var url by remember { mutableStateOf("") }
        var error by remember { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { adding = false },
            containerColor = c.surface, titleContentColor = c.text, textContentColor = c.text,
            shape = RoundedCornerShape(Dimens.radiusLarge),
            title = { Text("添加自定义服务") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(name, { name = it.take(24) }, label = { Text("名称") }, singleLine = true,
                        modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(Dimens.radius), colors = fieldColors())
                    OutlinedTextField(url, { url = it.trim() }, label = { Text("接口地址") }, singleLine = true,
                        placeholder = { Text("https://api.example.com/v1") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                        modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(Dimens.radius), colors = fieldColors())
                    Text(error.ifEmpty { "地址填到 /v1，不要带 /chat/completions" },
                        color = if (error.isEmpty()) c.muted else c.danger, fontSize = 12.sp)
                }
            },
            confirmButton = {
                XButton("保存并使用", {
                    scope.launch {
                        val result = withContext(Dispatchers.IO) {
                            JSONObject(PythonBridge.addCustomProvider(ctx, saved, name, url))
                        }
                        if (result.optBoolean("ok")) {
                            values[CUSTOM_PROVIDERS] = result.optString("value")
                            adding = false
                            pick(result.optString("endpoint"))
                        } else {
                            error = result.optString("error")
                        }
                    }
                }, kind = Kind.Primary)
            },
            dismissButton = { XButton("取消", { adding = false }, kind = Kind.Ghost) },
        )
    }

    removing?.let { s ->
        AlertDialog(
            onDismissRequest = { removing = null },
            containerColor = c.surface, titleContentColor = c.text, textContentColor = c.text,
            shape = RoundedCornerShape(Dimens.radiusLarge),
            title = { Text("删除自定义服务") },
            text = { Text("删除“${s.name}”（${s.endpoint}）？") },
            confirmButton = {
                XButton("删除", {
                    scope.launch {
                        values[CUSTOM_PROVIDERS] = withContext(Dispatchers.IO) {
                            PythonBridge.removeCustomProvider(ctx, saved, s.endpoint)
                        }
                        if (onPick == null && endpoint == s.endpoint) values["tiku.endpoint"] = ""
                        removing = null
                    }
                }, kind = Kind.Danger)
            },
            dismissButton = { XButton("取消", { removing = null }, kind = Kind.Ghost) },
        )
    }
}

@Composable
private fun PickerRow(
    title: String, subtitle: String, divider: Boolean, selected: Boolean = false, chevron: Boolean = false,
    onRemove: (() -> Unit)? = null, onClick: () -> Unit,
) {
    val c = X.colors
    Column {
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius))
            .background(if (selected) c.accentSoft else Color.Transparent).clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(title, color = if (selected) c.accent else c.text, fontSize = 15.sp,
                    fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium)
                Text(subtitle, color = c.muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            if (onRemove != null) Box(Modifier.size(36.dp).clip(RoundedCornerShape(Dimens.radius)).clickable(onClick = onRemove),
                contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Delete, "删除", tint = c.faint, modifier = Modifier.size(20.dp))
            }
            if (selected) Icon(Icons.Filled.Check, "正在使用", tint = c.accent, modifier = Modifier.size(20.dp))
            if (chevron) Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = c.faint)
        }
        if (divider) Box(Modifier.fillMaxWidth().padding(horizontal = 12.dp).height(1.dp).background(c.border))
    }
}
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ModelPicker() {
    val ctx = LocalContext.current
    val c = X.colors
    val scope = rememberCoroutineScope()
    val values = SettingsModel.values
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var hidden by remember { mutableStateOf(0) }
    val models = remember { mutableStateListOf<String>() }
    val endpoint = values["tiku.endpoint"] ?: ""
    val key = values["tiku.key"] ?: ""
    fun fetch() {
        busy = true; error = ""
        scope.launch {
            val result = withContext(Dispatchers.IO) { JSONObject(PythonBridge.listModels(ctx, endpoint, key, "")) }
            busy = false
            if (result.optBoolean("ok")) {
                models.clear()
                val arr = result.optJSONArray("models") ?: JSONArray()
                for (i in 0 until arr.length()) models.add(arr.getString(i))
                hidden = result.optInt("hidden")
            } else {
                error = result.optString("error")
            }
        }
    }
    // No "获取" step to learn: the list comes by itself shortly after the service and key are there.
    LaunchedEffect(endpoint, key) {
        models.clear(); error = ""
        if (endpoint.isNotBlank() && key.isNotBlank()) { kotlinx.coroutines.delay(900); fetch() }
    }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        XButton(if (busy) "正在获取…" else if (models.isEmpty()) "获取可用模型" else "重新获取", { fetch() },
            Modifier.fillMaxWidth(), enabled = !busy && endpoint.isNotBlank())
        if (error.isNotEmpty()) Text(error, color = c.danger, fontSize = 12.sp)
        if (models.isNotEmpty()) Text("${models.size} 个能答题的模型，点一个即可使用" +
            if (hidden > 0) "（已隐藏 $hidden 个向量、语音、绘图等模型）" else "", color = c.muted, fontSize = 12.sp)
        if (models.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            models.forEach { m ->
                val selected = values["tiku.model"] == m
                FilterChip(selected = selected, onClick = { values["tiku.model"] = m }, label = { Text(m) },
                    colors = chipColors(), border = chipBorder(selected))
            }
        }
    }
}

// ---------------------------------------------------------------- 备用服务商 (core/aiproviders.py)

private const val BACKUPS = "tiku.backup_providers"
private const val MAX_BACKUPS = 8

private data class Backup(val endpoint: String, val key: String, val model: String)

private fun backups(saved: String): List<Backup> = runCatching {
    JSONArray(saved.ifBlank { "[]" }).objects()
        .map { Backup(it.optString("endpoint").trim().trimEnd('/'), it.optString("key").trim(), it.optString("model").trim()) }
        .filter { it.endpoint.isNotEmpty() }
}.getOrDefault(emptyList())

private fun storeBackups(list: List<Backup>) {
    SettingsModel.values[BACKUPS] = if (list.isEmpty()) "" else JSONArray(list.take(MAX_BACKUPS).map {
        JSONObject().put("endpoint", it.endpoint).put("key", it.key).put("model", it.model)
    }).toString()
}

/** Same rules as core/aiproviders.problem with cloud_only (the phone only uses cloud services). */
private fun backupProblem(b: Backup): String = when {
    b.endpoint.isEmpty() -> "还没选择服务商"
    !b.endpoint.startsWith("https://") -> "手机上只能使用 https 开头的云端服务"
    b.model.isEmpty() -> "还没填写模型名称"
    b.key.isEmpty() -> "还没填写 API Key"
    else -> ""
}

/**
 * 备用服务商: tried in order when the primary service fails (connection, timeout, wrong key, quota,
 * server error). Each row moves up / down, becomes the primary (swapping with it), or is edited / removed.
 */
@Composable
private fun BackupProvidersField() {
    val c = X.colors
    val values = SettingsModel.values
    val list = backups(values[BACKUPS] ?: "")
    val names = SettingsModel.schema.optJSONArray("aiProviders").objects().associate { it.optString("endpoint") to it.optString("name") } +
        customProviders(values[CUSTOM_PROVIDERS] ?: "").associate { it.second to it.first }
    var editing by remember { mutableStateOf<Int?>(null) }      // -1: adding

    fun move(i: Int, d: Int) {
        val l = list.toMutableList(); val j = i + d
        if (j in l.indices) { val t = l[i]; l[i] = l[j]; l[j] = t; storeBackups(l) }
    }
    fun promote(i: Int) {
        val chosen = list[i]
        val old = Backup((values["tiku.endpoint"] ?: "").trim().trimEnd('/'), values["tiku.key"] ?: "", values["tiku.model"] ?: "")
        val rest = list.toMutableList()
        if (old.endpoint.isNotEmpty()) rest[i] = old else rest.removeAt(i)
        values["tiku.endpoint"] = chosen.endpoint; values["tiku.key"] = chosen.key; values["tiku.model"] = chosen.model
        storeBackups(rest)
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("备用服务商", color = c.text, fontSize = 14.sp)
                Text("上面的服务商出错（连不上、超时、Key 无效、额度不足）时按顺序换下一个", color = c.muted, fontSize = 12.sp)
            }
            XButton("添加", { editing = -1 }, enabled = list.size < MAX_BACKUPS)
        }
        list.forEachIndexed { i, b ->
            val problem = backupProblem(b)
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius))
                .border(1.dp, if (problem.isEmpty()) c.border else c.warning, RoundedCornerShape(Dimens.radius))
                .background(c.surface).padding(start = 12.dp, end = 2.dp, top = 6.dp, bottom = 6.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text("${i + 2}", color = c.accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.clip(RoundedCornerShape(11.dp)).background(c.accentSoft).padding(horizontal = 7.dp, vertical = 2.dp))
                Column(Modifier.weight(1f).padding(start = 10.dp)) {
                    // narrow screen: the service on the first line, the model (or what is missing) below
                    Text(names[b.endpoint] ?: b.endpoint, color = c.text,
                        fontSize = 14.sp, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(problem.ifEmpty { b.model }, color = if (problem.isEmpty()) c.muted else c.warning,
                        fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                RowIcon(Icons.Filled.KeyboardArrowUp, "上移", i > 0) { move(i, -1) }
                RowIcon(Icons.Filled.KeyboardArrowDown, "下移", i < list.lastIndex) { move(i, 1) }
                RowIcon(Icons.Filled.Star, "设为首选") { promote(i) }
                RowIcon(Icons.Filled.Edit, "编辑") { editing = i }
                RowIcon(Icons.Filled.Delete, "删除") { storeBackups(list.filterIndexed { j, _ -> j != i }) }
            }
        }
        if (list.isEmpty()) Text("还没有备用服务商：上面的服务商出错时，AI 答不了的题会随机作答或留空。", color = c.faint, fontSize = 12.sp)
    }

    editing?.let { i -> BackupEditor(i, list.getOrNull(i)) { editing = null } }
}

@Composable
private fun RowIcon(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, enabled: Boolean = true, onClick: () -> Unit) {
    val c = X.colors
    Box(Modifier.size(34.dp).clip(RoundedCornerShape(8.dp)).clickable(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center) {
        Icon(icon, label, tint = if (enabled) c.muted else c.faint.copy(alpha = 0.4f), modifier = Modifier.size(20.dp))
    }
}

/** Add (index -1) or change one backup: service, API Key, model (typed or from the service's list). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun BackupEditor(index: Int, entry: Backup?, onClose: () -> Unit) {
    val ctx = LocalContext.current
    val c = X.colors
    val scope = rememberCoroutineScope()
    val values = SettingsModel.values
    var endpoint by remember { mutableStateOf(entry?.endpoint ?: "") }
    var key by remember { mutableStateOf(entry?.key ?: "") }
    var model by remember { mutableStateOf(entry?.model ?: "") }
    var error by remember { mutableStateOf("") }
    var picking by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    val models = remember { mutableStateListOf<String>() }
    val saved = values[CUSTOM_PROVIDERS] ?: ""
    val custom = remember(saved) { customProviders(saved) }
    val builtIn = SettingsModel.schema.optJSONArray("aiProviders").objects()
    val name = builtIn.firstOrNull { it.optString("endpoint") == endpoint }?.optString("name")
        ?: custom.firstOrNull { it.second == endpoint }?.first ?: ""

    AlertDialog(
        onDismissRequest = onClose,
        containerColor = c.surface, titleContentColor = c.text, textContentColor = c.text,
        shape = RoundedCornerShape(Dimens.radiusLarge),
        title = { Text(if (index < 0) "添加备用服务商" else "编辑备用服务商 ${index + 2}") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius))
                    .border(1.dp, c.border, RoundedCornerShape(Dimens.radius)).background(c.surfaceAlt)
                    .clickable { picking = true }.padding(horizontal = 12.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(name.ifEmpty { if (endpoint.isEmpty()) "选择服务商" else "请重新选择" },
                            color = if (name.isEmpty()) c.muted else c.text, fontSize = 15.sp, fontWeight = FontWeight.Medium)
                        if (endpoint.isNotEmpty()) Text(endpoint, color = c.muted, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = c.faint)
                }
                OutlinedTextField(value = key, onValueChange = { key = it }, label = { Text("API Key") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(Dimens.radius), colors = fieldColors(),
                    visualTransformation = PasswordVisualTransformation())
                OutlinedTextField(value = model, onValueChange = { model = it }, label = { Text("模型名称") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(Dimens.radius), colors = fieldColors())
                XButton(if (busy) "正在获取…" else "获取可用模型", {
                    busy = true; error = ""
                    scope.launch {
                        val result = withContext(Dispatchers.IO) { JSONObject(PythonBridge.listModels(ctx, endpoint, key, "")) }
                        busy = false
                        if (result.optBoolean("ok")) {
                            models.clear()
                            val arr = result.optJSONArray("models") ?: JSONArray()
                            for (j in 0 until arr.length()) models.add(arr.getString(j))
                        } else error = result.optString("error")
                    }
                }, Modifier.fillMaxWidth(), enabled = !busy && endpoint.isNotEmpty())
                if (models.isNotEmpty()) {
                    val q = model.trim().lowercase()
                    val shown = if (q.isEmpty() || model.trim() in models) models else models.filter { q in it.lowercase() }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        shown.take(60).forEach { m ->
                            FilterChip(selected = model == m, onClick = { model = m }, label = { Text(m) },
                                colors = chipColors(), border = chipBorder(model == m))
                        }
                    }
                }
                if (error.isNotEmpty()) Text(error, color = c.warning, fontSize = 12.sp)
            }
        },
        confirmButton = {
            XButton("保存", {
                val b = Backup(endpoint.trim().trimEnd('/'), key.trim(), model.trim())
                error = backupProblem(b)
                if (error.isEmpty()) {
                    val list = backups(values[BACKUPS] ?: "").toMutableList()
                    if (index in list.indices) list[index] = b else list.add(b)
                    storeBackups(list)
                    onClose()
                }
            }, kind = Kind.Primary)
        },
        dismissButton = { XButton("取消", onClose, kind = Kind.Ghost) },
    )

    if (picking) ProviderPicker(endpoint, builtIn, custom, saved, onPick = { e ->
        if (e != endpoint) models.clear()
        endpoint = e
    }) { picking = false }
}

// ---------------------------------------------------------------- 更多 AI 选项 / 测试

/** One row that unfolds the rarely needed AI settings (图片、合并提问、请求间隔 …). */
@Composable
private fun MoreRow(label: String, hint: String) {
    val c = X.colors
    val open = SettingsModel.moreOpen
    val turn by androidx.compose.animation.core.animateFloatAsState(if (open) 180f else 0f, tween(X.motion.normal), label = "more")
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius)).clickable { SettingsModel.moreOpen = !open }
        .padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Filled.KeyboardArrowDown, null, tint = c.muted,
            modifier = Modifier.size(20.dp).graphicsLayer { rotationZ = turn })
        Spacer(Modifier.width(8.dp))
        Column(Modifier.weight(1f)) {
            Text(label, color = c.text, fontSize = 14.sp)
            if (!open) Text("$hint，一般不用改", color = c.faint, fontSize = 12.sp)
        }
    }
}

/** 测试: asks the chosen model one tiny question, so a wrong key / model shows now, not during the run. */
@Composable
private fun AiTestRow() {
    val ctx = LocalContext.current
    val c = X.colors
    val scope = rememberCoroutineScope()
    val values = SettingsModel.values
    val endpoint = values["tiku.endpoint"] ?: ""
    val key = values["tiku.key"] ?: ""
    val model = values["tiku.model"] ?: ""
    var state by remember(endpoint, key, model) { mutableStateOf("idle") }
    var message by remember(endpoint, key, model) { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        XButton(if (state == "running") "正在测试…" else "测试一下", {
            state = "running"
            scope.launch {
                val started = System.currentTimeMillis()
                val reason = withContext(Dispatchers.IO) { PythonBridge.testAi(ctx, endpoint, key, model) }
                state = if (reason.isEmpty()) "ok" else "error"
                message = reason.ifEmpty { "可以使用，%.1f 秒回答".format((System.currentTimeMillis() - started) / 1000.0) }
            }
        }, Modifier.fillMaxWidth(), kind = if (state == "ok") Kind.Secondary else Kind.Primary,
            enabled = state != "running" && endpoint.isNotBlank() && model.isNotBlank())
        Text(when (state) { "idle" -> "选好模型后点一下，确认 API Key 和模型都能用"; "ok" -> "✓ $message"; else -> message },
            color = when (state) { "ok" -> c.success; "error" -> c.danger; else -> c.muted }, fontSize = 12.sp)
    }
}
