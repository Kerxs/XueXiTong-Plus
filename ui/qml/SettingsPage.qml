import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: page
    signal guideRequested()
    signal updateRequested()

    onVisibleChanged: if (visible) controller.refreshDataStats()

    // A labelled row: title + optional description on the left, a control on the right.
    component SettingRow: RowLayout {
        id: row
        property string label: ""
        property string hint: ""
        default property alias control: holder.data
        Layout.fillWidth: true
        spacing: 16
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text { Layout.fillWidth: true; text: row.label; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 13 }
            Text {
                visible: row.hint !== ""
                Layout.fillWidth: true
                text: row.hint
                color: Theme.muted
                font.family: Theme.uiFont
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }
        }
        Item {
            id: holder
            implicitWidth: childrenRect.width
            implicitHeight: childrenRect.height
        }
    }

    component Divider: Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }

    // Title, cards and save bar share one width and sit centred in the page.
    ColumnLayout {
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.min(parent.width, 880)
        spacing: Theme.gap

        ColumnLayout {
            id: titleBlock
            spacing: 2
            transform: Translate { id: titleShift; y: 0 }
            ParallelAnimation {
                id: titleIn
                NumberAnimation { target: titleShift; property: "y"; from: 10; to: 0; duration: Theme.slow; easing.type: Easing.OutCubic }
                NumberAnimation { target: titleBlock; property: "opacity"; from: 0; to: 1; duration: Theme.slow }
            }
            Connections {
                target: page
                function onVisibleChanged() { if (page.visible && Theme.motion) titleIn.restart() }
            }
            Text { text: "设置"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 22; font.weight: Font.DemiBold }
            Text { text: "账号、运行、外观、数据与隐私。基本参数在运行面板中调整。"; color: Theme.muted; font.family: Theme.uiFont; font.pixelSize: 12 }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

        ScrollView {
            id: scroll
            anchors.fill: parent
            contentWidth: availableWidth
            clip: true

            ColumnLayout {
                width: scroll.availableWidth
                spacing: Theme.gap

                // ---------- 账号 ----------
                Card {
                    Layout.fillWidth: true
                    title: "账号"
                    subtitle: "账号信息只保存在本机配置目录（明文）"
                    icon: ""
                    appearDelay: 40
                    enabled: !controller.running

                    AppSwitch {
                        text: "使用本地 cookies 登录"
                        checked: controller.useCookies
                        onToggled: controller.useCookies = checked
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: controller.useCookies
                        text: controller.hasCookiesFile ? "已找到 cookies.txt。开启后账号密码不参与登录。"
                                                        : "配置目录中还没有 cookies.txt，请先放入该文件。"
                        color: controller.hasCookiesFile ? Theme.muted : Theme.warning
                        font.family: Theme.uiFont
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: 14
                        rowSpacing: 8
                        enabled: !controller.useCookies
                        opacity: enabled ? 1 : 0.5
                        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
                        Label { text: "账号"; color: Theme.muted; font.family: Theme.uiFont }
                        AppTextField {
                            Layout.fillWidth: true
                            placeholderText: "手机号或学习通账号"
                            text: controller.username
                            onTextEdited: controller.username = text
                        }
                        Label { text: "密码"; color: Theme.muted; font.family: Theme.uiFont }
                        RowLayout {
                            Layout.fillWidth: true
                            AppTextField {
                                Layout.fillWidth: true
                                placeholderText: "密码"
                                echoMode: reveal.checked ? TextInput.Normal : TextInput.Password
                                text: controller.password
                                onTextEdited: controller.password = text
                            }
                            IconButton {
                                id: reveal
                                checkable: true
                                glyph: checked ? "" : ""
                                tip: checked ? "隐藏密码" : "显示密码"
                            }
                        }
                    }
                }

                // ---------- 运行 ----------
                Card {
                    Layout.fillWidth: true
                    title: "运行"
                    icon: ""
                    appearDelay: 80

                    SettingRow {
                        label: "重试间隔"
                        hint: "任务失败或章节未开放时，等待多少秒后重试"
                        enabled: !controller.running
                        AppSpinBox {
                            from: 0
                            to: 600
                            stepSize: 5
                            editable: true
                            value: Math.round(controller.retryInterval * 10)
                            textFromValue: (v, locale) => (v / 10).toFixed(1) + " 秒"
                            valueFromText: (t, locale) => Math.round(parseFloat(t) * 10)
                            onValueModified: controller.retryInterval = value / 10
                        }
                    }
                    Divider {}
                    SettingRow {
                        visible: typeof tray !== "undefined" && tray.available
                        label: "关闭窗口时"
                        hint: "后台运行：程序留在系统托盘，任务继续进行，点击托盘图标重新打开，右键菜单可退出"
                        Segmented {
                            model: [{ value: "ask", label: "每次询问" }, { value: "tray", label: "后台运行" }, { value: "quit", label: "直接退出" }]
                            current: typeof tray !== "undefined" ? tray.closeAction : "quit"
                            onPicked: value => tray.closeAction = value
                        }
                    }
                    Divider { visible: typeof tray !== "undefined" && tray.available }
                    SettingRow {
                        label: "运行结束时提醒"
                        hint: "任务完成或退出时提醒：窗口在后台时用托盘通知，否则闪烁任务栏按钮"
                        AppSwitch {
                            checked: controller.alertOnFinish
                            onToggled: controller.alertOnFinish = checked
                        }
                    }
                }

                // ---------- 章节学习次数 ----------
                Card {
                    Layout.fillWidth: true
                    title: "章节学习次数"
                    subtitle: "完成所选课程的任务点后，继续轮询章节增加学习次数"
                    icon: ""
                    appearDelay: 120
                    enabled: !controller.running

                    SettingRow {
                        label: "完成课程后增加章节学习次数"
                        AppSwitch {
                            checked: controller.addLearningCount
                            onToggled: controller.addLearningCount = checked
                        }
                    }
                    SettingRow {
                        label: "目标总次数"
                        enabled: controller.addLearningCount
                        opacity: enabled ? 1 : 0.5
                        AppSpinBox {
                            from: 1
                            to: 10000
                            editable: true
                            value: controller.targetCount
                            onValueModified: controller.targetCount = value
                        }
                    }
                }

                // ---------- 高级选项 (config.ini) ----------
                AdvancedOptions {
                    Layout.fillWidth: true
                    appearDelay: 140
                }

                // ---------- 外观与动画 ----------
                Card {
                    Layout.fillWidth: true
                    title: "外观与动画"
                    icon: ""
                    appearDelay: 160

                    SettingRow {
                        label: "主题"
                        Segmented {
                            model: [
                                { value: "system", label: "跟随系统" },
                                { value: "light", label: "浅色" },
                                { value: "dark", label: "深色" }
                            ]
                            current: controller.themeMode
                            onPicked: value => controller.themeMode = value
                        }
                    }
                    Divider {}
                    SettingRow {
                        label: "界面动画"
                        hint: "页面切换、卡片和列表的过渡动画。关闭后立即切换"
                        AppSwitch {
                            checked: controller.animationsEnabled
                            onToggled: controller.animationsEnabled = checked
                        }
                    }
                    Divider {}
                    SettingRow {
                        label: "启动动画"
                        hint: "启动时显示启动画面。关闭后加载完成直接进入主界面（下次启动生效）"
                        AppSwitch {
                            checked: controller.splashEnabled
                            onToggled: controller.splashEnabled = checked
                        }
                    }
                }

                // ---------- 数据与隐私 ----------
                Card {
                    Layout.fillWidth: true
                    title: "数据与隐私"
                    subtitle: "配置、cookies 和日志位于 %APPDATA%\\ChaoxingDesktop"
                    icon: ""
                    appearDelay: 200

                    SettingRow {
                        label: "配置目录"
                        hint: "放入 cookies.txt、查看运行日志"
                        IconButton { glyph: ""; text: "打开"; flat: false; onClicked: controller.openDataDir() }
                    }
                    Divider {}
                    SettingRow {
                        label: "配置文件"
                        hint: "用默认编辑器打开 config.ini 修改全部配置项；改完后点“重新载入”生效"
                        Row {
                            spacing: 8
                            IconButton { glyph: ""; text: "编辑配置文件"; flat: false; onClicked: controller.openConfigFile() }
                            IconButton {
                                glyph: ""
                                text: "重新载入"
                                flat: false
                                enabled: !controller.running
                                onClicked: controller.dirty ? reloadConfirm.open() : controller.reloadConfig()
                            }
                        }
                    }
                    Divider {}
                    SettingRow {
                        label: "运行日志"
                        hint: "当前占用 " + controller.logSize + "。日志可能包含课程和章节名称"
                        IconButton { glyph: ""; text: "清除日志"; flat: false; onClicked: clearLogsConfirm.open() }
                    }
                    Divider {}
                    SettingRow {
                        label: "账号数据"
                        hint: "清除保存的账号、密码和 cookies。在公共电脑上使用后建议清除"
                        enabled: !controller.running
                        AppButton { glyph: ""; text: "清除账号数据"; kind: "danger"; onClicked: clearAccountConfirm.open() }
                    }
                    Divider {}
                    SettingRow {
                        label: "恢复默认设置"
                        hint: "把运行参数恢复为默认值，账号信息保留"
                        enabled: !controller.running
                        IconButton { glyph: ""; text: "恢复默认"; flat: false; onClicked: resetConfirm.open() }
                    }
                }

                // ---------- 关于 ----------
                Card {
                    Layout.fillWidth: true
                    title: "关于"
                    icon: ""
                    appearDelay: 240

                    RowLayout {
                        spacing: 12
                        Image {
                            source: controller.iconUrl
                            sourceSize.width: 40
                            sourceSize.height: 40
                            Layout.preferredWidth: 40
                            Layout.preferredHeight: 40
                            mipmap: true
                        }
                        ColumnLayout {
                            spacing: 2
                            Text { text: controller.appName + "  v" + controller.version; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 14; font.weight: Font.DemiBold }
                            Text { text: "基于开源项目 Samueli924/chaoxing，遵循 GPL-3.0 协议，禁止用于盈利。"; color: Theme.muted; font.family: Theme.uiFont; font.pixelSize: 12 }
                        }
                    }
                    Divider {}
                    SettingRow {
                        readonly property string st: controller.updater.state
                        label: "软件更新"
                        hint: st === "checking" ? "正在检查更新…"
                            : st === "latest" ? "已是最新版本"
                            : st === "available" || st === "downloading" || st === "ready" ? "发现新版本 " + controller.updater.latestVersion
                            : st === "error" ? controller.updater.errorText
                            : "从 GitHub Releases 检查新版本"
                        IconButton {
                            glyph: ""
                            text: parent.parent.st === "available" || parent.parent.st === "ready" || parent.parent.st === "downloading" ? "查看更新" : "检查更新"
                            flat: false
                            enabled: parent.parent.st !== "checking"
                            onClicked: {
                                const st = parent.parent.st
                                if (st === "available" || st === "ready" || st === "downloading") page.updateRequested()
                                else controller.updater.check(false)
                            }
                        }
                    }
                    SettingRow {
                        label: "启动时自动检查更新"
                        AppSwitch {
                            checked: controller.updater.autoCheck
                            onToggled: controller.updater.autoCheck = checked
                        }
                    }
                    Divider {}
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        IconButton { glyph: ""; text: "项目主页"; flat: false; onClicked: controller.openUrl(controller.homepage) }
                        IconButton { glyph: ""; text: "原仓库"; flat: false; onClicked: controller.openUrl(controller.upstreamUrl) }
                        IconButton {
                            glyph: ""
                            text: "重新查看开始引导"
                            flat: false
                            enabled: !controller.running
                            onClicked: page.guideRequested()
                        }
                    }
                }

                Item { implicitHeight: 4 }
            }
        }

            // Cards scroll under soft edges instead of being cut off by a hard line.
            Rectangle {
                anchors { left: parent.left; right: parent.right; top: parent.top }
                height: 14
                opacity: scroll.contentItem.contentY > 1 ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                gradient: Gradient {
                    GradientStop { position: 0; color: Theme.bg }
                    GradientStop { position: 1; color: Qt.rgba(Theme.bg.r, Theme.bg.g, Theme.bg.b, 0) }
                }
            }
            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: 14
                readonly property real rest: scroll.contentItem.contentHeight - scroll.contentItem.height - scroll.contentItem.contentY
                opacity: rest > 1 ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                gradient: Gradient {
                    GradientStop { position: 0; color: Qt.rgba(Theme.bg.r, Theme.bg.g, Theme.bg.b, 0) }
                    GradientStop { position: 1; color: Theme.bg }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 52
            radius: Theme.radiusLarge
            color: Theme.surface
            border.color: controller.dirty ? Theme.accent : Theme.border
            Behavior on border.color { ColorAnimation { duration: Theme.normal } }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 10
                Text {
                    Layout.fillWidth: true
                    text: controller.running ? "任务运行中，部分设置已锁定" : (controller.dirty ? "有未保存的修改" : "所有设置已保存到本机")
                    color: controller.dirty ? Theme.accent : Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                }
                AppButton {
                    text: "撤销修改"
                    enabled: controller.dirty && !controller.running
                    onClicked: controller.revertConfig()
                }
                AppButton {
                    text: "保存"
                    kind: "primary"
                    enabled: controller.dirty && !controller.running
                    onClicked: controller.saveConfig()
                }
            }
        }
    }

    ConfirmDialog {
        id: clearAccountConfirm
        title: "清除账号数据"
        message: "将清除保存的账号、密码和 cookies.txt，并关闭 cookies 登录。清除后需要重新填写账号才能运行。"
        acceptText: "清除"
        destructive: true
        onAccepted: controller.clearAccountData()
    }
    ConfirmDialog {
        id: clearLogsConfirm
        title: "清除运行日志"
        message: "将删除配置目录中的运行日志文件，并清空运行面板中的日志。"
        acceptText: "清除"
        destructive: true
        onAccepted: controller.clearLogs()
    }
    ConfirmDialog {
        id: reloadConfirm
        title: "重新载入配置文件"
        message: "界面里还有未保存的修改，重新载入会丢弃这些修改，改用 config.ini 中的内容。"
        acceptText: "重新载入"
        destructive: true
        onAccepted: controller.reloadConfig()
    }
    ConfirmDialog {
        id: resetConfirm
        title: "恢复默认设置"
        message: "运行参数（速度、并行章节数、重试间隔、学习次数等）和 config.ini 中的其他设置将恢复为默认值。账号信息保留。"
        acceptText: "恢复默认"
        destructive: true
        onAccepted: controller.resetConfig()
    }
}
