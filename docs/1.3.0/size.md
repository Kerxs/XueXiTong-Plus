# 1.3.0 安装包体积报告

所有数字都是在本机实际构建后量出来的（1.2.9 为已发布版本，1.3.0 为当前工作区的构建）。

## 结果

| 产物 | 1.2.9 | 1.3.0 | 变化 |
|---|---:|---:|---:|
| Windows 安装程序 | 115.9 MB | **72.3 MB** | −43.6 MB（−38%） |
| Windows 便携 zip | 95.6 MB | **84.4 MB** | −11.2 MB（−12%） |
| Windows 安装目录 | 221 MB / 1305 个文件 | **192.6 MB** / 1288 个文件 | −28.4 MB（−13%） |
| Android APK | 52.6 MB | **28.0 MB** | −24.6 MB（−47%） |

目标是安装程序降到约 100 MB，实际 72.3 MB。OCR、WebView2 视频预览、AI 接口、托盘、界面动画都保留。

## 做了什么

### 1. 安装程序不再把 Qt 和 Python 装两份（−约 30 MB）

安装程序自己是一个带界面的程序，自带一套 Qt 和 Python（41 MB）；它后面附带的“要安装的文件”里又有同样的一套。现在安装内容里不再重复存放这些文件，安装时直接从安装程序自己解开的目录里复制。

- 构建时逐个比对 SHA-256，只有内容完全相同的文件才共用（1204 个文件，98 MB）。
- 安装时每个共用文件再校验一次，不一致就报错停止，不会装出一份残缺的程序。

### 2. 安装内容改成整体压缩（−约 12 MB）

以前是每个文件单独压缩的 zip（74.5 MB）。现在是一条连续的压缩流（`.tar.xz`，64 MB 字典，可执行文件先过 x86 过滤器），相似的文件排在一起压。两项合计，安装内容从 74.5 MB 降到 30.4 MB。

便携 zip 仍然是普通 zip，因为 Windows 资源管理器打不开别的格式。

### 3. 去掉没有被加载的 onnxruntime.dll（安装目录 −18.4 MB）

`onnxruntime.dll` 是给 C/C++ 程序用的同一个运行库，Python 模块用的是旁边的 `.pyd`。验证方法：`.pyd` 里没有对它的引用；去掉后验证码识别的结果与原来完全相同。

### 4. AI 客户端换成精简版（安装目录 −约 10 MB）

官方 `openai` 包为了一种请求带进了 pydantic、pydantic_core、jiter。手机版一直用的是自己写的精简客户端（同样的接口和错误类型），桌面打包版现在用同一份，并补上了与官方包一致的重试（连接中断、超时、429、5xx）。从源码运行和测试时仍用官方包。

### 5. Android：代码压缩 + 原生库压缩存放（−24.6 MB）

- 开启 R8：两个 dex 从 39 MB 降到 2.5 MB（主要是用不到的图标库和 Compose 代码）。应用自己的类全部保留，因为 Python 一侧会按名字调用它们。
- 原生库（Python、OpenSSL、SQLite）在 APK 里压缩存放：下载小约 12 MB，系统安装时会解开，所以**安装后占用的空间没有变小**。

## 每一步之后的回归测试

| 检查 | 结果 |
|---|---|
| 安装程序 `--extract` 解到临时目录，与构建目录逐文件比对 SHA-256 | 1288 个文件，缺失 0、多余 0、不一致 0；用时 9 秒 |
| 打包版任务程序自检 `chaoxing-worker.exe --selftest`（验证码识别、AI 客户端、网页解析、字体解码、加密、任务模块） | 全部通过 |
| 打包版任务程序用模板账号运行 | 走到登录并按预期以退出码 2 结束 |
| 打包版界面启动 15 秒（独立数据目录） | 正常运行，`gui.log` 只有一条 1.2.9 就有的布局提示 |
| 便携 zip 解压 | 1288 个文件，与安装目录一致 |
| 自动测试 | 332 个全部通过（含安装内容格式的 7 个新测试） |
| APK 在模拟器（Android 15，x86_64）上安装并启动 | 启动正常，设置加载正常，无崩溃；签名证书与 1.2.9 相同 |

**没有验证的**：

- 没有用安装程序的正常安装流程（写注册表、建快捷方式）实际装一遍，因为那会改动这台电脑上已安装的版本；验证的是解包这一步，注册表和快捷方式的代码这次没有改。
- APK 只验证了启动和设置加载，没有在模拟器里实际跑一次任务，也没有在 arm64 真机上装过。
- 没有在一台没装过任何版本的干净 Windows 上测试。

## 最大的 20 个文件（1.3.0 安装目录）

| 大小 (MB) | 文件 |
|---:|---|
| 19.64 | numpy.libs/libscipy_openblas64_.dll |
| 19.07 | onnxruntime/capi/onnxruntime_pybind11_state.pyd |
| 12.98 | ddddocr/common_old.onnx |
| 9.99 | PySide6/Qt6Core.dll |
| 9.27 | chaoxing-worker.exe |
| 9.23 | PySide6/Qt6Gui.dll |
| 8.28 | PySide6/QtOpenGL.pyd |
| 6.44 | PySide6/Qt6Quick.dll |
| 6.22 | PySide6/Qt6Widgets.dll |
| 5.86 | python313.dll |
| 5.74 | libcrypto-3.dll |
| 5.14 | PySide6/Qt6Qml.dll |
| 4.68 | PySide6/QtWidgets.pyd |
| 3.85 | lxml/etree.pyd |
| 3.75 | PySide6/QtGui.pyd |
| 3.68 | numpy/_core/_multiarray_umath.pyd |
| 3.42 | PySide6/Qt6QuickControls2FluentWinUI3.dll |
| 3.36 | PySide6/QtCore.pyd |
| 2.65 | 卸载学习通PLUS.exe |
| 2.65 | 学习通PLUS.exe |

## 主要依赖是否真的在用

| 依赖 | 大小 | 结论 |
|---|---:|---|
| PySide6 / Qt | 约 85 MB | 在用。QtWidgets 是托盘图标需要的；QtOpenGL 是 QtQuick 导入时需要的；Fusion 样式是 FluentWinUI3 的基础 |
| onnxruntime（.pyd） | 19 MB | 在用（验证码识别） |
| numpy + OpenBLAS | 26 MB | numpy 在用（onnxruntime 的输入输出）；OpenBLAS 本身用不到，但 numpy 导入时就会加载它，去不掉 |
| ddddocr 模型 | 13 MB | 在用 |
| lxml | 6.6 MB | 在用（解析学习通页面） |
| Pillow | 3.2 MB | 在用（验证码图片、题目图片缩放） |
| openai / pydantic / jiter | 约 10 MB | **已去掉**，换成精简客户端 |
| onnxruntime.dll | 18.4 MB | **已去掉**，没有被加载 |

## 还能再小吗

| 方向 | 大约能省 | 为什么这次没做 |
|---|---:|---|
| APK 只带 arm64，不带 x86_64 | APK −约 6 MB | 电脑上的安卓模拟器多数是 x86_64，去掉后这些用户装不上；现有版本的应用内更新只认发布里的第一个 APK，分成两个包有装错的风险 |
| 换掉 numpy 的 OpenBLAS | 安装目录 −20 MB | 需要自己编译 numpy，维护成本高，出问题难排查 |
| 用 Python 自带的解析器代替 lxml | 安装目录 −7 MB | 两种解析器对不规范网页的处理不同，可能让题目解析出错 |
| 便携版另外提供 7z | 下载 −约 35 MB | 多一个发布文件；Windows 自带工具打不开 7z |
