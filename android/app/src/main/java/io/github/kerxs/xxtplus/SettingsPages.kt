package io.github.kerxs.xxtplus

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.AutoMode
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Palette
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Quiz
import androidx.compose.material.icons.filled.Security
import androidx.compose.material.icons.filled.SystemUpdate
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.TaskAlt
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

private data class Section(val id: String, val title: String, val icon: ImageVector, val summary: () -> String)

private const val HOMEPAGE = "https://github.com/Kerxs/XueXiTong-Plus"
private const val UPSTREAM = "https://github.com/Samueli924/chaoxing"

/** 设置: a menu of sections (二级菜单), each opening its own page — the desktop settings, grouped for a phone. */
@Composable
fun SettingsScreen(snackbar: SnackbarHostState, reopenGuide: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var page by rememberSaveable { mutableStateOf("") }
    val values = SettingsModel.values

    fun groupLabel(fieldId: String): String {
        val f = SettingsModel.groups().flatMap { it.optJSONArray("fields").objects() }.firstOrNull { it.optString("id") == fieldId }
        val v = values[fieldId] ?: ""
        return f?.optJSONArray("options").objects().firstOrNull { it.optString("value") == v }?.optString("label") ?: v
    }

    val sections = listOf(
        Section("account", "账号", Icons.Filled.Person) {
            if (values["common.use_cookies"] == "true") "cookies 登录" else values["common.username"].orEmpty().ifEmpty { "未填写" }
        },
        Section("run", "运行参数", Icons.Filled.Tune) {
            val names = Courses.selectedNames()
            val courses = when {
                names.isNotEmpty() -> names.joinToString("、")
                values["common.course_list"].isNullOrBlank() -> "开始时选择课程"
                else -> "课程 ${values["common.course_list"]}"
            }
            "$courses · 1 倍速"
        },
        Section("auto", "自动完成", Icons.Filled.AutoMode) {
            fun on(id: String) = values[id] != "false"
            listOfNotNull("视频", "章节检测", "课件".takeIf { on("common.auto_documents") },
                if (on("common.auto_homework")) (if (on("common.homework_submit")) "作业" else "作业（只保存）") else null)
                .joinToString("、")
        },
        Section("tiku", "答题来源", Icons.Filled.Quiz) {
            when (answerModeOf(values["tiku.provider"])) { "tiku" -> "题库"; "ai" -> "AI 大模型"; "both" -> "题库 + AI"; else -> "不查找" }
        },
        Section("answer", "答题", Icons.Filled.TaskAlt) {
            if (values["tiku.submit"] == "false") "只保存不提交"
            else "覆盖率 ${((values["tiku.cover_rate"]?.toFloatOrNull() ?: 0.75f) * 100).toInt()}% 时提交"
        },
        Section("notify", "通知推送", Icons.Filled.Notifications) { groupLabel("notification.provider").ifEmpty { "不推送" } },
        Section("ui", "界面", Icons.Filled.Palette) {
            mapOf("system" to "跟随系统", "light" to "浅色", "dark" to "深色")[UiPrefs.theme].orEmpty() +
                if (UiPrefs.motion) " · 动画开" else " · 动画关"
        },
        Section("data", "数据与隐私", Icons.Filled.Security) { "清除日志、账号数据" },
        Section("update", "检查更新", Icons.Filled.SystemUpdate) {
            "当前 ${Updater.currentVersion(ctx)}" + if (Updater.state == "available") " · 有新版本" else ""
        },
        Section("about", "关于", Icons.Filled.Info) { "学习通 PLUS ${Updater.currentVersion(ctx)}" },
    )

    fun leave() {
        page = ""
        scope.launch {
            SettingsModel.save(ctx)
            val problem = SettingsModel.problem(ctx)
            if (problem.isNotEmpty()) snackbar.showSnackbar("已保存。$problem")
        }
    }
    BackHandler(enabled = page.isNotEmpty()) { leave() }

    // Settings save themselves a moment after the last change — nothing to press. (The effect
    // restarts on every change, so typing in a field is one save, not one per letter.)
    var first by remember { mutableStateOf(true) }
    LaunchedEffect(values.toMap()) {
        if (first) { first = false; return@LaunchedEffect }
        kotlinx.coroutines.delay(600)
        SettingsModel.save(ctx)
    }

    PageSwitch(page, { if (it.isEmpty()) 0 else 1 }) { current ->
        if (current.isEmpty()) {
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(Dimens.pad),
                verticalArrangement = Arrangement.spacedBy(Dimens.gap)) {
                PageHeader("设置", "修改后自动保存")
                // heading → entries → the entry's page (which may open a further one, e.g. 选择服务商)
                listOf("账号与运行" to listOf("account", "run"), "任务" to listOf("auto", "tiku", "answer", "notify"),
                    "应用" to listOf("ui", "data", "update", "about")).forEach { (heading, ids) ->
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(heading, Modifier.padding(start = 6.dp), color = X.colors.accent, fontSize = 13.sp,
                            fontWeight = FontWeight.SemiBold)
                        XCard(Modifier.fillMaxWidth(), padding = 6.dp) {
                            val rows = sections.filter { it.id in ids }
                            rows.forEachIndexed { i, s -> MenuRow(s, divider = i < rows.size - 1) { page = s.id } }
                        }
                    }
                }
                if (RunState.running) {
                    Text("正在运行的任务使用开始时的设置，修改在下次开始时生效。", color = X.colors.muted, fontSize = 12.sp)
                }
            }
        } else {
            val section = sections.first { it.id == current }
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(Dimens.pad),
                verticalArrangement = Arrangement.spacedBy(Dimens.gap)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(40.dp).clip(RoundedCornerShape(Dimens.radius)).clickable { leave() },
                        contentAlignment = Alignment.Center) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "返回", tint = X.colors.text)
                    }
                    Spacer(Modifier.size(6.dp))
                    PageHeader(section.title)
                }
                when (current) {
                    "account" -> AccountPage(snackbar)
                    "run" -> RunParamsPage(snackbar)
                    "auto" -> SettingsModel.group("auto")?.let { SettingsGroupCard(it) }
                    "tiku" -> SettingsModel.group("tiku")?.let { SettingsGroupCard(it) }
                    "answer" -> SettingsModel.group("answer")?.let { SettingsGroupCard(it) }
                    "notify" -> SettingsModel.group("notify")?.let { SettingsGroupCard(it) }
                    "ui" -> InterfacePage()
                    "data" -> DataPage(snackbar)
                    "update" -> UpdatePage()
                    else -> AboutPage(reopenGuide)
                }
            }
        }
    }
}

fun answerModeOf(provider: String?): String {
    val ai = setOf("AI", "SiliconFlow")
    val picked = (provider ?: "").split(",").map { it.trim() }.filter { it.isNotEmpty() }
    return when {
        picked.isEmpty() -> "none"
        picked.all { it in ai } -> "ai"
        picked.none { it in ai } -> "tiku"
        else -> "both"
    }
}

@Composable
private fun MenuRow(s: Section, divider: Boolean, onClick: () -> Unit) {
    val c = X.colors
    Column {
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius)).clickable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(34.dp).clip(RoundedCornerShape(Dimens.radius)).background(c.accentSoft), contentAlignment = Alignment.Center) {
                Icon(s.icon, null, tint = c.accent, modifier = Modifier.size(18.dp))
            }
            Spacer(Modifier.size(12.dp))
            Column(Modifier.weight(1f)) {
                Text(s.title, color = c.text, fontSize = 15.sp, fontWeight = FontWeight.Medium)
                Text(s.summary(), color = c.muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = c.faint)
        }
        if (divider) Box(Modifier.fillMaxWidth().padding(start = 56.dp).height(1.dp).background(c.border))
    }
}

@Composable
private fun AccountPage(snackbar: SnackbarHostState) {
    val ctx = LocalContext.current
    val c = X.colors
    val scope = rememberCoroutineScope()
    var hasCookies by remember { mutableStateOf(PythonBridge.cookiesFile(ctx).exists()) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val msg = withContext(Dispatchers.IO) {
                runCatching {
                    val text = ctx.contentResolver.openInputStream(uri)!!.use { it.readBytes() }
                    if (text.size > 512 * 1024) error("文件太大，不像 cookies.txt")
                    PythonBridge.cookiesFile(ctx).apply { parentFile?.mkdirs() }.writeBytes(text)
                    "已导入 cookies.txt"
                }.getOrElse { "导入失败：${it.message}" }
            }
            hasCookies = PythonBridge.cookiesFile(ctx).exists()
            snackbar.showSnackbar(msg)
        }
    }
    XCard(Modifier.fillMaxWidth(), title = "学习通账号", subtitle = "账号、密码和 cookies 加密保存在本应用的私有目录") {
        BasicFields(listOf("common.use_cookies", "common.username", "common.password"))
        if (SettingsModel.values["common.use_cookies"] == "true") {
            Text(if (hasCookies) "已导入 cookies.txt。开启后账号密码不参与登录。" else "还没有 cookies.txt，请先导入。",
                color = if (hasCookies) c.success else c.warning, fontSize = 12.sp)
            XButton(if (hasCookies) "重新导入 cookies.txt" else "导入 cookies.txt",
                { picker.launch(arrayOf("text/plain", "*/*")) }, Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun RunParamsPage(snackbar: SnackbarHostState) {
    val ctx = LocalContext.current
    val c = X.colors
    val scope = rememberCoroutineScope()
    XCard(Modifier.fillMaxWidth(), title = "课程", subtitle = "留空则开始运行时选择") {
        val names = Courses.selectedNames()
        Text(if (names.isEmpty()) "未选择（全部课程或开始时选择）" else "已选：" + names.joinToString("、"),
            color = c.text, fontSize = 13.sp)
        XButton(if (Courses.state == "running") "正在识别课程…" else "识别课程", {
            scope.launch { Courses.detect(ctx)?.let { if (Courses.state == "error") snackbar.showSnackbar(it) } }
        }, Modifier.fillMaxWidth(), enabled = Courses.state != "running" && !RunState.running)
        if (Courses.state == "error") Text(Courses.error, color = c.danger, fontSize = 12.sp)
        BasicFields(listOf("common.course_list"))
    }
    XCard(Modifier.fillMaxWidth(), title = "运行", subtitle = "并行和重试") {
        Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius)).background(c.warningSoft)
            .padding(horizontal = 10.dp, vertical = 8.dp)) {
            Text("视频倍速已失效，统一按 1 倍速完整观看，看完并经平台确认后即完成。",
                color = c.warning, fontSize = 12.sp)
        }
        BasicFields(listOf("common.jobs", "common.retry_interval", "common.notopen_action"))
    }
}

@Composable
private fun InterfacePage() {
    val ctx = LocalContext.current
    val c = X.colors
    XCard(Modifier.fillMaxWidth(), title = "外观", subtitle = "与电脑版相同的选项") {
        Text("主题", color = c.text, fontSize = 14.sp)
        Segmented(listOf("system" to "跟随系统", "light" to "浅色", "dark" to "深色"), UiPrefs.theme,
            { UiPrefs.theme = it; UiPrefs.save(ctx) }, Modifier.fillMaxWidth())
        SwitchRow("界面动画", "关闭后所有过渡立即完成", UiPrefs.motion) { UiPrefs.motion = it; UiPrefs.save(ctx) }
        SwitchRow("启动动画", "打开应用时显示开屏动画", UiPrefs.splash) { UiPrefs.splash = it; UiPrefs.save(ctx) }
        SwitchRow("运行结束提醒", "任务结束时发送通知", UiPrefs.alertOnFinish) { UiPrefs.alertOnFinish = it; UiPrefs.save(ctx) }
    }
}

@Composable
private fun ConfirmDialog(title: String, message: String, confirm: String, onConfirm: () -> Unit, onDismiss: () -> Unit) {
    val c = X.colors
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = c.surface, titleContentColor = c.text, textContentColor = c.text,
        shape = RoundedCornerShape(Dimens.radiusLarge),
        title = { Text(title) }, text = { Text(message) },
        confirmButton = { XButton(confirm, { onDismiss(); onConfirm() }, kind = Kind.Danger) },
        dismissButton = { XButton("取消", onDismiss, kind = Kind.Ghost) },
    )
}

@Composable
private fun DataPage(snackbar: SnackbarHostState) {
    val ctx = LocalContext.current
    val c = X.colors
    val scope = rememberCoroutineScope()
    var logSize by remember { mutableStateOf("…") }
    var confirm by remember { mutableStateOf("") }
    suspend fun refresh() {
        logSize = withContext(Dispatchers.IO) {
            runCatching { JSONObject(PythonBridge.dataStats(ctx)).optString("logSize") }.getOrDefault("未知")
        }
    }
    LaunchedEffect(Unit) { refresh() }

    XCard(Modifier.fillMaxWidth(), title = "运行日志", subtitle = "当前占用 $logSize。日志可能包含课程和章节名称") {
        XButton("清除日志", { confirm = "logs" }, Modifier.fillMaxWidth())
    }
    XCard(Modifier.fillMaxWidth(), title = "账号数据", subtitle = "清除保存的账号、密码和 cookies") {
        XButton("清除账号数据", { confirm = "account" }, Modifier.fillMaxWidth(), Kind.Danger, enabled = !RunState.running)
    }
    XCard(Modifier.fillMaxWidth(), title = "恢复默认设置", subtitle = "答题、推送等设置恢复默认，账号信息保留") {
        XButton("恢复默认设置", { confirm = "reset" }, Modifier.fillMaxWidth(), enabled = !RunState.running)
    }
    // 匿名使用统计（api/telemetry.py，默认关闭）和一键反馈（打开 GitHub，由用户自己提交）
    var feedbackText by remember { mutableStateOf("") }
    var feedbackUrl by remember { mutableStateOf("") }
    XCard(Modifier.fillMaxWidth(), title = "匿名使用统计",
        subtitle = "只统计数字（各类任务成功 / 失败次数和耗时、错误类型、内存、版本），不含账号、课程、题目和日志；默认开启") {
        SwitchRow("发送匿名统计", "关闭后立即停止，并删除本机还没发送的数据", SettingsModel.values["common.telemetry"] != "false") {
            SettingsModel.values["common.telemetry"] = if (it) "true" else "false"
            scope.launch {
                SettingsModel.save(ctx)
                // off: what was recorded and what was waiting to be sent is deleted at once
                if (!it) withContext(Dispatchers.IO) { runCatching { PythonBridge.clearStats(ctx) } }
            }
        }
        XButton("预览并反馈", {
            scope.launch {
                val data = withContext(Dispatchers.IO) { runCatching { JSONObject(PythonBridge.feedback(ctx)) }.getOrNull() }
                feedbackText = data?.optString("text").orEmpty()
                feedbackUrl = data?.optString("url").orEmpty()
                confirm = "feedback"
            }
        }, Modifier.fillMaxWidth())
    }
    if (RunState.running) Text("任务运行中，停止后才能清除账号数据或恢复默认设置。", color = c.muted, fontSize = 12.sp)
    if (confirm == "feedback") {
        AlertDialog(
            onDismissRequest = { confirm = "" },
            containerColor = c.surface, titleContentColor = c.text, textContentColor = c.text,
            shape = RoundedCornerShape(Dimens.radiusLarge),
            title = { Text("反馈问题") },
            text = {
                Column(Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(if (feedbackText.isEmpty()) "还没有统计数据。打开“记录匿名统计”并运行一次后，这里会出现可以反馈的内容。"
                    else "将打开 GitHub 的新建反馈页面并填好下面的内容，你确认后再提交。只含计数，不含账号、课程、题目和日志。",
                        color = c.muted, fontSize = 13.sp)
                    if (feedbackText.isNotEmpty()) Text(feedbackText, fontSize = 12.sp, fontFamily = FontFamily.Monospace)
                }
            },
            confirmButton = {
                XButton("打开 GitHub 反馈", {
                    confirm = ""
                    runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(feedbackUrl)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
                }, kind = Kind.Primary, enabled = feedbackUrl.isNotEmpty())
            },
            dismissButton = {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (feedbackText.isNotEmpty()) XButton("清除统计", {
                        confirm = ""
                        scope.launch { withContext(Dispatchers.IO) { PythonBridge.clearStats(ctx) }; snackbar.showSnackbar("已清除匿名统计") }
                    }, kind = Kind.Ghost)
                    XButton("关闭", { confirm = "" }, kind = Kind.Ghost)
                }
            },
        )
    }

    when (confirm) {
        "logs" -> ConfirmDialog("清除运行日志", "将删除保存的运行日志文件，界面里的日志也会清空。", "清除", {
            scope.launch {
                val n = withContext(Dispatchers.IO) { runCatching { PythonBridge.clearLogs(ctx) }.getOrDefault(0) }
                RunState.logs.clear(); refresh()
                snackbar.showSnackbar("已清除运行日志（$n 个文件）")
            }
        }) { confirm = "" }
        "account" -> ConfirmDialog("清除账号数据", "将清除保存的账号、密码和 cookies.txt，并关闭 cookies 登录。清除后需要重新填写账号才能运行。", "清除", {
            scope.launch {
                withContext(Dispatchers.IO) { PythonBridge.clearAccountData(ctx) }
                SettingsModel.load(ctx)
                snackbar.showSnackbar("已清除账号、密码和 cookies")
            }
        }) { confirm = "" }
        "reset" -> ConfirmDialog("恢复默认设置", "除账号外的设置都会恢复为默认值。", "恢复", {
            scope.launch {
                withContext(Dispatchers.IO) { PythonBridge.resetConfig(ctx) }
                SettingsModel.load(ctx)
                snackbar.showSnackbar("已恢复默认设置（账号信息保留）")
            }
        }) { confirm = "" }
    }
}

@Composable
private fun UpdatePage() {
    val ctx = LocalContext.current
    val c = X.colors
    val scope = rememberCoroutineScope()
    XCard(Modifier.fillMaxWidth(), title = "学习通 PLUS ${Updater.currentVersion(ctx)}", subtitle = "从 GitHub Releases 检查新版本，下载后校验 SHA-256 再安装") {
        SwitchRow("启动时自动检查更新", "有新版本时提示", UiPrefs.autoUpdate) { UiPrefs.autoUpdate = it; UiPrefs.save(ctx) }
        val status = when (Updater.state) {
            "checking" -> "正在检查…"
            "latest" -> "已是最新版本"
            "available" -> "有新版本 ${Updater.release?.version}"
            "downloading" -> "正在下载 ${(Updater.progress * 100).toInt()}%"
            "ready" -> "下载完成，等待安装"
            "error" -> Updater.error
            else -> ""
        }
        if (status.isNotEmpty()) Text(status, color = if (Updater.state == "error") c.danger else c.text, fontSize = 13.sp)
        XButton("检查更新", { scope.launch { Updater.check(ctx, quiet = false) } }, Modifier.fillMaxWidth(), Kind.Primary,
            enabled = Updater.state != "checking" && Updater.state != "downloading")
    }
}

@Composable
private fun AboutPage(reopenGuide: () -> Unit) {
    val ctx = LocalContext.current
    val c = X.colors
    fun open(url: String) = runCatching {
        ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
    XCard(Modifier.fillMaxWidth(), title = "学习通 PLUS ${Updater.currentVersion(ctx)}", subtitle = "手机版") {
        Text("基于开源项目 Samueli924/chaoxing，遵循 GPL-3.0 协议，禁止用于盈利；与超星、学习通官方无任何关联。",
            color = c.text, fontSize = 13.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            XButton("项目主页", { open(HOMEPAGE) }, Modifier.weight(1f))
            XButton("原仓库", { open(UPSTREAM) }, Modifier.weight(1f))
        }
        XButton("重新打开开始引导", reopenGuide, Modifier.fillMaxWidth())
    }
}
