# Claude 项目交接说明

## 产品范围

- 产品名：学习通PLUS，Windows 桌面应用。
- 当前目标平台只有超星学习通。后续开发保持单平台，不加入其他网课平台入口。
- 界面为 Qt Quick（QML）+ FluentWinUI3 样式，跟随系统浅色/深色，也可在设置里固定。
- 首页左栏是仪表盘和基本参数，右栏是只读可视化面板（视频 / 答题）。可视化面板静音、不可操作。
- Windows 用户数据路径 `%APPDATA%\ChaoxingDesktop` 是为兼容已有配置而保留的，修改前先确认迁移影响。

## 代码结构

- `gui.py`：入口，创建 QGuiApplication 和 QML 引擎，设置 FluentWinUI3 样式，交给 `ui/startup.py`。
- `ui/startup.py`：`StartupLoader`。先显示 `Splash.qml`，再在后台依次读取配置、检查运行组件、异步编译 `Main.qml`、异步创建主窗口，并把进度报告给启动画面。启动画面要等打字动画结束且加载完成才关闭，然后显示主窗口。交接动画：启动画面先让主窗口显示，再淡出卡片；`Main.qml` 的 `introLogo` 在屏幕中心（启动画面原位置）画同样的图标和文字，然后移动、缩小到导航栏左上角的 `brandIcon`（`brandRow` 在此期间隐藏）。只在显示过启动画面（`startup.splashShown`）且开启界面动画时运行。安卓版 `Splash.kt` 做同样的动画。
- `ui/qml/Onboarding.qml`：首次启动引导（欢迎 > 免责声明 > 账号 > 高级设置 > 开始使用）。高级设置一步直接嵌入 `AdvancedOptions`（`embedded: true` 不显示卡片标题，`stacked: true` 三部分依次排列而不是标签页），缺必填项时（`controller.answerSetupProblem`）不能下一步，可“稍后配置”。免责声明一步要求用户在输入框里完整写一遍声明（忽略空白；声明文字可选中复制，但界面不提示），一致后才能继续。账号一步可以“稍后配置”，之后运行面板顶部会一直显示提醒条，导航“设置”上有闪烁的提醒点，点“开始运行”会直接跳到设置。完成状态存在 QSettings 的 `onboarding/done` 和 `onboarding/version`；**改动引导界面时把 `ui/controller.py` 的 `ONBOARDING_VERSION` 加 1**，所有完成过旧版引导的用户下次启动都会重新看到引导；设置页“关于”里可以重新打开。开发时设置 `CHAOXING_DESKTOP_ONBOARDING=1` 可强制显示。
- `ui/qml/AppButton.qml`、`AppCheckBox.qml`、`AppSwitch.qml`、`AppTextField.qml`、`BaseDialog.qml`：自绘控件，外观不依赖 Quick Controls 样式（打包版若样式回退也保持一致）。新增按钮/勾选框/开关/对话框请用这些，不要直接用 `Button` / `CheckBox` / `Switch` / `Dialog`。动画时长统一用 `Theme.fast / normal / slow`。
- `installer/setup.py` + `installer/qml/Setup.qml`：自制安装程序（欢迎 > 许可协议 > 安装选项 > 正在安装 > 完成），复用 `ui/qml` 的控件和 `Theme`。按当前用户安装到 `%LOCALAPPDATA%\Programs\学习通PLUS`，写 `HKCU\...\Uninstall\XueXiTongPlus`，可选桌面和开始菜单快捷方式。发行 zip 直接追加在安装程序 exe 末尾，`zipfile` 从文件尾部找到它；开发时用 `python installer\setup.py --payload dist\XueXiTong-Plus-Windows-<版本>.zip`。`--silent [--dir 路径] [--no-shortcuts]` 静默安装。日志在 `%TEMP%\xxtplus-setup.log`。
- `ui/runtime_deps.py`：外部运行组件。MSVC 运行库已打进包里；唯一需要系统提供的是 Microsoft Edge WebView2 运行时（视频预览）。安装程序在“安装选项”页显示检测结果（读 EdgeUpdate 注册表的 `pv`），缺少时安装过程中从 `go.microsoft.com` 下载 Evergreen 引导程序，用 `Get-AuthenticodeSignature` 确认是有效的 Microsoft 签名后 `/silent /install`（非管理员时按当前用户安装）。失败只在完成页提示，不让安装失败。`--silent` 安装同样会装，`--no-deps` 跳过。
- `ui/winsetup.py`：安装和卸载共用的注册表、快捷方式、进程检查逻辑。安装目录里会写 `.xxtplus-install` 标记文件，卸载只删除带这个标记的目录。
- `ui/uninstall.py` + `ui/qml/Uninstall.qml`：卸载程序就是 `学习通PLUS.exe --uninstall`（`--quiet` 无界面，默认清除账号数据，`--keep-account` 保留）。删除快捷方式和注册表项；“清除账号数据”默认勾选（清空 config.ini 的账号密码、关闭 cookies 登录、删除 cookies.txt），也可删除整个 `%APPDATA%\ChaoxingDesktop` 和 QSettings。退出后由 cmd 延迟删除程序目录。
- `ui/updater.py` + `ui/qml/UpdateDialog.qml`：联网更新。查询 `Kerxs/XueXiTong-Plus` 的 latest release，找文件名含 setup 的 `.exe` 资源，下载到 `%TEMP%\xxtplus-update`，用 GitHub 提供的 `digest`（sha256）校验后启动安装程序并退出。仓库名改了要同步改 `REPO`。只有打包版会在启动时自动检查（`XXTPLUS_UPDATE_CHECK=1` 可在开发时强制）。发布新版本：改 `APP_VERSION` → 构建 → 新建 tag `v<版本>` 的 Release，上传 Setup.exe（和 zip）。发行文件名必须是 ASCII（`XueXiTong-Plus-…`）：GitHub 会删掉资源名里的中文字符。
- `packaging/app.spec` / `packaging/setup.spec` / `packaging/prune.py`：PyInstaller 打包。GUI 和 worker 打进同一个目录，共用一个 `_internal`（worker 不再是单文件，启动任务时不用解压）。`prune.py` 去掉不用的 Qt 模块（3D、Charts、多媒体、其他控件样式、Qt5Compat、测试/设计器辅助库、翻译、软件 OpenGL 等）、多余的平台和图片格式插件、ddddocr 不加载的两个模型。OpenCV（约 83 MB）整个不打包：ddddocr 导入时要 `import cv2`，但 `api/captcha.py` 只用文字识别（`classification`，只用 Pillow），所以 worker 里放的是 `packaging/stubs/cv2` 占位模块，任何 OpenCV 调用都会报错说明。以后若要用滑块/目标检测，必须恢复真正的 OpenCV。注意 `PySide6.QtQuick` 依赖 `QtOpenGL.pyd`，不能删。改了裁剪规则后要跑 `tests/test_packaging_and_cleanup.py` 并启动打包版看 `gui.log`。
- 安装程序末尾追加的是 `packaging/make_payload.py` 生成的 LZMA zip（比 Deflate 小约四分之一）；单独发布的免安装 zip 仍用 Deflate，因为 Windows 资源管理器打不开 LZMA zip。`setup.spec` 必须保留 `lzma` 隐式导入。
- 性能：日志超过上限时只删最前面的行（不要改回整表重置，那会让日志面板每秒重建所有行）；`Theme.onScreen`（主窗口隐藏到托盘或最小化时为 false）让无限循环动画用 `Theme.loopMotion` 停下，视频预览也在最小化时释放、恢复后按任务进度重新打开。
- 设置页的界面偏好（主题、动画、启动动画、运行结束提醒、自动检查更新、关闭到托盘）都存 QSettings；`Theme.motion` 为 false 时所有 `Theme.fast/normal/slow` 变成 0，循环动画也停止。
- `ui/localmodels.py`：高级选项里“自动检测本机模型”。候选端口 = 常见默认端口（llama.cpp 8080、Ollama 11434、LM Studio 1234、vLLM 8000、5000/5001）+ 当前接口地址的端口 + 本机所有监听端口；对每个端口请求 `http://127.0.0.1:<端口>/v1/models`（不走代理，并发、短超时）。监听端口要同时问 `netstat` 和 PowerShell `Get-NetTCPConnection`：实测有 llama-server 只有后者能看到，状态列也可能是空的/本地化的，所以按“远端端口为 0”判断监听。llama.cpp 返回的模型名是 .gguf 路径，取文件名作为模型名称。
- `ui/videoproxy.py`：视频预览的本地代理（只监听 127.0.0.1，只代理已登记的 `*.chaoxing.com` / `*.cldisk.com` 地址；视频 CDN 实际在 `s1/s2.cldisk.com`）。WebView2 的 `loadHtml()` 实际是 data: URL，CDN 收不到学习通的 Referer 会拒绝视频；现在预览页面和视频都由代理提供，代理转发时带上 Referer 并透传 Range。
- `api/pause.py`：暂停 / 继续。GUI 暂停时创建 `%APPDATA%\ChaoxingDesktop\pause.flag`（路径经环境变量 `CHAOXING_PAUSE_FILE` 传给 worker），继续时删除。worker 在 `process_job` 开头和视频循环里调用 `wait_if_paused()`，视频循环把等待的秒数加到 `last_iter`，所以暂停时间不算观看时长、继续后进度不会跳。不要改成挂起进程：那样恢复后会把暂停时间算进进度。开始、停止、任务结束和退出时都会清掉标记。
- 主窗口是无边框窗口（`Qt.FramelessWindowHint`），标题栏和 最小化 / 最大化 / 关闭 按钮在 `Main.qml` 里自绘；拖动标题栏移动、双击最大化，边缘和四角的 `ResizeEdge` 调整大小。最大化不用 `showMaximized()`（无边框窗口会盖住任务栏），而是铺满 `screen.desktopAvailable*` 并记住还原尺寸；QSettings 只保存还原尺寸。关闭按钮走 `window.close()`，所以仍会按设置隐藏到托盘。
- `ui/tray.py`：后台模式（系统托盘 + 单实例）。关闭窗口默认隐藏到托盘，任务继续；再次启动程序会唤出已运行的窗口。所有真正退出的路径都走 `Main.qml` 的 `quitApp()`。
- 编码：打包版 worker 不认 `PYTHONUTF8`，`worker.py` 启动时强制 stdout/stderr 为 UTF-8；GUI 用 `StreamDecoder` 增量解码，遇到非 UTF-8 自动改用 GB18030。
- 运行日志和设置界面里不显示本机完整路径（统一写 `%APPDATA%\ChaoxingDesktop`），避免截图泄露用户名。
- `ui/controller.py`：`AppController`，暴露给 QML 的 `controller`。负责 `config.ini` 读写、启动/停止 worker、写 worker 标准输入（课程选择、Y/n 确认）、主题和预览数据。
- `ui/output_parser.py`：把 worker 输出解析成事件（loguru 日志、tqdm 进度、课程列表、输入提示、预览事件）。纯 Python，无 Qt 依赖。
- `ui/models.py`：日志模型（级别过滤、1200 行上限）和任务进度模型。
- `ui/qml/`：界面。`Main.qml` 是窗口和导航，`DashboardPage.qml` / `SettingsPage.qml` 是两个页面，`Theme.qml` 是颜色 token 单例（由 `qmldir` 注册），其余是组件。
- `worker.py`：桌面版子进程入口，负责切换到用户数据目录后调用 `main.py`。
- `main.py`：原命令行任务入口；桌面子进程通过它运行现有任务处理逻辑。
- `api/base.py`：学习通课程与任务处理，包括视频状态读取、进度上报和答题。
- `build_windows.ps1`：准备便携 Python、安装依赖、分别构建 worker 和 GUI，并生成发行 zip。
- `README_DESKTOP.md`：桌面版安装和使用说明。
- `assets/chaoxing_official.jpg`：学习通官方 App Store 图标原图。
- `assets/render_icon.py`：在原图左上方加 PLUS 字样，生成程序窗口用 PNG 和 exe 用 ICO。

## 预览数据流

GUI 启动 worker 时设置 `CHAOXING_DESKTOP_PREVIEW=1`（以及 `PYTHONUNBUFFERED=1`）。`api/base.py` 通过标准输出发送两种事件行，`ui/output_parser.py` 解析，不会进入普通日志：

- `__CX_VIDEO_PREVIEW__{"source","title"}`：获取视频状态后发送。`ui/controller.py` 生成静音、无控件的 HTML，交给 `VideoView.qml` 里的 WebView。Windows 构建使用 Qt WebView 的 native/WebView2 后端，运行机器需要 WebView2 Runtime。WebView2 后端不支持 `loadHtml` 的 base URL（页面按 `about:blank` 处理）。
- `__CX_WORK_PREVIEW__{...}`：`study_work` 填好答案、提交前发送 `phase=filled`（题目、选项、所填答案、来源、覆盖率），提交后发送 `submitted` / `saved` / `failed`。由 `_emit_work_preview` 输出，异常全部吞掉，不影响答题流程。题目一读取到就先发 `phase=questions`（答案未填，界面显示“查找中”），不必等查找答案结束。每题带 `source`（cover / random）和 `origin`（找到答案的来源：`tiku` 题库或 `ai` 大模型，来自各题库类的 `ORIGIN` 和 `Tiku.last_origins`），面板据此显示 题库匹配 / AI匹配 / 随机作答。答案缓存 `cache.json` 格式不变，来源另存在 `cache_origin.json`，旧缓存没有记录的按题库算。`WorkView.qml` 用 QML 原生绘制，不加载学习通网页。

视频预览地址必须来自学习通视频状态响应并通过现有域名检查。真实课程画面尚未用用户账号验证，若调整该流程，需要分别检查无可用地址、加载失败和任务结束时的面板状态。

原生 WebView 会盖住 QML 弹层，所以对话框打开时 `VideoView` 会被暂停显示（`suspended`）。

WebView2 在创建时就定下可见性：在主窗口还藏在启动画面后面、或 WebView 本身隐藏时创建的，之后即使显示出来，页面的 `document.visibilityState` 仍是 `hidden`，Chromium 不会加载 `<video>`（表现为白屏、代理收不到 `/v/` 请求）。所以 `VideoView` 用 `Loader` 只在真正显示时创建 WebView，每次显示都新建一个；不要改回常驻 WebView + 切换 `visible`。

## worker 标准输入

`main.py` 会在两处调用 `input()`：课程 ID 为空时选择课程、大模型连接检查失败时 Y/n 确认。GUI 识别这两种提示后弹出对话框，再把答案写入 worker 标准输入。新增 `input()` 调用时要同步更新 `ui/output_parser.py`，否则任务会卡住。

## 界面开发测试

非打包模式下，环境变量 `CHAOXING_DESKTOP_FAKE_WORKER=<脚本路径>` 会让 GUI 用指定脚本代替 `worker.py`，便于不登录就测试界面。设置 `APPDATA` 到临时目录可避免改动真实配置。

## 构建

在 Windows x64 PowerShell 中执行：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\build_windows.ps1
```

构建会联网准备便携 Python 和 Python 依赖。结果位于 `dist\学习通PLUS`，压缩包为 `dist\XueXiTong-Plus-Windows-<版本>.zip`，安装程序为 `dist\XueXiTong-Plus-Setup-<版本>.exe`（版本号取自 `ui/controller.py` 的 `APP_VERSION`）。构建会删除 Qt qml 目录里的 `objects-*` 编译残留，它们路径过深，安装时会超过 Windows 路径长度限制。界面的 Qt 日志写在 `%APPDATA%\ChaoxingDesktop\gui.log`，排查打包版问题先看这里。发行目录中的 `学习通PLUS.exe`、`chaoxing-worker.exe` 和 `_internal` 必须一起保留。

依赖清单：`requirements-desktop.txt`、`requirements-build.txt`。现有自动化测试位于 `tests/`。

## 开发注意事项

- 不要把真实账号、密码、cookies、个人 `config.ini` 或运行日志加入版本控制或交接包。
- 配置模板是 `config_template.ini`；用户配置在 `%APPDATA%\ChaoxingDesktop\config.ini`。
- UI 与 worker 通过进程标准输出通信，新增日志或事件时避免破坏 `__CX_VIDEO_PREVIEW__` / `__CX_WORK_PREVIEW__` 消息解析；解析规则的测试在 `tests/test_output_parser.py`。
- 修改打包相关内容时，检查 `ui/qml` 资源、Qt WebView 插件、图标资源和 worker 是否都进入发行目录。
- 界面偏好（主题、窗口尺寸）保存在 QSettings，不写入 `config.ini`。
- 变更 API、配置兼容或任务流程前，先保留现有配置键和学习通运行行为；做完变更后运行相关测试并构建桌面包。

## 共用核心（`core/`）与运行稳定性

- `core/`：两端共用、无 Qt / 安卓依赖的业务逻辑。`core/settings.py`（开始前检查 `start_problem`、引导检查 `guide_problem`，提示文字两端一致）、`core/courses.py`（识别课程，worker `--list-courses` 和安卓都调用）、`core/account.py`（清除账号数据、日志文件、日志大小；`ui/winsetup.py` 转调它）。新增共用逻辑放这里，平台代码只做适配。
- `api/logger.py`：loguru 的 `enqueue=True` 需要 multiprocessing（sem_open），安卓没有，曾导致手机一运行就报错；现在用 `can_enqueue()` 探测。日志脱敏：`main.register_config_secrets` 登记账号、密码、TOKEN、API Key、推送地址，日志和推送消息里替换为 `***`。不要在日志里打印 cookies 值或请求头里的 Cookie / Authorization（`api/base._safe_headers`）。
- `api/net.py`：网络断开时 `JobProcessor` 等网络恢复再重试该章节，不占用重试次数；章节处理抛异常不再让工作线程退出（以前会导致 `task_queue.join()` 永久卡住）。`SessionManager` 的重试带退避，超时 (10, 20) 秒。登录时没网也会等网络恢复后重试。
- 视频：倍速已失效，固定 1 倍速（`main.py` 强制；桌面和手机的倍速选项都显示“已失效”）。`Chaoxing.required_watch_ratio` 读取任务点的 `rt`（0.9 / 1），看到要求比例时立即上报，平台确认 `isPassed` 即结束。
- AI 客户端超时 120 秒、重试 2 次（openai 默认 600 秒）。题库请求携带 TOKEN 时校验 HTTPS 证书；只有自建的 TikuAdapter 不校验。
- 推送服务 `Local`（本机通知）：`api.notification.set_local_handler` 注册后可用；安卓注册为系统通知，桌面未注册（选项只在手机上出现）。

## 安卓版（`android/`，开发中）

- Kotlin + Compose + Chaquopy，构建时从仓库根目录复制 `main.py`、`api/*.py`、`core/*.py`、`ui/output_parser.py`、`ui/advanced.py`、`ui/cloudmodels.py`，所以这些文件里不能引入 Qt、Windows 专用依赖或 multiprocessing。详见 `android/README.md`。
- 手机功能与桌面对齐：设置是二级菜单（`SettingsPages.kt`）、识别课程（`Courses.kt`）、检查更新（`Updater.kt`，.part 下载 + SHA-256 校验后交给系统安装器）、cookies 导入、数据与隐私、关于。引导：欢迎 > 免责声明 > 账号 > 答题来源 > 权限设置（推送不在引导里，手机默认本机通知）。
- 稳定性：`TaskService` 运行时持有唤醒锁 + Wi-Fi 锁，记录网络断开/恢复；界面每 5 秒检查 `:worker` 进程，被系统杀掉时显示“已退出”。小屏（高度 < 640dp）运行面板整体可滚动。
- 手机上没有真正的 `openai` 包（pydantic-core / jiter 没有安卓版本），用的是 `android/app/src/main/python/openai` 精简替代。`api/answer.py` 若用到 openai 的新接口或新错误类型，要同步补到替代模块里。
- 手机只用模型公司的云服务 API：没有本机模型、自定义接口地址和代理（`xxtplus_android.py` 里过滤设置字段）。
- `tests/test_android_bridge.py` 在桌面 Python 上测试桥接和 openai 替代模块。
- 界面与桌面版一致：`Theme.kt` 的颜色、圆角、动画时长和 `ui/qml/Theme.qml` 相同，`Components.kt` 对应 AppButton / Card / StatTile / StatusPill / Segmented / QuestionCard。改桌面版样式时同步改这两个文件。
- 图标：`assets/render_android_icon.py` 从桌面图标生成启动器图标、应用内品牌图和通知图标；桌面图标改了要重新运行。自适应图标的 PLUS 徽标比桌面版往里移了一些，圆形遮罩下才不会被裁掉。
