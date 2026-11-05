import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Course list with checkboxes. Two uses:
//  * run mode    - the worker is waiting on input(); accept writes the ids to its stdin, cancel stops the run
//  * select mode - "识别课程" in 基本参数; accept fills the 课程 ID field, cancel just closes
BaseDialog {
    id: dialog
    property var courses: []
    property var checked: ({})
    property bool selectMode: false
    readonly property var selected: selectedIds()
    title: selectMode ? "识别到 " + courses.length + " 门课程" : "选择要学习的课程"
    closePolicy: selectMode ? Popup.CloseOnEscape : Popup.NoAutoClose
    width: Math.min(620, parent ? parent.width - 80 : 620)
    height: Math.min(Math.max(320, 210 + courses.length * 62), 560, parent ? parent.height - 80 : 560)

    function openWith(list) {
        selectMode = false
        courses = list
        checked = ({})
        open()
    }

    // Pre-ticks the courses already in the 课程 ID field.
    function openSelect(list, currentIds) {
        selectMode = true
        courses = list
        const next = {}
        for (const c of list)
            if (currentIds.indexOf(c.courseId) >= 0) next[c.courseId + "/" + c.clazzId] = true
        checked = next
        open()
    }

    function selectedIds() {
        const ids = []
        for (const c of courses) {
            if (checked[c.courseId + "/" + c.clazzId] && ids.indexOf(c.courseId) < 0)
                ids.push(c.courseId)
        }
        return ids
    }

    function toggle(key) {
        const next = Object.assign({}, checked)
        next[key] = !next[key]
        checked = next
    }

    function setAll(on) {
        const next = {}
        if (on) for (const c of courses) next[c.courseId + "/" + c.clazzId] = true
        checked = next
    }

    contentItem: ColumnLayout {
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: dialog.selectMode
                    ? "勾选要学习的课程，确定后会填入“课程 ID”。都不勾选表示学习全部课程。"
                    : "未填写课程 ID，任务进程正在等待选择。不勾选任何课程将学习全部课程；同一课程的多个班级会分别完成。"
                color: Theme.muted
                font.family: Theme.uiFont
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }
            IconButton {
                visible: dialog.courses.length > 0
                text: dialog.selected.length === dialog.courses.length ? "全不选" : "全选"
                onClicked: dialog.setAll(dialog.selected.length !== dialog.courses.length)
            }
        }
        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 6
            model: dialog.courses
            ScrollBar.vertical: ScrollBar {}

            delegate: Rectangle {
                id: row
                required property var modelData
                required property int index
                readonly property string key: modelData.courseId + "/" + modelData.clazzId
                readonly property bool on: !!dialog.checked[key]
                width: ListView.view.width - 8
                height: 56
                radius: Theme.radius
                color: on ? Theme.accentSoft : (rowHover.hovered ? Theme.surfaceAlt : Theme.surface)
                border.color: on ? Theme.accent : Theme.border
                Behavior on color { ColorAnimation { duration: Theme.fast } }
                Behavior on border.color { ColorAnimation { duration: Theme.fast } }

                // Staggered entrance.
                opacity: 0
                transform: Translate { id: slide; y: 10 }
                Component.onCompleted: appear.start()
                SequentialAnimation {
                    id: appear
                    PauseAnimation { duration: Math.min(row.index, 10) * (Theme.motion ? 40 : 0) }
                    ParallelAnimation {
                        NumberAnimation { target: row; property: "opacity"; to: 1; duration: Theme.normal }
                        NumberAnimation { target: slide; property: "y"; to: 0; duration: Theme.normal; easing.type: Easing.OutCubic }
                    }
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    spacing: 12
                    AppCheckBox {
                        checked: row.on
                        onClicked: dialog.toggle(row.key)
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text { text: modelData.title; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
                        Text {
                            Layout.fillWidth: true
                            text: "课程 " + modelData.courseId + " · 班级 " + modelData.clazzId + (modelData.teacher ? " · " + modelData.teacher : "")
                            color: Theme.muted
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                    }
                }
                HoverHandler { id: rowHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: dialog.toggle(row.key) }
            }

            Text {
                anchors.centerIn: parent
                visible: list.count === 0
                text: "没有读取到课程列表"
                color: Theme.faint
            }
        }
    }

    buttons: [
        AppButton {
            text: dialog.selectMode ? "取消" : "停止任务"
            kind: dialog.selectMode ? "secondary" : "danger"
            onClicked: dialog.reject()
        },
        AppButton {
            text: dialog.selectMode
                ? (dialog.selected.length > 0 ? "使用所选 " + dialog.selected.length + " 门" : "学习全部课程")
                : (dialog.selected.length > 0 ? "学习所选 " + dialog.selected.length + " 门" : "学习全部课程")
            kind: "primary"
            onClicked: dialog.accept()
        }
    ]

    onAccepted: dialog.selectMode ? controller.chooseCourses(selectedIds()) : controller.submitCourses(selectedIds())
    onRejected: if (!dialog.selectMode) controller.stopRun()
}
