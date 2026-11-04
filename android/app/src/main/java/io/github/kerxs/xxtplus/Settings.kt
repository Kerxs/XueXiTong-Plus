package io.github.kerxs.xxtplus

import android.content.Context
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
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
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.roundToInt

/**
 * config.ini values, edited with the field list from ui/advanced.py (shared with the desktop
 * settings page) plus the basic account / run fields; read and written by Python.
 */
object SettingsModel {
    var loaded by mutableStateOf(false)
    var schema: JSONObject = JSONObject()
        private set
    val values = mutableStateMapOf<String, String>()

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

    suspend fun problem(ctx: Context): String = withContext(Dispatchers.IO) { PythonBridge.setupProblem(ctx, json()) }

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
    SettingsModel.basic().filter { ids == null || it.optString("id") in ids }.forEach { FieldView(it) }
}

/** Dependent fields appear / disappear the way the desktop AdvancedOptions does (fade + height). */
@Composable
private fun AnimatedField(f: JSONObject) {
    val m = X.motion
    AnimatedVisibility(visible(f, SettingsModel.values),
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
        "aiprovider" -> Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(label, color = c.text, fontSize = 14.sp)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SettingsModel.schema.optJSONArray("aiProviders").objects().forEach { p ->
                    val endpoint = p.optString("endpoint")
                    val selected = values["tiku.endpoint"] == endpoint
                    FilterChip(selected = selected, onClick = { values["tiku.endpoint"] = endpoint },
                        label = { Text(p.optString("name")) }, colors = chipColors(), border = chipBorder(selected))
                }
            }
        }
        "modelpicker" -> ModelPicker()
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
        options.filter { it.optString("kind") in shownKinds }.forEach { o ->
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
        Hint(f.optString("hint"))
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
    val models = remember { mutableStateListOf<String>() }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        XButton(if (busy) "正在获取…" else "获取可用模型", {
            busy = true; error = ""
            scope.launch {
                val result = withContext(Dispatchers.IO) {
                    JSONObject(PythonBridge.listModels(ctx, values["tiku.endpoint"] ?: "", values["tiku.key"] ?: "", ""))
                }
                busy = false
                if (result.optBoolean("ok")) {
                    models.clear()
                    val arr = result.optJSONArray("models") ?: JSONArray()
                    for (i in 0 until arr.length()) models.add(arr.getString(i))
                } else {
                    error = result.optString("error")
                }
            }
        }, Modifier.fillMaxWidth(), enabled = !busy)
        if (error.isNotEmpty()) Text(error, color = c.danger, fontSize = 12.sp)
        if (models.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            models.forEach { m ->
                val selected = values["tiku.model"] == m
                FilterChip(selected = selected, onClick = { values["tiku.model"] = m }, label = { Text(m) },
                    colors = chipColors(), border = chipBorder(selected))
            }
        }
    }
}
