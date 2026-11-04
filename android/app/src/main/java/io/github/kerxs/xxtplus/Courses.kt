package io.github.kerxs.xxtplus

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.toMutableStateList
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/** 识别课程, as on the desktop: log in, read the course list, pick courses -> common.course_list. */
object Courses {
    var state by mutableStateOf("idle")      // idle | running | done | error
    var error by mutableStateOf("")
    var known by mutableStateOf<List<CourseItem>>(emptyList())
    var showPicker by mutableStateOf(false)

    private fun prefs(ctx: Context) = ctx.getSharedPreferences("app", Context.MODE_PRIVATE)

    fun load(ctx: Context) {
        known = runCatching {
            val arr = JSONArray(prefs(ctx).getString("courses_known", "[]"))
            (0 until arr.length()).map { arr.getJSONObject(it) }
                .map { CourseItem(it.optString("courseId"), it.optString("clazzId"), it.optString("title")) }
                .filter { it.courseId.isNotEmpty() }
        }.getOrDefault(emptyList())
    }

    /** Titles of the courses in course_list (from the last recognition). */
    fun selectedNames(): List<String> {
        val ids = (SettingsModel.values["common.course_list"] ?: "").split(",").map { it.trim() }.filter { it.isNotEmpty() }
        val names = known.associate { it.courseId to it.title }
        return ids.mapNotNull { names[it]?.takeIf { n -> n.isNotEmpty() } }
    }

    suspend fun detect(ctx: Context): String? {
        if (state == "running" || RunState.running) return null
        SettingsModel.save(ctx)
        state = "running"; error = ""
        val result = withContext(Dispatchers.IO) {
            runCatching { JSONObject(PythonBridge.listCourses(ctx)) }
                .getOrElse { JSONObject().put("ok", false).put("error", it.message ?: "识别失败") }
        }
        if (!result.optBoolean("ok")) {
            state = "error"
            error = result.optString("error", "识别失败")
            return "识别课程失败：$error"
        }
        val arr = result.optJSONArray("courses") ?: JSONArray()
        known = (0 until arr.length()).map { arr.getJSONObject(it) }
            .map { CourseItem(it.optString("courseId"), it.optString("clazzId"), it.optString("title")) }
        prefs(ctx).edit().putString("courses_known", arr.toString()).apply()
        state = "done"
        showPicker = true
        return "识别到 ${known.size} 门课程"
    }

    fun choose(ctx: Context, ids: List<String>) {
        SettingsModel.values["common.course_list"] = ids.distinct().joinToString(",")
    }
}

/** Pick courses after 识别课程; nothing ticked = all courses (desktop CoursePickerDialog). */
@Composable
fun CoursePickerDialog(onDone: (List<String>?) -> Unit) {
    val c = X.colors
    val current = (SettingsModel.values["common.course_list"] ?: "").split(",").map { it.trim() }.toSet()
    val courses = Courses.known
    val checked = remember(courses) { courses.map { it.courseId in current }.toMutableStateList() }
    AlertDialog(
        onDismissRequest = { onDone(null) },
        containerColor = c.surface, titleContentColor = c.text, textContentColor = c.text,
        shape = RoundedCornerShape(Dimens.radiusLarge),
        title = { Text("选择要学习的课程") },
        text = {
            Column(Modifier.heightIn(max = 440.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("不勾选则学习全部课程。同一课程有多个班级时会分别完成。", color = c.muted, fontSize = 12.sp)
                courses.forEachIndexed { i, course ->
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius))
                            .background(if (checked[i]) c.accentSoft else c.surfaceAlt)
                            .border(1.dp, if (checked[i]) c.accent else c.border, RoundedCornerShape(Dimens.radius))
                            .clickable { checked[i] = !checked[i] }.padding(horizontal = 8.dp, vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Checkbox(checked = checked[i], onCheckedChange = null, colors = checkboxColors())
                        Spacer(Modifier.width(8.dp))
                        Column {
                            Text(course.title, color = c.text, fontSize = 14.sp)
                            Text("ID ${course.courseId}", color = c.faint, fontSize = 11.sp)
                        }
                    }
                }
            }
        },
        confirmButton = {
            XButton("确定", { onDone(courses.filterIndexed { i, _ -> checked[i] }.map { it.courseId }) }, kind = Kind.Primary)
        },
        dismissButton = { XButton("取消", { onDone(null) }, kind = Kind.Ghost) },
    )
}
