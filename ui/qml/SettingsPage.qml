import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: page
    signal guideRequested()
    signal updateRequested()

    onVisibleChanged: if (visible) controller.refreshDataStats()

    // Categories on the left (heading → entries), the picked entry's options on the right.
    property string section: "account"
    function pick(id) {
        if (id === section) return
        section = id
        scroll.contentItem.contentY = 0
        if (Theme.motion) sectionIn.restart()
    }
    readonly property var advancedIds: controller.advancedGroups.map(g => g.id)
    function groupIcon(id) {
        const g = controller.advancedGroups.find(x => x.id === id)
        return g ? g.icon : ""
    }
    function groupTitle(id) {
        const g = controller.advancedGroups.find(x => x.id === id)
        return g ? g.title : id
    }
    readonly property var menu: [
        { heading: "账号与运行" },
        { id: "account", title: "账号", icon: "" },
        { id: "run", title: "运行", icon: "" },
        { id: "count", title: "章节学习次数", icon: "" },
        { heading: "任务" }
    ].concat(advancedIds.map(id => ({ id: id, title: groupTitle(id), icon: groupIcon(id) }))).concat([
        { heading: "应用" },
        { id: "look", title: "外观与动画", icon: "" },
        { id: "data", title: "数据与隐私", icon: "" },
        { id: "about", title: "关于", icon: "" }
    ])

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
        width: Math.min(parent.width, 1080)
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
            Text {
                // Changes are written a moment after they are made: there is no 保存 button.
                text: controller.running ? "任务运行中，部分设置已锁定"
                    : controller.dirty ? "正在保存…" : "修改后自动保存"
                color: Theme.muted; font.family: Theme.uiFont; font.pixelSize: 12
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.gap

        // ---------- left: categories ----------
        ScrollView {
            Layout.preferredWidth: 216
            Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true
            Item {
                width: 216
                implicitHeight: menuColumn.implicitHeight
            // One highlight that slides from the entry picked before to the one picked now. (Each
            // entry used to fade its own background: two animations at once, old out and new in.)
            Rectangle {
                id: menuMark
                readonly property int index: page.menu.findIndex(m => m.id === page.section)
                // (re-read when the entries are created: itemAt() does not notify)
                readonly property Item entry: { menuRep.count; return index >= 0 ? menuRep.itemAt(index) : null }
                visible: entry !== null
                x: 0
                width: parent.width
                y: entry ? entry.y : 0
                height: entry ? entry.height : 40
                radius: 20
                color: Theme.accentSoft
                Behavior on y { enabled: menuMark.placed; NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                Behavior on color { ColorAnimation { duration: Theme.slow } }
                property bool placed: false          // no slide from the top when the page is first laid out
                Timer { interval: 300; running: true; onTriggered: menuMark.placed = true }
            }
            ColumnLayout {
                id: menuColumn
                width: 216
                spacing: 2
                Repeater {
                    id: menuRep
                    model: page.menu
                    delegate: Item {
                        id: menuEntry
                        required property var modelData
                        readonly property bool heading: modelData.heading !== undefined
                        readonly property bool current: !heading && page.section === modelData.id
                        Layout.fillWidth: true
                        implicitHeight: heading ? 34 : 40
                        Text {
                            visible: parent.heading
                            anchors.left: parent.left
                            anchors.leftMargin: 12
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 6
                            text: parent.heading ? modelData.heading : ""
                            color: Theme.accent
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                        }
                        Rectangle {
                            visible: !parent.heading
                            anchors.fill: parent
                            radius: 20
                            color: !parent.current && entryHover.hovered ? Theme.surfaceAlt : "transparent"
                            Behavior on color { enabled: !menuEntry.current; ColorAnimation { duration: Theme.fast } }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 12
                                spacing: 12
                                Text {
                                    text: modelData.icon || ""
                                    font.family: Theme.iconFont
                                    font.pixelSize: 15
                                    color: parent.parent.parent.current ? Theme.accent : Theme.muted
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.title || ""
                                    color: Theme.text
                                    font.family: Theme.uiFont
                                    font.pixelSize: 13
                                    font.weight: parent.parent.parent.current ? Font.DemiBold : Font.Normal
                                    elide: Text.ElideRight
                                }
                            }
                            HoverHandler { id: entryHover; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: page.pick(modelData.id) }
                        }
                    }
                }
            }
            }
        }

        // ---------- right: the picked entry ----------
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

        ScrollView {
            id: scroll
            anchors.fill: parent
            contentWidth: availableWidth
            clip: true

            ColumnLayout {
                id: sectionBody
                width: scroll.availableWidth
                spacing: Theme.gap
                // The picked entry's content fades and lifts in (one animation per pick).
                transform: Translate { id: sectionShift; y: 0 }
                ParallelAnimation {
                    id: sectionIn
                    NumberAnimation { target: sectionBody; property: "opacity"; from: 0; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
                    NumberAnimation { target: sectionShift; property: "y"; from: 12; to: 0; duration: Theme.normal; easing.type: Easing.OutCubic }
                }

                // ---------- 账号 ----------
                Card {
                    visible: page.section === "account"
                    Layout.fillWidth: true
                    title: "账号"
                    subtitle: "账号信息加密保存在本机（只有当前 Windows 用户能解密）"
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
                    visible: page.section === "run"
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
                    visible: page.section === "count"
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
                    // one group of config.ini options at a time, picked in the list on the left
                    visible: page.advancedIds.indexOf(page.section) >= 0
                    Layout.fillWidth: true
                    only: visible ? [page.section] : [page.advancedIds[0]]
                    stacked: true
                    embedded: true          // the group's own title is enough: no second "高级选项" heading
                    title: ""
                    subtitle: ""
                    icon: ""
                    appearDelay: 0
                }

                // ---------- 外观与动画 ----------
                Card {
                    visible: page.section === "look"
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
                    visible: page.section === "data"
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
                                onClicked: controller.reloadConfig()
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
                    Divider {}
                    SettingRow {
                        label: "匿名使用统计"
                        hint: "只统计数字（各类任务成功 / 失败次数和耗时、错误类型、启动时间和内存、版本），不含账号、课程、题目和日志。"
                            + (controller.telemetryUploads ? "关闭后立即停止上传，并删除本机还没发送的数据" : "这个版本只保存在本机；关闭后删除本机统计")
                        AppSwitch {
                            checked: controller.telemetryEnabled
                            onToggled: controller.telemetryEnabled = checked
                        }
                    }
                    Divider {}
                    SettingRow {
                        label: "反馈问题"
                        hint: "把匿名统计整理好，打开 GitHub 的反馈页面，由你确认后提交"
                        AppButton {
                            text: "预览并反馈"
                            onClicked: { feedbackDialog.text = controller.feedbackText(); feedbackDialog.open() }
                        }
                    }
                }

                // ---------- 关于 ----------
                Card {
                    visible: page.section === "about"
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

        }
    }

    // 一键反馈：先给用户看要发送的内容，再打开 GitHub（由用户在网页上点“提交”）
    BaseDialog {
        id: feedbackDialog
        property string text: ""
        title: "反馈问题"
        width: 520
        contentItem: ColumnLayout {
            spacing: 10
            Text {
                Layout.fillWidth: true
                text: feedbackDialog.text === ""
                    ? "还没有统计数据。打开“匿名使用统计”并运行一次后，这里会出现可以反馈的内容。"
                    : "将打开 GitHub 的新建反馈页面并填好下面的内容，你可以补充问题描述后再提交。只含计数，不含账号、课程、题目和日志。"
                color: Theme.muted
                font.family: Theme.uiFont
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }
            ScrollView {
                visible: feedbackDialog.text !== ""
                Layout.fillWidth: true
                Layout.preferredHeight: 240
                clip: true
                TextArea {
                    readOnly: true
                    text: feedbackDialog.text
                    wrapMode: Text.Wrap
                    font.family: Theme.monoFont
                    font.pixelSize: 12
                    color: Theme.text
                    background: Rectangle { color: Theme.sunken; radius: Theme.radius }
                }
            }
        }
        buttons: [
            AppButton { text: "清除统计"; kind: "ghost"; visible: feedbackDialog.text !== ""; onClicked: { controller.clearStats(); feedbackDialog.close() } },
            AppButton { text: "关闭"; onClicked: feedbackDialog.close() },
            AppButton { text: "打开 GitHub 反馈"; kind: "primary"; enabled: feedbackDialog.text !== ""; onClicked: { controller.openFeedback(feedbackDialog.text); feedbackDialog.close() } }
        ]
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
