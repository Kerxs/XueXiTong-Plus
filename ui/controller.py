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

from core import secret
from ui import advanced, cloudmodels, localmodels
from ui.models import LogModel, TaskModel
from ui.videoproxy import VideoProxy as _VideoProxyForCodes
from ui.output_parser import (
    ActivityEvent,
    CourseListEvent,
    LogEvent,
    ManualTaskEvent,
    OutputParser,
    StreamDecoder,
    strip_ansi,
    ProgressEvent,
    clock_seconds,
    PromptEvent,
    VideoPreviewEvent,
    WorkPreviewEvent,
)

APP_NAME = "学习通PLUS"          # identity — do not change
DISPLAY_NAME = "学习通 PLUS"     # shown to users
# 稳定性: a task process that exits unexpectedly (crash, killed, Python error) or stays silent for
# HANG_SECONDS is started again, at most MAX_RESTARTS times; the count starts over after a stretch
# of RESTART_RESET_SECONDS without trouble. Exit code 2 (main.EXIT_STOPPED) is a deliberate stop.
MAX_RESTARTS = 3
RESTART_DELAY_MS = 10_000
RESTART_RESET_SECONDS = 30 * 60
HANG_SECONDS = 20 * 60
EXIT_STOPPED = 2
APP_VERSION = "1.3.0"
# Bump whenever the 开始引导 changes: everyone who finished an older guide sees it again.
# 1: 欢迎 / 免责声明 / 账号 / 开始使用   2: + 答题设置 (1.1.7)
# 3: 答题设置 -> 高级设置, showing 答题来源 / 答题 / 通知推送 together (1.1.9)
# 4: + 自动完成 step (课件 / 作业 and its 自动提交 / 课堂活动提醒) (1.2.8)
AUTOSAVE_MS = 600           # settings are written this long after the last change
ONBOARDING_VERSION = 5      # 5: + 匿名统计 (1.3.0)
ROOT_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
BUNDLE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT_DIR

if os.name == "nt":
    DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "ChaoxingDesktop"
else:
    DATA_DIR = Path.home() / ".config" / "chaoxing-desktop"
CONFIG_PATH = DATA_DIR / "config.ini"
# 暂停标记：存在时任务进程在安全位置等待（api/pause.py）
PAUSE_FILE = DATA_DIR / "pause.flag"
# The app asks the task for a fresh preview address by creating this file (api/base.py
# Chaoxing._preview_refresh_requested); at most once per PREVIEW_REFRESH_SECONDS.
PREVIEW_REFRESH_FILE = DATA_DIR / "preview_refresh.flag"
PREVIEW_REFRESH_SECONDS = 90

SPEED_OPTIONS = ["1", "1.25", "1.5", "1.75", "2"]
VIDEO_BASE_URL = "https://mooc1.chaoxing.com/ananas/modules/video/index.html?v=2025-0725-1842"
TYPE_LABELS = {
    "single": "单选题",
    "multiple": "多选题",
    "judgement": "判断题",
    "completion": "填空题",
}


# The guide's steps in order: (id, the guide version that added or last changed it). A user who
# finished an older guide only sees the steps that are newer than the version they finished — not the
# whole guide again. When a step is added or changed: give it the new ONBOARDING_VERSION here.
ONBOARDING_STEPS = (("welcome", 1), ("disclaimer", 1), ("account", 1), ("auto", 4), ("advanced", 1),
                    ("telemetry", 5), ("start", 1))
# The disclaimer has its own version: it is shown (and has to be written out) again only when its
# text changes. Bump this when the text in Onboarding.qml / Screens.kt changes.
DISCLAIMER_VERSION = 1


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def disclaimer_accepted(value) -> int:
    """The disclaimer version the user accepted. Older versions stored the app version ("1.2.9")
    here: that was the same text as DISCLAIMER_VERSION 1."""
    text = str(value or "").strip()
    if not text:
        return 0
    return _int(text) if text.isdigit() else 1


def onboarding_done(done, version, disclaimer=DISCLAIMER_VERSION) -> bool:
    """Nothing of the guide left to show?"""
    return not onboarding_plan(done, version, disclaimer)[0]


def onboarding_plan(done, version, disclaimer) -> tuple[list[str], bool]:
    """(the step ids to show, new_only). new_only: the user finished an older guide and only gets
    what is new since then — which can be skipped (except a changed disclaimer)."""
    seen = _int(version)
    finished = str(done).lower() == "true"
    need_disclaimer = disclaimer_accepted(disclaimer) < DISCLAIMER_VERSION
    if finished and seen <= 0:
        finished = False                 # from before guide versions existed: the whole guide once
    if not finished:
        # the whole guide; a disclaimer already accepted in its current wording is not asked again
        return [sid for sid, _ in ONBOARDING_STEPS if sid != "disclaimer" or need_disclaimer], False
    steps = [sid for sid, since in ONBOARDING_STEPS
             if (sid == "disclaimer" and need_disclaimer) or (sid not in ("disclaimer", "welcome", "start") and since > seen)]
    return steps, True


def load_config() -> configparser.ConfigParser:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        template = ROOT_DIR / "config_template.ini"
        if template.exists():
            CONFIG_PATH.write_bytes(template.read_bytes())

    # Secrets are stored encrypted (core/secret.py); plain text from older versions is encrypted now.
    try:
        secret.migrate(CONFIG_PATH)
    except OSError:
        pass
    config = secret.read_config(CONFIG_PATH)
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
    """Muted, read-only preview page. It does not give up on an error: it retries with growing
    waits (2, 4, 8, 16, 30 s ...), reopens at the task's position, reloads after a long stall, and
    after 3 failures in a row tells the proxy (/f/...) so the app fetches a fresh video address."""
    safe_source = html.escape(source, quote=True)
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="unsafe-url">
        <style>html,body{{width:100%;height:100%;margin:0;background:#05080f;overflow:hidden}}
        body{{pointer-events:none;user-select:none}}
        video{{position:fixed;inset:0;width:100%;height:100%;object-fit:contain;background:#05080f;pointer-events:none}}
        #note{{position:fixed;inset:0;display:none;align-items:center;justify-content:center;color:#8e9bb3;font:14px "Segoe UI","Microsoft YaHei UI",sans-serif}}
        </style></head><body><video id="preview" autoplay muted playsinline disablepictureinpicture
        disableremoteplayback controlslist="nodownload noplaybackrate nofullscreen">
        <source id="src" src="{safe_source}"></video><div id="note"></div><script>
        const player=document.getElementById('preview'); player.muted=true;
        const source=document.getElementById('src'); const base=source.getAttribute('src');
        const note=document.getElementById('note');
        // #t=<seconds>&r=<rate>: open at the task's position and play at its speed; cxSync(t)
        // (called from the app as the task advances) pulls the picture back if it drifts.
        const hash=new URLSearchParams(location.hash.slice(1));
        const rate=Math.min(4,Math.max(0.5,parseFloat(hash.get('r'))||1));
        let wanted=parseFloat(hash.get('t')); let paused=false; let tries=0; let timer=null; let lastMove=Date.now();
        const show=t=>{{note.textContent=t||'';note.style.display=t?'flex':'none';}};
        const seekTo=t=>{{if(!(t>=0)||!isFinite(player.duration))return;player.currentTime=Math.min(t,Math.max(0,player.duration-0.5));}};
        const play=()=>{{if(!paused)player.play().catch(()=>{{}});}};
        player.addEventListener('loadedmetadata',()=>{{player.playbackRate=rate;seekTo(wanted);}});
        player.addEventListener('canplay',play); player.addEventListener('loadeddata',play);
        player.addEventListener('playing',()=>{{tries=0;show('');lastMove=Date.now();}});
        player.addEventListener('timeupdate',()=>{{lastMove=Date.now();}});
        window.cxSync=t=>{{wanted=t;if(player.readyState>=1&&Math.abs(player.currentTime-t)>4)seekTo(t);}};
        window.cxPause=p=>{{paused=!!p;if(p)player.pause();else play();}};
        function retry(){{
          if(timer)return;
          tries++;
          const wait=Math.min(30,2*Math.pow(2,Math.min(tries-1,4)));
          show(tries>=3?'视频暂时无法加载，正在重试…':'视频加载失败，正在重试…');
          if(tries===3)fetch(base.replace('/v/','/f/')).catch(()=>{{}});
          timer=setTimeout(()=>{{timer=null;source.src=base+'?n='+tries+'-'+Date.now();player.load();}},wait*1000);
        }}
        player.addEventListener('error',retry,true);
        // Stuck without progress (network stall, half-open connection): load it again.
        setInterval(()=>{{if(!paused&&!timer&&Date.now()-lastMove>25000&&player.readyState<3)retry();}},5000);
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
    _previewProblem = Signal(str, int, str)  # (video address, status, reason) from the video proxy thread
    dirtyChanged = Signal()
    runStateChanged = Signal()
    dashboardChanged = Signal()
    videoChanged = Signal()
    videoProgressChanged = Signal()
    videosChanged = Signal()                 # the list of videos being watched (chapters run in parallel)
    videoTick = Signal(str, float)           # one video's task position, for the grid's tiles
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
        # Every video being watched right now, by task name (insertion order). The single-video
        # properties (videoTitle, videoPageUrl …) are the selected one.
        self._videos: dict[str, dict] = {}
        self._work: dict = {}
        self._work_status = ""
        # The last WORKS_KEPT quizzes; work / workStatus are the selected one.
        self._works: list[dict] = []
        self._work_sel = -1
        self._work_picked_at = 0.0           # when the user last switched quizzes (monotonic)
        self._manual_tasks: list[dict] = []
        self._theme = str(self._settings.value("ui/theme", "system"))
        self._autosave = QTimer(self)
        self._autosave.setSingleShot(True)
        self._autosave.setInterval(AUTOSAVE_MS)
        self._autosave.timeout.connect(self._auto_save)
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._tick)
        # Automatic restart after an unexpected exit / hang (see MAX_RESTARTS).
        self._restarts = 0
        self._restart_pending = False
        self._launched_at = 0.0
        self._last_output = 0.0
        self._waiting_input = False          # a course list / Y-n question is waiting for the user
        self._chosen_courses: str | None = None   # answered again by itself after a restart
        self._prompt_answer: bool | None = None
        self._hung = False
        self._stopping = False
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(60_000)
        self._watchdog.timeout.connect(self._check_hang)
        self._read_values()
        self._apply_theme()
        from ui.updater import Updater

        self._updater = Updater(APP_VERSION, self)
        from ui.videoproxy import VideoProxy

        self._course_state = "idle"     # idle | running | done | error
        self._course_error = ""
        self._course_process = None
        self._known_courses = self._load_known_courses()

        self._video_source = ""          # the 学习通 address of the previewed video
        self._preview_refreshed_at = 0.0
        self._preview_noted: set[tuple[str, int]] = set()
        self._previewProblem.connect(self._on_preview_problem)
        self._video_proxy = VideoProxy(
            on_problem=lambda url, status, reason="": self._previewProblem.emit(url, status, reason or ""))
        self._start_telemetry()

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
            "jobs": min(8, max(1, common.getint("jobs", fallback=2))),
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
        if value:
            # Settings save themselves a moment after the last change (no 保存 button): the timer
            # restarts on every change, so typing in a field is one save, not one per letter.
            self._autosave.start()

    def _auto_save(self) -> None:
        if self._dirty:
            self.saveConfig(quiet=True)

    username = _config_property("username", str, "", configChanged)
    password = _config_property("password", str, "", configChanged)
    courseList = _config_property("course_list", str, "", configChanged)
    speed = _config_property("speed", str, "1", configChanged)
    jobs = _config_property("jobs", int, 2, configChanged)
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
    aiProviders = Property("QVariantList", lambda self: cloudmodels.public_providers(), constant=True)
    aiRegions = Property("QVariantList", lambda self: cloudmodels.REGIONS, constant=True)
    # 自定义服务商: saved with the other settings (保存), like every field of 高级选项.
    customProviders = Property("QVariantList", lambda self: cloudmodels.parse_custom(
        self._advanced.get(cloudmodels.CUSTOM_KEY, "")), notify=configChanged)
    cloudModels = Property("QVariantList", lambda self: self._cloud_models, notify=cloudModelsChanged)
    cloudModelState = Property(str, lambda self: self._cloud_state, notify=cloudModelsChanged)
    cloudModelError = Property(str, lambda self: self._cloud_error, notify=cloudModelsChanged)

    @Slot(str, result=str)
    def providerName(self, endpoint: str) -> str:
        return cloudmodels.identify(endpoint, self._advanced.get(cloudmodels.CUSTOM_KEY, ""))

    @Slot(str, result=str)
    def providerConsole(self, endpoint: str) -> str:
        return cloudmodels.console_url(endpoint)

    @Slot(str, str, result=str)
    def customProviderProblem(self, name: str, endpoint: str) -> str:
        return cloudmodels.custom_problem(name, endpoint, self._advanced.get(cloudmodels.CUSTOM_KEY, ""))

    @Slot(str, str, result=str)
    def addCustomProvider(self, name: str, endpoint: str) -> str:
        """Save a custom provider and switch to it. Returns why it could not be saved ("" = saved)."""
        saved = self._advanced.get(cloudmodels.CUSTOM_KEY, "")
        problem = cloudmodels.custom_problem(name, endpoint, saved)
        if problem:
            return problem
        self.setAdvanced(cloudmodels.CUSTOM_KEY, cloudmodels.dump_custom(cloudmodels.add_custom(saved, name, endpoint)))
        self.setAdvanced("tiku.endpoint", cloudmodels.normalize_endpoint(endpoint))
        return ""

    @Slot(str)
    def removeCustomProvider(self, endpoint: str) -> None:
        saved = self._advanced.get(cloudmodels.CUSTOM_KEY, "")
        self.setAdvanced(cloudmodels.CUSTOM_KEY, cloudmodels.dump_custom(cloudmodels.remove_custom(saved, endpoint)))

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
    appName = Property(str, lambda self: DISPLAY_NAME, constant=True)
    dataDir = Property(str, lambda self: str(DATA_DIR), constant=True)
    iconUrl = Property(QUrl, lambda self: QUrl.fromLocalFile(str(ROOT_DIR / "assets" / "learning_plus.png")), constant=True)

    @Slot(result=bool)
    def saveConfig(self, quiet: bool = False) -> bool:
        """Write config.ini. ``quiet``: the automatic save after a change (no line in the run log)."""
        self._autosave.stop()
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
            secret.write_config(self._config, CONFIG_PATH)
        except OSError as exc:
            self.toast.emit(f"保存失败：{exc}", "error")
            return False
        self._set_dirty(False)
        if not quiet:
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
        from core import account

        return account.log_size_text(DATA_DIR)

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

    # ----- 匿名使用统计 / 一键反馈（api/telemetry.py） -----------------------
    telemetryChanged = Signal()

    def _telemetry_on(self) -> bool:
        return str(self._advanced.get("common.telemetry", "true")).lower() in ("true", "1", "yes", "on")

    def _set_telemetry(self, value: bool) -> None:
        """The switch in 数据与隐私 and in the guide. Off: stop at once and delete what was waiting."""
        from api import telemetry

        if value != self._telemetry_on():
            self.setAdvanced("common.telemetry", "true" if value else "false")
            self.saveConfig()
        telemetry.configure(value, DATA_DIR, process="gui")
        self.telemetryChanged.emit()

    telemetryEnabled = Property(bool, _telemetry_on, _set_telemetry, notify=telemetryChanged)
    # False while no collector address is built in: the numbers stay on this device.
    telemetryUploads = Property(bool, lambda self: bool(__import__("api.telemetry", fromlist=["x"]).upload_url()),
                                constant=True)

    def _start_telemetry(self) -> None:
        """Once at start-up. Users from before 1.3.0 have "false" in config.ini that they never chose
        (it was the default): the first time, it is switched on — the guide's new page says so and
        has the switch. After that the user's choice is never touched."""
        from api import telemetry

        if str(self._settings.value("telemetry/asked", "false")).lower() != "true":
            self._settings.setValue("telemetry/asked", "true")
            if not self._telemetry_on():
                self.setAdvanced("common.telemetry", "true")
                self.saveConfig()
        os.environ["XXTPLUS_VERSION"] = APP_VERSION
        telemetry.configure(self._telemetry_on(), DATA_DIR, process="gui")
        telemetry.count("app.start")
        telemetry.flush()

    def note(self, key: str, n: int = 1) -> None:
        from api import telemetry

        telemetry.count(key, n)

    @Slot(QObject, bool, result=int)
    def roundCorners(self, window, rounded: bool) -> int:
        """Round the corners of a frameless window (Windows 11). Returns the corner radius the
        window now has: 0 when it is square (asked to be, or the system has no rounded windows)."""
        from ui import wincorners

        try:
            ok = wincorners.set_rounded(int(window.winId()), rounded)
        except Exception:  # noqa: BLE001
            ok = False
        return wincorners.RADIUS if ok and rounded else 0

    @Slot(float)
    def noteStartup(self, seconds: float) -> None:
        """How long the app took to show its window (ui/startup.py)."""
        from api import telemetry

        telemetry.gauge("perf.startup_s", seconds)

    @Slot(result=str)
    def feedbackText(self) -> str:
        from api import telemetry

        return telemetry.summary(telemetry.load(DATA_DIR))

    @Slot(str)
    def openFeedback(self, text: str) -> None:
        from api import telemetry

        QDesktopServices.openUrl(QUrl(telemetry.feedback_url(text)))

    @Slot()
    def clearStats(self) -> None:
        from api import telemetry

        telemetry.clear(DATA_DIR)
        self.dataStatsChanged.emit()
        self.toast.emit("已清除匿名统计", "info")

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
        return not self._onboarding_plan()[0]

    def _onboarding_plan(self) -> tuple[list[str], bool]:
        if os.environ.get("CHAOXING_DESKTOP_ONBOARDING") == "1":
            return [sid for sid, _ in ONBOARDING_STEPS], False
        return onboarding_plan(self._settings.value("onboarding/done", "false"),
                               self._settings.value("onboarding/version", 0),
                               self._settings.value("onboarding/disclaimerVersion", ""))

    onboardingDone = Property(bool, _onboarding_done, notify=onboardingChanged)
    # Which steps the guide shows (ids from ONBOARDING_STEPS), and whether it is the short
    # "what is new" guide for someone who finished an older one.
    onboardingSteps = Property("QVariantList", lambda self: self._onboarding_plan()[0], notify=onboardingChanged)
    onboardingNewOnly = Property(bool, lambda self: self._onboarding_plan()[1], notify=onboardingChanged)

    @Slot()
    def finishOnboarding(self) -> None:
        """The guide was finished or skipped: everything shown counts as seen."""
        self._settings.setValue("onboarding/done", "true")
        self._settings.setValue("onboarding/version", ONBOARDING_VERSION)
        self._settings.setValue("onboarding/disclaimerVersion", DISCLAIMER_VERSION)
        self.onboardingChanged.emit()

    @Slot()
    def resetOnboarding(self) -> None:
        self._settings.setValue("onboarding/done", "false")
        self.onboardingChanged.emit()

    # ----- run state -----------------------------------------------------
    # True while a run is active, including the few seconds before an automatic restart (停止 cancels it).
    running = Property(bool, lambda self: self._process is not None or self._restart_pending, notify=runStateChanged)
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
                self._last_output = time.monotonic()
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
        self._restarts = 0
        self._restart_pending = False
        self._chosen_courses = None
        self._prompt_answer = None
        self._launch()

    def _launch(self) -> None:
        if self._process is not None:
            return
        from core import settings as core_settings  # same checks and wording as the Android app

        v = self._values
        values = {**self._advanced, "common.username": v["username"], "common.password": v["password"],
                  "common.use_cookies": "true" if v["use_cookies"] else "false"}
        problem = core_settings.account_problem(values)
        if problem:
            self.toast.emit(problem + "。", "warning")
            return
        problem = core_settings.start_problem(values)
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
        environment.insert("XXTPLUS_VERSION", APP_VERSION)          # api/telemetry.py
        PREVIEW_REFRESH_FILE.unlink(missing_ok=True)
        environment.insert("CHAOXING_PREVIEW_REFRESH_FILE", str(PREVIEW_REFRESH_FILE))
        process.setProcessEnvironment(environment)
        process.start(str(program), arguments)
        if not process.waitForStarted(2500):
            self.toast.emit(f"启动失败：{process.errorString()}", "error")
            process.deleteLater()
            return

        self._process = process
        self._stopping = False
        self._parser = OutputParser()
        self._decoder = StreamDecoder()
        self._task_model.clear()
        self._course = self._chapter = self._task = ""
        self._completed = 0
        self._started_at = time.monotonic()
        self._elapsed = 0
        self._clock.start()
        self._works, self._work_sel = [], -1
        self._work = {}
        self._work_status = ""
        self.workChanged.emit()
        self._manual_tasks = []
        self.manualTasksChanged.emit()
        self._set_video(video_message_html("等待视频任务开始"), "", False, "等待视频任务开始")
        self.dashboardChanged.emit()
        self._set_status("正在运行", "running")
        self._log("INFO", "任务进程已启动。")
        self._launched_at = self._last_output = time.monotonic()
        self._waiting_input = False
        self._hung = False
        self._watchdog.start()
        from ui import keepawake

        if keepawake.hold():
            self._log("INFO", "运行期间不会自动睡眠（屏幕仍可关闭）。")

    @Slot()
    def stopRun(self) -> None:
        if self._process is None:
            if self._restart_pending:
                self._restart_pending = False
                self._log("INFO", "已取消自动重新开始。")
                self._set_status("已停止", "idle")
            return
        self._set_paused(False)          # a paused worker must not sit waiting while it is stopped
        self._stopping = True            # the exit code that follows is ours, not a crash
        self._process.terminate()
        QTimer.singleShot(1800, self._kill_if_running)
        self._log("WARNING", "已发送停止请求。")

    def _kill_if_running(self) -> None:
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()

    @Slot()
    def shutdown(self) -> None:
        if self._dirty:                 # a change made in the last moment before closing
            self.saveConfig(quiet=True)
        try:
            from api import telemetry

            telemetry.count("app.exit")
            telemetry.gauge("cfg.preview_" + self._get_preview_mode(), 1)
            telemetry.save("app")
        except Exception:  # noqa: BLE001 - statistics only
            pass
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
        self._chosen_courses = ",".join(ids)
        self._waiting_input = False
        self._write_stdin(",".join(ids))
        self._log("INFO", f"已选择课程：{', '.join(ids) if ids else '全部课程'}")

    @Slot(bool)
    def answerPrompt(self, yes: bool) -> None:
        self._prompt_answer = yes
        self._waiting_input = False
        self._write_stdin("y" if yes else "n")

    def _read_output(self, final: bool = False) -> None:
        if self._process is None:
            return
        chunk = self._decoder.decode(bytes(self._process.readAllStandardOutput()), final=final)
        if chunk:
            self._last_output = time.monotonic()
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
                self._task_model.start(event.value)
            elif event.kind in ("task_pending", "task_failed"):
                self._task_model.finish(event.value, event.kind.removeprefix("task_"))
                if event.value in self._videos or event.value == self._video_title:   # its preview ends
                    message = f"{event.value} 等待平台确认" if event.kind == "task_pending" else f"{event.value} 未完成"
                    self._set_video(video_message_html(message, "等待下一个视频任务"), event.value, False, message)
            elif event.kind == "task_finished":
                self._completed += 1
                self._task_model.finish(event.value, "done")
                # The task's viewing time is done: stop the preview instead of letting it play on.
                if event.value in self._videos or event.value == self._video_title:   # its preview ends
                    message = f"{event.value} 已看完"
                    self._set_video(video_message_html(message, "等待下一个视频任务"), event.value, False, message)
            self.dashboardChanged.emit()
        elif isinstance(event, ProgressEvent):
            self._task_model.upsert(event.name, percent=event.percent, detail=f"{event.done} / {event.total}")
            entry = self._videos.get(event.name)
            seconds = clock_seconds(event.done) if entry else None
            if seconds is not None and seconds != entry["pos"]:
                entry["pos"] = seconds
                self.videoTick.emit(event.name, seconds)
                if event.name == self._video_title:
                    self._video_pos = seconds
                    self.videoProgressChanged.emit()
        elif isinstance(event, VideoPreviewEvent):
            if self.previewMode == "off":
                pass                     # previews are switched off: nothing is registered or decoded
            elif not event.valid:
                self._set_video(video_message_html("无法读取当前视频预览"), "", False, "无法读取当前视频预览")
            elif event.source:
                # Played through the local proxy so the CDN gets the Referer it expects.
                try:
                    # every address the task sent: the proxy falls back to the next one by itself
                    local = self._video_proxy.register(getattr(event, "sources", None) or [event.source])
                except ValueError:
                    self._set_video(video_message_html("视频地址不是学习通域名，已忽略"), event.title, False, "视频地址不是学习通域名，已忽略")
                else:
                    if event.source != self._video_source:
                        self._preview_noted.clear()
                    self._video_source = event.source
                    page = self._video_proxy.register_page(video_source_html(local))
                    self._set_video(video_source_html(local), event.title, True, "", page,
                                    sources=getattr(event, "sources", None) or [event.source])
            else:
                note = getattr(event, "message", "") or "当前章节没有可显示的视频流"
                self._set_video(video_message_html(note), event.title, False, note)
        elif isinstance(event, WorkPreviewEvent):
            self._handle_work(event)
        elif isinstance(event, ManualTaskEvent):
            self._on_manual_task(event)
        elif isinstance(event, CourseListEvent):
            if self._chosen_courses is not None:      # restarted: same choice as before
                self._log("INFO", "自动重新开始：沿用之前选择的课程。")
                self._write_stdin(self._chosen_courses)
            else:
                self._waiting_input = True
                self.courseSelectionRequested.emit(event.courses)
        elif isinstance(event, PromptEvent):
            if self._prompt_answer is not None:
                self._write_stdin("y" if self._prompt_answer else "n")
            else:
                self._waiting_input = True
                self.promptRequested.emit(event.text)

    # ----- content the program does not do (api/manual.py) ------------------
    manualTasksChanged = Signal()
    manualPopupRequested = Signal()
    manualResolved = Signal()          # every reminder was taken back: the popup closes itself

    manualTasks = Property("QVariantList", lambda self: self._manual_tasks, notify=manualTasksChanged)
    pushConfigured = Property(bool, lambda self: self.push_configured(), notify=configChanged)

    def push_configured(self) -> bool:
        """A push service that can reach the user (the desktop has no 本机通知)."""
        provider = str(self._advanced.get("notification.provider", "")).strip()
        url = str(self._advanced.get("notification.url", "")).strip()
        return bool(provider) and provider != "Local" and bool(url)

    def _on_manual_task(self, event: ManualTaskEvent) -> None:
        item = {"course": event.course, "chapter": event.chapter, "kind": event.kind, "name": event.name}
        if event.checking:
            # Not a reminder yet: the task process reloads the chapter, logs in again and retries
            # first. Only a line at the bottom of the window — no popup, nothing in the list.
            what = f"{event.kind}「{event.name}」" if event.name else event.kind
            self.toast.emit(f"{what}可能需要手动完成，正在确认中…", "info")
            return
        if event.resolved:
            left = [t for t in self._manual_tasks if not (t["course"] == event.course and t["name"] == event.name)]
            if len(left) != len(self._manual_tasks):
                self._manual_tasks = left
                self.manualTasksChanged.emit()
                self.toast.emit(f"「{event.name}」已自动完成，不需要手动处理了", "info")
                if not left:
                    self.manualResolved.emit()
            return
        if item in self._manual_tasks:
            return
        self._manual_tasks = [*self._manual_tasks, item]
        self.manualTasksChanged.emit()
        if self.push_configured():
            self.toast.emit(f"发现需要手动完成的{event.kind}，已推送提醒", "warning")
        else:
            # No push service: tell the user in the window instead.
            self.manualPopupRequested.emit()

    WORKS_KEPT = 6
    WORK_FINAL = ("已提交", "已保存")

    def _work_item(self, title: str, create: bool) -> dict | None:
        """The quiz these events belong to: the newest unfinished one with this title (events of the
        result phases written by an older task process carry no title: the newest unfinished one)."""
        for item in reversed(self._works):
            if (not title or item["title"] == title) and item["status"] not in self.WORK_FINAL \
                    and not item["status"].startswith("提交失败"):
                return item
        if not create:
            return None
        item = {"title": title, "view": {}, "status": ""}
        self._works.append(item)
        if len(self._works) > self.WORKS_KEPT:
            dropped = len(self._works) - self.WORKS_KEPT
            del self._works[:dropped]
            self._work_sel = max(-1, self._work_sel - dropped)
        # Show the new quiz, unless the user just picked another one to look at.
        if self._work_sel < 0 or time.monotonic() - self._work_picked_at > 30:
            self._work_sel = len(self._works) - 1
        return item

    def _handle_work(self, event: WorkPreviewEvent) -> None:
        if not event.valid:
            return
        if event.phase in ("submitted", "saved"):
            self._completed += 1
            self.dashboardChanged.emit()
        if self.previewMode == "off":
            return                       # counted above; no question list is built
        title = str(event.data.get("title", "") or "")
        if event.phase == "questions":
            item = self._work_item(title or "章节检测", create=True)
            item["view"] = build_work_view(event.data, pending=True)
            item["status"] = "正在查找答案"
        elif event.phase == "filled":
            item = self._work_item(title or "章节检测", create=True)
            item["view"] = build_work_view(event.data)
            item["status"] = "正在提交" if item["view"]["submit"] else "仅保存，不提交"
        else:
            item = self._work_item(title, create=False)
            if item is None:
                return
            if event.phase in ("submitted", "saved"):
                item["status"] = "已提交" if event.phase == "submitted" else "已保存"
            elif event.phase == "failed":
                item["status"] = f"提交失败：{event.data.get('msg', '')}"
        self._show_work()

    def _show_work(self) -> None:
        if 0 <= self._work_sel < len(self._works):
            self._work = self._works[self._work_sel]["view"]
            self._work_status = self._works[self._work_sel]["status"]
        else:
            self._work, self._work_status = {}, ""
        self.workChanged.emit()

    workCount = Property(int, lambda self: len(self._works), notify=workChanged)
    workIndex = Property(int, lambda self: self._work_sel, notify=workChanged)

    @Slot(int)
    def stepWork(self, delta: int) -> None:
        """‹ › in the quiz header: look at another of the recent quizzes."""
        if not self._works:
            return
        self._work_sel = (max(0, self._work_sel) + delta) % len(self._works)
        self._work_picked_at = time.monotonic()
        self._show_work()

    def _on_finished(self, exit_code: int, _status) -> None:
        self._read_output(final=True)
        self._set_paused(False)
        self._clock.stop()
        self._watchdog.stop()
        PREVIEW_REFRESH_FILE.unlink(missing_ok=True)
        from ui import keepawake

        keepawake.release()
        self._task_model.finish_running()
        ok = exit_code == 0
        stopped = getattr(self, "_stopping", False) and not ok
        self._stopping = False
        unexpected = not ok and not stopped and exit_code != EXIT_STOPPED
        if stopped:
            # Ended by 停止: the non-zero code comes from terminate()/kill(), not from an error.
            self._log("INFO", "任务已停止。")
        elif exit_code == EXIT_STOPPED:
            self._log("ERROR", "任务已停止，原因见上方日志。")
        elif not self._hung:
            self._log("INFO" if ok else "ERROR", f"任务进程结束，退出码：{exit_code}")
        if self._process is not None:
            self._process.deleteLater()
        self._process = None
        self.runStateChanged.emit()
        self._set_video(video_message_html("视频任务已结束", "下次运行时会继续显示当前视频"), "", False, "视频任务已结束")
        if unexpected and self._schedule_restart(exit_code):
            return
        if stopped:
            self._set_status("已停止", "idle")
        else:
            self._set_status("已完成" if ok else "已退出", "done" if ok else "error")

    def _schedule_restart(self, exit_code: int) -> bool:
        """After an unexpected exit: start the task again in a moment. False when out of restarts."""
        if time.monotonic() - self._launched_at > RESTART_RESET_SECONDS:
            self._restarts = 0           # it ran fine for a long while: count from the start again
        if self._restarts >= MAX_RESTARTS:
            self._log("ERROR", f"任务进程连续 {MAX_RESTARTS} 次意外退出，已停止。请查看上面的日志；"
                               "确认账号、网络和设置都正常后重新开始，学习通会保留已看的进度。")
            return False
        self._restarts += 1
        self.note("worker.hang" if self._hung else "worker.crash")
        self.note("worker.restart")
        reason = "长时间没有响应" if self._hung else f"意外退出（退出码 {exit_code}）"
        self._log("WARNING", f"任务进程{reason}，{RESTART_DELAY_MS // 1000} 秒后自动重新开始"
                             f"（第 {self._restarts}/{MAX_RESTARTS} 次），学习通会保留已看的进度。")
        self._restart_pending = True
        self._set_status("即将重新开始", "paused")
        QTimer.singleShot(RESTART_DELAY_MS, self._restart)
        return True

    def _restart(self) -> None:
        if not self._restart_pending or self._process is not None:
            return                       # cancelled with 停止, or the user started a run already
        self._restart_pending = False
        self._launch()
        if self._process is None:        # could not start (settings changed, worker missing)
            self._set_status("已退出", "error")

    def _check_hang(self) -> None:
        """No output for HANG_SECONDS while running (not paused, not waiting for the user): restart."""
        if self._process is None or self._paused or self._waiting_input or self._stopping:
            return
        silent = time.monotonic() - self._last_output
        if silent < HANG_SECONDS:
            return
        self._hung = True
        self._log("WARNING", f"任务已经 {silent / 60:.0f} 分钟没有任何输出，可能卡住了，正在结束任务进程…")
        self._process.kill()

    def _on_error(self, error) -> None:
        if self._process and error != QProcess.ProcessError.Crashed:
            self._log("ERROR", f"任务进程错误：{self._process.errorString()}")

    def _on_preview_problem(self, url: str, status: int, reason: str = "") -> None:
        """The video proxy could not get the previewed video. Refused / broken: ask the task for a
        fresh address (it re-reads the video status once); the preview page retries by itself."""
        if self._process is None or not any(url in v["sources"] for v in self._videos.values()):
            return                       # an older video, or nothing running
        refused = status in _VideoProxyForCodes.REFUSED or status == 0
        key = (url, status)
        if key not in self._preview_noted:
            self._preview_noted.add(key)
            self.note("preview.fail")
            if status == 502:
                why = f"（原因：{reason}）" if reason else ""
                self._log("WARNING", f"视频预览：所有视频地址都暂时连不上{why}，会自动重试（不影响任务运行）。")
            elif status == 0:
                self._log("WARNING", "视频预览：视频多次加载失败，正在重新获取视频地址（不影响任务运行）。")
            else:
                self._log("WARNING", f"视频预览：视频服务器拒绝了当前地址（HTTP {status}，可能已过期），"
                                     "正在重新获取（不影响任务运行）。")
        if not refused or time.monotonic() - self._preview_refreshed_at < PREVIEW_REFRESH_SECONDS:
            return
        self._preview_refreshed_at = time.monotonic()
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            PREVIEW_REFRESH_FILE.write_text("refresh", encoding="utf-8")
        except OSError:
            pass

    # ----- visual panel --------------------------------------------------
    def _set_video(self, markup: str, title: str, active: bool, message: str = "", page_url: str = "",
                   sources=()) -> None:
        """A video starts (active) or ends / cannot be shown (not active). Several can be watched at
        once; the one shown in the single view stays the same until it ends."""
        if active and title:
            old = self._videos.get(title)
            self._videos[title] = {"title": title, "html": markup, "page": page_url, "sources": list(sources),
                                   "pos": old["pos"] if old else -1.0}
            self.videosChanged.emit()
            if self._video_title == title or self._video_title not in self._videos:
                self._show_video(title)
            return
        if title and title in self._videos:
            del self._videos[title]
            self.videosChanged.emit()
            if title != self._video_title:
                return                   # the one on screen goes on
            if self._videos:
                self._show_video(next(iter(self._videos)))
                return
        elif self._videos and title:
            return                       # a message about a video that is not shown: the others go on
        elif self._videos:               # no title: the run ended / was reset
            self._videos.clear()
            self.videosChanged.emit()
        self._video_html = markup
        self._video_message = message
        self._video_page = ""
        if title != self._video_title:
            self._video_pos = -1.0
        self._video_title = title
        self._video_active = False
        self.videoChanged.emit()

    def _show_video(self, title: str) -> None:
        entry = self._videos[title]
        self._video_html, self._video_page = entry["html"], entry["page"]
        self._video_message = ""
        self._video_title, self._video_pos = title, entry["pos"]
        self._video_active = True
        self.videoChanged.emit()

    def _page_at(self, entry: dict) -> str:
        return f"{entry['page']}#t={max(0.0, entry['pos']):g}&r={self._video_rate():g}" if entry["page"] else ""

    videos = Property("QVariantList", lambda self: [
        {"title": v["title"], "page": self._page_at(v)} for v in self._videos.values()], notify=videosChanged)
    videoCount = Property(int, lambda self: len(self._videos), notify=videosChanged)
    videoIndex = Property(int, lambda self: list(self._videos).index(self._video_title)
                          if self._video_title in self._videos else -1, notify=videoChanged)

    @Slot(int)
    def stepVideo(self, delta: int) -> None:
        """‹ › under the single view: show another of the videos being watched."""
        titles = list(self._videos)
        if len(titles) > 1:
            at = titles.index(self._video_title) if self._video_title in titles else 0
            self._show_video(titles[(at + delta) % len(titles)])

    @Slot(str, result=str)
    def videoPageFor(self, title: str) -> str:
        """A tile's page, opening at that video's current task position."""
        entry = self._videos.get(title)
        return self._page_at(entry) if entry else ""

    # single: one video, ‹ 1/4 › to switch · grid: all of them side by side · off: no previews at all
    PREVIEW_MODES = ("single", "grid", "off")

    def _get_preview_mode(self) -> str:
        value = str(self._settings.value("ui/previewMode", "single") or "single")
        return value if value in self.PREVIEW_MODES else "single"

    def _set_preview_mode(self, value: str) -> None:
        if value not in self.PREVIEW_MODES or value == self._get_preview_mode():
            return
        self._settings.setValue("ui/previewMode", value)
        if value == "off":
            self._works, self._work_sel = [], -1
            self._show_work()
            self._set_video(video_message_html("预览已关闭", "任务照常运行；在面板右上角可以重新打开"), "", False, "预览已关闭")
        elif self._process is not None and not self._videos:
            # switched back on during a run: ask the task for the current video again
            self._set_video(video_message_html("等待视频任务开始"), "", False, "等待视频任务开始")
            try:
                PREVIEW_REFRESH_FILE.write_text("refresh", encoding="utf-8")
            except OSError:
                pass
        self.prefsChanged.emit()

    previewMode = Property(str, _get_preview_mode, _set_preview_mode, notify=prefsChanged)

    def _video_rate(self) -> float:
        return 1.0  # 倍速已失效：任务和预览都按 1 倍速

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
