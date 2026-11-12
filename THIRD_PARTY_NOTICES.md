# 第三方软件声明

学习通 PLUS 以 GPL-3.0 发布（见 `LICENSE`），基于开源项目 [Samueli924/chaoxing](https://github.com/Samueli924/chaoxing)（GPL-3.0）。发行包里包含下列第三方软件，它们各自的许可证都允许与 GPL-3.0 的程序一起分发。各软件的完整许可证文本随其安装包提供（发行目录 `_internal` 里各包的 `*.dist-info`），也可以在其项目主页查看。

版本号是 1.3.0 构建时使用的版本。

## Windows 版

### 运行库

| 软件 | 版本 | 许可证 | 用途 |
|---|---|---|---|
| Python | 3.13 | PSF-2.0 | 运行环境 |
| Qt（PySide6 Essentials / Addons、shiboken6） | 6.12.0 | LGPL-3.0 | 界面 |
| OpenSSL（随 Python） | 3.x | Apache-2.0 | HTTPS |
| Microsoft Visual C++ 运行库 | — | 微软再分发许可 | Python 和 Qt 的运行库 |

Qt 以 LGPL-3.0 使用：发行包里的 Qt 库是未经修改的动态库，可以用同版本的 Qt 6.12 库替换。Qt 源码见 <https://download.qt.io/official_releases/qt/>。

### Python 包

| 软件 | 版本 | 许可证 |
|---|---|---|
| requests | 2.34.2 | Apache-2.0 |
| urllib3 | 2.8.0 | MIT |
| certifi | 2026.10.23 | MPL-2.0 |
| charset-normalizer | 3.5.2 | MIT |
| idna | 3.20 | BSD-3-Clause |
| httpx / httpx2 | 0.28.1 / 2.16.0 | BSD-3-Clause |
| httpcore / httpcore2 | 1.0.9 / 2.16.0 | BSD-3-Clause |
| h11 | 0.16.0 | MIT |
| anyio | 4.16.0 | MIT |
| sniffio | 1.3.1 | MIT 或 Apache-2.0 |
| socksio | 1.0.0 | MIT |
| truststore | 0.10.5 | MIT |
| beautifulsoup4 | 4.15.0 | MIT |
| soupsieve | 3.0.4 | MIT |
| lxml | 6.1.3 | BSD-3-Clause |
| loguru | 0.7.3 | MIT |
| colorama | 0.4.6 | BSD-3-Clause |
| win32_setctime | 1.2.1 | MIT |
| fonttools | 4.68.0 | MIT |
| pyaes | 1.6.1 | MIT |
| tqdm | 4.70.1 | MPL-2.0 和 MIT |
| tenacity | 9.2.1 | Apache-2.0 |
| typing_extensions | 4.16.0 | PSF-2.0 |
| ddddocr（含文字识别模型 `common_old.onnx`） | 1.6.1 | MIT |
| onnxruntime | 1.31.1 | MIT |
| numpy（含 OpenBLAS） | 2.5.4 | BSD-3-Clause 等 |
| flatbuffers | 25.12.19 | Apache-2.0 |
| protobuf | 7.36.2 | BSD-3-Clause |
| packaging | 26.3 | Apache-2.0 或 BSD-2-Clause |
| Pillow | 13.0.0 | MIT-CMU |

构建时安装但**不随发行包分发**的：openai、pydantic、pydantic_core、jiter、annotated-types、typing-inspection（1.3.0 起打包版改用项目自带的精简客户端）、opencv-python（用占位模块代替）、pip、setuptools、wheel。

### 打包工具

| 软件 | 版本 | 许可证 | 说明 |
|---|---|---|---|
| PyInstaller | 6.22.3 | GPL-2.0，带引导程序例外 | 只在构建时使用。发行包里的启动器（引导程序）适用它的例外条款，可以随任何许可证的程序分发 |
| pyinstaller-hooks-contrib、altgraph、pefile、pywin32-ctypes | — | Apache-2.0 / GPL-2.0 / MIT / BSD | 只在构建时使用，不随发行包分发 |

## Android 版

| 软件 | 许可证 | 用途 |
|---|---|---|
| Chaquopy（含 Python 3.13、OpenSSL、SQLite） | MIT（Chaquopy）；PSF-2.0、Apache-2.0、公有领域 | 在手机上运行 Python |
| Kotlin 标准库、kotlinx.coroutines | Apache-2.0 | 应用代码 |
| AndroidX、Jetpack Compose、Material 3、Material Icons | Apache-2.0 | 界面 |
| requests、urllib3、certifi、charset-normalizer、idna、httpx、httpcore、h11、anyio、sniffio、socksio、beautifulsoup4、soupsieve、lxml、loguru、fonttools、pyaes、tqdm、tenacity、typing_extensions | 同上表 | 与 Windows 版相同的任务逻辑 |

手机版没有验证码识别（onnxruntime 没有 Android 版本），也没有官方 openai 包。

## 开发工具（不随任何发行包分发）

Ruff（MIT）、pip-audit（Apache-2.0）、pytest（MIT）、Node.js 自带的测试运行器。

## 统计后台

`server/telemetry/` 是本项目自己的代码，没有第三方依赖；运行在 Cloudflare Workers 和 D1 上。

## 商标和图标

“超星”“学习通”及其图标是其权利人的商标或作品。本项目与超星、学习通官方没有任何关联。应用图标是在学习通官方图标上加了“PLUS”字样得到的（`assets/render_icon.py`），**这不是一份许可**：权利人提出要求时应当更换图标。这一点在安全审计报告里列为未解决的风险。
