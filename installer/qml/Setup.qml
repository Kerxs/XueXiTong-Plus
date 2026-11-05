import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "../../ui/qml"

// 学习通PLUS setup wizard: 欢迎 > 许可协议 > 安装选项 > 正在安装 > 完成
ApplicationWindow {
    id: window
    width: 820
    height: 560
    minimumWidth: 820
    minimumHeight: 560
    maximumWidth: 820
    maximumHeight: 560
    visible: true
    flags: Qt.Window | Qt.FramelessWindowHint
    color: "transparent"
    title: installer.appName + " 安装程序"

    property int step: 0
    property string targetDir: installer.defaultDir
    readonly property bool busy: installer.state === "installing"
    readonly property var steps: ["欢迎", "许可协议", "安装选项", "正在安装", "完成"]

    function go(i) { step = i }

    Connections {
        target: installer
        function onStateChanged() {
            if (installer.state === "installing") window.go(3)
            else if (installer.state === "done" || installer.state === "error") window.go(4)
        }
    }

    FolderDialog {
        id: folderDialog
        title: "选择安装位置"
        onAccepted: window.targetDir = installer.normalizeDir(selectedFolder.toString())
    }

    Rectangle {
        id: frame
        anchors.fill: parent
        anchors.margins: 8
        radius: 14
        color: Theme.surface
        border.color: Theme.border
        clip: true
        opacity: 0
        scale: 0.97
        Component.onCompleted: intro.start()
        ParallelAnimation {
            id: intro
            NumberAnimation { target: frame; property: "opacity"; to: 1; duration: Theme.slow; easing.type: Easing.OutCubic }
            NumberAnimation { target: frame; property: "scale"; to: 1; duration: Theme.slow; easing.type: Easing.OutCubic }
        }

        RowLayout {
            anchors.fill: parent
            spacing: 0

            // ---------- left: brand + steps ----------
            Rectangle {
                Layout.preferredWidth: 250
                Layout.fillHeight: true
                color: Theme.pane

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 26
                    spacing: 6

                    Image {
                        source: installer.iconUrl
                        sourceSize.width: 64
                        sourceSize.height: 64
                        Layout.preferredWidth: 64
                        Layout.preferredHeight: 64
                        mipmap: true
                    }
                    Text { Layout.topMargin: 10; text: installer.appName; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 20; font.weight: Font.Bold }
                    Text { text: "版本 " + installer.version + " · 安装程序"; color: Theme.muted; font.family: Theme.uiFont; font.pixelSize: 12 }

                    Item { Layout.preferredHeight: 26 }

                    Item {
                        Layout.fillWidth: true
                        implicitHeight: stepColumn.implicitHeight
                        // Sliding marker next to the current step.
                        Rectangle {
                            width: 3
                            height: 18
                            radius: 2
                            color: Theme.accent
                            x: 0
                            y: window.step * 34 + 8
                            Behavior on y { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                        }
                        Column {
                            id: stepColumn
                            x: 14
                            spacing: 0
                            Repeater {
                                model: window.steps
                                RowLayout {
                                    required property string modelData
                                    required property int index
                                    height: 34
                                    spacing: 10
                                    Rectangle {
                                        width: 20; height: 20; radius: 10
                                        color: index < window.step ? Theme.accent : (index === window.step ? Theme.accentSoft : "transparent")
                                        border.color: index <= window.step ? Theme.accent : Theme.borderStrong
                                        Behavior on color { ColorAnimation { duration: Theme.normal } }
                                        Text {
                                            anchors.centerIn: parent
                                            text: index < window.step ? "" : String(index + 1)
                                            font.family: index < window.step ? Theme.iconFont : Theme.uiFont
                                            font.pixelSize: 10
                                            font.weight: Font.DemiBold
                                            color: index < window.step ? Theme.accentText : (index === window.step ? Theme.accent : Theme.muted)
                                        }
                                    }
                                    Text {
                                        text: modelData
                                        color: index === window.step ? Theme.text : Theme.muted
                                        font.family: Theme.uiFont
                                        font.pixelSize: 13
                                        font.weight: index === window.step ? Font.DemiBold : Font.Normal
                                        Behavior on color { ColorAnimation { duration: Theme.normal } }
                                    }
                                }
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }
                    Text {
                        Layout.fillWidth: true
                        text: "基于开源项目 Samueli924/chaoxing\n遵循 GPL-3.0 协议"
                        color: Theme.faint
                        font.family: Theme.uiFont
                        font.pixelSize: 11
                        lineHeight: 1.3
                        wrapMode: Text.Wrap
                    }
                }
            }

            // ---------- right: pages ----------
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                // Title bar: drag to move, minimise, close.
                Item {
                    id: titleBar
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 44
                    z: 5
                    DragHandler {
                        target: null
                        onActiveChanged: if (active) window.startSystemMove()
                    }
                    Row {
                        anchors.right: parent.right
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        IconButton { glyph: ""; tip: "最小化"; onClicked: window.showMinimized() }
                        IconButton { glyph: ""; tip: window.busy ? "安装中，无法关闭" : "关闭"; enabled: !window.busy; onClicked: Qt.quit() }
                    }
                }

                Item {
                    id: pages
                    anchors.fill: parent
                    anchors.leftMargin: 36
                    anchors.rightMargin: 36
                    anchors.topMargin: 44
                    anchors.bottomMargin: 84
                    clip: true

                    component Page: Item {
                        property int pageIndex: 0
                        readonly property bool current: window.step === pageIndex
                        width: pages.width
                        height: pages.height
                        opacity: current ? 1 : 0
                        visible: opacity > 0.01
                        x: current ? 0 : (pageIndex < window.step ? -40 : 40)
                        Behavior on opacity { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                        Behavior on x { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
                    }

                    // 0 欢迎 — title types out like the app's splash screen.
                    Page {
                        pageIndex: 0
                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 14
                            Item { Layout.preferredHeight: 24 }
                            Row {
                                spacing: 4
                                Text {
                                    id: typedTitle
                                    readonly property string full: "学习通 PLUS"
                                    property int shown: 0
                                    text: full.substring(0, shown)
                                    color: Theme.text
                                    font.family: Theme.uiFont
                                    font.pixelSize: 40
                                    font.weight: Font.Black
                                    Timer {
                                        interval: 230
                                        repeat: true
                                        running: typedTitle.shown < typedTitle.full.length
                                        onTriggered: {
                                            typedTitle.shown += 1
                                            interval = 160 + Math.round(Math.random() * 120)
                                        }
                                    }
                                }
                                Rectangle {
                                    width: 4; height: 42; radius: 2
                                    color: Theme.text
                                    anchors.verticalCenter: parent.verticalCenter
                                    SequentialAnimation on opacity {
                                        loops: Animation.Infinite
                                        NumberAnimation { to: 0; duration: 420 }
                                        NumberAnimation { to: 1; duration: 420 }
                                    }
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: installer.installedVersion !== ""
                                    ? "检测到已安装版本 " + installer.installedVersion + "，将升级到 " + installer.version + "。你的配置和账号不会受影响。"
                                    : "欢迎！安装向导将把 " + installer.appName + " " + installer.version + " 安装到这台电脑上。"
                                color: Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 14
                                lineHeight: 1.35
                                wrapMode: Text.Wrap
                            }
                            Repeater {
                                model: [
                                    { glyph: "", text: "按当前用户安装，不需要管理员权限" },
                                    { glyph: "", text: "约 " + installer.requiredMb + " MB，可自选安装位置" },
                                    { glyph: "", text: "可随时在“设置 → 应用”中卸载" }
                                ]
                                RowLayout {
                                    id: bullet
                                    required property var modelData
                                    required property int index
                                    spacing: 12
                                    opacity: 0
                                    transform: Translate { id: bulletShift; x: -10 }
                                    SequentialAnimation {
                                        running: true
                                        PauseAnimation { duration: 500 + bullet.index * 120 }
                                        ParallelAnimation {
                                            NumberAnimation { target: bullet; property: "opacity"; to: 1; duration: Theme.normal }
                                            NumberAnimation { target: bulletShift; property: "x"; to: 0; duration: Theme.normal; easing.type: Easing.OutCubic }
                                        }
                                    }
                                    Rectangle {
                                        width: 30; height: 30; radius: 8
                                        color: Theme.accentSoft
                                        Text { anchors.centerIn: parent; text: modelData.glyph; font.family: Theme.iconFont; font.pixelSize: 14; color: Theme.accent }
                                    }
                                    Text { text: modelData.text; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 13 }
                                }
                            }
                            Text {
                                visible: !installer.payloadOk
                                Layout.fillWidth: true
                                text: "安装包内容缺失或已损坏，请重新下载安装程序。"
                                color: Theme.danger
                                font.family: Theme.uiFont
                                font.pixelSize: 13
                                wrapMode: Text.Wrap
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }

                    // 1 许可协议
                    Page {
                        pageIndex: 1
                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 12
                            Text { text: "许可协议"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 22; font.weight: Font.Bold }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                radius: Theme.radius
                                color: Theme.sunken
                                ScrollView {
                                    id: licenseScroll
                                    anchors.fill: parent
                                    anchors.margins: 14
                                    clip: true
                                    contentWidth: availableWidth
                                    Text {
                                        width: licenseScroll.availableWidth
                                        color: Theme.text
                                        font.family: Theme.uiFont
                                        font.pixelSize: 13
                                        lineHeight: 1.35
                                        wrapMode: Text.Wrap
                                        text: "本软件基于开源项目 Samueli924/chaoxing，以 GNU 通用公共许可证第 3 版（GPL-3.0）发布：\n\n"
                                            + "• 你可以自由使用、复制、修改和再分发本软件；再分发或衍生的版本必须同样以 GPL-3.0 开源，并附带源代码。\n"
                                            + "• 禁止将本软件或其衍生版本作为闭源商业软件发布或销售，禁止用于盈利。\n"
                                            + "• 本软件不提供任何担保。完整协议见安装目录中的 LICENSE 或 https://www.gnu.org/licenses/gpl-3.0.html。\n\n"
                                            + "使用须知：\n\n"
                                            + "• 本软件与超星、学习通官方无任何关联。\n"
                                            + "• 使用自动化工具可能违反学习通用户协议及学校的课程或学术诚信规定，可能导致账号受限或成绩作废，相关后果由使用者自行承担。\n"
                                            + "• 账号、密码、TOKEN、API Key 和 cookies 加密保存在本机 %APPDATA%\\ChaoxingDesktop（只有当前 Windows 用户能解密）。"
                                    }
                                }
                            }
                            AppCheckBox {
                                id: licenseBox
                                text: "我接受许可协议和使用须知"
                            }
                        }
                    }

                    // 2 安装选项
                    Page {
                        pageIndex: 2
                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 14
                            Text { text: "安装选项"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 22; font.weight: Font.Bold }
                            Text { text: "安装位置"; color: Theme.muted; font.family: Theme.uiFont; font.pixelSize: 12 }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                AppTextField {
                                    id: dirField
                                    Layout.fillWidth: true
                                    text: window.targetDir
                                    onTextEdited: window.targetDir = text
                                }
                                AppButton {
                                    text: "浏览…"
                                    glyph: ""
                                    onClicked: {
                                        folderDialog.currentFolder = "file:///" + window.targetDir.replace(/\\/g, "/")
                                        folderDialog.open()
                                    }
                                }
                            }
                            Text {
                                text: "需要约 " + installer.requiredMb + " MB · " + installer.freeSpaceText(window.targetDir)
                                color: Theme.faint
                                font.family: Theme.uiFont
                                font.pixelSize: 12
                            }
                            Item { Layout.preferredHeight: 6 }
                            AppSwitch { id: desktopSwitch; text: "创建桌面快捷方式"; checked: true }
                            AppSwitch { id: startMenuSwitch; text: "添加到开始菜单"; checked: true }
                            AppSwitch { id: launchSwitch; text: "安装完成后启动 " + installer.appName; checked: true }

                            // Runtime components: WebView2 is needed for the video preview.
                            Item { Layout.preferredHeight: 4 }
                            Text { text: "运行组件"; color: Theme.muted; font.family: Theme.uiFont; font.pixelSize: 12 }
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: depRow.implicitHeight + 20
                                radius: Theme.radius
                                color: installer.webview2Version !== "" ? Theme.sunken : Theme.warningSoft
                                RowLayout {
                                    id: depRow
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    anchors.leftMargin: 12
                                    spacing: 10
                                    Text {
                                        text: installer.webview2Version !== "" ? "" : ""
                                        font.family: Theme.iconFont
                                        font.pixelSize: 14
                                        color: installer.webview2Version !== "" ? Theme.success : Theme.warning
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 1
                                        Text { text: installer.webview2Name; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 13 }
                                        Text {
                                            Layout.fillWidth: true
                                            text: installer.webview2Version !== ""
                                                ? "已安装 · 版本 " + installer.webview2Version
                                                : "未安装。视频预览需要它，可在安装时从微软官网下载（约 2 MB，安装过程中再联网获取运行时）"
                                            color: Theme.muted
                                            font.family: Theme.uiFont
                                            font.pixelSize: 11
                                            wrapMode: Text.Wrap
                                        }
                                    }
                                    AppSwitch {
                                        id: depsSwitch
                                        visible: installer.webview2Version === ""
                                        checked: true
                                    }
                                }
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }

                    // 3 正在安装
                    Page {
                        pageIndex: 3
                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 16
                            Item { Layout.preferredHeight: 30 }
                            Text { text: "正在安装"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 22; font.weight: Font.Bold }
                            Text {
                                text: Math.round(installer.progress * 100) + "%"
                                color: Theme.accent
                                font.family: Theme.uiFont
                                font.pixelSize: 44
                                font.weight: Font.Black
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                height: 8
                                radius: 4
                                color: Theme.sunken
                                clip: true
                                Rectangle {
                                    id: bar
                                    width: parent.width * installer.progress
                                    height: parent.height
                                    radius: 4
                                    color: Theme.accent
                                    Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                                    // Moving sheen on the filled part.
                                    Rectangle {
                                        width: 80
                                        height: parent.height
                                        radius: 4
                                        opacity: 0.35
                                        gradient: Gradient {
                                            orientation: Gradient.Horizontal
                                            GradientStop { position: 0; color: "transparent" }
                                            GradientStop { position: 0.5; color: "#ffffff" }
                                            GradientStop { position: 1; color: "transparent" }
                                        }
                                        NumberAnimation on x {
                                            from: -80
                                            to: bar.width
                                            duration: 1200
                                            loops: Animation.Infinite
                                            running: window.busy
                                        }
                                    }
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: installer.currentFile
                                color: Theme.faint
                                font.family: Theme.uiFont
                                font.pixelSize: 11
                                elide: Text.ElideMiddle
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }

                    // 4 完成 / 出错
                    Page {
                        pageIndex: 4
                        readonly property bool ok: installer.state === "done"
                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 14
                            Item { Layout.preferredHeight: 30 }
                            Rectangle {
                                width: 72; height: 72; radius: 36
                                color: parent.parent.ok ? Theme.successSoft : Theme.dangerSoft
                                scale: window.step === 4 ? 1 : 0.4
                                Behavior on scale { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutBack; easing.overshoot: 2 } }
                                Text {
                                    anchors.centerIn: parent
                                    text: parent.parent.parent.ok ? "" : ""
                                    font.family: Theme.iconFont
                                    font.pixelSize: 30
                                    color: parent.parent.parent.ok ? Theme.success : Theme.danger
                                }
                            }
                            Text {
                                text: parent.parent.ok ? "安装完成" : "安装没有完成"
                                color: Theme.text
                                font.family: Theme.uiFont
                                font.pixelSize: 26
                                font.weight: Font.Bold
                            }
                            Text {
                                Layout.fillWidth: true
                                text: parent.parent.ok
                                    ? installer.appName + " 已安装到：\n" + window.targetDir
                                    : installer.errorText
                                color: parent.parent.ok ? Theme.muted : Theme.danger
                                font.family: Theme.uiFont
                                font.pixelSize: 13
                                lineHeight: 1.35
                                wrapMode: Text.WrapAnywhere
                            }
                            // Installed, but a runtime component could not be set up.
                            Rectangle {
                                visible: parent.parent.ok && installer.warningText !== ""
                                Layout.fillWidth: true
                                implicitHeight: warnCol.implicitHeight + 20
                                radius: Theme.radius
                                color: Theme.warningSoft
                                ColumnLayout {
                                    id: warnCol
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    anchors.leftMargin: 12
                                    spacing: 6
                                    Text {
                                        Layout.fillWidth: true
                                        text: installer.warningText + "程序可以正常使用，只是视频预览无法显示。"
                                        color: Theme.warning
                                        font.family: Theme.uiFont
                                        font.pixelSize: 12
                                        lineHeight: 1.3
                                        wrapMode: Text.Wrap
                                    }
                                    AppButton {
                                        text: "打开微软 WebView2 下载页"
                                        glyph: ""
                                        onClicked: installer.openUrl(installer.webview2Page)
                                    }
                                }
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }
                }

                // ---------- footer ----------
                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 76
                    color: "transparent"
                    Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: Theme.border }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 36
                        anchors.rightMargin: 28
                        spacing: 10
                        AppButton {
                            visible: window.step === 1 || window.step === 2
                            text: "上一步"
                            kind: "ghost"
                            glyph: ""
                            onClicked: window.go(window.step - 1)
                        }
                        Item { Layout.fillWidth: true }
                        AppButton {
                            visible: window.step < 3
                            text: "取消"
                            onClicked: Qt.quit()
                        }
                        AppButton {
                            visible: window.step === 0
                            text: installer.installedVersion !== "" ? "开始升级" : "开始"
                            kind: "primary"
                            enabled: installer.payloadOk
                            onClicked: window.go(1)
                        }
                        AppButton {
                            visible: window.step === 1
                            text: "下一步"
                            kind: "primary"
                            enabled: licenseBox.checked
                            onClicked: window.go(2)
                        }
                        AppButton {
                            visible: window.step === 2
                            text: "安装"
                            glyph: ""
                            kind: "primary"
                            enabled: window.targetDir.trim() !== ""
                            onClicked: installer.install(window.targetDir, desktopSwitch.checked, startMenuSwitch.checked,
                                                         installer.webview2Version === "" && depsSwitch.checked)
                        }
                        AppButton {
                            visible: window.step === 4 && installer.state === "error"
                            text: "返回重试"
                            onClicked: window.go(2)
                        }
                        AppButton {
                            visible: window.step === 4
                            text: installer.state === "done" && launchSwitch.checked ? "完成并启动" : "完成"
                            kind: "primary"
                            onClicked: {
                                if (installer.state === "done" && launchSwitch.checked)
                                    installer.launch(window.targetDir)
                                Qt.quit()
                            }
                        }
                    }
                }
            }
        }
    }
}
