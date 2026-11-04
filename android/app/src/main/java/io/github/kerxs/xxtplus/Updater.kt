package io.github.kerxs.xxtplus

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * 检查更新, like the desktop ui/updater.py: the latest GitHub release of [REPO], its .apk asset,
 * downloaded to the app cache and checked against the SHA-256 digest GitHub publishes, then
 * handed to the system installer (which asks the user to confirm).
 */
object Updater {
    const val REPO = "Kerxs/XueXiTong-Plus"

    data class Release(val version: String, val notes: String, val url: String, val name: String,
                       val size: Long, val digest: String, val page: String)

    // UI state (the update dialog and the 设置 → 检查更新 page read these)
    var state by mutableStateOf("idle")   // idle | checking | latest | available | downloading | ready | error
    var release by mutableStateOf<Release?>(null)
    var error by mutableStateOf("")
    var progress by mutableFloatStateOf(0f)
    var showDialog by mutableStateOf(false)

    fun currentVersion(ctx: Context): String =
        ctx.packageManager.getPackageInfo(ctx.packageName, 0).versionName ?: "0"

    /** Dotted versions compared numerically: 1.10.0 > 1.9.2. */
    fun newer(candidate: String, current: String): Boolean {
        val a = candidate.trim().removePrefix("v").split('.').map { it.takeWhile(Char::isDigit).toIntOrNull() ?: 0 }
        val b = current.trim().removePrefix("v").split('.').map { it.takeWhile(Char::isDigit).toIntOrNull() ?: 0 }
        for (i in 0 until maxOf(a.size, b.size)) {
            val x = a.getOrElse(i) { 0 }; val y = b.getOrElse(i) { 0 }
            if (x != y) return x > y
        }
        return false
    }

    private fun get(url: String): HttpURLConnection = (URL(url).openConnection() as HttpURLConnection).apply {
        connectTimeout = 15_000
        readTimeout = 30_000
        setRequestProperty("Accept", "application/vnd.github+json")
        setRequestProperty("User-Agent", "XueXiTong-Plus-Android")
    }

    /** [quiet]: the automatic check on start only shows the dialog when there is an update. */
    suspend fun check(ctx: Context, quiet: Boolean) {
        if (state == "checking" || state == "downloading") return
        state = "checking"; error = ""
        try {
            val json = withContext(Dispatchers.IO) {
                val conn = get("https://api.github.com/repos/$REPO/releases/latest")
                try {
                    if (conn.responseCode != 200) throw IllegalStateException("GitHub 返回 ${conn.responseCode}")
                    JSONObject(conn.inputStream.bufferedReader().readText())
                } finally { conn.disconnect() }
            }
            val version = json.optString("tag_name").removePrefix("v")
            val assets = json.optJSONArray("assets")
            var apk: JSONObject? = null
            for (i in 0 until (assets?.length() ?: 0)) {
                val a = assets!!.getJSONObject(i)
                if (a.optString("name").lowercase().endsWith(".apk")) { apk = a; break }
            }
            if (apk == null) {
                state = "latest"
                if (!quiet) { error = "最新版本 $version 没有提供安卓安装包"; showDialog = true }
                return
            }
            release = Release(version, json.optString("body").trim(), apk.optString("browser_download_url"),
                apk.optString("name"), apk.optLong("size"), apk.optString("digest"), json.optString("html_url"))
            state = if (newer(version, currentVersion(ctx))) "available" else "latest"
            if (state == "available" || !quiet) showDialog = true
        } catch (e: Exception) {
            state = "error"
            error = "检查更新失败：${e.message ?: e.javaClass.simpleName}"
            if (!quiet) showDialog = true
        }
    }

    suspend fun downloadAndInstall(ctx: Context) {
        val rel = release ?: return
        state = "downloading"; progress = 0f; error = ""
        try {
            val file = withContext(Dispatchers.IO) {
                val dir = File(ctx.cacheDir, "update").apply { mkdirs(); listFiles()?.forEach { it.delete() } }
                val target = File(dir, rel.name.ifEmpty { "update.apk" })
                // Written as .part and renamed only after the digest matches (desktop updater does the
                // same): an interrupted download never looks like a finished APK.
                val out = File(dir, target.name + ".part")
                val digest = MessageDigest.getInstance("SHA-256")
                var conn = get(rel.url).apply { instanceFollowRedirects = true }
                // GitHub redirects to its CDN (another host); HttpURLConnection follows same-protocol redirects.
                if (conn.responseCode in 300..399) {
                    val next = conn.getHeaderField("Location"); conn.disconnect(); conn = get(next)
                }
                try {
                    if (conn.responseCode != 200) throw IllegalStateException("下载返回 ${conn.responseCode}")
                    val total = if (rel.size > 0) rel.size else conn.contentLengthLong
                    conn.inputStream.use { input ->
                        out.outputStream().use { output ->
                            val buf = ByteArray(64 * 1024)
                            var done = 0L
                            while (true) {
                                val n = input.read(buf)
                                if (n < 0) break
                                output.write(buf, 0, n); digest.update(buf, 0, n)
                                done += n
                                if (total > 0) progress = (done.toFloat() / total).coerceIn(0f, 1f)
                            }
                        }
                    }
                } finally { conn.disconnect() }
                val hex = digest.digest().joinToString("") { "%02x".format(it) }
                val expected = rel.digest.removePrefix("sha256:").lowercase()
                if (expected.isNotEmpty() && expected != hex) {
                    out.delete()
                    throw IllegalStateException("安装包校验失败（SHA-256 不一致），已删除，请稍后重试")
                }
                if (!out.renameTo(target)) throw IllegalStateException("保存安装包失败")
                target
            }
            state = "ready"
            install(ctx, file)
        } catch (e: Exception) {
            File(File(ctx.cacheDir, "update"), rel.name + ".part").delete()
            state = "error"
            error = when (e) {
                is java.net.UnknownHostException, is java.net.ConnectException -> "下载失败：网络连接不可用，请检查网络后重试"
                is java.net.SocketTimeoutException -> "下载失败：连接超时，请稍后重试"
                else -> e.message ?: "下载失败"
            }
        }
    }

    /** Opens the system installer; asks for 安装未知应用 permission first when needed. */
    fun install(ctx: Context, file: File) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !ctx.packageManager.canRequestPackageInstalls()) {
            error = "请允许“安装未知应用”后，再点一次“安装”"
            ctx.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            return
        }
        val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", file)
        ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    fun downloadedFile(ctx: Context): File? =
        release?.let { File(File(ctx.cacheDir, "update"), it.name) }?.takeIf { it.exists() }
}
