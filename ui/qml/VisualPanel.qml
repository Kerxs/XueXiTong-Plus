import QtQuick
import QtQuick.Layouts
import "."

// Read-only visual panel: current video on top, the chapter quiz below.
Card {
    id: card
    property bool suspended: false
    readonly property var work: controller.work
    readonly property bool hasWork: !!(work && work.questions && work.questions.length > 0)
    readonly property bool previewOff: controller.previewMode === "off"
    // Grid: every video being watched side by side (2 → left and right, 3-4 → 2 × 2, more → 3 columns).
    readonly property bool grid: controller.previewMode === "grid" && controller.videoCount > 1

    title: "可视化面板"
    subtitle: "视频与答题 · 只读"
    icon: ""
    bodySpacing: 10

    actions: [
        Segmented {
            model: [{ value: "single", label: "普通" }, { value: "grid", label: "网格" }, { value: "off", label: "关闭" }]
            current: controller.previewMode
            onPicked: (value) => controller.previewMode = value
        }
    ]

    // ---------- previews switched off ----------
    Item {
        visible: card.previewOff
        Layout.fillWidth: true
        Layout.fillHeight: true
        onVisibleChanged: if (visible && Theme.motion) offIn.restart()
        Column {
            id: offNote
            anchors.centerIn: parent
            spacing: 6
            transform: Translate { id: offShift; y: 0 }
            ParallelAnimation {
                id: offIn
                NumberAnimation { target: offNote; property: "opacity"; from: 0; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
                NumberAnimation { target: offShift; property: "y"; from: 10; to: 0; duration: Theme.normal; easing.type: Easing.OutCubic }
            }
            width: parent.width - 40
            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: "预览已关闭"
                color: Theme.muted
                font.family: Theme.uiFont
                font.pixelSize: 14
                font.weight: Font.DemiBold
            }
            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                text: "不加载视频画面和题目，节省内存和 CPU；任务照常运行，进度看左边的“任务进度”。\n在右上角选“普通”或“网格”可以重新打开。"
                color: Theme.faint
                font.family: Theme.uiFont
                font.pixelSize: 12
                lineHeight: 1.3
            }
        }
    }

    // ---------- top: video ----------
    Item {
        id: videoArea
        visible: !card.previewOff
        Layout.fillWidth: true
        // 16:9 for one row of tiles, but never more than 45% of the panel (55% for two rows)
        // so the quiz keeps room below.
        readonly property int columns: !card.grid ? 1 : controller.videoCount <= 2 ? controller.videoCount
            : controller.videoCount <= 4 ? 2 : 3
        readonly property int rows: card.grid ? Math.ceil(controller.videoCount / columns) : 1
        Layout.preferredHeight: Math.min(width / columns * 9 / 16 * rows, card.height * (rows > 1 ? 0.55 : 0.45))
        VideoView {
            anchors.fill: parent
            visible: !card.grid
            suspended: card.suspended
        }
        GridLayout {
            anchors.fill: parent
            visible: card.grid
            columns: videoArea.columns
            rowSpacing: 6
            columnSpacing: 6
            Repeater {
                model: card.grid ? controller.videos : []
                delegate: Item {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    VideoView {
                        anchors.fill: parent
                        slotTitle: modelData.title
                        suspended: card.suspended
                    }
                    Rectangle {            // the tile's name, over its bottom edge
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 18
                        color: Qt.rgba(0, 0, 0, 0.55)
                        visible: card.suspended
                        Text {
                            anchors.fill: parent
                            anchors.leftMargin: 6
                            anchors.rightMargin: 6
                            verticalAlignment: Text.AlignVCenter
                            text: modelData.title
                            color: "#e6ecf5"
                            font.family: Theme.uiFont
                            font.pixelSize: 10
                            elide: Text.ElideMiddle
                        }
                    }
                }
            }
        }
    }
    RowLayout {
        visible: !card.previewOff
        Layout.fillWidth: true
        spacing: 6
        Text {
            text: ""
            font.family: Theme.iconFont
            font.pixelSize: 11
            color: Theme.faint
        }
        Text {
            Layout.fillWidth: true
            text: card.grid ? controller.videoCount + " 个视频同时预览 · 静音"
                : controller.videoTitle !== "" ? controller.videoTitle + " · 静音" : "视频预览静音，播放、进度、右键和键盘操作均已禁用"
            color: Theme.faint
            font.family: Theme.uiFont
            font.pixelSize: 11
            elide: Text.ElideMiddle
        }
        Pager {
            visible: !card.grid && controller.videoCount > 1
            index: Math.max(0, controller.videoIndex)
            count: controller.videoCount
            onStep: (delta) => controller.stepVideo(delta)
        }
    }

    // ---------- divider: quiz header ----------
    Rectangle { visible: !card.previewOff; Layout.fillWidth: true; height: 1; color: Theme.border; Behavior on color { ColorAnimation { duration: Theme.slow } } }
    RowLayout {
        visible: !card.previewOff
        Layout.fillWidth: true
        spacing: 10
        Text { text: ""; font.family: Theme.iconFont; font.pixelSize: 14; color: Theme.accent }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            Text {
                Layout.fillWidth: true
                text: card.hasWork ? "章节检测 · " + card.work.title : "章节检测"
                color: Theme.text
                font.family: Theme.uiFont
                font.pixelSize: 13
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            Text {
                text: !card.hasWork ? "运行到章节检测时，下方会显示题目和填写的答案"
                    : card.work.pending ? "共 " + card.work.questions.length + " 题 · 正在查找答案"
                    : "共 " + card.work.questions.length + " 题 · 题库覆盖率 " + card.work.coverRate + "%"
                color: Theme.muted
                font.family: Theme.uiFont
                font.pixelSize: 11
            }
        }
        Pager {
            index: Math.max(0, controller.workIndex)
            count: controller.workCount
            onStep: (delta) => controller.stepWork(delta)
        }
        StatusPill {
            visible: controller.workStatus !== ""
            text: controller.workStatus
            kind: controller.workStatus.indexOf("失败") >= 0 ? "error"
                : (controller.workStatus === "已提交" || controller.workStatus === "已保存") ? "done" : "running"
        }
    }
    // Coverage bar: grows from 0 each time a new quiz arrives.
    Rectangle {
        Layout.fillWidth: true
        height: 4
        radius: 2
        color: Theme.border
        visible: card.hasWork && !card.previewOff
        Rectangle {
            id: coverFill
            // Animate a 0..1 fraction (not a pixel width) so it is right however the bar is sized.
            property real fill: 0
            readonly property real target: card.hasWork ? card.work.coverRate / 100 : 0
            width: parent.width * fill
            height: parent.height
            radius: 2
            color: Theme.success
            NumberAnimation {
                id: coverGrow
                target: coverFill
                property: "fill"
                duration: Theme.slow * 2
                easing.type: Easing.OutCubic
            }
            function replay() {
                coverGrow.stop()
                fill = 0
                coverGrow.to = target
                coverGrow.start()
            }
            // Replay only when a different quiz arrives (status updates re-send the same quiz).
            readonly property string quizKey: card.hasWork
                ? card.work.title + "|" + card.work.questions.length + "|" + card.work.coverRate : ""
            onQuizKeyChanged: if (quizKey !== "") replay()
        }
    }

    // ---------- bottom: questions ----------
    WorkView {
        id: workView
        visible: !card.previewOff
        onVisibleChanged: if (visible && Theme.motion) workIn.restart()
        NumberAnimation { id: workIn; target: workView; property: "opacity"; from: 0; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 120
        compactHeader: true
    }
}
