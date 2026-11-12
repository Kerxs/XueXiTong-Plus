import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Read-only view of the chapter quiz the worker is filling in.
Rectangle {
    id: root
    // In the stacked visual panel the title / coverage live in the panel's divider bar.
    property bool compactHeader: false
    readonly property var work: controller.work
    readonly property bool hasWork: !!(work && work.questions && work.questions.length > 0)
    // The list model only changes when a different quiz arrives, so status updates
    // ("已提交") don't rebuild the list and replay the entrance cascade.
    readonly property string quizKey: hasWork ? work.title + "|" + work.questions.length + "|" + work.coverRate : ""
    property var questions: []
    onQuizKeyChanged: {
        questions = hasWork ? work.questions : []
        list.positionViewAtBeginning()
    }

    color: Theme.sunken
    radius: Theme.radius
    Behavior on color { ColorAnimation { duration: Theme.slow } }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 10
        visible: root.hasWork

        RowLayout {
            visible: !root.compactHeader
            Layout.fillWidth: true
            spacing: 10
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    Layout.fillWidth: true
                    text: root.hasWork ? root.work.title : ""
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                Text {
                    text: !root.hasWork ? "" : root.work.pending ? "共 " + root.work.questions.length + " 题 · 正在查找答案"
                        : "共 " + root.work.questions.length + " 题 · 题库覆盖率 " + root.work.coverRate + "%"
                    color: Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                }
            }
            StatusPill {
                text: controller.workStatus
                kind: controller.workStatus.indexOf("失败") >= 0 ? "error"
                    : (controller.workStatus === "已提交" || controller.workStatus === "已保存") ? "done" : "running"
            }
        }

        Rectangle {
            visible: !root.compactHeader
            Layout.fillWidth: true
            height: 4
            radius: 2
            color: Theme.border
            Rectangle {
                width: parent.width * (root.hasWork ? root.work.coverRate : 0) / 100
                height: parent.height
                radius: 2
                color: Theme.success
                Behavior on width { NumberAnimation { duration: Theme.slow * 2; easing.type: Easing.OutCubic } }
            }
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 8
            model: root.questions
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            // Question cards cascade in each time a new quiz arrives.
            populate: Transition {
                id: cascade
                SequentialAnimation {
                    PauseAnimation { duration: Math.min(cascade.ViewTransition.index, 8) * (Theme.motion ? 70 : 0) }
                    ParallelAnimation {
                        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.normal }
                        NumberAnimation { property: "y"; from: cascade.ViewTransition.destination.y + 16; duration: Theme.slow; easing.type: Easing.OutCubic }
                    }
                }
            }
            delegate: QuestionCard {
                required property var modelData
                required property int index
                width: ListView.view.width - 10
                question: modelData
                revealDelay: Math.min(index, 8) * (Theme.motion ? 70 : 0) + Theme.normal
            }
        }
    }

    // Empty state with a slow breathing icon.
    ColumnLayout {
        anchors.centerIn: parent
        visible: !root.hasWork
        spacing: 8
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: ""
            font.family: Theme.iconFont
            font.pixelSize: 28
            color: Theme.faint
            id: emptyIcon
            Pulse {
                target: emptyIcon
                from: 1.0
                to: 0.35
                period: 2800
                // loopMotion (not motion): it also rests while the window is minimized or in the tray
                active: !root.hasWork && Theme.loopMotion && root.visible
            }
        }
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: "暂无答题内容"
            color: Theme.muted
            font.family: Theme.uiFont
            font.pixelSize: 14
        }
        Text {
            visible: !root.compactHeader
            Layout.alignment: Qt.AlignHCenter
            text: "运行到章节检测时，这里会显示题目和填写的答案"
            color: Theme.faint
            font.family: Theme.uiFont
            font.pixelSize: 12
        }
    }
}
