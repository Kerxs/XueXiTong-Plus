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
data class ManualTask(val course: String, val chapter: String, val kind: String, val name: String)

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
    /** Run time without pauses, as of [activeAt] (from the service). */
    var activeMs by mutableLongStateOf(0L)
    var activeAt by mutableLongStateOf(0L)
    /** How the last run ended: "" (none yet) | done | stopped | error — like the desktop status. */
    var lastResult by mutableStateOf("")

    /** Content the program does not do (api/manual.py): documents, reading, surveys … */
    val manualTasks = mutableStateListOf<ManualTask>()
    var showManualDialog by mutableStateOf(false)

    /** System notification permission (refreshed by MainActivity on start / resume). */
    var notificationsAllowed by mutableStateOf(true)

    /** 本机通知 (with permission) or a push service with an address: the task process can reach the user. */
    fun pushConfigured(): Boolean {
        val provider = SettingsModel.values["notification.provider"].orEmpty()
        if (provider == "Local") return notificationsAllowed
        return provider.isNotEmpty() && SettingsModel.values["notification.url"].orEmpty().isNotBlank()
    }

    fun elapsedSeconds(now: Long): Long =
        if (!running) 0 else (activeMs + if (paused) 0 else (now - activeAt).coerceAtLeast(0)) / 1000

    /** Position of the previewed video in the task, seconds (-1 unknown): the preview starts there. */
    fun videoPosition(): Double {
        val p = progress[videoTitle] ?: progress.values.firstOrNull { videoTitle.isNotEmpty() && it.name.contains(videoTitle) }
            ?: return -1.0
        val parts = p.done.split(':').mapNotNull { it.toDoubleOrNull() }
        if (parts.isEmpty()) return -1.0
        return parts.fold(0.0) { acc, v -> acc * 60 + v }
    }
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

    /** The :worker process disappeared (killed by the system / a cleaner) without saying so. */
    fun workerLost(ctx: Context) {
        running = false
        paused = false
        prompt = null
        courses = null
        lastResult = "error"
        logs.add(LogLine("ERROR", if (TaskService.pendingRun(ctx))
            "任务进程被系统结束（省电策略或清理后台），系统允许时会自动重新开始；也可以直接点“开始运行”继续，学习通会保留已看的进度。"
        else "任务进程已被系统结束（可能是省电策略或清理后台）。请检查“权限”设置后重新开始运行，学习通会保留已看的进度。", ""))
    }

    fun reset() {
        logs.clear(); progress.clear(); questions.clear(); RevealedAnswers.clear(); manualTasks.clear(); showManualDialog = false
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
                if (running) {
                    lastResult = ""
                    activeMs = e.optLong("activeMs")
                    activeAt = e.optLong("at", System.currentTimeMillis())
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
            "manualtask" -> {
                val task = ManualTask(e.optString("course"), e.optString("chapter"), e.optString("kind"), e.optString("name"))
                if (task !in manualTasks) {
                    manualTasks.add(task)
                    if (!pushConfigured()) showManualDialog = true   // no notification: tell the user in the app
                }
            }
            "courselist" -> {
                val arr = e.optJSONArray("courses") ?: JSONArray()
                courses = (0 until arr.length()).map {
                    val c = arr.getJSONObject(it)
                    CourseItem(c.optString("courseId"), c.optString("clazzId"), c.optString("title"))
                }
            }
            "finished" -> {
                val stopped = e.optBoolean("stopped")
                lastResult = when { stopped -> "stopped"; e.optInt("code") == 0 -> "done"; else -> "error" }
                addLog(if (stopped || e.optInt("code") == 0) "INFO" else "ERROR",
                    if (stopped) "已停止" else if (e.optInt("code") == 0) "运行结束" else "运行异常结束（代码 ${e.optInt("code")}）", "")
            }
        }
    }

    private fun applyWork(data: JSONObject) {
        val phase = data.optString("phase")
        // A submitted / saved 章节检测 counts as a finished task, like on the desktop.
        if ((phase == "submitted" || phase == "saved") && workPhase != phase) finishedTasks += 1
        workPhase = phase
        workTitle = data.optString("title", workTitle)
        workCoverRate = data.optInt("cover_rate", workCoverRate)
        val arr = data.optJSONArray("questions") ?: return
        questions.clear(); RevealedAnswers.clear()
        for (i in 0 until arr.length()) {
            val q = arr.getJSONObject(i)
            questions.add(Question(
                q.optInt("index", i + 1), q.optString("type"), q.optString("title"), q.optString("options"),
                q.optString("answer"), q.optString("source"), q.optString("origin"),
            ))
        }
    }
}
