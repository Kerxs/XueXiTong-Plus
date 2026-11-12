# 学习通 PLUS 1.3.0 项目审计报告

审计对象：`main` 分支提交 `9b2bd05`（1.2.9）和它的发行文件。只读检查，没有改任何代码。
数据来源：源码、`dist/` 里的 1.2.9 构建产物、两份真实运行日志（11-05 至 11-09，共约 29.6 万行）。

**没有做的检查**（留到对应阶段，不在这里下结论）：Ruff、pytest、pip-audit 还没装进开发环境，所以代码规范扫描、依赖漏洞扫描的结果本报告里没有；启动时间、内存、CPU 没有实测；真机没有测。

---

## 1. 结构

| 部分 | 内容 | 规模 |
|---|---|---|
| 任务进程 | `main.py`（调度）、`api/`（学习通接口、答题、验证码、通知、遥测） | 约 7,900 行，`api/answer.py` 2,131 行、`api/base.py` 2,066 行 |
| 共用逻辑 | `core/`（开始前检查、课程识别、账号数据、加密） | 约 450 行 |
| 桌面界面 | `gui.py`、`ui/*.py`、`ui/qml/*.qml` | Python 约 3,900 行，QML 约 6,200 行 |
| 安装 / 卸载 | `installer/`、`ui/winsetup.py`、`ui/uninstall.py` | |
| 打包 | `build_windows.ps1`、`packaging/*.spec`、`packaging/prune.py` | |
| 手机 | `android/`（Kotlin + Compose + Chaquopy，构建时复制 `main.py`、`api/`、`core/`） | |
| 测试 | `tests/` 38 个文件，259 个用例（1.2.9 发布时全部通过） | |

结构本身清楚：界面和任务进程通过标准输出通信，两端共用同一份业务代码。主要的维护负担在两个 2,000 行的文件，但这次不建议拆（“不为重构而重构”）。

## 2. 发现的问题（按严重程度）

### A. 确认存在、影响运行结果

| # | 问题 | 证据 | 位置 |
|---|---|---|---|
| A1 | **验证码大多是程序自己触发的**。视频到结尾后 2/3/5/8 秒连发“已看完”上报，第 3、4 次被平台拦截 | 65 次验证码拦截里 60 次紧跟“已到结尾，等待平台确认（第 3 次）”；重新登录后平台都显示该视频已完成 | `api/base.py` `study_video` |
| A2 | **进度条停在“进行中”**。界面只认“任务完成:”一句，但视频还有 4 种结束方式不输出它 | 265 次“开始任务”只有 145 次“任务完成” | `ui/output_parser.py`、`api/base.py` |
| A3 | **并行线程浪费在未开放章节上**。闯关课程后面的章节未开放，被并行线程取走后重试 5 次再报错 | 日志里“章节未开启”数百条 | `main.py` `JobProcessor` |
| A4 | **重新登录时网络出错会停止整次运行** | 11-07 22:30 `重新登录时出错：ConnectionError` 后运行停止 | `main.py` `_relogin` / `_captcha_restart` |
| A5 | **验证码重启计数没有加锁**。多个线程同时遇到验证码时 `_captcha_restarts` 可能少计或多计 | 代码检查 | `main.py` |

### B. 确认存在、影响隐私或磁盘

| # | 问题 | 证据 | 位置 |
|---|---|---|---|
| B1 | **日志文件里有真实姓名和整页网页**。`chaoxing.log` 用 TRACE 级别，写入“当前登录用户: <姓名>”和章节页面的完整 HTML | 两份日志第一屏就能看到 | `api/logger.py:80`、`api/base.py` |
| B2 | **日志只轮转不清理**。每 10 MB 换一个文件，旧文件永远留着 | 用户目录里已有多份 9 MB 以上的日志 | `api/logger.py:80` |
| B3 | 答案缓存每查一题就把整个 `cache.json` 读一遍 | 代码检查（`CacheDAO.get_cache`） | `api/answer.py` |

建议：日志文件降到 DEBUG、不写整页 HTML、姓名打码、保留最近 5 个文件；缓存读入内存后复用。

### C. 维护性

| # | 问题 |
|---|---|
| C1 | `pyproject.toml` 版本还是 1.2.0，`requirements.txt` 里有桌面版用不到的 celery、flask、chardet、argparse |
| C2 | 桌面默认并行数在三处各写一遍（模板、`ui/controller.py`、手机 `xxtplus_android.py`），`main.py` 的缺省值又是 4 |
| C3 | 没有 `requirements-dev.txt`，测试用 `unittest`，没有统一的检查命令 |
| C4 | `api/answer.py` 有 1 处裸 `except:`（解析模型输出），会吞掉包括中断在内的所有异常 |

### 没有发现问题的地方

- 网络超时：学习通会话统一带 (10, 20) 秒超时；题库和 AI 请求都有超时。
- 线程：共享状态（缓存、cookies、遥测、手动提醒、网络等待）都有锁，除了 A5。
- 密钥：配置和 cookies 用 DPAPI / 系统密钥库加密；软件里没有内置任何令牌。
- 暂停 / 继续 / 停止：现有测试覆盖，日志里没有相关异常。这一项在阶段 1 还会用假任务脚本再跑一遍。

## 3. 构建流程

- **Windows**：`build_windows.ps1` 准备便携 Python 3.13 → 装依赖 → PyInstaller 把界面和任务进程打进同一个目录 → `prune.py` 裁剪 → 生成 zip 和安装程序（LZMA）。一次约 8 分钟。可重复，没有发现问题。
- **Android**：Gradle + Chaquopy。**没有开启代码压缩**（`isMinifyEnabled = false`），并且发布包同时带 arm64 和 x86_64 两套原生库（x86_64 只有模拟器用）。

## 4. 体积构成（1.2.9）

| 产物 | 大小 |
|---|---|
| 安装程序 | 115.9 MB |
| 便携 zip | 95.6 MB |
| 安装目录 | 221 MB，1,305 个文件 |
| Android APK | 52.6 MB |

### 安装目录按依赖

| 依赖 | 大小 | 用途 | 是否必需 |
|---|---|---|---|
| PySide6 / Qt | 85.5 MB | 界面 | 必需，已裁过一轮 |
| onnxruntime | 37.5 MB | 验证码识别 | 必需；其中 `onnxruntime.dll`（18.4 MB）是否和 `.pyd` 重复要验证 |
| numpy + OpenBLAS | 26.3 MB | onnxruntime 的输入输出 | 必需；OpenBLAS（19.6 MB）只为线性代数，验证码识别用不到，但 numpy 导入时会加载它 |
| 任务进程 exe | 13.4 MB | 内嵌全部纯 Python 模块 | 可以瘦 |
| ddddocr 模型 | 13.0 MB | 验证码识别 | 必需 |
| Python 运行库、OpenSSL 等 | 19.5 MB | | 必需 |
| openai + pydantic + httpx 一组 | 约 10 MB（含 `pydantic_core` 5.5 MB） | AI 答题 | **可替换**：手机版已经用自写的精简客户端，桌面可以用同一个 |
| lxml | 6.6 MB | 解析网页 | 有风险，不建议动 |
| Pillow | 3.2 MB | 图片缩放、验证码 | 必需 |

### 最大的 20 个文件

| 大小 (MB) | 文件 |
|---|---|
| 19.64 | numpy.libs/libscipy_openblas64_.dll |
| 19.07 | onnxruntime/capi/onnxruntime_pybind11_state.pyd |
| 18.40 | onnxruntime/capi/onnxruntime.dll |
| 13.38 | chaoxing-worker.exe |
| 12.98 | ddddocr/common_old.onnx |
| 9.99 | PySide6/Qt6Core.dll |
| 9.23 | PySide6/Qt6Gui.dll |
| 8.28 | PySide6/QtOpenGL.pyd |
| 6.44 | PySide6/Qt6Quick.dll |
| 6.22 | PySide6/Qt6Widgets.dll |
| 5.86 | python313.dll |
| 5.74 | libcrypto-3.dll |
| 5.48 | pydantic_core/_pydantic_core.pyd |
| 5.14 | PySide6/Qt6Qml.dll |
| 4.68 | PySide6/QtWidgets.pyd |
| 3.85 | lxml/etree.pyd |
| 3.75 | PySide6/QtGui.pyd |
| 3.68 | numpy/_core/_multiarray_umath.pyd |
| 3.42 | PySide6/Qt6QuickControls2FluentWinUI3.dll |
| 3.36 | PySide6/QtCore.pyd |

### APK

`classes.dex` + `classes2.dex` 共 39 MB（没有压缩的 Kotlin / Compose 代码），x86_64 原生库和依赖约 12 MB。

### 优化空间（都要在阶段 4 实测后才算数）

| 方向 | 预计 | 风险 |
|---|---|---|
| 桌面改用精简 AI 客户端，去掉 openai / pydantic / httpx | 安装目录 −10 MB 左右 | 中：要核对流式、错误类型、代理设置 |
| 验证 `onnxruntime.dll` 是否重复 | 0 或 −18 MB | 低：不需要就不会被加载，启动一次即可确认 |
| 任务进程 exe 里的模块去重、卸载器改成小启动器 | −2 至 −5 MB | 低 |
| Fusion 样式、未用到的 QML 模块再裁一轮 | −2 至 −4 MB | 中：样式回退要截图对比 |
| 安装程序压缩参数（更大的字典、固实压缩） | 安装程序 −3 至 −6 MB | 低：安装时间略长 |
| APK 开启 R8 压缩、发布包只带 arm64 | APK 52.6 → 约 25 MB | 中：要加保留规则并在模拟器和真机上跑 |

**对目标的判断**：安装程序从 115.9 MB 降到约 100 MB 需要压缩后省 16 MB 左右。上面几项都成立的话可以达到；如果 `onnxruntime.dll` 不能去掉，预计停在 105 MB 上下。不会为了数字去掉 OCR、WebView2、AI、托盘或动画。

## 5. 风险

1. **验证码相关改动只能在真实课程上验证**。单元测试能保证上报次数和间隔，不能保证平台不再拦截。
2. **遥测默认开启**：必须在引导里告知并能一键关闭，否则对开源项目的信任有损。后台要你用自己的 Cloudflare 账号部署，部署前软件只在本机统计。
3. **体积裁剪容易造成“我的机器能跑”**：每裁一项都要启动打包版并看 `gui.log`。
4. **APK 压缩**可能删掉 Chaquopy 通过反射调用的类，需要保留规则和模拟器验证。
5. 这一版范围很大（修复 + 新功能 + 遥测 + 体积 + 性能 + 安全）。按阶段交付，每阶段可以单独停下。

## 6. 实施顺序

1. **阶段 1 稳定性**：A1–A5、B1–B3、弹窗不打断任务。先做，因为直接影响每次运行。
2. **阶段 2 功能**：多视频预览、答题切换、关闭预览、AI 提示词省费用、引导只显示新内容。
3. **阶段 3 遥测**：客户端、Worker 后台、Dashboard、隐私说明。
4. **阶段 4 体积** → **阶段 5 性能** → **阶段 6 安全**（含 pip-audit、许可证清单）。
5. **阶段 7**：全量测试、三个平台产物验证、各项报告、Release Notes。发布等你确认。
