# 学习通PLUS 安卓版（开发中）

Kotlin + Jetpack Compose 界面，用 [Chaquopy](https://chaquo.com/chaquopy/) 在手机上运行与桌面版相同的 Python 任务代码（`main.py`、`api/`、`ui/output_parser.py`、`ui/advanced.py`、`ui/cloudmodels.py`）。构建时由 Gradle 从仓库根目录复制，不另存一份。

> 状态：可构建的初版，**尚未在真机上验证**。

## 结构

| 文件 | 作用 |
| --- | --- |
| `app/src/main/python/xxtplus_android.py` | Python 桥接：读写 config.ini、设置字段（来自 `ui/advanced.py`）、运行 `main.main()` 并把输出解析成事件交给 Kotlin、回答 `input()` |
| `app/src/main/python/openai/` | `openai` 包的精简替代：真正的包依赖 pydantic-core / jiter，没有安卓版本。只实现 `api/answer.py` 用到的 `chat.completions.create` 和错误类型 |
| `TaskService.kt` | 前台服务（`specialUse`，独立进程 `:worker`）+ 部分唤醒锁；通知里有 暂停/继续、停止。停止时结束 `:worker` 进程（与桌面版结束 worker 一致） |
| `RunState.kt` | 界面进程接收服务广播，维护运行状态、日志、进度、视频和答题预览 |
| `KeepAlive.kt` | 忽略电池优化请求；按厂商（小米、华为、荣耀、OPPO/一加、vivo、三星）打开自启动页面并给出手动步骤 |
| `RunScreen.kt` / `Screens.kt` / `Settings.kt` | 运行面板、设置、后台保活、开始引导（欢迎 > 免责声明 > 账号 > 答题来源 > 推送服务 > 后台保活） |

与桌面版的差异：

- 只支持模型公司的云服务 API（`ui/cloudmodels.py` 的服务商列表），没有本机模型、自定义接口地址和代理。
- 没有 ddddocr（onnxruntime 无安卓版本），自动验证码识别不可用；`api/captcha.py` 已处理缺少该模块的情况。
- 视频预览用系统播放器（`PreviewPlayer.kt`，MediaPlayer + TextureView），请求视频时直接带上学习通播放页的 Referer，不需要本地代理。

## 构建

需要 JDK 17、Android SDK（compileSdk 35），以及完整安装的 **Python 3.13**（Chaquopy 构建时用，要有 venv；默认用 `py -3.13` 查找，也可以在 `gradle.properties` 里设置 `xxtplus.buildPython`）。`..\.build` 里的便携 Python 是嵌入版，没有 venv，不能用。

Android Gradle 插件拒绝含中文的项目路径（`学习通PLUS`），所以通过 ASCII 目录联接构建：

```powershell
cmd /c mklink /J D:\Claude\xxtplus D:\Claude\学习通PLUS   # 只需一次
cd D:\Claude\xxtplus\android
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17.0.21.9-hotspot"
.\gradlew.bat assembleDebug
```

`local.properties` 写 `sdk.dir`（不提交）。Android Studio 也要从联接路径打开。

APK 在 `app/build/outputs/apk/debug/`。发布用 `.\gradlew.bat assembleRelease`，输出 `app/build/outputs/apk/release/app-release.apk`。

**发布签名**：密钥不在仓库里，在 `%USERPROFILE%\.gradle\gradle.properties` 中设置 `xxtplus.storeFile`、`xxtplus.storePassword`、`xxtplus.keyAlias`、`xxtplus.keyPassword`。以后每个版本都必须用同一个密钥签名，否则手机无法覆盖安装（只能卸载重装，数据丢失）——请备份密钥文件和密码。没有这些设置时 release 构建退回 debug 签名。

版本号与桌面版同步：`versionName` 与 `ui/controller.py` 的 `APP_VERSION` 一致，`versionCode` = 主×10000 + 次×100 + 修订（1.2.1 → 10201）。

## 待验证

- Chaquopy 下各依赖能否安装（lxml 有官方安卓包；其余为纯 Python）。
- 真机息屏长时间运行：各品牌在“未关闭电池优化 / 已关闭 / 已关闭 + 自启动 + 锁定任务”下的存活情况。
- 视频预览在真机上能否正常播放（系统播放器 + Referer）。
