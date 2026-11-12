import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: page
    property bool overlayOpen: false
    property bool accountConfigured: true
    signal stopRequested()
    signal settingsRequested()

    function start() {
        if (!accountConfigured) {
            settingsRequested()
            return
        }
        controller.startRun()
    }

    RowLayout {
        anchors.fill: parent
        spacing: Theme.gap

        // ---------- left: dashboard + basic parameters ----------
        // When the window is too low for everything (a maximised window on a 200 % screen leaves
        // about 900 px: Issue #1, the log was cut off below the window) the column scrolls instead
        // of squeezing; when it fits, it fills the height exactly and nothing scrolls.
        Flickable {
            id: leftScroll
            Layout.preferredWidth: Math.max(470, page.width * 0.44)
            Layout.maximumWidth: 640
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: leftCol.height
            boundsBehavior: Flickable.StopAtBounds
            interactive: contentHeight > height + 1
            ScrollBar.vertical: ScrollBar { policy: leftScroll.interactive ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }

        ColumnLayout {
            id: leftCol
            // Log height: expanded it takes what the fixed parts leave (keeping 190 for tasks),
            // collapsed just its header. `logOpen` animates 0..1 so only toggling animates,
            // not window resizing.
            readonly property real fixedHeight: headerRow.height + accountBanner.height + tiles.height
                + params.height + 4 * spacing
            readonly property real logExpanded: Math.max(160, leftScroll.height - fixedHeight - 190 - spacing)
            readonly property real logCollapsed: 64
            // the least the column needs: fixed parts, the task list's minimum and the log as it is now
            readonly property real needed: fixedHeight + 120 + spacing + log.Layout.preferredHeight
            property real logOpen: log.expanded ? 1 : 0
            Behavior on logOpen { NumberAnimation { duration: Theme.slow; easing.type: Easing.InOutCubic } }
            width: leftScroll.width - (leftScroll.interactive ? 10 : 0)       // room for the scroll bar
            height: Math.max(leftScroll.height, needed)
            spacing: Theme.gap

            RowLayout {
                id: headerRow
                Layout.fillWidth: true
                spacing: 10
                ColumnLayout {
                    spacing: 2
                    // Title lifts in each time the page is shown.
                    transform: Translate { id: titleShift; y: 0 }
                    opacity: 1
                    id: titleBlock
                    Connections {
                        target: page
                        function onVisibleChanged() { if (page.visible && Theme.motion) titleIn.restart() }
                    }
                    ParallelAnimation {
                        id: titleIn
                        NumberAnimation { target: titleShift; property: "y"; from: 10; to: 0; duration: Theme.slow; easing.type: Easing.OutCubic }
                        NumberAnimation { target: titleBlock; property: "opacity"; from: 0; to: 1; duration: Theme.slow }
                    }
                    Text { text: "运行面板"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 22; font.weight: Font.DemiBold }
                    Text {
                        text: controller.useCookies ? "使用 cookies 登录" : (controller.username !== "" ? "账号 " + controller.username : "尚未填写账号")
                        color: page.accountConfigured ? Theme.muted : Theme.warning
                        font.family: Theme.uiFont
                        font.pixelSize: 12
                        Behavior on color { ColorAnimation { duration: Theme.normal } }
                    }
                }
                Item { Layout.fillWidth: true }
                StatusPill { text: controller.status; kind: controller.statusKind }

                // 暂停 / 继续, next to start / stop while a run is going.
                AppButton {
                    text: controller.paused ? "继续" : "暂停"
                    glyph: controller.paused ? "" : ""
                    kind: controller.paused ? "primary" : "warning"
                    opacity: controller.running ? 1 : 0
                    visible: opacity > 0.01
                    enabled: controller.running
                    Behavior on opacity { NumberAnimation { duration: Theme.normal } }
                    onClicked: controller.paused ? controller.resumeRun() : controller.pauseRun()
                }

                // Start / stop swap with a crossfade.
                Item {
                    implicitWidth: Math.max(startButton.implicitWidth, stopButton.implicitWidth)
                    implicitHeight: startButton.implicitHeight
                    AppButton {
                        id: startButton
                        anchors.right: parent.right
                        text: "开始运行"
                        glyph: ""
                        kind: "primary"
                        opacity: controller.running ? 0 : 1
                        visible: opacity > 0.01
                        enabled: !controller.running
                        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
                        onClicked: page.start()
                    }
                    AppButton {
                        id: stopButton
                        anchors.right: parent.right
                        text: "停止"
                        glyph: ""
                        kind: "danger"
                        opacity: controller.running ? 1 : 0
                        visible: opacity > 0.01
                        enabled: controller.running
                        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
                        onClicked: page.stopRequested()
                    }
                }
            }

            // Reminder shown until an account (or cookies login) is configured.
            Rectangle {
                id: accountBanner
                Layout.fillWidth: true
                Layout.preferredHeight: page.accountConfigured ? 0 : 50
                Layout.topMargin: page.accountConfigured ? -Theme.gap : 0
                clip: true
                radius: Theme.radiusLarge
                color: Theme.warningSoft
                border.color: Theme.warning
                opacity: page.accountConfigured ? 0 : 1
                Behavior on Layout.preferredHeight { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                Behavior on Layout.topMargin { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                Behavior on opacity { NumberAnimation { duration: Theme.normal } }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 8
                    spacing: 10
                    Text { text: ""; font.family: Theme.iconFont; font.pixelSize: 15; color: Theme.warning }
                    Text {
                        Layout.fillWidth: true
                        text: "还没有配置账号。请到“设置 → 账号”填写账号密码，或开启 cookies 登录。"
                        color: Theme.text
                        font.family: Theme.uiFont
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                    AppButton {
                        text: "去设置"
                        glyph: ""
                        implicitHeight: 32
                        onClicked: page.settingsRequested()
                    }
                }
            }

            GridLayout {
                id: tiles
                Layout.fillWidth: true
                columns: 4
                columnSpacing: 10
                rowSpacing: 10
                StatTile { Layout.fillWidth: true; Layout.preferredWidth: 1; appearDelay: 60; label: "当前课程"; icon: ""; value: controller.currentCourse }
                StatTile { Layout.fillWidth: true; Layout.preferredWidth: 1; appearDelay: 110; label: "当前章节"; icon: ""; value: controller.currentChapter }
                StatTile { Layout.fillWidth: true; Layout.preferredWidth: 1; appearDelay: 160; label: "已完成任务"; icon: ""; countValue: controller.completedCount; counter: true }
                StatTile { Layout.fillWidth: true; Layout.preferredWidth: 1; appearDelay: 210; label: "运行时长"; icon: ""; value: controller.running || controller.completedCount > 0 ? controller.elapsed : ""; placeholder: "00:00" }
            }

            BasicParams { id: params; Layout.fillWidth: true; appearDelay: 260 }

            TaskList {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 120
                appearDelay: 320
            }

            LogPanel {
                id: log
                Layout.fillWidth: true
                Layout.preferredHeight: leftCol.logCollapsed + (leftCol.logExpanded - leftCol.logCollapsed) * leftCol.logOpen
                appearDelay: 380
                // opening the log on a low window: bring it into view
                onExpandedChanged: if (expanded && leftScroll.interactive) revealLog.restart()
            }
        }
            Timer {
                id: revealLog
                interval: Theme.slow + 20
                onTriggered: leftScroll.contentY = Math.max(0, leftScroll.contentHeight - leftScroll.height)
            }
        }

        // ---------- right: read-only visual panel ----------
        VisualPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            // Without these the panel asks for its longest line of text and, at the minimum
            // window width, runs past the right edge.
            Layout.preferredWidth: 1
            Layout.minimumWidth: 320
            suspended: page.overlayOpen
            appearDelay: 200
        }
    }
}
