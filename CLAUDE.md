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
- `ui/uninstall.py` + `ui/qml/Uninstall.qml`：卸载程序是安装目录里的 `卸载学习通PLUS.exe`（`build_windows.ps1` 复制 `学习通PLUS.exe` 得到，同一个启动器、共用 `_internal`；`gui.py` 按文件名 `winsetup.UNINSTALL_EXE` 进入卸载模式），旧的 `学习通PLUS.exe --uninstall` 仍可用（`--quiet` 无界面，默认清除账号数据，`--keep-account` 保留）。注册表 `UninstallString` 指向卸载器（`winsetup.uninstall_commands`）。打包版启动时 `winsetup.ensure_registered` 在后台检查：带安装标记的目录若缺少“应用和功能”条目、或条目版本/位置/卸载命令过时，就重新写入。删除快捷方式和注册表项；“清除账号数据”默认勾选（清空 config.ini 的账号密码、关闭 cookies 登录、删除 cookies.txt），也可删除整个 `%APPDATA%\ChaoxingDesktop` 和 QSettings。退出后由 cmd 延迟删除程序目录。
- `ui/updater.py` + `ui/qml/UpdateDialog.qml`：联网更新。查询 `Kerxs/XueXiTong-Plus` 的 latest release，找文件名含 setup 的 `.exe` 资源，下载到 `%TEMP%\xxtplus-update`，用 GitHub 提供的 `digest`（sha256）校验后启动安装程序并退出。仓库名改了要同步改 `REPO`。只有打包版会在启动时自动检查（`XXTPLUS_UPDATE_CHECK=1` 可在开发时强制）。发布新版本：改 `APP_VERSION` → 构建 → 新建 tag `v<版本>` 的 Release，上传 Setup.exe（和 zip）。发行文件名必须是 ASCII（`XueXiTong-Plus-…`）：GitHub 会删掉资源名里的中文字符。
- `packaging/app.spec` / `packaging/setup.spec` / `packaging/prune.py`：PyInstaller 打包。GUI 和 worker 打进同一个目录，共用一个 `_internal`（worker 不再是单文件，启动任务时不用解压）。`prune.py` 去掉不用的 Qt 模块（3D、Charts、多媒体、其他控件样式、Qt5Compat、测试/设计器辅助库、翻译、软件 OpenGL 等）、多余的平台和图片格式插件、ddddocr 不加载的两个模型。OpenCV（约 83 MB）整个不打包：ddddocr 导入时要 `import cv2`，但 `api/captcha.py` 只用文字识别（`classification`，只用 Pillow），所以 worker 里放的是 `packaging/stubs/cv2` 占位模块，任何 OpenCV 调用都会报错说明。以后若要用滑块/目标检测，必须恢复真正的 OpenCV。注意 `PySide6.QtQuick` 依赖 `QtOpenGL.pyd`，不能删。改了裁剪规则后要跑 `tests/test_packaging_and_cleanup.py` 并启动打包版看 `gui.log`。
- 安装内容（1.3.0，`installer/payload.py`，无 Qt，可单独测试）：追加在安装程序 exe 末尾的是 `[JSON 头][一条 .tar.xz 流][尾部：魔数 + 两个长度]`，不再是 LZMA zip。两点让它从 74 MB 降到 30 MB：整体压缩（按扩展名排序、x86 过滤器、64 MB 字典）；安装程序自带的 Qt / Python 文件不重复存放——`packaging/setup.spec` 写出 `.build/setup-manifest.json`（安装程序自身目录里每个文件的 sha256），`make_payload.py` 把哈希相同的发行文件记为 `shared`，安装时从 `sys._MEIPASS` 复制并再次校验。所以**构建顺序是先安装程序、后安装内容**（`build_windows.ps1`）。`--payload <发行 zip>` 仍可用。`setup.exe --extract <目录>` 只解包（不写注册表、不建快捷方式）：验证构建时用它解到临时目录再与 `dist\学习通PLUS` 逐文件比哈希。单独发布的免安装 zip 仍是 Deflate。
- 打包裁剪（1.3.0）：`onnxruntime/capi/onnxruntime.dll` 不打包（Python 模块不加载它）；任务进程不打包官方 `openai` / pydantic / jiter，用的是 `android/app/src/main/python/openai` 那份精简客户端（`app.spec` 作为数据文件放进 `_internal/openai`）——所以 `api/answer.py` 用到 openai 的新接口时，两端都要看这份精简客户端。`chaoxing-worker.exe --selftest` 加载并实际使用每个重组件（验证码识别、AI 客户端、lxml、字体、加密、任务模块），**每次改打包内容后都要跑**。体积数字和验证记录在 `docs/1.3.0/size.md`。
- 性能：日志超过上限时只删最前面的行（不要改回整表重置，那会让日志面板每秒重建所有行）；`Theme.onScreen`（主窗口隐藏到托盘或最小化时为 false）让无限循环动画用 `Theme.loopMotion` 停下，视频预览也在最小化时释放、恢复后按任务进度重新打开。
- 设置页的界面偏好（主题、动画、启动动画、运行结束提醒、自动检查更新、关闭到托盘）都存 QSettings；`Theme.motion` 为 false 时所有 `Theme.fast/normal/slow` 变成 0，循环动画也停止。
- `ui/localmodels.py`：高级选项里“自动检测本机模型”。候选端口 = 常见默认端口（llama.cpp 8080、Ollama 11434、LM Studio 1234、vLLM 8000、5000/5001）+ 当前接口地址的端口 + 本机所有监听端口；对每个端口请求 `http://127.0.0.1:<端口>/v1/models`（不走代理，并发、短超时）。监听端口要同时问 `netstat` 和 PowerShell `Get-NetTCPConnection`：实测有 llama-server 只有后者能看到，状态列也可能是空的/本地化的，所以按“远端端口为 0”判断监听。llama.cpp 返回的模型名是 .gguf 路径，取文件名作为模型名称。
- `ui/cloudmodels.py`：AI 服务商。`PROVIDERS` 每项有 `region`（cn 国内 / intl 海外，界面按 `REGIONS` 分组）、`endpoint`、`hosts`（按域名识别）、`console`（“获取 API Key”链接）。自定义服务商存在 `config.ini` 的 `[tiku] custom_providers`（JSON 列表 `{name, endpoint}`，`advanced.py` 里是 `hidden` 类型字段，没有自己的控件，由“服务商”字段编辑）；`custom_problem()` 校验（手机 `cloud_only`：只能 https、不能本机地址）。手机开始运行要求接口地址是内置服务商或已保存的自定义服务商（`core/settings._cloud_problem`）。界面上“服务商”是一行，点开是二级菜单“选择服务商”（分类 国内 / 海外 / 自定义 → 该分类的服务；桌面 `ProviderPickerDialog.qml`，手机 `Settings.kt` 的 `ProviderPicker` 全屏对话框），自定义服务在“自定义”分类里添加、删除。新增服务商时补上 `console`，`tests/test_cloudmodels.py` 会检查。QML 里不能用 `console` 作属性名。
- 手机视频预览：`PreviewPlayer.kt`（系统 MediaPlayer + TextureView，静音、不申请音频焦点），请求时带与 `ui/videoproxy.py` 相同的 Referer / User-Agent（CDN 没有这个 Referer 会拒绝）。不用 WebView：网页无法发出这个 Referer。
- `ui/videoproxy.py`：视频预览的本地代理（只监听 127.0.0.1，只代理已登记的 `*.chaoxing.com` / `*.cldisk.com` 地址；视频 CDN 实际在 `s1/s2.cldisk.com`）。WebView2 的 `loadHtml()` 实际是 data: URL，CDN 收不到学习通的 Referer 会拒绝视频；现在预览页面和视频都由代理提供，代理转发时带上 Referer 并透传 Range。
- 桌面稳定性（`ui/controller.py`）：运行期间 `ui/keepawake.py` 阻止系统自动睡眠（`SetThreadExecutionState`，屏幕仍可关闭；合盖按电源设置）。任务进程意外退出（退出码不是 0、不是用户停止、不是 `main.EXIT_STOPPED`=2）或 `HANG_SECONDS`（20 分钟）没有任何输出（暂停、等用户选课程 / 回答时不算）时，`RESTART_DELAY_MS` 后自动重新开始，最多 `MAX_RESTARTS`=3 次，正常运行超过 30 分钟后重新计数；重启时自动沿用之前选的课程和 Y/n 回答。等待重启时 `running` 仍为 true，“停止”可取消。登录失败、章节重新登录后仍失败用退出码 2，不会重启。`api/net.py` 等网络时每 5 分钟输出一行，避免被当成卡住。
- 章节内容与保底（不卡住）：读取章节任务点 HTTP 出错时 `get_job_list` 抛错（按失败重试），不再当成“没有任务点”直接算完成；只有文字等内容、没有任务点的章节记一条日志并访问一次页面。章节检测页面没有题目时按页面文字分类（`api/base.classify_empty_work_page`）：已提交 / 待批阅 → 算完成；已截止 / 未开始 / 空 → `StudyResult.NEEDS_USER`（不算失败、不重试），`main.process_job` 交给 `api/manual.py` 提醒用户；只有真正的请求错误才算失败。不认识的任务点按卡片的 type / module / resourceType 命名（`decode._content_kind`，`manual.KIND_LABELS`）。应用里（`CHAOXING_DESKTOP_PREVIEW=1`）跳过需要终端输入的“手动输入题库”。密码登录请求也有超时。
- 视频预览恢复（桌面）：预览页出错不再停在“视频加载失败”，按 2/4/8/16/30 秒重试并回到任务位置，长时间卡住也会重载；第 3 次失败请求 `/f/<token>`。代理（`ui/videoproxy.py`）对连不上的地址重试一次，视频服务器拒绝（401/403/404/410）或页面放弃时回调 `on_problem`；`AppController._on_preview_problem` 每个视频只记一条日志，并最多每 90 秒写一次 `preview_refresh.flag`，任务进程在视频循环里看到后重新读取视频状态并再发一次 `__CX_VIDEO_PREVIEW__`（新地址）。手机 `PreviewPlayer` 同样重试，第 3 次失败写同一个标记文件。手机 `TaskService` 也有 20 分钟无输出的卡住检测（结束进程后由 START_STICKY 重新开始）。
- `api/pause.py`：暂停 / 继续。GUI 暂停时创建 `%APPDATA%\ChaoxingDesktop\pause.flag`（路径经环境变量 `CHAOXING_PAUSE_FILE` 传给 worker），继续时删除。worker 在 `process_job` 开头和视频循环里调用 `wait_if_paused()`，视频循环把等待的秒数加到 `last_iter`，所以暂停时间不算观看时长、继续后进度不会跳。不要改成挂起进程：那样恢复后会把暂停时间算进进度。开始、停止、任务结束和退出时都会清掉标记。
- 窗口动画：最小化 / 隐藏到托盘 / 退出时窗口淡出并略微缩小（`fadeOutThen`），回到屏幕时淡入；最大化 / 还原不逐帧改窗口尺寸（这个窗口每次改尺寸代价大，动画会直接跳到终点），而是“淡一下 → 一次改尺寸 → 缩放淡入”（`maximizeFx`）。拖动最大化窗口还原时不加动画。关闭动画时 `Theme.motion` 为 false 全部立即完成。
- 关闭窗口：`tray.closeAction` = ask（默认，弹窗选“后台运行 / 直接退出”，可勾“以后都这样”）/ tray / quit，存在 QSettings `ui/closeAction`；旧版 `ui/closeToTray=false` 迁移为 quit。设置页“运行”卡片里可改。
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
- `core/secret.py`：账号数据加密保存。`config.ini` 里 `SECRET_KEYS` 列出的字段（账号、密码、TOKEN、API Key、推送地址）和 `cookies.txt` 存为 `enc:v1:<base64>`；Windows 用 DPAPI（当前用户），安卓用 `DataKey.kt` 生成、由系统密钥库包装的数据密钥（经 `XXTPLUS_DATA_KEY` 传给 Python，AES-CTR + HMAC），两者都没有时保持明文。没有前缀的旧明文照常读取，启动时 `migrate()` 顺带加密。解不开的值（复制到别的电脑 / 账户）读作空，让用户重填。读写 `config.ini` 一律用 `secret.read_config` / `secret.write_config`（无插值，密码里的 `%` 不再报错），不要直接用 `ConfigParser`；新增敏感字段时加到 `SECRET_KEYS`。
- 章节重试（`main.JobProcessor`）：一个章节失败 5 次（`max_tries`）后重新登录（多个章节同时到达时一分钟内只登录一次）、重新读取该课程的章节列表，再试 5 次；仍失败、或重新登录失败，就抛 `RunStopped` 停止整次运行，`main()` 记一条说明（哪一章、最后的错误、可能原因）并推送，退出码 1。网络断开不计次数。
- `SessionManager`（`api/base.py`）只建一次 `requests.Session`：`get_instance()` 每次都会调用 `__init__`，以前每个请求都重建会话、重新解密 cookies.txt 并丢下未关闭的连接（手机日志里的 ResourceWarning）。`main.py` 忽略 ResourceWarning。
- `api/net.py`：网络断开时 `JobProcessor` 等网络恢复再重试该章节，不占用重试次数；章节处理抛异常不再让工作线程退出（以前会导致 `task_queue.join()` 永久卡住）。`SessionManager` 的重试带退避，超时 (10, 20) 秒。登录时没网也会等网络恢复后重试。
- 视频：倍速已失效，固定 1 倍速（`main.py` 强制；桌面和手机的倍速选项都显示“已失效”）。“看到 90% 即完成”已失效并已删除（1.2.5）：每个视频都看到结尾，平台确认 `isPassed` 即结束；任务点的 `rt` 只作为上报参数原样带回（`Chaoxing._job_rt`）。
- AI 客户端超时 120 秒、重试 2 次（openai 默认 600 秒）。题库请求携带 TOKEN 时校验 HTTPS 证书；只有自建的 TikuAdapter 不校验。
- 自动化范围：视频（含音频）和章节检测总是自动；课件 / 文档（`common.auto_documents`，`main.AUTO_DOCUMENTS`，`Chaoxing.study_document`，失败转手动提醒、不重试）和作业（`common.auto_homework`、`common.homework_submit`）可在“高级选项 → 自动完成”开关，默认都开。阅读、直播、问卷、讨论等以及解码器不认识的任务点交给 `api/manual.py`：写日志、输出 `__CX_MANUAL_TASK__` 事件、有推送服务时推送，运行结束时汇总。界面：配置了推送（手机：本机通知且有通知权限）只提示；没有推送时弹窗列出（桌面 `manualDialog`，手机 `RunDialogs`）。
- 作业与课堂活动（`api/homework.py`，章节处理完后逐门课程执行）：课程页（`visit/stucoursemiddle` 跳到 `mooc2-ans/mycourse/stu`）隐藏字段 `workEnc` → 作业列表 `mooc2/work/list?courseId&classId&cpi&ut=s&enc`，每项 `<li data=".../mooc2/work/task?...workId&answerId&enc">`、`p.overHidden2` 标题、`p.status` 状态（结构已用真实账号核对）。只做未完成且未截止的；作答页按隐藏字段 `answertype<id>` 找题，题目格式与 `decode_questions_info` 相同，查答案用 `Chaoxing._fill_answers`、提交用 `Chaoxing._post_work_form`（两者从 `study_work` 抽出，章节检测共用），`pyFlag` 由 `homework_submit` 决定。作答页结构和提交返回尚未用真实未交作业验证。课堂活动（`mobilelearn …/active/student/activelist`）：activeType 42 随堂练习、35 课堂任务，进行中（status 1）的只提醒（`common.watch_activities`），不能自动作答。一份作业出错只跳过并提醒，不影响其他作业和整次运行。
- 附件类型（`decode.file_kind` / `file_label`）：卡片类型不是 document / video 的附件按播放模块和扩展名识别——Word / PPT / PDF / txt / Excel / WPS / CAJ / epub 等按课件完成（`DOCUMENT_EXTENSIONS`、`DOCUMENT_MODULES`），mp3 等音频、mp4 等视频按音视频任务点（需要卡片有 `mid`）。课件任务带 `file_label`（“PDF”“PPT 课件”…），日志和“需要手动完成”列表用它命名。
- 视频进度上报的 `isdrag` 与学习通播放器一致：开头 3、播放中 0、到结尾 4（以前全程都是 3，结尾常不被确认：“视频已到末尾，但平台连续8次未确认完成”是日志里最多的错误）。
- 章节检测成绩判断（`_parse_work_record_detail`）：很多课程不公布“正确答案”，结果页只有“我的答案”和对错标记（`span.marking_dui` 对 / `marking_cuo`、`marking_bandui` 错，已用真实页面核对）；没有正确答案时按标记判断，错题反馈“上次答案 X 判为错误，请换一个”。“答错后自动重做”默认开启；重做时拿不到题目（只允许作答一次）保留已提交的成绩、算成功，不让章节重试。
- 验证码（不改识别方法）：`video_progress_log` 里 3 次都过不去（常见是验证码图片 404）抛 `api.exceptions.CaptchaBlocked`；`JobProcessor._captcha_restart` 等 `CAPTCHA_COOLDOWN`（30 秒，尊重暂停）→ `_relogin(force=True)` → 章节重新入队（不计重试），每次运行最多 `MAX_CAPTCHA_RESTARTS`（3）次，之后提醒用户手动播放该视频（`manual` 类型 `captcha`）。
- 已批阅检测：`api/base.is_graded_work_page`（地址含 `selectWorkQuestionYiPiYue`，或有 `myAnswerBx` / `marking_*` 且没有 `answer<id>` 输入框）→ `study_work` 抛 `AlreadyGraded`，直接成功、不再作答和提交；作业同样跳过。以前章节重试会把已提交的检测再提交一遍。
- 视频完成确认（1.3.0）：到结尾只上报一次 `isdrag=4`；没确认就只读任务点卡片（`_card_passed`，3 / 6 / 12 秒后各一次），再上报**一次**（距第一次 ≥ 20 秒）并再读一次卡片（`Chaoxing._confirm_end`）。不要改回连发结尾上报：1.2.9 的 2/3/5/8 秒连发正是验证码的主要来源（日志里 65 次验证码有 60 次紧跟第 3 次结尾上报）。结尾上报遇到验证码不重启章节，记“待确认”。
- 视频结果标记：`study_video` 无论怎么结束都输出一行 `任务完成:` / `任务待确认:` / `任务未完成:`（`_study_video` 是原来的实现），界面据此结束进度行（`TaskModel.start` / `finish`，状态 running / done / pending / failed / stopped）。新增视频结束路径时不用再单独写日志。
- 章节调度（`main.JobProcessor`）：`need_unlock` 的章节先放在 `_held`，同一门课没有章节在进行时 `_release` 重新读取章节列表、把已开放的放进队列（都没显示开放就试下一个）。章节返回未开放而同课程还有章节在进行 → `_hold`（不计重试）；确实打不开 → `_drop_locked` 把后面仍锁着的章节一次性放弃。所有“章节结束”的出口都走 `_done`（先放行等待的章节，再 `task_done`，否则运行会提前结束）。
- 弹窗：`ConfirmDialog.countdown`（秒）到时间自动回答 / 关闭；“需要手动完成”60 秒自动关闭，Y/n 确认 60 秒自动选“继续”。任务点后来自动完成时 `manual.resolve` 发 `__CX_MANUAL_TASK__{…,"resolved":true}`，界面移除该项，列表空了自动关窗。
- 日志文件：默认 DEBUG（`CHAOXING_TRACE=1` 才写整页 HTML 的 TRACE），旧文件保留 30 天（`LOG_DAYS`），且最多 30 个（`LOG_FILES_MAX`，每个 10 MB）；登录用户名打码（`_mask_name`）。`CacheDAO` 按文件修改时间缓存解析结果。
- 视频预览备用：任务进程的 `__CX_VIDEO_PREVIEW__` 带 `sources`（全部可用地址，最好的在前）；桌面代理一个本地地址登记多个上游地址，每个先按系统代理 + certifi 证书、再直连各试一次（不用 requests，避免界面程序重复打包），被拒绝或连不上就换下一个，成功的记到最前；全部失败才 `on_problem(url, status, reason)`，日志写出原因。手机 `PreviewPlayer` 出错先换下一个地址再退避重试。
- 匿名统计（1.3.0 重写，`api/telemetry.py`，两端共用）：`common.telemetry` **默认开启**，引导的“匿名统计”页说明并可关闭（老用户配置里的 false 是旧默认值，首次启动改为开启一次：桌面 QSettings `telemetry/asked`，手机 prefs `telemetry_asked`）。只收固定分类名下的数字：`count` / `timing` / `gauge`，名字必须匹配 `_KEY` 白名单（否则丢弃——不要把课程名、题目等当 key 传）；崩溃用 `record_crash`（类型 + 程序内代码位置 + `scrub_text` 脱敏后的消息）。每个进程一份待发送队列 `telemetry_queue_<gui|worker>.json`（最多 50 条 / 200 KB），`flush()` 在后台线程用 urllib POST 到 `TELEMETRY_URL`（已填线上地址；**只有打包版和手机版会用它**，从源码运行——开发、测试、测量——不上传；为空则都不上传）。环境变量 `XXTPLUS_TELEMETRY_URL` 可以覆盖（只接受 https 或 127.0.0.1），设成 `off` 则一律不上传：**启动打包版做测试时必须设 `off`**，否则测试数据会进线上统计。关闭开关 = `configure(False)` → 删除 stats.json 和队列。任何失败都不影响任务。界面进程用 `process="gui"`（`AppController._start_telemetry`、`telemetryEnabled`）。新增统计项时把分类组加进 `_KEY`，并同步 `server/telemetry/worker.js` 的 `KEY`。“反馈问题”仍是手动打开预填的 GitHub Issue，软件里没有任何令牌。
- 统计后台（`server/telemetry/`）：Cloudflare Worker + D1。`POST /v1/report`（白名单校验、每安装每小时 30 条、不存 IP）、`GET /`（管理页面，无外部脚本）、`/api/summary` 和 `/api/export.csv`（`Authorization: Bearer <ADMIN_TOKEN>`，密码少于 12 位一律拒绝）、每天清理 90 天前的数据。测试 `node --test test/`（用 node:sqlite 代替 D1），本机预览 `node test/dev-server.js 8787 --sample`。已部署在仓库所有者的 Cloudflare 账号下（`https://xxtplus-telemetry.q26112419.workers.dev`，数据库 `xxtplus-telemetry`，`wrangler.toml` 里有 database_id）；改了 `worker.js` 后在该目录 `npx wrangler deploy`，改了表结构要 `wrangler d1 execute … --remote`。管理密码是 Worker 的 secret `ADMIN_TOKEN`，只有所有者知道。用户说明在根目录 `PRIVACY.md`。
- 直播（1.3.0）：以前直播任务点直接进“需要手动完成”，从不观看。现在 `common.auto_live`（默认开，`main.AUTO_LIVE`）时由 `api/live_process.LiveProcessor.run_live` 按直播时长逐分钟上报观看时长（1 倍速，尊重暂停，像视频一样输出 开始任务 / 进度 / 任务完成）；读不到直播状态或连续 3 次上报失败 → 转手动提醒。章节本身“未开放”（直播还没开始）时仍然只能等。已用两场真实回放验证（59 和 42 分钟，上报全部 `@success`，学习通显示完成）。完成判断：直播卡片常常没有顶层 `jobid`（任务的 jobid 是卡片 id，真正的在 `property._jobid`），`Chaoxing._same_card` 同时比较这几个 id 和 `liveId`；`_card_state` 返回 True / False / None（读不到或找不到卡片），`main.live_confirmed`：显示通过 → 完成；找不到卡片但时长全部提交成功 → 完成；卡片在但仍未通过（0 / 5 / 10 秒各看一次）→ 待确认。进度每秒刷新。预览：状态里有学习通域名的 mp4 回放地址才播放，否则 `__CX_VIDEO_PREVIEW__` 带 `message`（“直播观看中（这场直播没有可预览的画面）”），面板显示这句话（HLS 直播流预览播放不了）。
- 完成率（`main.unfinished_chapters` / `completion_report`）：章节处理完后重新读取每门课的章节列表，学习通仍未显示完成的章节再处理一遍（这一遍未开放的章节直接跳过）；运行结束再读一次，日志和结束推送里写“完成情况：课程 a/b 章（共 x%）”。只含问卷、讨论等需要手动内容的章节会一直未完成，补漏时只是重复提醒（同一项每次运行只提醒一次）。
- 题目图片（`api/images.py`，只用于“AI”答题来源）：题干和选项里的图片保留为 `<img src="…">`（`decode._extract_title` / `_extract_choices`、`homework.parse_work_page`）。设置 `tiku.image_mode`：`auto`（默认，先把图片直接发给答题模型，模型拒绝（HTTP 400/413/415/422 或报错提到 image）后本次运行改为转文字，`AI._vision_refused` 记住 (接口, 模型)）、`direct`（只直接发）、`transcribe`（先由识图模型 `tiku.vision_model` / `vision_endpoint` / `vision_key`（留空=答题模型）把每张图转成文字，公式 LaTeX、表格 Markdown，再把 `【图片内容：…】` 交给答题模型；同一张图每次运行只转一次）、`off`。图片经学习通会话下载（带 Referer），桌面有 Pillow 时缩到最长边 1280，每题最多 4 张。手机不显示识图模型地址和 Key（只用所选服务商）。不在代码里写死哪些模型能看图。硅基流动答题来源暂不处理图片。
- 开始引导（桌面 `Onboarding.qml`，`ONBOARDING_VERSION` 4；手机 `Screens.kt`，`ONBOARDING_VERSION` 2）：欢迎 > 免责声明 > 账号 > 自动完成 > 高级设置（手机：答题来源）> 开始使用（手机：权限设置）。自动完成一步列出“总是自动”的视频和章节检测，并只显示“自动完成”设置组（`AdvancedOptions.only`），高级设置一步用 `except` 排除它；最后一页汇总自动完成的选择。
- 引导只显示新内容（1.3.0）：`ui/controller.ONBOARDING_STEPS` 给每个步骤记“从第几版开始有 / 有变化”；`onboarding_plan(done, version, disclaimer)` 返回这次要显示的步骤和是否“只看新内容”。完成过旧版的用户只看到版本号更大的步骤，可以直接“跳过”；免责声明单独记 `DISCLAIMER_VERSION`，只有文字改了才再出现（旧值是应用版本号，按已接受第 1 版算）。**新增或改动步骤时：`ONBOARDING_VERSION` 加 1，并把该步骤的版本改成新值**（不要再让所有人从头走一遍）。手机对应 `MainActivity.kt` 的 `Guide`。上面“改动引导就全部重新显示”的旧说法作废。
- 多视频预览（1.3.0）：`AppController._videos`（按任务名）保存所有正在看的视频，单视频属性（`videoTitle`、`videoPageUrl`…）是“选中的那个”；`previewMode`（QSettings `ui/previewMode`）= single（一个视频 + `Pager` ‹ 1/4 › 切换）/ grid（`VisualPanel` 网格平铺，每格一个 `VideoView { slotTitle }`）/ off（不登记代理地址、不建题目列表）。答题保留最近 6 份（`_works`），用户手动切换后 30 秒内不自动跳到新的一份。`__CX_WORK_PREVIEW__` 的结果阶段现在带 `title`。手机 `RunState.videos` / `works` 同理。离屏渲染时 WebView2 会卡住，截图脚本要用真实窗口放到屏幕外。
- AI 费用（1.3.0）：`LLM_SYSTEM_PROMPT` 是所有题型共用的固定短提示词（便于服务商按缓存计费），题型规则、输出格式、上一轮反馈放在用户消息里；`AI._query_all` 把不含图片的题每 `tiku.ai_batch`（默认 5）题合成一次请求（`_query_batch`，按题号返回），缺的题或读不懂的回复逐题补问；重做轮只重新问反馈里出现的题（`Tiku._marked_wrong`），其余沿用缓存。
- 视频上报容错：进度上报请求失败（`state == 0`）不再直接算失败——没网就 `net.wait_for_network()`，有网则重试，连续 `REPORT_RETRIES`（4）次才失败。手机 `KeepAlive.backgroundNetworkHint` 在没关电池优化 / 开着流量节省时在日志里说明。
- 引导精简（1.3.0）：新用户的完整引导是 4 步——桌面 欢迎与声明 → 账号 → 答题来源 → 开始使用；手机 欢迎与声明 → 账号 → 答题来源 → 权限设置。免责声明和欢迎在同一页（`Onboarding.qml` 第 0 页，`needDisclaimer` 时显示声明和输入框，图标缩小；启动画面的图标仍落在这一页的图标上）。“自动完成”和“匿名统计”的开关在最后一页（手机在答题来源页底部），不再各占一步；只看新内容的老用户仍会单独看到新增的那一页。页面编号（`pageIndex` 0–6）没变，`plan()` 决定显示哪些。
- 设置页（1.3.0）：桌面 `SettingsPage.qml` 是左边分类列表（`menu`：标题 → 条目）+ 右边所选条目的内容（各 `Card` 用 `visible: page.section === …`；高级选项的每个分组是一个条目，`AdvancedOptions { only: [section] }`）。手机 `SettingsScreen` 把条目按同样的三个标题分组。**设置改完自动保存**：桌面 `_set_dirty(True)` 启动 `AUTOSAVE_MS`（600 ms）定时器 → `saveConfig(quiet=True)`，退出时还有未保存的也会保存；手机 `LaunchedEffect(values.toMap())` 延迟 600 ms 保存。没有“保存”按钮了。
- 空闲占用（1.3.0）：循环的“呼吸”效果用 `ui/qml/Pulse.qml`（定时器每 80 ms 一步），**不要用 `loops: Animation.Infinite` 的动画**——只要有一个在跑，整个窗口每次屏幕刷新都重绘（240 Hz 屏幕上每秒 240 帧，实测占一个核心的 2%–24%）。启动画面的光标动画只在启动画面可见时运行（以前关闭后在隐藏窗口里无限空转）。启动各阶段耗时写在 `gui.log` 的 `startup:` 一行。测量方法和数字见 `docs/1.3.0/performance.md`。
- 测试隔离：界面偏好（QSettings）在注册表 `HKCU\Software\<组织名>` 下，**只改 `APPDATA` 隔离不了它**。启动真实界面做测试或测量时必须同时设置环境变量 `CHAOXING_DESKTOP_SETTINGS_ORG`（`gui.py`），否则会读写真实用户的偏好。
- 安全（1.3.0，`docs/1.3.0/security.md`）：启动 Windows 自带程序（powershell、tasklist、cmd、netstat、ping）一律用 `winsetup.system_exe()` 的完整路径——只写程序名时 Windows 会先在当前 exe 所在的文件夹（安装程序是“下载”文件夹）里找，可能运行冒名文件。应用内更新只接受 `https://github.com/<REPO>/releases/download/` 开头的地址，没有 SHA-256 校验值就不安装（桌面 `updater.trusted_download`，手机 `Updater.kt`）。依赖扫描用 `pip-audit`，代码扫描用 `ruff --select S,F,E9,B`，命令在 `requirements-dev.txt`。第三方许可证清单在 `THIRD_PARTY_NOTICES.md`，换依赖时同步更新。
- 开屏交接：图标先到，标题逐字（学、习、通、P、L、U、S，每个晚 60 ms）飞到真正的标题位置；每个字是原生文字、字号逐帧变化，落点每帧实时读取目标位置（窗口尺寸恢复、页面入场位移都不影响），所以落地时与真实标题一致（桌面标题 100 ms 交叉淡入，手机同帧交接）。首次启动有引导时落到引导欢迎页的图标和标题。所有品牌图标用 256 px 纹理 + mipmap（高 DPI 清晰）。手机逐字按基线对齐（单个拉丁字母的行高与中英混排不同）。品牌下没有副标题；启动画面没有进度条。
- 显示名称是“学习通 PLUS”（`DISPLAY_NAME` / `appName`，带空格）；`APP_NAME = "学习通PLUS"` 是身份名（安装目录、exe、快捷方式文件、QSettings 位置），不要改。
- 推送服务 `Local`（本机通知）：`api.notification.set_local_handler` 注册后可用；安卓注册为系统通知，桌面未注册（选项只在手机上出现）。

## 安卓版（`android/`，开发中）

- Kotlin + Compose + Chaquopy，构建时从仓库根目录复制 `main.py`、`api/*.py`、`core/*.py`、`ui/output_parser.py`、`ui/advanced.py`、`ui/cloudmodels.py`，所以这些文件里不能引入 Qt、Windows 专用依赖或 multiprocessing。详见 `android/README.md`。
- 手机功能与桌面对齐：设置是二级菜单（`SettingsPages.kt`）、识别课程（`Courses.kt`）、检查更新（`Updater.kt`，.part 下载 + SHA-256 校验后交给系统安装器）、cookies 导入、数据与隐私、关于。引导：欢迎 > 免责声明 > 账号 > 答题来源 > 权限设置（推送不在引导里，手机默认本机通知）。
- 后台被杀自动恢复：运行中 `TaskService` 返回 `START_STICKY` 并写 `files/run.json`（正常结束 / 停止时删除）。系统杀掉 :worker 后会重启服务（`onStartCommand` 收到 null intent），`restartAfterKill` 重新开始运行并记一条日志，最多 5 次；Android 12+ 若不允许后台启动前台服务则保留 run.json，界面提示点“开始运行”继续。已在模拟器上验证（kill -9 后约 1 秒重启）。
- 稳定性：`TaskService` 运行时持有唤醒锁 + Wi-Fi 锁，记录网络断开/恢复；界面每 5 秒检查 `:worker` 进程，被系统杀掉时显示“已退出”。小屏（高度 < 640dp）运行面板整体可滚动。
- 发布包开启了 R8（`proguard-rules.pro` 保留应用自己的全部类：Python 一侧按名字调用它们），原生库压缩存放（`useLegacyPackaging`）；APK 仍同时带 arm64 和 x86_64。
- 手机上没有真正的 `openai` 包（pydantic-core / jiter 没有安卓版本），用的是 `android/app/src/main/python/openai` 精简替代。`api/answer.py` 若用到 openai 的新接口或新错误类型，要同步补到替代模块里。
- 手机只用模型公司的云服务 API：没有本机模型、自定义接口地址和代理（`xxtplus_android.py` 里过滤设置字段）。
- `tests/test_android_bridge.py` 在桌面 Python 上测试桥接和 openai 替代模块。
- 界面与桌面版一致：`Theme.kt` 的颜色、圆角、动画时长和 `ui/qml/Theme.qml` 相同，`Components.kt` 对应 AppButton / Card / StatTile / StatusPill / Segmented / QuestionCard。改桌面版样式时同步改这两个文件。
- 图标：`assets/render_android_icon.py` 从桌面图标生成启动器图标、应用内品牌图和通知图标；桌面图标改了要重新运行。自适应图标的 PLUS 徽标比桌面版往里移了一些，圆形遮罩下才不会被裁掉。
- 窗口圆角（1.3.0）：主窗口无边框，Windows 11 不会自动给它圆角；`ui/wincorners.py` 用 `DwmSetWindowAttribute` 请求圆角（最大化时改回直角），`controller.roundCorners(window, 是否圆角)` 返回当前圆角半径（Windows 10 返回 0），`Main.qml` 的描边跟随 `window.cornerRadius`。
- 启动飞入动画：标题的每个字按启动画面的字号排一次版，飞行中只改 `scale`（不要改回逐帧改 `font.pixelSize`：七个文字每帧重新排版，一帧 11–16 ms）；飞行等主窗口先画出 4 帧（或 250 ms）再开始，避开新窗口头几帧的一次性开销。测量：`QT_LOGGING_RULES=qt.scenegraph.time.renderloop=true` 看 `gui.log` 里每帧的 sync 时间。
- 设置页左侧菜单只有一个高亮块（`menuMark`），在条目之间滑动；不要让每个条目各自淡入淡出背景（那是两个动画同时出现）。切换条目时右侧内容整体淡入上移一次（`page.pick`）。
- 手动提醒先确认（1.3.0）：`manual.report` 只发“可能需要手动，正在确认”（事件带 `"checking": true`，界面只在窗口底部提示一行，不进列表、不弹窗、不推送）。章节处理完后 `JobProcessor._settle_manual` 再确认：重新读取该章节的任务点（学习通不再列为未完成的 → `manual.dismiss`，不提醒）；还在就重新登录（最多每 10 分钟一次）再读一次；程序自己能做的（课件、直播、章节检测）再试一次；仍然还在才 `manual.confirm`（弹窗 / 推送 / 结束汇总）。`urgent=True`（正在进行的随堂练习和课堂任务、作业出错、验证码重启 3 次后）跳过确认直接提醒。运行结束前 `manual.confirm_all()`。新增 `manual.report` 调用时想清楚要不要 `urgent`。
- 手机后台联网与保活（1.3.0）：真正决定后台能否联网的是系统的两项设置——电池优化豁免（省电休眠时系统会断开未豁免应用的网络，前台服务和唤醒锁都不管用）和流量节省白名单。`KeepAlive.backgroundNetworkProblems` 列出缺的项；点“开始运行”时缺就弹“先让任务在后台能联网”（`RunScreen` 的 `networkGate`：去开启 → 系统页面，回来自动开始；也可“仍然开始”）。`TaskService`：断网恢复、Wi-Fi / 流量切换、结束省电休眠后调 Python `network_changed()` → `api/net.reset_connections()` → `SessionManager.reset_connections()` 丢弃连接池里的旧连接（它们已经失效，否则每个都要等一次超时和重试；桌面断网恢复后也会丢弃）；进入 / 结束省电休眠写日志（`watchIdle`）；唤醒锁每分钟续期（以前只拿 24 小时）。`Watchdog.kt`：运行期间每 10 分钟一个 `setAndAllowWhileIdle` 闹钟（接收器在 :worker 进程，`TaskService.alive` 判断任务是否还在），任务进程没了而 `run.json` 还在就 `ACTION_REVIVE` 重新开始——很多国产系统不执行 START_STICKY；后台启动前台服务需要电池优化豁免，否则保留 `run.json` 等用户打开应用。被结束的次数在平稳运行 30 分钟后重新计。模拟器上验证过闹钟拉起（未豁免时被系统拒绝、豁免后成功）。
