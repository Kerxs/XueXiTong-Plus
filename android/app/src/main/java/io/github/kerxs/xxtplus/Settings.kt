package io.github.kerxs.xxtplus

import android.content.Context
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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
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

@Composable
fun SettingsGroupCard(group: JSONObject, showTitle: Boolean = true) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (showTitle) {
                Text(group.optString("title"), style = MaterialTheme.typography.titleMedium)
                group.optString("subtitle").takeIf { it.isNotEmpty() }?.let {
                    Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            group.optJSONArray("fields").objects().forEach { f ->
                if (visible(f, SettingsModel.values)) FieldView(f)
            }
        }
    }
}

@Composable
fun BasicFieldsCard(ids: List<String>? = null) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            SettingsModel.basic().filter { ids == null || it.optString("id") in ids }.forEach { FieldView(it) }
        }
    }
}

@Composable
private fun Hint(text: String) {
    if (text.isNotEmpty()) Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FieldView(f: JSONObject) {
    val id = f.optString("id")
    val values = SettingsModel.values
    val value = values[id] ?: f.optString("default")
    val label = f.optString("label")
    val hint = f.optString("hint")
    when (f.optString("type")) {
        "heading" -> Text(label, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        "switch" -> Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) { Text(label); Hint(hint) }
            Switch(checked = value.lowercase() == "true", onCheckedChange = { values[id] = if (it) "true" else "false" })
        }
        "percent" -> Column {
            val v = value.toFloatOrNull() ?: 0f
            Text("$label：${(v * 100).roundToInt()}%")
            Slider(value = v, onValueChange = { values[id] = String.format(java.util.Locale.US, "%.2f", (it * 20).roundToInt() / 20f) }, valueRange = 0f..1f, steps = 19)
            Hint(hint)
        }
        "number" -> {
            val decimals = f.optInt("decimals", 0)
            OutlinedTextField(
                value = value, onValueChange = { values[id] = it.trim() },
                label = { Text(label) }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                suffix = { Text(f.optString("suffix")) },
                keyboardOptions = KeyboardOptions(keyboardType = if (decimals > 0) KeyboardType.Decimal else KeyboardType.Number),
                supportingText = {
                    val n = value.toDoubleOrNull()
                    val min = f.optDouble("min"); val max = f.optDouble("max")
                    val bad = n == null || (!min.isNaN() && n < min) || (!max.isNaN() && n > max)
                    Text(if (bad) "范围 ${fmt(min)} – ${fmt(max)}" else hint)
                },
                isError = value.toDoubleOrNull()?.let { n ->
                    val min = f.optDouble("min"); val max = f.optDouble("max")
                    (!min.isNaN() && n < min) || (!max.isNaN() && n > max)
                } ?: true,
            )
        }
        "choice" -> Column {
            Text(label)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                f.optJSONArray("options").objects().forEach { o ->
                    FilterChip(selected = value == o.optString("value"), onClick = { values[id] = o.optString("value") },
                        label = { Text(o.optString("label")) })
                }
            }
            Hint(hint)
        }
        "text", "secret" -> OutlinedTextField(
            value = value, onValueChange = { values[id] = it }, label = { Text(label) },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
            visualTransformation = if (f.optString("type") == "secret") PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
            supportingText = { if (hint.isNotEmpty()) Text(hint) },
        )
        "providers" -> ProvidersField(f)
        "aiprovider" -> Column {
            Text(label)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SettingsModel.schema.optJSONArray("aiProviders").objects().forEach { p ->
                    val endpoint = p.optString("endpoint")
                    FilterChip(selected = values["tiku.endpoint"] == endpoint, onClick = { values["tiku.endpoint"] = endpoint },
                        label = { Text(p.optString("name")) })
                }
            }
        }
        "modelpicker" -> ModelPicker()
        else -> Unit  // display-only types the phone does not use
    }
}

private fun fmt(d: Double) = if (d.isNaN()) "" else if (d == d.toLong().toDouble()) d.toLong().toString() else d.toString()

/** 答题方式: mode (none / 题库 / AI / both) + the providers of those kinds, 题库 first (ui/advanced.py). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ProvidersField(f: JSONObject) {
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

    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(f.optString("label"))
        val modes = f.optJSONArray("modes").objects()
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            modes.forEach { m ->
                FilterChip(selected = mode == m.optString("value"), onClick = { applyMode(m.optString("value")) },
                    label = { Text(m.optString("label")) })
            }
        }
        modes.firstOrNull { it.optString("value") == mode }?.let { Hint(it.optString("hint")) }
        val shownKinds = when (mode) { "tiku" -> setOf("tiku"); "ai" -> setOf("ai"); "both" -> setOf("tiku", "ai"); else -> emptySet() }
        options.filter { it.optString("kind") in shownKinds }.forEach { o ->
            val v = o.optString("value")
            val index = picked.indexOf(v)
            Row(Modifier.fillMaxWidth().clickable {
                store(if (index >= 0) picked - v else picked + v)
            }, verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = index >= 0, onCheckedChange = null)
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f)) {
                    Text(o.optString("label") + if (index >= 0 && picked.size > 1) "（第 ${index + 1} 个查询）" else "")
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
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val scope = rememberCoroutineScope()
    val values = SettingsModel.values
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    val models = remember { mutableStateListOf<String>() }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        OutlinedButton(enabled = !busy, onClick = {
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
        }) { Text(if (busy) "正在获取…" else "获取可用模型") }
        if (error.isNotEmpty()) Text(error, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        if (models.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            models.forEach { m ->
                FilterChip(selected = values["tiku.model"] == m, onClick = { values["tiku.model"] = m }, label = { Text(m) })
            }
        }
    }
}
