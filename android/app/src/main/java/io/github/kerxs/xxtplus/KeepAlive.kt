package io.github.kerxs.xxtplus

import android.annotation.SuppressLint
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings

/**
 * Keeping the task alive in the background.
 *
 * What actually works system-wide is the foreground service + wake lock (TaskService) and the
 * battery-optimisation exemption below. Vendor "自启动 / 后台运行" switches have no public API:
 * we can only open the vendor page (when its activity exists on this ROM) and explain the steps.
 */
object KeepAlive {

    data class Vendor(val id: String, val name: String, val steps: List<String>)

    fun isIgnoringBatteryOptimizations(ctx: Context): Boolean =
        ctx.getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(ctx.packageName)

    @SuppressLint("BatteryLife")
    fun requestIgnoreBatteryOptimizations(ctx: Context) {
        val direct = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${ctx.packageName}"))
        if (!tryStart(ctx, direct)) tryStart(ctx, Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
    }

    fun vendor(): Vendor {
        val m = (Build.MANUFACTURER + " " + Build.BRAND).lowercase()
        return when {
            listOf("xiaomi", "redmi", "poco").any { it in m } -> Vendor("xiaomi", "小米 / Redmi（HyperOS、MIUI）", listOf(
                "安全中心 → 应用管理 → 权限 → 自启动管理：打开学习通PLUS",
                "设置 → 应用设置 → 学习通PLUS → 省电策略：选“无限制”",
                "最近任务里下拉（或长按）学习通PLUS卡片，点锁形图标锁定",
            ))
            "honor" in m -> Vendor("honor", "荣耀（MagicOS）", listOf(
                "设置 → 应用和服务 → 应用启动管理：关闭学习通PLUS的“自动管理”，打开允许自启动、关联启动、后台活动",
                "设置 → 电池 → 更多电池设置：打开“休眠时始终保持网络连接”",
                "最近任务里下拉学习通PLUS卡片锁定",
            ))
            "huawei" in m -> Vendor("huawei", "华为（EMUI、HarmonyOS 4 及以下）", listOf(
                "设置 → 应用和服务 → 应用启动管理：关闭学习通PLUS的“自动管理”，打开允许自启动、关联启动、后台活动",
                "设置 → 电池 → 更多电池设置：打开“休眠时始终保持网络连接”",
                "最近任务里下拉学习通PLUS卡片锁定",
                "注意：纯血鸿蒙（HarmonyOS NEXT）不能安装 APK",
            ))
            listOf("oppo", "oneplus", "realme").any { it in m } -> Vendor("oppo", "OPPO / 一加 / realme（ColorOS）", listOf(
                "设置 → 应用 → 自启动管理（或 应用管理 → 学习通PLUS）：允许自启动",
                "设置 → 电池 → 学习通PLUS：允许后台运行（或“完全允许后台行为”）",
                "最近任务里长按学习通PLUS卡片，选“锁定”",
            ))
            listOf("vivo", "iqoo").any { it in m } -> Vendor("vivo", "vivo / iQOO（OriginOS、Funtouch）", listOf(
                "i 管家 → 应用管理 → 权限管理 → 自启动：打开学习通PLUS",
                "设置 → 电池 → 后台耗电管理 → 学习通PLUS：选“允许后台高耗电”",
                "最近任务里下拉学习通PLUS卡片锁定",
            ))
            "samsung" in m -> Vendor("samsung", "三星（One UI）", listOf(
                "设置 → 应用程序 → 学习通PLUS → 电池：选“不受限制”",
                "设置 → 电池 → 后台使用限制：确认学习通PLUS不在“休眠应用”里",
            ))
            else -> Vendor("other", "其他品牌", listOf(
                "系统设置 → 应用 → 学习通PLUS → 电池：选“不受限制 / 允许后台活动”",
                "如果系统有“自启动”或“后台运行”管理，为学习通PLUS打开",
                "在最近任务里锁定学习通PLUS",
            ))
        }
    }

    private val autostartPages: Map<String, List<ComponentName>> = mapOf(
        "xiaomi" to listOf(
            ComponentName("com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity"),
        ),
        "honor" to listOf(
            ComponentName("com.hihonor.systemmanager", "com.hihonor.systemmanager.startupmgr.ui.StartupNormalAppListActivity"),
            ComponentName("com.huawei.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity"),
        ),
        "huawei" to listOf(
            ComponentName("com.huawei.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity"),
            ComponentName("com.huawei.systemmanager", "com.huawei.systemmanager.optimize.process.ProtectActivity"),
        ),
        "oppo" to listOf(
            ComponentName("com.coloros.safecenter", "com.coloros.safecenter.permission.startup.StartupAppListActivity"),
            ComponentName("com.coloros.safecenter", "com.coloros.safecenter.startupapp.StartupAppListActivity"),
            ComponentName("com.oplus.safecenter", "com.oplus.safecenter.permission.startup.StartupAppListActivity"),
        ),
        "vivo" to listOf(
            ComponentName("com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.BgStartUpManagerActivity"),
            ComponentName("com.iqoo.secure", "com.iqoo.secure.ui.phoneoptimize.BgStartUpManager"),
        ),
        "samsung" to listOf(
            ComponentName("com.samsung.android.lool", "com.samsung.android.sm.battery.ui.BatteryActivity"),
        ),
    )

    /** Opens the vendor's 自启动 page; falls back to this app's system settings page. */
    fun openAutostartSettings(ctx: Context): Boolean {
        for (component in autostartPages[vendor().id].orEmpty()) {
            if (tryStart(ctx, Intent().setComponent(component))) return true
        }
        return openAppDetails(ctx)
    }

    fun openAppDetails(ctx: Context): Boolean =
        tryStart(ctx, Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${ctx.packageName}")))

    fun openNotificationSettings(ctx: Context): Boolean =
        tryStart(ctx, Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, ctx.packageName))

    private fun tryStart(ctx: Context, intent: Intent): Boolean = try {
        ctx.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        true
    } catch (_: Exception) {
        false
    }
}
