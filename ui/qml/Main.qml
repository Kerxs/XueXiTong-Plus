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

    // ---------- window animations (own title bar) ----------
    // 最小化 / 隐藏到托盘 / 退出: the window fades out while its content shrinks a little, then the
    // action runs; coming back (taskbar, tray) fades it in again. 最大化 / 还原 glide the frame.
    // All instant when 界面动画 is off (Theme.motion).
    property var afterFade: null
    function fadeOutThen(action) {
        if (!Theme.motion) { action(); return }
        window.afterFade = action
        fadeIn.stop()
        fadeOut.start()
    }
    function animatedMinimize() { fadeOutThen(() => window.showMinimized()) }
    function animatedHide() { fadeOutThen(() => { window.hide(); if (window.trayObj) window.trayObj.hintOnce() }) }
    function animatedQuit() { fadeOutThen(() => window.quitApp()) }

    ParallelAnimation {
        id: fadeOut
        NumberAnimation { target: window; property: "opacity"; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { target: window.contentItem; property: "scale"; to: 0.96; duration: 170; easing.type: Easing.InCubic }
        onFinished: {
            const action = window.afterFade
            window.afterFade = null
            if (action) action()
        }
    }
    ParallelAnimation {
        id: fadeIn
        NumberAnimation { target: window; property: "opacity"; to: 1; duration: 220; easing.type: Easing.OutCubic }
        NumberAnimation { target: window.contentItem; property: "scale"; to: 1; duration: 220; easing.type: Easing.OutCubic }
    }
    // Back on screen after 最小化 or the tray: fade in from where fadeOut left it.
    onVisibilityChanged: visibility => {
        if (visibility === Window.Hidden || visibility === Window.Minimized || fadeOut.running)
            return
        if (window.opacity < 1 || window.contentItem.scale < 1) {
            if (!Theme.motion) { window.opacity = 1; window.contentItem.scale = 1; return }
            fadeIn.start()
        }
    }
    readonly property bool accountConfigured: controller.useCookies
        || (controller.username.trim() !== "" && controller.password !== "")
    readonly property bool overlayOpen: coursePicker.visible || stopConfirm.visible
        || closeConfirm.visible || promptDialog.visible || guide.visible || updateDialog.visible
        || manualDialog.visible || closeChoice.visible

    Component.onCompleted: {
        window.contentItem.transformOrigin = Item.Center   // window fade / shrink animations
        window.width = Math.max(window.minimumWidth, windowSettings.width)
        window.height = Math.max(window.minimumHeight, windowSettings.height)
        if (windowSettings.maximized)
            Qt.callLater(() => window.toggleMaximize(false))
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

    // animate: false when restoring the saved state at start-up (no glide while opening).
    function toggleMaximize(animate) {
        let target
        if (window.maximized) {
            window.maximized = false
            target = normalGeometry
        } else {
            normalGeometry = Qt.rect(window.x, window.y, window.width, window.height)
            window.maximized = true
            const s = window.screen
            target = Qt.rect(s.virtualX, s.virtualY, s.desktopAvailableWidth, s.desktopAvailableHeight)
        }
        window.pendingGeometry = target
        if (animate === false || !Theme.motion || !window.visible) {
            maximizeFx.stop()
            window.applyPendingGeometry()
            window.opacity = 1
            window.contentItem.scale = 1
            return
        }
        // Resizing this window is expensive (layouts + the native video view), so the frame is not
        // animated pixel by pixel (it would jump anyway): the window dips, changes size once, and
        // settles in with a small zoom — the same feel as 最小化 / 还原.
        maximizeFx.restart()
    }
    property rect pendingGeometry: Qt.rect(0, 0, 0, 0)
    function applyPendingGeometry() {
        window.x = pendingGeometry.x; window.y = pendingGeometry.y
        window.width = pendingGeometry.width; window.height = pendingGeometry.height
    }
    SequentialAnimation {
        id: maximizeFx
        ParallelAnimation {
            NumberAnimation { target: window; property: "opacity"; to: 0.35; duration: 90; easing.type: Easing.InQuad }
            NumberAnimation { target: window.contentItem; property: "scale"; to: 0.985; duration: 90; easing.type: Easing.InQuad }
        }
        ScriptAction { script: window.applyPendingGeometry() }
        ParallelAnimation {
            NumberAnimation { target: window; property: "opacity"; to: 1; duration: 200; easing.type: Easing.OutCubic }
            NumberAnimation { target: window.contentItem; property: "scale"; from: 0.985; to: 1; duration: 220; easing.type: Easing.OutCubic }
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
                    window.toggleMaximize(false)   // instant: the window follows the cursor
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
            CaptionButton { glyph: ""; tip: "最小化"; onClicked: window.animatedMinimize() }
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

    // ---- splash hand-off: the splash logo moves from the screen centre to the brand ----
    // The splash (a separate window) was centred on the screen; this copy of its logo starts at
    // that same spot inside the main window, so when the splash card dissolves the logo stays
    // put, then glides and shrinks onto the brand: the nav-pane brand, or on a first start the
    // guide's welcome icon and title. Icon and text move together.
    // No twitch on landing:
    //  * every brand image decodes the same 256 px texture with mipmaps, so the shrunken flying
    //    icon and the real icon are sampled the same way (also sharp on 150 % / 200 % displays);
    //  * the title copy is not scaled text: it flies on its own and animates its real font size
    //    down to the target's, so it ends as native text at the target's exact position;
    //  * the targets are followed live on every frame (window resize, entrance slides).
    readonly property bool splashIntro: typeof startup !== "undefined" && startup && startup.splashShown && Theme.motion
    readonly property size brandTexture: Qt.size(256, 256)
    Item {
        id: introLogo
        z: 90
        visible: window.splashIntro && !introDone
        property bool introDone: false
        property Text titleSource: brandTitle   // set in start(): nav brand title or the guide's welcome title
        transformOrigin: Item.TopLeft
        width: introRow.implicitWidth
        height: introRow.implicitHeight

        Row {
            id: introRow
            spacing: 28
            Image {
                id: introIcon
                source: controller.iconUrl
                sourceSize: window.brandTexture
                width: 112
                height: 112
                smooth: true
                mipmap: true
            }
            Item {
                id: introTextBox
                anchors.verticalCenter: parent.verticalCenter
                width: introText.implicitWidth
                height: introText.implicitHeight
                transform: Translate { id: textShift }
                Text {
                    id: introText              // the splash wordmark; fades out while the title copy fades in
                    anchors.verticalCenter: parent.verticalCenter
                    text: "学习通 PLUS"
                    color: Theme.text
                    font.family: "Microsoft YaHei UI"
                    font.pixelSize: 44
                    font.weight: Font.Black
                }
            }
        }

        // Targets are read live on every frame (not computed once at the start): the window may
        // still be resized (restored size / maximised) and the shell or guide card still sliding in
        // while the logo travels, and a precomputed spot then ends a few pixels off and jumps.
        property Item iconTarget: brandIcon
        property real fromX: 0
        property real fromY: 0
        property real prog: 0          // 0 → 1 with InOutCubic (flyAnim)
        onProgChanged: follow()

        function follow() {
            const t = iconTarget.mapToItem(window.contentItem, 0, 0)
            const k = iconTarget.width / 112
            x = fromX + (t.x - fromX) * prog
            y = fromY + (t.y - fromY) * prog
            scale = 1 + (k - 1) * prog
            // The wordmark (inside the scaled row) heads for the title's left / middle.
            const title = titleSource.mapToItem(window.contentItem, 0, 0)
            textShift.x = ((title.x - t.x) / k - introTextBox.x) * prog
            textShift.y = ((title.y + titleSource.height / 2 - t.y) / k - (introTextBox.y + introTextBox.height / 2)) * prog
        }

        function start() {
            // Splash centre (screen centre) in window coordinates; the splash logo sat 12 px above centre.
            const s = window.screen
            const cx = (s ? s.virtualX + s.width / 2 : window.x + window.width / 2) - window.x
            const cy = (s ? s.virtualY + s.height / 2 : window.y + window.height / 2) - window.y - 12
            // First start: the guide covers the window, so the logo lands on the welcome page's
            // icon and title instead of the nav-pane brand behind it.
            const onGuide = window.showGuide
            iconTarget = onGuide ? guide.welcomeIconItem : brandIcon
            titleSource = onGuide ? guide.welcomeTitleItem : brandTitle
            fromX = cx - width / 2
            fromY = cy - height / 2
            prog = 0
            follow()
            // Title copy one character at a time — 学, 习, 通, P, L, U, S — each its own flight a little
            // later than the one before, landing where the real title draws that character.
            const full = titleSource.text
            const k = iconTarget.width / 112
            introTitles.fromSize = titleSource.font.pixelSize / k
            introTitles.toSize = titleSource.font.pixelSize
            const pieces = []
            for (let i = 0; i < full.length; ++i) {
                const ch = full.charAt(i)
                if (ch.trim().length === 0) continue          // spaces only take up room
                const before = full.substring(0, i)
                pieces.push({ text: ch, fromOffset: fmFrom.advanceWidth(before), toOffset: fmTo.advanceWidth(before) })
            }
            introTitles.fromX = fromX + introTextBox.x
            introTitles.fromY = fromY + (112 - fmFrom.height) / 2
            introTitles.landed = 0
            introTitles.opacity = 1
            introTitles.pieces = pieces
            flyAnim.start()
            for (let i = 0; i < pieceRep.count; ++i) pieceRep.itemAt(i).go()
        }

        ParallelAnimation {
            id: flyAnim
            NumberAnimation { target: introLogo; property: "prog"; from: 0; to: 1; duration: 560; easing.type: Easing.InOutCubic }
            // The wordmark gives way to the title pieces while it travels.
            SequentialAnimation {
                PauseAnimation { duration: 200 }
                NumberAnimation { target: introText; property: "opacity"; from: 1; to: 0; duration: 240; easing.type: Easing.InOutQuad }
            }
        }
    }
    // The title copy, in pieces: native text whose font size animates (sharp and identical when
    // it lands). Arrival order: the icon (560 ms), then 学, 习, 通, P, L, U, S one by one.
    Item {
        id: introTitles
        z: 91
        visible: introLogo.visible
        property var pieces: []
        property real fromX: 0
        property real fromY: 0
        property real fromSize: 44
        property real toSize: 15
        property int landed: 0
        function pieceLanded() {
            landed += 1
            if (landed === pieces.length) {
                // The real brand takes over: the icon in the same frame (identical), the title with a
                // 100 ms cross-fade (separately drawn pieces vs one string differ by a hair).
                introLogo.titleSource.opacity = 0
                brandRow.opacity = 1
                titleHandoff.start()
            }
        }
        SequentialAnimation {
            id: titleHandoff
            ParallelAnimation {
                NumberAnimation { target: introLogo.titleSource; property: "opacity"; from: 0; to: 1; duration: 100 }
                NumberAnimation { target: introTitles; property: "opacity"; from: 1; to: 0; duration: 100 }
            }
            ScriptAction { script: introLogo.introDone = true }
        }
        FontMetrics {                 // the title's font at the splash size (start positions)
            id: fmFrom
            font.family: introLogo.titleSource.font.family
            font.weight: introLogo.titleSource.font.weight
            font.pixelSize: introTitles.fromSize
        }
        FontMetrics {                 // ... and at its real size (landing positions)
            id: fmTo
            font.family: introLogo.titleSource.font.family
            font.weight: introLogo.titleSource.font.weight
            font.pixelSize: introTitles.toSize
        }
        Repeater {
            id: pieceRep
            model: introTitles.pieces
            Text {
                id: piece
                required property var modelData
                required property int index
                // first character 90 ms after the icon starts, then each one 45 ms after the previous
                readonly property int delay: 90 + index * 45
                property real prog: 0
                opacity: 0
                text: modelData.text
                color: introLogo.titleSource.color
                font.family: introLogo.titleSource.font.family
                font.weight: introLogo.titleSource.font.weight
                font.pixelSize: introTitles.fromSize
                x: introTitles.fromX + modelData.fromOffset
                y: introTitles.fromY
                onProgChanged: {
                    // Live target: wherever the real title is right now (exact, unrounded).
                    const title = introLogo.titleSource.mapToItem(window.contentItem, 0, 0)
                    const sx = introTitles.fromX + modelData.fromOffset
                    x = sx + (title.x + modelData.toOffset - sx) * prog
                    y = introTitles.fromY + (title.y - introTitles.fromY) * prog
                    font.pixelSize = introTitles.fromSize + (introTitles.toSize - introTitles.fromSize) * prog
                }
                function go() { pieceFly.start(); pieceFade.start() }
                SequentialAnimation {
                    id: pieceFly
                    PauseAnimation { duration: piece.delay }
                    NumberAnimation { target: piece; property: "prog"; from: 0; to: 1; duration: 560; easing.type: Easing.InOutCubic }
                    ScriptAction { script: introTitles.pieceLanded() }
                }
                SequentialAnimation {
                    id: pieceFade
                    PauseAnimation { duration: 150 + piece.delay / 2 }
                    NumberAnimation { target: piece; property: "opacity"; to: 1; duration: 240; easing.type: Easing.InOutQuad }
                }
            }
        }
    }
    onVisibleChanged: {
        if (visible && splashIntro && !introLogo.introDone && !flyAnim.running) {
            // Wait one frame so the window is laid out before the flight starts.
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
                        // Hidden while the splash logo flies in; fades in as it lands (see `fly`).
                        opacity: window.splashIntro ? 0 : 1
                        Image {
                            id: brandIcon
                            source: controller.iconUrl
                            sourceSize: window.brandTexture
                            Layout.preferredWidth: 36
                            Layout.preferredHeight: 36
                            smooth: true
                            mipmap: true
                        }
                        ColumnLayout {
                            spacing: 0
                            Text { id: brandTitle; text: controller.appName; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 15; font.weight: Font.DemiBold }
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
        brandHidden: window.splashIntro && !introLogo.introDone
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
        onAccepted: window.visible ? window.animatedQuit() : window.quitApp()
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
                        window.trayObj.notify(controller.appName, controller.statusKind === "done" ? "任务已全部完成" : "任务进程已退出，请查看运行日志")
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
        function onManualPopupRequested() {
            if (!manualDialog.visible && !guide.visible) manualDialog.open()
        }
    }

    // Content the program does not do (documents, reading, surveys …), shown when no push
    // service is configured. The list keeps growing while the dialog is open.
    ConfirmDialog {
        id: manualDialog
        title: "有内容需要手动完成"
        width: 480
        acceptText: "去设置推送"
        rejectText: "知道了"
        message: {
            const items = controller.manualTasks
            let text = "下面的内容程序无法自动完成，需要你到学习通手动完成：\n"
            for (let i = 0; i < Math.min(items.length, 8); ++i) {
                const t = items[i]
                text += "\n• " + t.kind + (t.name ? "「" + t.name + "」" : "") + " — " + t.chapter
            }
            if (items.length > 8) text += "\n… 共 " + items.length + " 项（完整列表见运行日志）"
            return text + "\n\n设置推送服务后，会改为推送提醒，不再弹窗。"
        }
        onAccepted: window.openSettings()
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

    // Closing the window: ask (default) whether to keep running in the background or quit, with
    // "以后都这样" to remember it; the remembered choice can be changed in 设置 → 运行.
    onClosing: close => {
        if (window.allowClose)
            return
        close.accepted = false
        const action = window.trayObj ? window.trayObj.closeAction : "quit"
        if (action === "tray") {
            window.animatedHide()           // keeps running; the tray icon brings the window back
        } else if (action === "quit") {
            if (controller.running) closeConfirm.open()
            else window.animatedQuit()
        } else {
            closeChoice.remember = false
            closeChoice.open()
        }
    }

    BaseDialog {
        id: closeChoice
        title: "关闭窗口"
        width: 460
        property bool remember: false
        contentItem: ColumnLayout {
            spacing: 14
            Text {
                Layout.fillWidth: true
                text: "要让学习通 PLUS 在后台继续运行，还是直接退出？"
                    + (controller.running ? "\n任务正在运行：后台运行会继续任务，直接退出会结束任务。"
                                          : "\n后台运行时程序留在系统托盘，点击托盘图标可以重新打开。")
                color: Theme.text
                font.family: Theme.uiFont
                font.pixelSize: 13
                lineHeight: 1.3
                wrapMode: Text.Wrap
            }
            AppCheckBox {
                text: "以后都这样，不再询问（可在“设置 → 运行”里修改）"
                checked: closeChoice.remember
                onToggled: closeChoice.remember = checked
            }
        }
        buttons: [
            AppButton { text: "取消"; kind: "ghost"; onClicked: closeChoice.close() },
            AppButton {
                text: "直接退出"
                kind: "danger"
                onClicked: {
                    if (closeChoice.remember && window.trayObj) window.trayObj.closeAction = "quit"
                    closeChoice.close()
                    window.animatedQuit()
                }
            },
            AppButton {
                text: "后台运行"
                kind: "primary"
                visible: !!window.trayObj && window.trayObj.available
                onClicked: {
                    if (closeChoice.remember) window.trayObj.closeAction = "tray"
                    closeChoice.close()
                    window.animatedHide()
                }
            }
        ]
    }
}
