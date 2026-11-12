import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Card {
    title: "任务进度"
    subtitle: controller.taskModel.count > 0 ? "最近 " + controller.taskModel.count + " 个音视频任务" : "运行后显示视频和音频任务的进度"
    icon: ""

    ListView {
        id: list
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 60
        clip: true
        spacing: 6
        model: controller.taskModel
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

        add: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.normal }
                NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
            }
        }
        displaced: Transition {
            NumberAnimation { properties: "y"; duration: Theme.normal; easing.type: Easing.OutCubic }
        }

        delegate: Rectangle {
            required property string name
            required property int percent
            required property string detail
            required property bool done
            required property string state
            readonly property color tint: state === "done" ? Theme.success
                : state === "pending" ? Theme.warning
                : (state === "failed" || state === "stopped") ? Theme.muted : Theme.accent
            width: ListView.view.width - 8
            height: 46
            radius: Theme.radius
            color: done ? Theme.successSoft : Theme.surfaceAlt
            Behavior on color { ColorAnimation { duration: Theme.slow } }

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                anchors.topMargin: 7
                anchors.bottomMargin: 8
                spacing: 5
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: done ? "" : ""
                        font.family: Theme.iconFont
                        font.pixelSize: 11
                        color: tint
                    }
                    Text {
                        Layout.fillWidth: true
                        text: name
                        color: Theme.text
                        font.pixelSize: 12
                        elide: Text.ElideMiddle
                    }
                    Text {
                        text: detail !== "" ? detail : percent + "%"
                        color: Theme.muted
                        font.pixelSize: 11
                        font.family: Theme.monoFont
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    height: 4
                    radius: 2
                    color: Theme.border
                    Rectangle {
                        width: parent.width * Math.max(0, Math.min(100, percent)) / 100
                        height: parent.height
                        radius: 2
                        color: tint
                        Behavior on color { ColorAnimation { duration: Theme.slow } }
                        Behavior on width { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
                    }
                }
            }
        }

        Text {
            anchors.centerIn: parent
            visible: list.count === 0
            text: "暂无任务"
            color: Theme.faint
            font.pixelSize: 12
        }
    }
}
