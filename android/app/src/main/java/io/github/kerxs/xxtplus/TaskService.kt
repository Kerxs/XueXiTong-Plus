package io.github.kerxs.xxtplus

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.os.Process
import org.json.JSONObject
import java.util.ArrayDeque

/**
 * Foreground service in the :worker process that runs the shared Python task code.
 *
 * Keeps the task alive with the screen off: a foreground notification (暂停/继续, 停止) and a
 * partial wake lock held only while running. Events go to the UI process as package-private
 * broadcasts; the last few hundred are kept so a reopened UI can catch up (ACTION_SYNC).
 * 停止 kills this process, like the desktop app kills its worker.
 */
class TaskService : Service() {

    companion object {
        const val ACTION_START = "io.github.kerxs.xxtplus.START"
        const val ACTION_PAUSE = "io.github.kerxs.xxtplus.PAUSE"
        const val ACTION_RESUME = "io.github.kerxs.xxtplus.RESUME"
        const val ACTION_STOP = "io.github.kerxs.xxtplus.STOP"
        const val ACTION_ANSWER = "io.github.kerxs.xxtplus.ANSWER"
        const val ACTION_SYNC = "io.github.kerxs.xxtplus.SYNC"
        const val ACTION_EVENT = "io.github.kerxs.xxtplus.EVENT"
        const val EXTRA_TEXT = "text"
        const val EXTRA_ALERT = "alertOnFinish"
        const val EXTRA_JSON = "json"
        const val EXTRA_SNAPSHOT = "snapshot"

        const val CHANNEL_TASK = "task"
        const val CHANNEL_ALERT = "alert"
        private const val NOTIFY_TASK = 1
        private const val NOTIFY_ALERT = 2
        private const val NOTIFY_PUSH = 3
        private const val HISTORY = 400
        // A run the system killed is started again (START_STICKY) at most this many times.
        private const val MAX_RESTARTS = 5
        // No output at all for this long while running (not paused, not waiting for the user):
        // the task is stuck; end this process so START_STICKY starts the run again.
        private const val HANG_MS = 20 * 60 * 1000L

        /** Present while a run is active; left behind when the system kills the :worker process. */
        fun runFile(ctx: Context) = java.io.File(ctx.filesDir, "run.json")

        fun pendingRun(ctx: Context): Boolean = runFile(ctx).exists()

        fun send(ctx: Context, action: String, text: String? = null) {
            val intent = Intent(ctx, TaskService::class.java).setAction(action)
            if (text != null) intent.putExtra(EXTRA_TEXT, text)
            if (action == ACTION_START) {
                // Read here (UI process): SharedPreferences are not shared live with the :worker process.
                intent.putExtra(EXTRA_ALERT, UiPrefs.alertOnFinish)
                ctx.startForegroundService(intent)
            } else ctx.startService(intent)
        }

        fun createChannels(ctx: Context) {
            val nm = ctx.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(NotificationChannel(
                CHANNEL_TASK, ctx.getString(R.string.channel_task), NotificationManager.IMPORTANCE_LOW,
            ).apply { description = ctx.getString(R.string.channel_task_desc); setShowBadge(false) })
            nm.createNotificationChannel(NotificationChannel(
                CHANNEL_ALERT, ctx.getString(R.string.channel_alert), NotificationManager.IMPORTANCE_HIGH,
            ).apply { description = ctx.getString(R.string.channel_alert_desc) })
        }
    }

    private val main = Handler(Looper.getMainLooper())
    private val history = ArrayDeque<String>()
    private var wakeLock: PowerManager.WakeLock? = null
    // Keeps Wi-Fi from dozing with the screen off (otherwise requests stall until the screen is on).
    private var wifiLock: android.net.wifi.WifiManager.WifiLock? = null
    private var networkCallback: android.net.ConnectivityManager.NetworkCallback? = null
    private var worker: Thread? = null
    private var paused = false
    private var course = ""
    private var chapter = ""
    private var progress = ""
    private var lastNotify = 0L
    private var startedAt = 0L
    private var alertOnFinish = true
    // Run time without pauses (desktop 运行时长 does not count paused time).
    private var activeMs = 0L
    private var resumedAt = 0L

    private fun activeNow() = activeMs + if (!paused && resumedAt > 0) System.currentTimeMillis() - resumedAt else 0L

    private fun stateJson(running: Boolean) = JSONObject().put("type", "state").put("running", running)
        .put("paused", running && paused).put("startedAt", startedAt)
        .put("activeMs", if (running) activeNow() else 0L).put("at", System.currentTimeMillis()).toString()

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannels(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent == null) {
            // Restarted by the system after it killed this process (START_STICKY).
            restartAfterKill()
            return if (worker != null) START_STICKY else START_NOT_STICKY
        }
        when (intent.action) {
            ACTION_START -> {
                alertOnFinish = intent.getBooleanExtra(EXTRA_ALERT, true)
                if (worker == null) restarts = 0
                start()
            }
            ACTION_PAUSE -> setPaused(true)
            ACTION_RESUME -> setPaused(false)
            ACTION_STOP -> finish(stopped = true, code = 0)
            ACTION_ANSWER -> answer(intent.getStringExtra(EXTRA_TEXT) ?: "")
            ACTION_SYNC -> sync()
        }
        // While a run is active the system restarts this service after killing the process
        // (省电策略 / 清理后台), and the run continues: the platform keeps the watch progress.
        return if (worker != null) START_STICKY else START_NOT_STICKY
    }

    private var restarts = 0

    private fun restartAfterKill() {
        val saved = runCatching { JSONObject(runFile(this).readText()) }.getOrNull()
        if (saved == null) { stopSelf(); return }
        restarts = saved.optInt("restarts") + 1
        if (restarts > MAX_RESTARTS) {
            runFile(this).delete()
            alert("任务已停止", "任务进程被系统结束了 $MAX_RESTARTS 次。请在“权限设置”里允许后台运行后重新开始。")
            stopSelf()
            return
        }
        alertOnFinish = saved.optBoolean("alert", true)
        if (!start()) return
        record(JSONObject().put("type", "log").put("level", "WARNING")
            .put("message", "任务进程被系统结束，已自动重新开始（第 $restarts 次），学习通会保留已看的进度")
            .put("time", "").toString())
    }

    private fun saveRun() {
        runCatching {
            runFile(this).writeText(JSONObject().put("alert", alertOnFinish).put("restarts", restarts)
                .put("at", System.currentTimeMillis()).toString())
        }
    }

    /** Returns false when Android does not allow the foreground service right now. */
    private fun start(): Boolean {
        try {
            startForegroundCompat(buildNotification())
        } catch (e: Exception) {
            // Android 12+: a foreground service cannot start from the background unless the app is
            // exempt from battery optimisation. Keep run.json: the app offers to continue when opened.
            android.util.Log.w("TaskService", "cannot start in the foreground: ${e.javaClass.simpleName}")
            stopSelf()
            return false
        }
        if (worker != null) return true
        saveRun()
        PythonBridge.pauseFile(this).delete()
        paused = false
        startedAt = System.currentTimeMillis()
        activeMs = 0L
        resumedAt = startedAt
        val pm = getSystemService(PowerManager::class.java)
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "xxtplus:task").apply {
            setReferenceCounted(false)
            acquire(24 * 60 * 60 * 1000L)
        }
        @Suppress("DEPRECATION")
        wifiLock = runCatching {
            applicationContext.getSystemService(android.net.wifi.WifiManager::class.java)
                .createWifiLock(android.net.wifi.WifiManager.WIFI_MODE_FULL_HIGH_PERF, "xxtplus:task")
                .apply { setReferenceCounted(false); acquire() }
        }.getOrNull()
        watchNetwork()
        lastEventAt = System.currentTimeMillis()
        waitingInput = false
        main.removeCallbacks(hangCheck)
        main.postDelayed(hangCheck, 60_000)
        record(stateJson(true))
        val sink = Sink()
        worker = Thread({
            val code = try {
                PythonBridge.module(this).callAttr(
                    "run",
                    PythonBridge.configFile(this).absolutePath,
                    PythonBridge.dataDir(this).absolutePath,
                    PythonBridge.pauseFile(this).absolutePath,
                    sink,
                ).toInt()
            } catch (t: Throwable) {
                sink.emit(JSONObject().put("type", "log").put("level", "ERROR")
                    .put("message", "运行组件出错：${t.message}").put("time", "").toString())
                1
            }
            main.post { finish(stopped = false, code = code) }
        }, "xxtplus-task").apply { isDaemon = true; start() }
        return true
    }

    /** Called from Python (any thread) with one parsed output event as JSON. */
    inner class Sink {
        fun emit(json: String) {
            main.post { onEvent(json) }
        }
    }

    private var lastEventAt = 0L
    private var waitingInput = false

    private val hangCheck = object : Runnable {
        override fun run() {
            if (worker == null) return
            val silent = System.currentTimeMillis() - lastEventAt
            if (!paused && !waitingInput && silent > HANG_MS) {
                record(JSONObject().put("type", "log").put("level", "WARNING")
                    .put("message", "任务已经 ${silent / 60000} 分钟没有任何输出，可能卡住了，正在重新开始…")
                    .put("time", "").toString())
                // run.json stays: the system restarts this service and the run continues.
                main.postDelayed({ Process.killProcess(Process.myPid()) }, 500)
                return
            }
            main.postDelayed(this, 60_000)
        }
    }

    private fun onEvent(json: String) {
        record(json)
        lastEventAt = System.currentTimeMillis()
        val event = runCatching { JSONObject(json) }.getOrNull() ?: return
        when (event.optString("type")) {
            "activity" -> when (event.optString("kind")) {
                "course" -> course = event.optString("value")
                "chapter" -> chapter = event.optString("value")
            }
            "progress" -> progress = "${event.optString("name")}  ${event.optInt("percent")}%"
            "prompt" -> { waitingInput = true; alert("需要你确认", event.optString("text")) }
            "courselist" -> { waitingInput = true; alert("请选择要学习的课程", "打开学习通 PLUS 选择课程后继续") }
            "notify" -> pushNotification(event.optString("text"))
        }
        val now = System.currentTimeMillis()
        if (now - lastNotify > 1000) {
            lastNotify = now
            notifyTask()
        }
    }

    private fun record(json: String) {
        history.addLast(json)
        while (history.size > HISTORY) history.removeFirst()
        sendBroadcast(Intent(ACTION_EVENT).setPackage(packageName).putExtra(EXTRA_JSON, json))
    }

    private fun sync() {
        if (worker == null) {
            // Started only to answer SYNC: nothing is running here.
            sendBroadcast(Intent(ACTION_EVENT).setPackage(packageName).putExtra(EXTRA_JSON,
                JSONObject().put("type", "state").put("running", false).put("paused", false).toString()))
            stopSelf()
            return
        }
        val state = stateJson(true)
        sendBroadcast(Intent(ACTION_EVENT).setPackage(packageName)
            .putStringArrayListExtra(EXTRA_SNAPSHOT, ArrayList(history + state)))
    }

    private fun answer(text: String) {
        if (worker == null) return
        waitingInput = false
        lastEventAt = System.currentTimeMillis()
        PythonBridge.module(this).callAttr("answer", text)
        getSystemService(NotificationManager::class.java).cancel(NOTIFY_ALERT)
    }

    private fun setPaused(value: Boolean) {
        if (worker == null) return
        val flag = PythonBridge.pauseFile(this)
        if (value == paused) return
        if (value) flag.writeText("paused") else flag.delete()
        if (value) activeMs = activeNow() else { resumedAt = System.currentTimeMillis(); lastEventAt = resumedAt }
        paused = value
        // The wake lock is kept while paused: a paused run is resumed from the notification
        // and should continue at once; it is released on stop / end.
        record(stateJson(true))
        notifyTask()
    }

    private fun finish(stopped: Boolean, code: Int) {
        PythonBridge.pauseFile(this).delete()
        runFile(this).delete()     // ended on purpose: nothing to restart
        main.removeCallbacks(hangCheck)
        val was = worker != null
        worker = null
        releaseLocks()
        record(JSONObject().put("type", "finished").put("stopped", stopped).put("code", code).toString())
        record(stateJson(false))
        // Skip the end alert when 本机通知 has just said the same thing.
        if (was && !stopped && alertOnFinish && System.currentTimeMillis() - lastPush > 10_000) {
            alert(if (code == 0) "任务已结束" else "任务异常结束", if (code == 0) "所有课程任务已处理完" else "打开应用查看日志")
        }
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
        // Python threads cannot be interrupted; end the process like the desktop app ends its worker.
        if (was) main.postDelayed({ Process.killProcess(Process.myPid()) }, 500)
    }

    private fun startForegroundCompat(notification: Notification) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIFY_TASK, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIFY_TASK, notification)
        }
    }

    private fun notifyTask() {
        if (worker == null) return
        getSystemService(NotificationManager::class.java).notify(NOTIFY_TASK, buildNotification())
    }

    private fun servicePending(action: String, code: Int) = PendingIntent.getService(
        this, code, Intent(this, TaskService::class.java).setAction(action),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

    private fun openApp() = PendingIntent.getActivity(
        this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

    private fun buildNotification(): Notification {
        val title = when {
            paused -> "已暂停"
            course.isNotEmpty() -> "正在学习：$course"
            else -> "正在运行"
        }
        val text = listOf(chapter, progress).filter { it.isNotEmpty() }.joinToString(" · ").ifEmpty { "正在登录和读取课程…" }
        val toggle = if (paused) {
            Notification.Action.Builder(null, "继续", servicePending(ACTION_RESUME, 2)).build()
        } else {
            Notification.Action.Builder(null, "暂停", servicePending(ACTION_PAUSE, 1)).build()
        }
        return Notification.Builder(this, CHANNEL_TASK)
            .setSmallIcon(R.drawable.ic_notify)
            .setContentTitle(title)
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(openApp())
            .addAction(toggle)
            .addAction(Notification.Action.Builder(null, "停止", servicePending(ACTION_STOP, 3)).build())
            .build()
    }

    private var lastPush = 0L

    /** 推送服务 = 本机通知: the task's own messages (all done, errors) as system notifications. */
    private fun pushNotification(raw: String) {
        val text = raw.removePrefix("chaoxing :").trim()
        val firstLine = text.lineSequence().firstOrNull().orEmpty()
        lastPush = System.currentTimeMillis()
        val n = Notification.Builder(this, CHANNEL_ALERT)
            .setSmallIcon(R.drawable.ic_notify)
            .setContentTitle("学习通 PLUS")
            .setContentText(firstLine)
            .setStyle(Notification.BigTextStyle().bigText(text.take(1500)))
            .setAutoCancel(true)
            .setContentIntent(openApp())
            .build()
        getSystemService(NotificationManager::class.java).notify(NOTIFY_PUSH, n)
    }

    private fun alert(title: String, text: String) {
        val n = Notification.Builder(this, CHANNEL_ALERT)
            .setSmallIcon(R.drawable.ic_notify)
            .setContentTitle(title)
            .setContentText(text)
            .setAutoCancel(true)
            .setContentIntent(openApp())
            .build()
        getSystemService(NotificationManager::class.java).notify(NOTIFY_ALERT, n)
    }

    private fun releaseLocks() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        wifiLock?.let { if (it.isHeld) it.release() }
        wifiLock = null
        networkCallback?.let { cb ->
            runCatching { getSystemService(android.net.ConnectivityManager::class.java).unregisterNetworkCallback(cb) }
        }
        networkCallback = null
    }

    /** Logs network loss / return; the task itself waits for the network (api/net.py). */
    private fun watchNetwork() {
        if (networkCallback != null) return
        val cm = getSystemService(android.net.ConnectivityManager::class.java)
        var lost = false
        val cb = object : android.net.ConnectivityManager.NetworkCallback() {
            override fun onLost(network: android.net.Network) {
                main.post {
                    if (worker == null || lost) return@post
                    lost = true
                    record(JSONObject().put("type", "log").put("level", "WARNING")
                        .put("message", "手机网络已断开，任务会在网络恢复后继续").put("time", "").toString())
                }
            }

            override fun onAvailable(network: android.net.Network) {
                main.post {
                    if (worker == null || !lost) return@post
                    lost = false
                    record(JSONObject().put("type", "log").put("level", "INFO")
                        .put("message", "手机网络已恢复").put("time", "").toString())
                }
            }
        }
        if (runCatching { cm.registerDefaultNetworkCallback(cb) }.isSuccess) networkCallback = cb
    }

    override fun onDestroy() {
        releaseLocks()
        super.onDestroy()
    }
}
