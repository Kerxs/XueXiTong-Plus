package io.github.kerxs.xxtplus

import android.app.ActivityManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import org.json.JSONArray
import org.json.JSONObject

data class LogLine(val level: String, val message: String, val time: String)
data class Progress(val name: String, val percent: Int, val done: String, val total: String)
data class CourseItem(val courseId: String, val clazzId: String, val title: String)
data class Question(
    val index: Int, val type: String, val title: String, val options: String,
    val answer: String, val source: String, val origin: String,
)

/** UI-process view of the run, fed by TaskService broadcasts (same events as the desktop parser). */
object RunState {
    private const val MAX_LOG = 1200

    var running by mutableStateOf(false)
    var paused by mutableStateOf(false)
    var startedAt by mutableLongStateOf(0L)
    var course by mutableStateOf("")
    var chapter by mutableStateOf("")
    var finishedTasks by mutableIntStateOf(0)
    val logs = mutableStateListOf<LogLine>()
    val progress = mutableStateMapOf<String, Progress>()
    var videoSource by mutableStateOf("")
    var videoTitle by mutableStateOf("")
    var workPhase by mutableStateOf("")
    var workTitle by mutableStateOf("")
    var workCoverRate by mutableIntStateOf(0)
    val questions = mutableStateListOf<Question>()
    var prompt by mutableStateOf<String?>(null)
    var courses by mutableStateOf<List<CourseItem>?>(null)

    val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            intent.getStringArrayListExtra(TaskService.EXTRA_SNAPSHOT)?.let { list ->
                reset()
                // The last entry is the current state; take its run id first so replaying
                // the history does not look like a new run.
                startedAt = list.lastOrNull()?.let { runCatching { JSONObject(it).optLong("startedAt") }.getOrNull() } ?: 0L
                list.forEach { apply(it) }
                return
            }
            intent.getStringExtra(TaskService.EXTRA_JSON)?.let { apply(it) }
        }
    }

    fun workerAlive(ctx: Context): Boolean {
        val name = ctx.packageName + ":worker"
        val am = ctx.getSystemService(ActivityManager::class.java)
        return am.runningAppProcesses?.any { it.processName == name } == true
    }

    /** Catch up with a run that was started before this UI process (or while it was closed). */
    fun sync(ctx: Context) {
        if (workerAlive(ctx)) {
            TaskService.send(ctx, TaskService.ACTION_SYNC)
        } else {
            running = false
            paused = false
            prompt = null
            courses = null
        }
    }

    fun reset() {
        logs.clear(); progress.clear(); questions.clear()
        course = ""; chapter = ""; finishedTasks = 0
        videoSource = ""; videoTitle = ""; workPhase = ""; workTitle = ""; workCoverRate = 0
        prompt = null; courses = null
    }

    private fun addLog(level: String, message: String, time: String) {
        logs.add(LogLine(level, message, time))
        if (logs.size > MAX_LOG) logs.removeRange(0, logs.size - MAX_LOG)
    }

    fun apply(json: String) {
        val e = runCatching { JSONObject(json) }.getOrNull() ?: return
        when (e.optString("type")) {
            "state" -> {
                running = e.optBoolean("running")
                paused = e.optBoolean("paused")
                if (running && e.has("startedAt") && e.optLong("startedAt") != startedAt) {
                    reset()  // a new run
                    startedAt = e.optLong("startedAt")
                }
                if (!running) { prompt = null; courses = null }
            }
            "log" -> addLog(e.optString("level", "INFO"), e.optString("message"), e.optString("time"))
            "activity" -> when (e.optString("kind")) {
                "course" -> course = e.optString("value")
                "chapter" -> chapter = e.optString("value")
                "task_finished" -> finishedTasks += 1
            }
            "progress" -> {
                val p = Progress(e.optString("name"), e.optInt("percent"), e.optString("done"), e.optString("total"))
                progress[p.name] = p
            }
            "videopreview" -> if (e.optBoolean("valid", true)) {
                videoSource = e.optString("source")
                videoTitle = e.optString("title")
            }
            "workpreview" -> if (e.optBoolean("valid", true)) applyWork(e.optJSONObject("data") ?: JSONObject())
            "prompt" -> prompt = e.optString("text")
            "courselist" -> {
                val arr = e.optJSONArray("courses") ?: JSONArray()
                courses = (0 until arr.length()).map {
                    val c = arr.getJSONObject(it)
                    CourseItem(c.optString("courseId"), c.optString("clazzId"), c.optString("title"))
                }
            }
            "finished" -> {
                val stopped = e.optBoolean("stopped")
                addLog(if (stopped || e.optInt("code") == 0) "INFO" else "ERROR",
                    if (stopped) "已停止" else if (e.optInt("code") == 0) "运行结束" else "运行异常结束（代码 ${e.optInt("code")}）", "")
            }
        }
    }

    private fun applyWork(data: JSONObject) {
        workPhase = data.optString("phase")
        workTitle = data.optString("title", workTitle)
        workCoverRate = data.optInt("cover_rate", workCoverRate)
        val arr = data.optJSONArray("questions") ?: return
        questions.clear()
        for (i in 0 until arr.length()) {
            val q = arr.getJSONObject(i)
            questions.add(Question(
                q.optInt("index", i + 1), q.optString("type"), q.optString("title"), q.optString("options"),
                q.optString("answer"), q.optString("source"), q.optString("origin"),
            ))
        }
    }
}
