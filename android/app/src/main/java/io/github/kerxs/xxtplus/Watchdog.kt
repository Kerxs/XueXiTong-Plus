package io.github.kerxs.xxtplus

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.SystemClock

/**
 * Brings a run back after the system ended the task process.
 *
 * TaskService asks for that itself (START_STICKY), but many phones (小米、华为、OPPO、vivo …) do not
 * restart a service they cleaned up. While a run is active an alarm fires every few minutes — also
 * during the power-saving sleep — in the :worker process: when the task is not there any more and
 * the run was not ended on purpose (run.json is still there), it is started again.
 */
class Watchdog : BroadcastReceiver() {

    override fun onReceive(ctx: Context, intent: Intent?) {
        if (!TaskService.pendingRun(ctx)) return          // ended on purpose: nothing to watch
        schedule(ctx)
        if (TaskService.alive) return                     // this is the task's process and it is running
        try {
            ctx.startForegroundService(Intent(ctx, TaskService::class.java).setAction(TaskService.ACTION_REVIVE))
        } catch (e: Exception) {
            // Android 12+: not allowed from the background unless the app is exempt from battery
            // optimisation. run.json stays: the app offers to continue when it is opened.
            android.util.Log.w("Watchdog", "cannot restart the run: ${e.javaClass.simpleName}")
        }
    }

    companion object {
        private const val EVERY_MS = 10 * 60 * 1000L

        private fun pending(ctx: Context) = PendingIntent.getBroadcast(
            ctx, 7, Intent(ctx, Watchdog::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        fun schedule(ctx: Context, inMs: Long = EVERY_MS) {
            runCatching {
                ctx.getSystemService(AlarmManager::class.java).setAndAllowWhileIdle(
                    AlarmManager.ELAPSED_REALTIME_WAKEUP, SystemClock.elapsedRealtime() + inMs, pending(ctx),
                )
            }
        }

        fun cancel(ctx: Context) {
            runCatching { ctx.getSystemService(AlarmManager::class.java).cancel(pending(ctx)) }
        }
    }
}
