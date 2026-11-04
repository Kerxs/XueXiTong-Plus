import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtCore
import "."

ApplicationWindow {
    id: window
    width: 1380
    height: 880
    minimumWidth: 1140
    minimumHeight: 720
    visible: false
    flags: Qt.Window | Qt.FramelessWindowHint
    title: controller.appName
    color: Theme.bg
    Behavior on color { ColorAnimation { duration: Theme.slow } }

    property int page: 0
    property bool allowClose: false
    property bool showGuide: false
    // Tray / background mode (absent when the UI is loaded without it, e.g. in test harnesses).
    readonly property var trayObj: typeof tray !== "undefined" ? tray : null

    function showWindow() {
        window.showNormal()
        window.raise()
        window.requestActivate()
    }
    // Every real exit goes through here so onClosing does not hide-to-tray instead.
    function quitApp() {
        window.allowClose = true
        controller.shutdown()
        Qt.quit()
    }
    readonly property bool accountConfigured: controller.useCookies
        || (controller.username.trim() !== "" && controller.password !== "")
    readonly property bool overlayOpen: coursePicker.visible || stopConfirm.visible
        || closeConfirm.visible || promptDialog.visible || guide.visible || updateDialog.visible

    Component.onCompleted: {
        window.width = Math.max(window.minimumWidth, windowSettings.width)
        window.height = Math.max(window.minimumHeight, windowSettings.height)
        if (windowSettings.maximized)
            Qt.callLater(window.toggleMaximize)
        showGuide = !controller.onboardingDone
        controller.updater.checkOnStartup()
    }

    function openSettings() { window.page = 1 }

    // Hidden to the tray or minimized: nothing on screen to animate or play.
    readonly property bool onScreen: window.visible && window.visibility !== Window.Minimized
    onOnScreenChanged: Theme.onScreen = window.onScreen

    // Only the normal (not maximized) size is remembered.
    Settings {
        id: windowSettings
        category: "window"
        property int width: 1380
        property int height: 880
        property bool maximized: false
    }
    Component.onDestruction: windowSettings.maximized = window.maximized
    onWidthChanged: if (!window.maximized && visible) windowSettings.width = width
    onHeightChanged: if (!window.maximized && visible) windowSettings.height = height

    // ---------- own title bar (frameless window) ----------
    // Windows' frame is replaced by the app's own 最小化 / 最大化 / 关闭. A frameless window that
    // is maximized the usual way covers the taskbar, so 最大化 fills the screen's available area.
    property bool maximized: false
    property rect normalGeometry: Qt.rect(0, 0, 0, 0)
    readonly property int titleHeight: 36

    function toggleMaximize() {
        if (window.maximized) {
            window.maximized = false
            window.x = normalGeometry.x; window.y = normalGeometry.y
            window.width = normalGeometry.width; window.height = normalGeometry.height
        } else {
            normalGeometry = Qt.rect(window.x, window.y, window.width, window.height)
            window.maximized = true
            const s = window.screen
            window.x = s.virtualX
            window.y = s.virtualY
            window.width = s.desktopAvailableWidth
            window.height = s.desktopAvailableHeight
        }
    }

    component CaptionButton: Rectangle {
        id: cap
        property string glyph: ""
        property string tip: ""
        property bool danger: false
        signal clicked()
        width: 46
        height: window.titleHeight
        color: !capHover.hovered ? "transparent"
            : cap.danger ? "#c42b1c" : Theme.surfaceAlt
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        HoverHandler { id: capHover }
        TapHandler { onTapped: cap.clicked() }
        ToolTip.visible: capHover.hovered && cap.tip !== ""
        ToolTip.delay: 600
        ToolTip.text: cap.tip
        Text {
            anchors.centerIn: parent
            text: cap.glyph
            font.family: Theme.iconFont
            font.pixelSize: 10
            color: capHover.hovered && cap.danger ? "white" : Theme.text
        }
    }

    Item {
        id: titleBar
        z: 50
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: window.titleHeight
        // Continues the navigation pane on the left, the page background on the right.
        Rectangle { width: 208; height: parent.height; color: Theme.pane; Behavior on color { ColorAnimation { duration: Theme.slow } } }
        DragHandler {
            target: null
            onActiveChanged: if (active) {
                if (window.maximized) {
                    // Dragging a maximized window restores it under the cursor, like Windows does.
                    const ratio = point.position.x / window.width
                    window.toggleMaximize()
                    window.x = point.scenePosition.x + window.x - window.width * ratio
                }
                window.startSystemMove()
            }
        }
        TapHandler {
            onDoubleTapped: window.toggleMaximize()
        }
        Row {
            anchors.right: parent.right
            anchors.top: parent.top
            CaptionButton { glyph: ""; tip: "最小化"; onClicked: window.showMinimized() }
            CaptionButton {
                glyph: window.maximized ? "" : ""
                tip: window.maximized ? "向下还原" : "最大化"
                onClicked: window.toggleMaximize()
            }
            CaptionButton { glyph: ""; tip: "关闭"; danger: true; onClicked: window.close() }
        }
    }

    // Hairline frame so the window edge stays visible without the system border.
    Rectangle {
        z: 55
        anchors.fill: parent
        visible: !window.maximized
        color: "transparent"
        border.width: 1
        border.color: Theme.borderStrong
    }

    // Resize from the edges and corners (the frameless window has no system border).
    component ResizeEdge: MouseArea {
        property int edges: 0
        enabled: !window.maximized
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onPressed: window.startSystemResize(edges)
    }
    readonly property int grip: 6
    ResizeEdge { z: 60; edges: Qt.LeftEdge; cursorShape: Qt.SizeHorCursor; x: 0; y: grip; width: grip; height: parent.height - 2 * grip }
    ResizeEdge { z: 60; edges: Qt.RightEdge; cursorShape: Qt.SizeHorCursor; x: parent.width - grip; y: grip; width: grip; height: parent.height - 2 * grip }
    ResizeEdge { z: 60; edges: Qt.TopEdge; cursorShape: Qt.SizeVerCursor; x: grip; y: 0; width: parent.width - 2 * grip; height: 3 }
    ResizeEdge { z: 60; edges: Qt.BottomEdge; cursorShape: Qt.SizeVerCursor; x: grip; y: parent.height - grip; width: parent.width - 2 * grip; height: grip }
    ResizeEdge { z: 60; edges: Qt.LeftEdge | Qt.TopEdge; cursorShape: Qt.SizeFDiagCursor; x: 0; y: 0; width: grip; height: grip }
    ResizeEdge { z: 60; edges: Qt.RightEdge | Qt.TopEdge; cursorShape: Qt.SizeBDiagCursor; x: parent.width - grip; y: 0; width: grip; height: grip }
    ResizeEdge { z: 60; edges: Qt.LeftEdge | Qt.BottomEdge; cursorShape: Qt.SizeBDiagCursor; x: 0; y: parent.height - grip; width: grip; height: grip }
    ResizeEdge { z: 60; edges: Qt.RightEdge | Qt.BottomEdge; cursorShape: Qt.SizeFDiagCursor; x: parent.width - grip; y: parent.height - grip; width: grip; height: grip }

    // ---- splash hand-off: the splash logo moves from the screen centre to the nav-pane brand ----
    // The splash (a separate window) was centred on the screen; this copy of its logo starts at
    // that same spot inside the main window, so when the splash card dissolves the logo stays
    // put, then glides and shrinks onto the brand icon in the top-left while its text fades.
    readonly property bool splashIntro: typeof startup !== "undefined" && startup && startup.splashShown && Theme.motion
    Item {
        id: introLogo
        z: 90
        visible: window.splashIntro && !introDone
        property bool introDone: false
        transformOrigin: Item.TopLeft
        width: introRow.implicitWidth
        height: introRow.implicitHeight

        Row {
            id: introRow
            spacing: 28
            Image {
                source: controller.iconUrl
                sourceSize.width: 112
                sourceSize.height: 112
                width: 112
                height: 112
                smooth: true
                mipmap: true
            }
            Text {
                id: introText
                anchors.verticalCenter: parent.verticalCenter
                text: "学习通 PLUS"
                color: Theme.text
                font.family: "Microsoft YaHei UI"
                font.pixelSize: 44
                font.weight: Font.Black
            }
        }

        function start() {
            // Splash centre (screen centre) in window coordinates; the splash logo sat 12 px above centre.
            const s = window.screen
            const cx = (s ? s.virtualX + s.width / 2 : window.x + window.width / 2) - window.x
            const cy = (s ? s.virtualY + s.height / 2 : window.y + window.height / 2) - window.y - 12
            const target = brandIcon.mapToItem(window.contentItem, 0, 0)
            fly.fromX = cx - width / 2
            fly.fromY = cy - height / 2
            fly.toX = target.x
            fly.toY = target.y
            fly.toScale = brandIcon.width / 112
            fly.start()
        }

        ParallelAnimation {
            id: fly
            property real fromX: 0
            property real fromY: 0
            property real toX: 0
            property real toY: 0
            property real toScale: 0.32
            NumberAnimation { target: introLogo; property: "x"; from: fly.fromX; to: fly.toX; duration: 720; easing.type: Easing.InOutCubic }
            NumberAnimation { target: introLogo; property: "y"; from: fly.fromY; to: fly.toY; duration: 720; easing.type: Easing.InOutCubic }
            NumberAnimation { target: introLogo; property: "scale"; from: 1; to: fly.toScale; duration: 720; easing.type: Easing.InOutCubic }
            SequentialAnimation {
                PauseAnimation { duration: 160 }
                NumberAnimation { target: introText; property: "opacity"; from: 1; to: 0; duration: 320; easing.type: Easing.OutCubic }
            }
            onFinished: introLogo.introDone = true
        }
    }
    onVisibleChanged: {
        if (visible && splashIntro && !introLogo.introDone && !fly.running) {
            // Wait one frame so the layout (and a restored maximised size) has settled.
            introLogo.x = -10000
            Qt.callLater(introLogo.start)
        }
    }

    // Content fades and lifts in when the window first appears after the splash.
    Item {
        id: shell
        anchors.fill: parent
        anchors.topMargin: window.titleHeight
        opacity: 0
        transform: Translate { id: shellShift; y: 14 }

        ParallelAnimation {
            id: reveal
            running: window.visible
            NumberAnimation { target: shell; property: "opacity"; to: 1; duration: Theme.slow; easing.type: Easing.OutCubic }
            NumberAnimation { target: shellShift; property: "y"; to: 0; duration: Theme.slow; easing.type: Easing.OutCubic }
        }

        RowLayout {
            anchors.fill: parent
            spacing: 0

            // ---------- navigation pane ----------
            Rectangle {
                Layout.preferredWidth: 208
                Layout.fillHeight: true
                color: Theme.pane
                Behavior on color { ColorAnimation { duration: Theme.slow } }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    anchors.topMargin: 20
                    spacing: 4

                    RowLayout {
                        id: brandRow
                        spacing: 10
                        Layout.leftMargin: 4
                        Layout.bottomMargin: 22
                        // Hidden while the splash logo flies in; shown the moment it lands.
                        opacity: introLogo.visible ? 0 : 1
                        Image {
                            id: brandIcon
                            source: controller.iconUrl
                            sourceSize.width: 36
                            sourceSize.height: 36
                            Layout.preferredWidth: 36
                            Layout.preferredHeight: 36
                            smooth: true
                            mipmap: true
                        }
                        ColumnLayout {
                            spacing: 0
                            Text { text: controller.appName; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 15; font.weight: Font.DemiBold }
                            Text { text: "学习通课程助手"; color: Theme.muted; font.family: Theme.uiFont; font.pixelSize: 11 }
                        }
                    }

                    Item {
                        id: navList
                        Layout.fillWidth: true
                        implicitHeight: navColumn.implicitHeight

                        // One highlight that slides between items.
                        Rectangle {
                            id: navHighlight
                            width: parent.width
                            height: 38
                            y: window.page * (38 + navColumn.spacing)
                            radius: Theme.radius
                            color: Theme.surface
                            border.color: Theme.border
                            Behavior on y { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                            Behavior on color { ColorAnimation { duration: Theme.slow } }
                            Rectangle {
                                width: 3; height: 16; radius: 2
                                color: Theme.accent
                                anchors.left: parent.left
                                anchors.leftMargin: 2
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }

                        Column {
                            id: navColumn
                            width: parent.width
                            spacing: 4
                            Repeater {
                                model: [
                                    { glyph: "", label: "运行面板" },
                                    { glyph: "", label: "设置" }
                                ]
                                delegate: Rectangle {
                                    required property var modelData
                                    required property int index
                                    readonly property bool active: window.page === index
                                    width: navColumn.width
                                    height: 38
                                    radius: Theme.radius
                                    color: !active && navHover.hovered ? Theme.surfaceAlt : "transparent"
                                    Behavior on color { ColorAnimation { duration: Theme.fast } }

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 14
                                        spacing: 12
                                        Text {
                                            text: modelData.glyph
                                            font.family: Theme.iconFont
                                            font.pixelSize: 15
                                            color: parent.parent.active ? Theme.accent : Theme.muted
                                            Behavior on color { ColorAnimation { duration: Theme.normal } }
                                        }
                                        Text {
                                            text: modelData.label
                                            color: Theme.text
                                            font.family: Theme.uiFont
                                            font.pixelSize: 13
                                            font.weight: parent.parent.active ? Font.DemiBold : Font.Normal
                                            Layout.fillWidth: true
                                        }
                                        // Dot on 设置: unsaved changes or account still missing.
                                        Rectangle {
                                            visible: index === 1 && (controller.dirty || !window.accountConfigured)
                                            width: 7; height: 7; radius: 4
                                            color: window.accountConfigured ? Theme.accent : Theme.warning
                                            Layout.rightMargin: 12
                                            SequentialAnimation on scale {
                                                running: index === 1 && !window.accountConfigured && Theme.loopMotion
                                                loops: Animation.Infinite
                                                NumberAnimation { to: 1.5; duration: 700; easing.type: Easing.InOutSine }
                                                NumberAnimation { to: 1.0; duration: 700; easing.type: Easing.InOutSine }
                                            }
                                        }
                                    }
                                    HoverHandler { id: navHover; cursorShape: Qt.PointingHandCursor }
                                    TapHandler { onTapped: window.page = index }
                                }
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: noteCol.implicitHeight + 20
                        radius: Theme.radius
                        color: Theme.surfaceAlt
                        Behavior on color { ColorAnimation { duration: Theme.slow } }
                        ColumnLayout {
                            id: noteCol
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 3
                            Text { text: "仅限学习通"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 12; font.weight: Font.DemiBold }
                            Text {
                                Layout.fillWidth: true
                                text: "配置保存在当前 Windows 用户目录。"
                                color: Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 11
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                    Text {
                        Layout.topMargin: 8
                        Layout.leftMargin: 4
                        text: "v" + controller.version
                        color: Theme.faint
                        font.pixelSize: 11
                    }
                }
            }

            // ---------- pages (fade + slide between them) ----------
            Item {
                id: pages
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: 20

                component PageSlot: Item {
                    property int pageIndex: 0
                    readonly property bool current: window.page === pageIndex
                    width: pages.width
                    height: pages.height
                    opacity: current ? 1 : 0
                    // Hidden pages must be invisible so the native video view disappears with them.
                    visible: opacity > 0.01
                    x: current ? 0 : (pageIndex < window.page ? -36 : 36)
                    Behavior on opacity { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                    Behavior on x { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
                }

                PageSlot {
                    pageIndex: 0
                    DashboardPage {
                        anchors.fill: parent
                        overlayOpen: window.overlayOpen || !parent.current
                        accountConfigured: window.accountConfigured
                        onStopRequested: stopConfirm.open()
                        onSettingsRequested: window.openSettings()
                    }
                }
                PageSlot {
                    pageIndex: 1
                    SettingsPage {
                        anchors.fill: parent
                        onUpdateRequested: window.showUpdates()
                        onGuideRequested: {
                            guide.reset()
                            window.showGuide = true
                        }
                    }
                }
            }
        }
    }

    // ---------- first-run guide ----------
    Onboarding {
        id: guide
        objectName: "guide"
        anchors.fill: parent
        z: 10
        opacity: window.showGuide ? 1 : 0
        visible: opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        onCompleted: {
            window.showGuide = false
            if (!window.accountConfigured)
                toast.show("还没有配置账号，请到“设置 → 账号”填写后再开始运行。", "warning")
        }
    }

    // ---------- toast ----------
    Rectangle {
        id: toast
        property string kind: "info"
        property bool shown: false
        anchors.horizontalCenter: parent.horizontalCenter
        y: shown ? parent.height - height - 26 : parent.height + 8
        z: 20
        width: Math.min(620, toastRow.implicitWidth + 40)
        height: 44
        radius: Theme.radius
        color: kind === "error" ? Theme.dangerSoft : kind === "warning" ? Theme.warningSoft : Theme.surface
        border.color: kind === "error" ? Theme.danger : kind === "warning" ? Theme.warning : Theme.border
        opacity: shown ? 1 : 0
        visible: opacity > 0.01
        Behavior on y { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutBack; easing.overshoot: 1.1 } }
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        Row {
            id: toastRow
            anchors.centerIn: parent
            spacing: 10
            Text {
                text: toast.kind === "error" ? "" : toast.kind === "warning" ? "" : ""
                font.family: Theme.iconFont
                font.pixelSize: 14
                color: toast.kind === "error" ? Theme.danger : toast.kind === "warning" ? Theme.warning : Theme.accent
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                id: toastText
                width: Math.min(implicitWidth, 560)
                elide: Text.ElideRight
                color: toast.kind === "error" ? Theme.danger : toast.kind === "warning" ? Theme.warning : Theme.text
                font.family: Theme.uiFont
                font.pixelSize: 13
                anchors.verticalCenter: parent.verticalCenter
            }
        }
        Timer { id: toastTimer; interval: 4600; onTriggered: toast.shown = false }
        function show(message, kind) {
            toastText.text = message
            toast.kind = kind
            toast.shown = true
            toastTimer.restart()
        }
    }

    // ---------- dialogs ----------
    UpdateDialog {
        id: updateDialog
        onInstallRequested: {
            if (controller.updater.installAndQuit())
                window.quitApp()
        }
    }
    Connections {
        target: controller.updater
        function onUpdateAvailable() {
            if (!guide.visible) updateDialog.open()
        }
    }
    function showUpdates() { updateDialog.open() }

    CoursePickerDialog { id: coursePicker; objectName: "coursePicker" }

    ConfirmDialog {
        id: stopConfirm
        title: "停止任务"
        message: "立即结束当前任务进程？未完成的章节可在下次启动时重试。"
        acceptText: "停止"
        destructive: true
        onAccepted: controller.stopRun()
    }

    ConfirmDialog {
        id: closeConfirm
        title: "任务仍在运行"
        message: "关闭窗口将结束当前任务。仍要退出吗？"
        acceptText: "退出"
        destructive: true
        onAccepted: window.quitApp()
    }

    ConfirmDialog {
        id: promptDialog
        title: "任务进程需要确认"
        acceptText: "继续"
        rejectText: "不继续"
        onAccepted: controller.answerPrompt(true)
        onRejected: controller.answerPrompt(false)
    }

    Connections {
        target: controller
        function onToast(message, kind) { toast.show(message, kind) }
        function onRunStateChanged() {
            if (!controller.running) {
                coursePicker.close()
                promptDialog.close()
                stopConfirm.close()
                if (controller.statusKind === "done" || controller.statusKind === "error") {
                    if (!window.visible && window.trayObj)  // hidden in the tray: use a notification
                        window.trayObj.notify("学习通PLUS", controller.statusKind === "done" ? "任务已全部完成" : "任务进程已退出，请查看运行日志")
                    else if (controller.alertOnFinish && !window.active)
                        window.alert(0)  // flash the taskbar button until the window is focused
                    toast.show(controller.statusKind === "done" ? "任务已全部完成" : "任务进程已退出，请查看运行日志",
                               controller.statusKind === "done" ? "info" : "warning")
                }
            }
        }
        function onCourseSelectionRequested(courses) { coursePicker.openWith(courses) }
        function onCoursesDetected(courses) {
            coursePicker.openSelect(courses, controller.courseList.split(",").map(x => x.trim()))
        }
        function onPromptRequested(text) {
            promptDialog.message = text
            promptDialog.open()
        }
    }

    Connections {
        target: window.trayObj
        function onQuitRequested() {
            if (controller.running) {
                window.showWindow()
                closeConfirm.open()
            } else {
                window.quitApp()
            }
        }
        function onToggleRunRequested() {
            if (controller.running) {
                window.showWindow()
                stopConfirm.open()
            } else if (!window.accountConfigured) {
                window.showWindow()
                window.openSettings()
            } else {
                controller.startRun()
            }
        }
    }

    onClosing: close => {
        if (window.allowClose)
            return
        if (window.trayObj && window.trayObj.closeToTray) {
            // Keep running in the background; the tray icon brings the window back.
            close.accepted = false
            window.hide()
            window.trayObj.hintOnce()
            return
        }
        close.accepted = false
        if (controller.running)
            closeConfirm.open()
        else
            window.quitApp()
    }
}
