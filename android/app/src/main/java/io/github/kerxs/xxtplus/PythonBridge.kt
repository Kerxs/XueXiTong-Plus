package io.github.kerxs.xxtplus

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File

/**
 * Chaquopy entry points. Both the UI process (settings) and the :worker process (the task)
 * start their own Python; the shared code is the same as the desktop app's (see app/build.gradle.kts).
 */
object PythonBridge {
    private const val MODULE = "xxtplus_android"
    private val assetFiles = listOf("resource/font_map_table.json", "config_template.ini")

    @Volatile private var ready = false

    fun configFile(ctx: Context) = File(ctx.filesDir, "config.ini")
    fun templateFile(ctx: Context) = File(ctx.filesDir, "config_template.ini")
    fun dataDir(ctx: Context) = File(ctx.filesDir, "data")
    fun pauseFile(ctx: Context) = File(ctx.filesDir, "pause.flag")

    /** The bridge module; starts Python on first use. Call off the main thread: the first start is slow. */
    @Synchronized
    fun module(ctx: Context): PyObject {
        val app = ctx.applicationContext
        if (!Python.isStarted()) Python.start(AndroidPlatform(app))
        val module = Python.getInstance().getModule(MODULE)
        if (!ready) {
            copyAssets(app)
            module.callAttr("setup", app.filesDir.absolutePath)
            ready = true
        }
        return module
    }

    /** Data files the task code opens by path; refreshed whenever the APK changes. */
    private fun copyAssets(ctx: Context) {
        val stamp = File(ctx.filesDir, ".assets-version")
        val version = ctx.packageManager.getPackageInfo(ctx.packageName, 0).lastUpdateTime.toString()
        if (stamp.exists() && stamp.readText() == version && assetFiles.all { File(ctx.filesDir, it).exists() }) return
        for (path in assetFiles) {
            val target = File(ctx.filesDir, path)
            target.parentFile?.mkdirs()
            ctx.assets.open(path).use { input -> target.outputStream().use { input.copyTo(it) } }
        }
        stamp.writeText(version)
    }

    fun settingsSchema(ctx: Context): String = module(ctx).callAttr("settings_schema").toString()

    fun loadSettings(ctx: Context): String =
        module(ctx).callAttr("load_settings", configFile(ctx).absolutePath, templateFile(ctx).absolutePath).toString()

    fun saveSettings(ctx: Context, valuesJson: String) {
        module(ctx).callAttr("save_settings", configFile(ctx).absolutePath, templateFile(ctx).absolutePath, valuesJson)
    }

    fun setupProblem(ctx: Context, valuesJson: String): String =
        module(ctx).callAttr("setup_problem", valuesJson).toString()

    fun listModels(ctx: Context, endpoint: String, key: String, proxy: String): String =
        module(ctx).callAttr("list_models", endpoint, key, proxy).toString()
}
