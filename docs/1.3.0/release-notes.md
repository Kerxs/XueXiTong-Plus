## 改进

- **预览** 多个章节并行时可以切换（‹ 1/4 ›）或网格平铺；可以关闭预览节省资源
- **答题** 最近几份检测可以翻页查看；AI 提示词更短、几道题合成一次请求，重做只问错题，费用更低
- **直播** 自动观看直播任务点
- **调度** 并行按已开放的章节来，未开放的章节不再反复重试
- **设置** 分类菜单，改完自动保存；手机默认用系统通知
- **引导** 新用户 4 步完成；老用户只看新增内容，可以跳过
- **弹窗** 不打断任务，带倒计时自动关闭；“需要手动完成”先自动确认（重新读取、重新登录、重试），确实做不了才弹窗
- **体积** 安装程序 116 → 72 MB，APK 53 → 28 MB
- **性能** 空闲时不再占用 CPU
- **界面** 窗口圆角；启动动画更流畅；设置页切换动画
- **统计** 匿名使用统计（默认开启，可关闭，只有数字）；运行日志保留 30 天

## 修复

- **视频** 已完成的视频进度条仍显示“进行中”
- **验证码** 视频结尾重复上报触发验证码
- **网络** 重新登录时断网会停止整次运行；手机在后台断网导致视频失败重来
- **手机后台** 开始前检查后台联网的系统设置；网络切换后立即重连；任务被系统结束后定时自动恢复
- **更新** 没有校验值的更新包不再安装
- **日志** 不再记录整页网页，登录用户名打码

## 下载

| 系统 | 下载 |
| --- | --- |
| Windows | [![Setup x64](https://img.shields.io/badge/Setup-x64-2563eb?logo=windows)](https://github.com/Kerxs/XueXiTong-Plus/releases/download/v1.3.0/XueXiTong-Plus-Setup-1.3.0.exe) [![Portable x64](https://img.shields.io/badge/Portable-x64-64748b?logo=windows)](https://github.com/Kerxs/XueXiTong-Plus/releases/download/v1.3.0/XueXiTong-Plus-Windows-1.3.0.zip) |
| Android | [![APK arm64 + x64](https://img.shields.io/badge/APK-arm64%20%2B%20x64-16a34a?logo=android)](https://github.com/Kerxs/XueXiTong-Plus/releases/download/v1.3.0/XueXiTong-Plus-Android-1.3.0.apk) |

已安装旧版本的可以在应用内“检查更新”直接升级，配置不受影响。[隐私说明](https://github.com/Kerxs/XueXiTong-Plus/blob/main/PRIVACY.md)
