# -*- coding: utf-8 -*-
"""Bridge between the QML interface, ``config.ini`` and the worker process."""

from __future__ import annotations

import configparser
import html
import os
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QObject,
    QProcess,
    QProcessEnvironment,
    QSettings,
    QTimer,
    QUrl,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices, QGuiApplication

from ui import advanced, cloudmodels, localmodels
from ui.models import LogModel, TaskModel
from ui.output_parser import (
    ActivityEvent,
    CourseListEvent,
    LogEvent,
    OutputParser,
    StreamDecoder,
    strip_ansi,
    ProgressEvent,
    clock_seconds,
    PromptEvent,
    VideoPreviewEvent,
    WorkPreviewEvent,
)

APP_NAME = "学习通PLUS"
APP_VERSION = "1.2.1"
# Bump whenever the 开始引导 changes: everyone who finished an older guide sees it again.
# 1: 欢迎 / 免责声明 / 账号 / 开始使用   2: + 答题设置 (1.1.7)
# 3: 答题设置 -> 高级设置, showing 答题来源 / 答题 / 通知推送 together (1.1.9)
ONBOARDING_VERSION = 3
ROOT_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
BUNDLE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT_DIR

if os.name == "nt":
    DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "ChaoxingDesktop"
else:
    DATA_DIR = Path.home() / ".config" / "chaoxing-desktop"
CONFIG_PATH = DATA_DIR / "config.ini"
# 暂停标记：存在时任务进程在安全位置等待（api/pause.py）
PAUSE_FILE = DATA_DIR / "pause.flag"

SPEED_OPTIONS = ["1", "1.25", "1.5", "1.75", "2"]
VIDEO_BASE_URL = "https://mooc1.chaoxing.com/ananas/modules/video/index.html?v=2025-0725-1842"
TYPE_LABELS = {
    "single": "单选题",
    "multiple": "多选题",
    "judgement": "判断题",
    "completion": "填空题",
}


def onboarding_done(done, version) -> bool:
    """Finished the current 开始引导? A guide finished before it last changed does not count."""
    try:
        seen = int(version or 0)
    except (TypeError, ValueError):
        seen = 0
    return str(done).lower() == "true" and seen >= ONBOARDING_VERSION


def load_config() -> configparser.ConfigParser:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        template = ROOT_DIR / "config_template.ini"
        if template.exists():
            CONFIG_PATH.write_bytes(template.read_bytes())

    config = configparser.ConfigParser(interpolation=None)
    config.read(CONFIG_PATH, encoding="utf-8")
    for section in ("common", "tiku", "notification"):
        if not config.has_section(section):
            config.add_section(section)

    # Turn the template placeholders into empty form fields.
    for key in ("username", "password", "course_list"):
        if config["common"].get(key, "").strip().lower() == "xxx":
            config["common"][key] = ""
    return config


def video_message_html(message: str, sub: str = "运行学习通视频任务后，画面会自动显示") -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
        html,body{{height:100%;margin:0;background:#0b1020;color:#d7e0ee;font-family:'Segoe UI','Microsoft YaHei UI',sans-serif}}
        body{{display:flex;align-items:center;justify-content:center;text-align:center;user-select:none}}
        .box{{padding:32px}} .title{{font-size:20px;font-weight:600}} .sub{{margin-top:10px;color:#8e9bb3;font-size:13px}}
        </style></head><body><div class="box"><div class="title">{html.escape(message)}</div>
        <div class="sub">{html.escape(sub)}</div></div></body></html>"""


def video_source_html(source: str) -> str:
    safe_source = html.escape(source, quote=True)
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="unsafe-url">
        <style>html,body{{width:100%;height:100%;margin:0;background:#05080f;overflow:hidden}}
        body{{pointer-events:none;user-select:none}}
        video{{position:fixed;inset:0;width:100%;height:100%;object-fit:contain;background:#05080f;pointer-events:none}}
        </style></head><body><video id="preview" autoplay muted playsinline disablepictureinpicture
        disableremoteplayback controlslist="nodownload noplaybackrate nofullscreen">
        <source src="{safe_source}"></video><script>
        const player=document.getElementById('preview'); player.muted=true;
        // #t=<seconds>&r=<rate>: open at the task's position and play at its speed; cxSync(t)
        // (called from the app as the task advances) pulls the picture back if it drifts.
        const hash=new URLSearchParams(location.hash.slice(1));
        const rate=Math.min(4,Math.max(0.5,parseFloat(hash.get('r'))||1));
        const seekTo=t=>{{if(!(t>=0)||!isFinite(player.duration))return;player.currentTime=Math.min(t,Math.max(0,player.duration-0.5));}};
        player.addEventListener('loadedmetadata',()=>{{player.playbackRate=rate;seekTo(parseFloat(hash.get('t')));}},{{once:true}});
        window.cxSync=t=>{{if(player.readyState>=1&&Math.abs(player.currentTime-t)>4)seekTo(t);}};
        window.cxPause=p=>{{if(p)player.pause();else player.play().catch(()=>{{}});}};
        player.addEventListener('canplay',()=>player.play().catch(()=>{{}}),{{once:true}});
        player.addEventListener('loadeddata',()=>player.play().catch(()=>{{}}),{{once:true}});
        player.addEventListener('error',()=>{{document.body.innerHTML='<div style="color:#8e9bb3;font:14px Segoe UI;display:flex;height:100%;align-items:center;justify-content:center">视频加载失败</div>'}},true);
        document.addEventListener('contextmenu',e=>e.preventDefault());
        document.addEventListener('keydown',e=>{{e.preventDefault();e.stopPropagation();}},true);
        </script></body></html>"""


def build_work_view(data: dict, pending: bool = False) -> dict:
    """Shape a ``__CX_WORK_PREVIEW__`` payload into plain data for QML.

    ``pending``: the questions were just read and answers are still being looked up.
    """
    questions = []
    for raw in data.get("questions") or []:
        if not isinstance(raw, dict):
            continue
        q_type = str(raw.get("type", ""))
        answer = str(raw.get("answer", "") or "")
        options = []
        if q_type == "judgement":
            options = [
                {"text": "正确", "selected": answer == "true"},
                {"text": "错误", "selected": answer == "false"},
            ]
        elif q_type in ("single", "multiple"):
            for line in str(raw.get("options", "") or "").splitlines():
                line = line.strip()
                if line:
                    options.append({"text": line, "selected": bool(answer) and line[:1].upper() in answer.upper()})
        questions.append({
            "index": int(raw.get("index", len(questions) + 1) or 0),
            "typeLabel": TYPE_LABELS.get(q_type, "简答题" if q_type else "题目"),
            "title": str(raw.get("title", "")),
            "options": options,
            "answerText": answer if not options else "",
            "fromBank": raw.get("source") == "cover",
            # Where a found answer came from: "ai" (大模型) or "tiku" (题库 / 缓存).
            "fromAI": raw.get("source") == "cover" and raw.get("origin") == "ai",
            "pending": pending,
        })
    return {
        "title": str(data.get("title", "") or "章节检测"),
        "coverRate": int(data.get("cover_rate", 0) or 0),
        "submit": bool(data.get("submit", False)),
        "pending": pending,
        "questions": questions,
    }


def _config_property(key: str, type_, default, notify):
    def getter(self):
        return self._values.get(key, default)

    def setter(self, value):
        if self._values.get(key) != value:
            self._values[key] = value
            self._set_dirty(True)
            self.configChanged.emit()

    return Property(type_, getter, setter, notify=notify)


class AppController(QObject):
    configChanged = Signal()
    localModelsChanged = Signal()
    _localModelsFound = Signal(list)   # emitted from the detection thread
    cloudModelsChanged = Signal()
    _cloudModelsFound = Signal(list, str)   # (models, error) from the fetch thread
    dirtyChanged = Signal()
    runStateChanged = Signal()
    dashboardChanged = Signal()
    videoChanged = Signal()
    videoProgressChanged = Signal()
    workChanged = Signal()
    themeChanged = Signal()
    toast = Signal(str, str)  # message, kind
    courseSelectionRequested = Signal("QVariantList")
    promptRequested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._settings = QSettings()
        self._config = load_config()
        self._values: dict = {}
        self._dirty = False
        self._process: QProcess | None = None
        self._parser = OutputParser()
        self._decoder = StreamDecoder()
        self._log_model = LogModel(parent=self)
        self._task_model = TaskModel(parent=self)
        self._status = "就绪"
        self._status_kind = "idle"
        self._started_at = 0.0
        self._paused = False
        self._elapsed = 0
        self._course = ""
        self._chapter = ""
        self._task = ""
        self._completed = 0
        self._video_html = video_message_html("等待视频任务开始")
        self._video_message = "等待视频任务开始"
        self._video_page = ""
        self._video_title = ""
        self._video_pos = -1.0          # task position of the previewed video, seconds (-1 unknown)
        self._local_models: list[dict] = []
        self._local_state = "idle"      # idle | running | done
        self._localModelsFound.connect(self._on_local_models)
        self._cloud_models: list[str] = []
        self._cloud_state = "idle"      # idle | running | done | error
        self._cloud_error = ""
        self._cloudModelsFound.connect(self._on_cloud_models)
        self._video_active = False
        self._work: dict = {}
        self._work_status = ""
        self._theme = str(self._settings.value("ui/theme", "system"))
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._tick)
        self._read_values()
        self._apply_theme()
        from ui.updater import Updater

        self._updater = Updater(APP_VERSION, self)
        from ui.videoproxy import VideoProxy

        self._course_state = "idle"     # idle | running | done | error
        self._course_error = ""
        self._course_process = None
        self._known_courses = self._load_known_courses()

        self._video_proxy = VideoProxy()

    updater = Property(QObject, lambda self: self._updater, constant=True)

    # ----- configuration -------------------------------------------------
    def _read_values(self) -> None:
        common = self._config["common"]
        try:
            speed = f"{float(common.get('speed', '1')):g}"
        except (TypeError, ValueError):
            speed = "1"
        try:
            retry_interval = float(common.get("retry_interval", "5"))
        except (TypeError, ValueError):
            retry_interval = 5.0
        action = common.get("notopen_action", "retry")
        self._values = {
            "username": common.get("username", ""),
            "password": common.get("password", ""),
            "course_list": common.get("course_list", ""),
            "speed": speed if speed in SPEED_OPTIONS else "1",
            "jobs": min(8, max(1, common.getint("jobs", fallback=1))),
            "notopen_action": action if action in ("retry", "continue") else "retry",
            "use_cookies": common.getboolean("use_cookies", fallback=False),
            "retry_interval": max(0.0, retry_interval),
            "add_learning_count": common.getboolean("add_learning_count", fallback=False),
            "target_count": max(1, common.getint("target_count", fallback=100)),
        }
        self._advanced = advanced.read_values(self._config)

    def _set_dirty(self, value: bool) -> None:
        if self._dirty != value:
            self._dirty = value
            self.dirtyChanged.emit()

    username = _config_property("username", str, "", configChanged)
    password = _config_property("password", str, "", configChanged)
    courseList = _config_property("course_list", str, "", configChanged)
    speed = _config_property("speed", str, "1", configChanged)
    jobs = _config_property("jobs", int, 1, configChanged)
    notopenAction = _config_property("notopen_action", str, "retry", configChanged)
    useCookies = _config_property("use_cookies", bool, False, configChanged)
    retryInterval = _config_property("retry_interval", float, 5.0, configChanged)
    addLearningCount = _config_property("add_learning_count", bool, False, configChanged)
    targetCount = _config_property("target_count", int, 100, configChanged)

    # ----- advanced options (the rest of config.ini) ----------------------
    advancedGroups = Property("QVariantList", lambda self: advanced.GROUPS, constant=True)
    advancedValues = Property("QVariantMap", lambda self: self._advanced, notify=configChanged)

    @Slot(str, "QVariant")
    def setAdvanced(self, field_id: str, value) -> None:
        if field_id not in self._advanced:
            return
        text = advanced.normalize(field_id, value)
        if self._advanced[field_id] != text:
            self._advanced[field_id] = text
            if field_id in ("tiku.endpoint", "tiku.key") and self._cloud_state != "running":
                self._reset_cloud_models()   # the list belonged to the old address / key
            self._set_dirty(True)
            self.configChanged.emit()

    # 开始引导的“答题设置”一步：缺什么必填项（空字符串表示可以继续）。
    answerSetupProblem = Property(str, lambda self: advanced.answer_setup_problem(self._advanced), notify=configChanged)

    # ----- 自动检测本机模型 (高级选项 → 答题来源 → OpenAI 兼容接口) -----------
    localModels = Property("QVariantList", lambda self: self._local_models, notify=localModelsChanged)
    localModelState = Property(str, lambda self: self._local_state, notify=localModelsChanged)

    @Slot()
    def detectLocalModels(self) -> None:
        if self._local_state == "running":
            return
        self._local_state = "running"
        self.localModelsChanged.emit()
        extra = [p for p in (localmodels.port_of(self._advanced.get("tiku.endpoint", "")),) if p]
        threading.Thread(target=lambda: self._localModelsFound.emit(localmodels.detect(extra)),
                         name="detect-local-models", daemon=True).start()

    def _on_local_models(self, found: list) -> None:
        # One row per model: [{endpoint, port, server, model}].
        self._local_models = [{"endpoint": s["endpoint"], "port": s["port"], "server": s["server"], "model": m}
                              for s in found for m in s["models"]]
        self._local_state = "done"
        self.localModelsChanged.emit()

    # ----- 云端模型：常用服务、识别公司、获取模型列表 ------------------------
    aiProviders = Property("QVariantList", lambda self: [{"id": p["id"], "name": p["name"], "endpoint": p["endpoint"]}
                                                       for p in cloudmodels.PROVIDERS], constant=True)
    cloudModels = Property("QVariantList", lambda self: self._cloud_models, notify=cloudModelsChanged)
    cloudModelState = Property(str, lambda self: self._cloud_state, notify=cloudModelsChanged)
    cloudModelError = Property(str, lambda self: self._cloud_error, notify=cloudModelsChanged)

    @Slot(str, result=str)
    def providerName(self, endpoint: str) -> str:
        return cloudmodels.identify(endpoint)

    @Slot(str)
    def useProvider(self, endpoint: str) -> None:
        self.setAdvanced("tiku.endpoint", endpoint)

    def _reset_cloud_models(self) -> None:
        if self._cloud_models or self._cloud_state != "idle":
            self._cloud_models, self._cloud_state, self._cloud_error = [], "idle", ""
            self.cloudModelsChanged.emit()

    @Slot()
    def fetchCloudModels(self) -> None:
        if self._cloud_state == "running":
            return
        endpoint, key = self._advanced.get("tiku.endpoint", ""), self._advanced.get("tiku.key", "")
        proxy = self._advanced.get("tiku.http_proxy", "")
        self._cloud_state, self._cloud_error = "running", ""
        self.cloudModelsChanged.emit()

        def work():
            try:
                self._cloudModelsFound.emit(cloudmodels.list_models(endpoint, key, proxy), "")
            except cloudmodels.ModelListError as exc:
                self._cloudModelsFound.emit([], str(exc))

        threading.Thread(target=work, name="fetch-cloud-models", daemon=True).start()

    def _on_cloud_models(self, models: list, error: str) -> None:
        self._cloud_models = list(models)
        self._cloud_error = error
        self._cloud_state = "error" if error else "done"
        self.cloudModelsChanged.emit()

    @Slot(str)
    def useCloudModel(self, model: str) -> None:
        self.setAdvanced("tiku.model", model)

    @Slot(str, str)
    def useLocalModel(self, endpoint: str, model: str) -> None:
        self.setAdvanced("tiku.endpoint", endpoint)
        self.setAdvanced("tiku.model", model)

    @Slot(str, result=str)
    def answerMode(self, provider: str) -> str:
        return advanced.answer_mode(provider)

    @Slot(str, str)
    def setAnswerMode(self, field_id: str, mode: str) -> None:
        self.setAdvanced(field_id, advanced.apply_answer_mode(self._advanced.get(field_id, ""), mode))

    @Slot(str, "QStringList")
    def setProviders(self, field_id: str, picked: list) -> None:
        self.setAdvanced(field_id, advanced.order_providers(list(picked)))

    dirty = Property(bool, lambda self: self._dirty, notify=dirtyChanged)
    speedOptions = Property("QStringList", lambda self: SPEED_OPTIONS, constant=True)
    version = Property(str, lambda self: APP_VERSION, constant=True)
    appName = Property(str, lambda self: APP_NAME, constant=True)
    dataDir = Property(str, lambda self: str(DATA_DIR), constant=True)
    iconUrl = Property(QUrl, lambda self: QUrl.fromLocalFile(str(ROOT_DIR / "assets" / "learning_plus.png")), constant=True)

    @Slot(result=bool)
    def saveConfig(self) -> bool:
        common = self._config["common"]
        v = self._values
        common["username"] = v["username"].strip()
        common["password"] = v["password"]
        common["course_list"] = v["course_list"].strip()
        common["speed"] = v["speed"]
        common["jobs"] = str(v["jobs"])
        common["notopen_action"] = v["notopen_action"]
        common["use_cookies"] = str(v["use_cookies"]).lower()
        common["retry_interval"] = f"{v['retry_interval']:g}"
        common["add_learning_count"] = str(v["add_learning_count"]).lower()
        common["target_count"] = str(v["target_count"])
        advanced.write_values(self._config, self._advanced)
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with CONFIG_PATH.open("w", encoding="utf-8") as config_file:
                self._config.write(config_file)
        except OSError as exc:
            self.toast.emit(f"保存失败：{exc}", "error")
            return False
        self._set_dirty(False)
        # No path here: the log is on screen and ends up in screenshots.
        self._log("INFO", "配置已保存")
        return True

    @Slot()
    def revertConfig(self) -> None:
        self._config = load_config()
        self._read_values()
        self._set_dirty(False)
        self.configChanged.emit()

    @Slot()
    def openDataDir(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR)))

    @Slot()
    def openConfigFile(self) -> None:
        """Open config.ini in the system's default editor (created from the template if missing)."""
        if not CONFIG_PATH.exists():
            load_config()
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(CONFIG_PATH))):
            self.toast.emit("无法打开配置文件，请在配置目录中手动打开 config.ini。", "warning")

    @Slot()
    def reloadConfig(self) -> None:
        """Re-read config.ini after it was edited outside the app."""
        if self._process is not None:
            self.toast.emit("任务运行中，停止后再重新载入配置。", "warning")
            return
        self.revertConfig()
        self.toast.emit("已重新载入配置文件。", "info")

    # ----- theme ---------------------------------------------------------
    def _apply_theme(self) -> None:
        hints = QGuiApplication.styleHints()
        scheme = {
            "light": Qt.ColorScheme.Light,
            "dark": Qt.ColorScheme.Dark,
        }.get(self._theme, Qt.ColorScheme.Unknown)
        if hasattr(hints, "setColorScheme"):
            hints.setColorScheme(scheme)

    def _get_theme(self) -> str:
        return self._theme

    def _set_theme(self, value: str) -> None:
        value = value if value in ("system", "light", "dark") else "system"
        if value != self._theme:
            self._theme = value
            self._settings.setValue("ui/theme", value)
            self._apply_theme()
            self.themeChanged.emit()

    themeMode = Property(str, _get_theme, _set_theme, notify=themeChanged)

    # ----- general preferences (QSettings, not config.ini) ----------------
    prefsChanged = Signal()

    def _pref(self, key: str, default: bool) -> bool:
        return str(self._settings.value(key, "true" if default else "false")).lower() == "true"

    def _set_pref(self, key: str, value: bool) -> None:
        if self._pref(key, not value) != value or self._settings.value(key) is None:
            self._settings.setValue(key, "true" if value else "false")
            self.prefsChanged.emit()

    splashEnabled = Property(bool, lambda self: self._pref("ui/splash", True),
                             lambda self, v: self._set_pref("ui/splash", v), notify=prefsChanged)
    animationsEnabled = Property(bool, lambda self: self._pref("ui/animations", True),
                                 lambda self, v: self._set_pref("ui/animations", v), notify=prefsChanged)
    alertOnFinish = Property(bool, lambda self: self._pref("ui/alertOnFinish", True),
                             lambda self, v: self._set_pref("ui/alertOnFinish", v), notify=prefsChanged)

    # ----- data & privacy -------------------------------------------------
    dataStatsChanged = Signal()

    def _log_size_text(self) -> str:
        from ui import winsetup

        total = sum(p.stat().st_size for p in winsetup.log_files(DATA_DIR))
        if total < 1024 * 1024:
            return f"{total / 1024:.0f} KB"
        return f"{total / 1024 / 1024:.1f} MB"

    logSize = Property(str, _log_size_text, notify=dataStatsChanged)
    hasCookiesFile = Property(bool, lambda self: (DATA_DIR / "cookies.txt").exists(), notify=dataStatsChanged)

    @Slot()
    def refreshDataStats(self) -> None:
        self.dataStatsChanged.emit()

    @Slot()
    def clearAccountData(self) -> None:
        from ui import winsetup

        if self._process is not None:
            self.toast.emit("任务运行中，停止后再清除账号数据。", "warning")
            return
        winsetup.clear_account_data(DATA_DIR)
        self._config = load_config()
        self._read_values()
        self._set_dirty(False)
        self.configChanged.emit()
        self.dataStatsChanged.emit()
        self.toast.emit("已清除账号、密码和 cookies。", "info")

    @Slot()
    def clearLogs(self) -> None:
        from ui import winsetup

        removed = 0
        for path in winsetup.log_files(DATA_DIR):
            try:
                if path.name == "gui.log":
                    path.write_text("", encoding="utf-8")  # still open by this process
                else:
                    path.unlink()
                removed += 1
            except OSError:
                pass
        self._log_model.clear()
        self.dataStatsChanged.emit()
        self.toast.emit(f"已清除运行日志（{removed} 个文件）。", "info")

    @Slot()
    def resetConfig(self) -> None:
        """Restore config.ini from the template but keep the account fields."""
        if self._process is not None:
            self.toast.emit("任务运行中，停止后再恢复默认设置。", "warning")
            return
        keep = {k: self._values[k] for k in ("username", "password", "use_cookies")}
        try:
            CONFIG_PATH.unlink(missing_ok=True)
        except OSError as exc:
            self.toast.emit(f"恢复失败：{exc}", "error")
            return
        self._config = load_config()
        self._read_values()
        self._values.update(keep)
        self.saveConfig()
        self.configChanged.emit()
        self.toast.emit("已恢复默认设置（账号信息保留）。", "info")

    @Slot(str)
    def openUrl(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    homepage = Property(str, lambda self: "https://github.com/Kerxs/XueXiTong-Plus", constant=True)
    upstreamUrl = Property(str, lambda self: "https://github.com/Samueli924/chaoxing", constant=True)

    # ----- first-run guide -------------------------------------------------
    onboardingChanged = Signal()

    def _onboarding_done(self) -> bool:
        if os.environ.get("CHAOXING_DESKTOP_ONBOARDING") == "1":
            return False
        return onboarding_done(self._settings.value("onboarding/done", "false"),
                               self._settings.value("onboarding/version", 0))

    onboardingDone = Property(bool, _onboarding_done, notify=onboardingChanged)

    @Slot()
    def finishOnboarding(self) -> None:
        self._settings.setValue("onboarding/done", "true")
        self._settings.setValue("onboarding/version", ONBOARDING_VERSION)
        self._settings.setValue("onboarding/disclaimerVersion", APP_VERSION)
        self.onboardingChanged.emit()

    @Slot()
    def resetOnboarding(self) -> None:
        self._settings.setValue("onboarding/done", "false")
        self.onboardingChanged.emit()

    # ----- run state -----------------------------------------------------
    running = Property(bool, lambda self: self._process is not None, notify=runStateChanged)
    status = Property(str, lambda self: self._status, notify=runStateChanged)
    statusKind = Property(str, lambda self: self._status_kind, notify=runStateChanged)
    logModel = Property(QObject, lambda self: self._log_model, constant=True)
    taskModel = Property(QObject, lambda self: self._task_model, constant=True)

    currentCourse = Property(str, lambda self: self._course, notify=dashboardChanged)
    currentChapter = Property(str, lambda self: self._chapter, notify=dashboardChanged)
    currentTask = Property(str, lambda self: self._task, notify=dashboardChanged)
    completedCount = Property(int, lambda self: self._completed, notify=dashboardChanged)

    def _format_elapsed(self) -> str:
        minutes, seconds = divmod(self._elapsed, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"

    elapsed = Property(str, _format_elapsed, notify=dashboardChanged)

    def _set_status(self, text: str, kind: str) -> None:
        self._status = text
        self._status_kind = kind
        self.runStateChanged.emit()

    # ----- 暂停 / 继续 -----------------------------------------------------
    pauseChanged = Signal()
    paused = Property(bool, lambda self: self._paused, notify=pauseChanged)

    @staticmethod
    def _clear_pause_flag() -> None:
        try:
            PAUSE_FILE.unlink(missing_ok=True)
        except OSError:
            pass

    def _set_paused(self, value: bool) -> None:
        if value:
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                PAUSE_FILE.write_text("paused", encoding="utf-8")
            except OSError as exc:
                self.toast.emit(f"暂停失败：{exc}", "error")
                return
        else:
            self._clear_pause_flag()
        if self._paused == value:
            return
        self._paused = value
        if self._process is not None:
            if value:
                self._clock.stop()       # 运行时长 does not count the pause
                self._set_status("已暂停", "paused")
            else:
                self._started_at = time.monotonic() - self._elapsed
                self._clock.start()
                self._set_status("正在运行", "running")
        self.pauseChanged.emit()

    @Slot()
    def pauseRun(self) -> None:
        if self._process is None or self._paused:
            return
        self._set_paused(True)
        if self._paused:
            self._log("INFO", "已暂停：正在进行的请求完成后停下，视频观看时长不计入暂停的时间")

    @Slot()
    def resumeRun(self) -> None:
        if self._process is None or not self._paused:
            return
        self._set_paused(False)
        self._log("INFO", "已继续运行")

    def _tick(self) -> None:
        self._elapsed = int(time.monotonic() - self._started_at)
        self.dashboardChanged.emit()

    def _log(self, level: str, message: str, stamp: str = "") -> None:
        self._log_model.append(level, message, stamp or time.strftime("%H:%M:%S"))

    def _worker_command(self, mode: str = "--worker") -> tuple[Path, list[str]] | None:
        args = [mode, str(CONFIG_PATH), str(DATA_DIR)]
        fake = os.environ.get("CHAOXING_DESKTOP_FAKE_WORKER")
        if fake and not getattr(sys, "frozen", False):
            return Path(sys.executable), [fake, *args]
        if getattr(sys, "frozen", False):
            program = BUNDLE_DIR / "chaoxing-worker.exe"
            if not program.exists():
                self.toast.emit(f"找不到任务运行组件：{program}", "error")
                return None
            return program, args
        return Path(sys.executable), [str(BUNDLE_DIR / "worker.py"), *args]

    # ----- course recognition ("识别课程") ---------------------------------
    coursesChanged = Signal()
    coursesDetected = Signal("QVariantList")

    courseDetectState = Property(str, lambda self: self._course_state, notify=coursesChanged)
    courseDetectError = Property(str, lambda self: self._course_error, notify=coursesChanged)
    knownCourses = Property("QVariantList", lambda self: self._known_courses, notify=coursesChanged)

    def _load_known_courses(self) -> list[dict]:
        import json

        try:
            data = json.loads(str(self._settings.value("courses/known", "[]")))
        except ValueError:
            return []
        return [c for c in data if isinstance(c, dict) and c.get("courseId")]

    def selected_course_names(self) -> list[str]:
        """Titles of the courses in course_list (from the last recognition)."""
        ids = [i.strip() for i in self._values.get("course_list", "").split(",") if i.strip()]
        names = {c["courseId"]: c.get("title", "") for c in self._known_courses}
        return [names[i] for i in ids if names.get(i)]

    @Slot()
    def detectCourses(self) -> None:
        """Log in with the saved account and read the course list (worker --list-courses)."""
        if self._course_state == "running" or self._process is not None:
            return
        v = self._values
        if not v["use_cookies"] and (not v["username"].strip() or not v["password"]):
            self.toast.emit("请先在设置中填写账号和密码，或开启 cookies 登录。", "warning")
            return
        if not self.saveConfig():
            return
        command = self._worker_command("--list-courses")
        if command is None:
            return
        program, arguments = command
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONUTF8", "1")
        environment.insert("PYTHONUNBUFFERED", "1")
        process.setProcessEnvironment(environment)
        process.setWorkingDirectory(str(DATA_DIR))
        decoder = StreamDecoder()
        buffer: list[str] = []
        process.readyReadStandardOutput.connect(
            lambda: buffer.append(decoder.decode(bytes(process.readAllStandardOutput()))))
        process.finished.connect(lambda code, _s: self._on_courses_finished(process, buffer, decoder, code))
        process.errorOccurred.connect(
            lambda err: self._on_courses_finished(process, buffer, decoder, -1)
            if err == QProcess.ProcessError.FailedToStart else None)
        self._course_state, self._course_error = "running", ""
        self.coursesChanged.emit()
        self._log("INFO", "正在登录并识别课程…")
        process.start(str(program), arguments)
        self._course_process = process
        QTimer.singleShot(90_000, lambda: process.kill() if process.state() != QProcess.ProcessState.NotRunning else None)

    def _on_courses_finished(self, process, buffer, decoder, code) -> None:
        import json

        if self._course_process is not process:
            return
        self._course_process = None
        buffer.append(decoder.decode(bytes(process.readAllStandardOutput()), final=True))
        process.deleteLater()
        payload = None
        for line in "".join(buffer).splitlines():
            line = strip_ansi(line).strip()
            if line.startswith("__CX_COURSES__"):
                try:
                    payload = json.loads(line[len("__CX_COURSES__"):])
                except ValueError:
                    payload = None
        if not payload or not payload.get("ok"):
            self._course_state = "error"
            self._course_error = (payload or {}).get("error") or f"识别失败（任务组件退出代码 {code}）"
            self._log("ERROR", f"识别课程失败：{self._course_error}")
            self.toast.emit(f"识别课程失败：{self._course_error}", "error")
            self.coursesChanged.emit()
            return
        courses = payload.get("courses") or []
        self._known_courses = courses
        self._settings.setValue("courses/known", json.dumps(courses, ensure_ascii=False))
        self._course_state = "done"
        self._log("SUCCESS", f"识别到 {len(courses)} 门课程")
        self.coursesChanged.emit()
        self.coursesDetected.emit(courses)

    @Slot("QVariantList")
    def chooseCourses(self, course_ids) -> None:
        """Selection from the 识别课程 dialog -> course_list (empty = all courses)."""
        ids = []
        for i in course_ids:
            i = str(i).strip()
            if i and i not in ids:
                ids.append(i)
        self.courseList = ",".join(ids)
        self.coursesChanged.emit()

    @Slot()
    def startRun(self) -> None:
        if self._process is not None:
            return
        v = self._values
        if not v["use_cookies"] and (not v["username"].strip() or not v["password"]):
            self.toast.emit("请在设置中填写账号和密码，或开启 cookies 登录。", "warning")
            return
        problem = advanced.ai_config_problem(self._advanced)
        if problem:
            self.toast.emit(problem + "（设置 → 高级选项 → 答题来源）", "warning")
            return
        if not self.saveConfig():
            return
        command = self._worker_command()
        if command is None:
            return
        program, arguments = command

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_output)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)
        process.setWorkingDirectory(str(DATA_DIR))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONUTF8", "1")
        environment.insert("PYTHONUNBUFFERED", "1")
        environment.insert("CHAOXING_DESKTOP_PREVIEW", "1")
        self._clear_pause_flag()
        environment.insert("CHAOXING_PAUSE_FILE", str(PAUSE_FILE))
        process.setProcessEnvironment(environment)
        process.start(str(program), arguments)
        if not process.waitForStarted(2500):
            self.toast.emit(f"启动失败：{process.errorString()}", "error")
            process.deleteLater()
            return

        self._process = process
        self._parser = OutputParser()
        self._decoder = StreamDecoder()
        self._task_model.clear()
        self._course = self._chapter = self._task = ""
        self._completed = 0
        self._started_at = time.monotonic()
        self._elapsed = 0
        self._clock.start()
        self._work = {}
        self._work_status = ""
        self.workChanged.emit()
        self._set_video(video_message_html("等待视频任务开始"), "", False, "等待视频任务开始")
        self.dashboardChanged.emit()
        self._set_status("正在运行", "running")
        self._log("INFO", "任务进程已启动。")

    @Slot()
    def stopRun(self) -> None:
        if self._process is None:
            return
        self._set_paused(False)          # a paused worker must not sit waiting while it is stopped
        self._process.terminate()
        QTimer.singleShot(1800, self._kill_if_running)
        self._log("WARNING", "已发送停止请求。")

    def _kill_if_running(self) -> None:
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()

    @Slot()
    def shutdown(self) -> None:
        self._clear_pause_flag()
        self._updater.shutdown()
        self._video_proxy.stop()
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()
            self._process.waitForFinished(1500)

    def _write_stdin(self, text: str) -> None:
        if self._process is not None:
            self._process.write((text + "\n").encode("utf-8"))

    @Slot("QVariantList")
    def submitCourses(self, course_ids) -> None:
        ids = [str(i) for i in course_ids if str(i)]
        self._write_stdin(",".join(ids))
        self._log("INFO", f"已选择课程：{', '.join(ids) if ids else '全部课程'}")

    @Slot(bool)
    def answerPrompt(self, yes: bool) -> None:
        self._write_stdin("y" if yes else "n")

    def _read_output(self, final: bool = False) -> None:
        if self._process is None:
            return
        chunk = self._decoder.decode(bytes(self._process.readAllStandardOutput()), final=final)
        for event in self._parser.feed(chunk, final=final):
            self._handle_event(event)

    def _handle_event(self, event) -> None:
        if isinstance(event, LogEvent):
            self._log(event.level, event.message, event.time)
        elif isinstance(event, ActivityEvent):
            if event.kind == "course":
                self._course = event.value
            elif event.kind == "chapter":
                self._chapter = event.value
            elif event.kind == "task_started":
                self._task = event.value
                self._task_model.upsert(event.value, detail="进行中")
            elif event.kind == "task_finished":
                self._completed += 1
                self._task_model.upsert(event.value, detail="已完成", done=True)
                # The task's viewing time is done: stop the preview instead of letting it play on.
                if self._video_active and event.value == self._video_title:
                    message = f"{event.value} 已看完"
                    self._set_video(video_message_html(message, "等待下一个视频任务"), event.value, False, message)
            self.dashboardChanged.emit()
        elif isinstance(event, ProgressEvent):
            self._task_model.upsert(event.name, percent=event.percent, detail=f"{event.done} / {event.total}")
            if self._video_active and event.name == self._video_title:
                seconds = clock_seconds(event.done)
                if seconds is not None and seconds != self._video_pos:
                    self._video_pos = seconds
                    self.videoProgressChanged.emit()
        elif isinstance(event, VideoPreviewEvent):
            if not event.valid:
                self._set_video(video_message_html("无法读取当前视频预览"), "", False, "无法读取当前视频预览")
            elif event.source:
                # Played through the local proxy so the CDN gets the Referer it expects.
                try:
                    local = self._video_proxy.register(event.source)
                except ValueError:
                    self._set_video(video_message_html("视频地址不是学习通域名，已忽略"), event.title, False, "视频地址不是学习通域名，已忽略")
                else:
                    page = self._video_proxy.register_page(video_source_html(local))
                    self._set_video(video_source_html(local), event.title, True, "", page)
            else:
                self._set_video(video_message_html("当前章节没有可显示的视频流"), event.title, False, "当前章节没有可显示的视频流")
        elif isinstance(event, WorkPreviewEvent):
            self._handle_work(event)
        elif isinstance(event, CourseListEvent):
            self.courseSelectionRequested.emit(event.courses)
        elif isinstance(event, PromptEvent):
            self.promptRequested.emit(event.text)

    def _handle_work(self, event: WorkPreviewEvent) -> None:
        if not event.valid:
            return
        if event.phase == "questions":
            self._work = build_work_view(event.data, pending=True)
            self._work_status = "正在查找答案"
        elif event.phase == "filled":
            self._work = build_work_view(event.data)
            self._work_status = "正在提交" if self._work["submit"] else "仅保存，不提交"
        elif event.phase in ("submitted", "saved"):
            self._work_status = "已提交" if event.phase == "submitted" else "已保存"
            self._completed += 1
            self.dashboardChanged.emit()
        elif event.phase == "failed":
            self._work_status = f"提交失败：{event.data.get('msg', '')}"
        self.workChanged.emit()

    def _on_finished(self, exit_code: int, _status) -> None:
        self._read_output(final=True)
        self._set_paused(False)
        self._clock.stop()
        self._task_model.finish_running()
        ok = exit_code == 0
        self._log("INFO" if ok else "ERROR", f"任务进程结束，退出码：{exit_code}")
        if self._process is not None:
            self._process.deleteLater()
        self._process = None
        self._set_status("已完成" if ok else "已退出", "done" if ok else "error")
        self._set_video(video_message_html("视频任务已结束", "下次运行时会继续显示当前视频"), "", False, "视频任务已结束")

    def _on_error(self, error) -> None:
        if self._process and error != QProcess.ProcessError.Crashed:
            self._log("ERROR", f"任务进程错误：{self._process.errorString()}")

    # ----- visual panel --------------------------------------------------
    def _set_video(self, markup: str, title: str, active: bool, message: str = "", page_url: str = "") -> None:
        self._video_html = markup
        self._video_message = message
        self._video_page = page_url
        if title != self._video_title:
            self._video_pos = -1.0
        self._video_title = title
        self._video_active = active
        self.videoChanged.emit()

    def _video_rate(self) -> float:
        try:
            return float(self._values.get("speed", "1"))
        except (TypeError, ValueError):
            return 1.0

    @Slot(result=str)
    def videoPageAtPosition(self) -> str:
        """Preview page URL that opens at the task's current position and speed."""
        if not self._video_page:
            return ""
        position = max(0.0, self._video_pos)
        return f"{self._video_page}#t={position:g}&r={self._video_rate():g}"

    videoPosition = Property(float, lambda self: self._video_pos, notify=videoProgressChanged)

    videoHtml = Property(str, lambda self: self._video_html, notify=videoChanged)
    videoTitle = Property(str, lambda self: self._video_title, notify=videoChanged)
    videoActive = Property(bool, lambda self: self._video_active, notify=videoChanged)
    videoMessage = Property(str, lambda self: self._video_message, notify=videoChanged)
    # http://127.0.0.1 page served by the video proxy (preferred over loadHtml, see ui/videoproxy.py).
    videoPageUrl = Property(str, lambda self: self._video_page, notify=videoChanged)
    videoBaseUrl = Property(str, lambda self: VIDEO_BASE_URL, constant=True)
    work = Property("QVariantMap", lambda self: self._work, notify=workChanged)
    workStatus = Property(str, lambda self: self._work_status, notify=workChanged)
