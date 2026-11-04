import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Card {
    id: card
    title: "基本参数"
    subtitle: controller.running ? "任务运行中，参数已锁定；停止后可修改" : "点击开始时自动保存"
    icon: ""

    GridLayout {
        Layout.fillWidth: true
        columns: 2
        columnSpacing: 14
        rowSpacing: 8
        enabled: !controller.running
        opacity: enabled ? 1 : 0.6
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }

        Label { text: "课程 ID"; color: Theme.muted; font.pixelSize: 12; Layout.columnSpan: 2 }
        RowLayout {
            Layout.columnSpan: 2
            Layout.fillWidth: true
            spacing: 8
            AppTextField {
                Layout.fillWidth: true
                placeholderText: "点“识别课程”自动读取，或手动填写；多个 ID 用英文逗号分隔，留空学习全部"
                text: controller.courseList
                onTextEdited: controller.courseList = text
            }
            AppButton {
                objectName: "detectCoursesButton"
                text: controller.courseDetectState === "running" ? "识别中…" : "识别课程"
                glyph: ""
                enabled: controller.courseDetectState !== "running"
                onClicked: controller.detectCourses()
            }
        }
        // Names of the courses in the field (known from the last recognition).
        Text {
            readonly property var names: {
                const ids = controller.courseList.split(",").map(s => s.trim()).filter(s => s !== "")
                const byId = {}
                for (const c of controller.knownCourses) byId[c.courseId] = c.title
                return ids.map(i => byId[i] || ("未识别的课程 " + i))
            }
            visible: names.length > 0 || controller.courseDetectState === "error"
            Layout.columnSpan: 2
            Layout.fillWidth: true
            text: controller.courseDetectState === "error" && names.length === 0
                ? "⚠ " + controller.courseDetectError
                : "已选：" + names.join("、")
            color: controller.courseDetectState === "error" && names.length === 0 ? Theme.danger : Theme.muted
            font.family: Theme.uiFont
            font.pixelSize: 12
            elide: Text.ElideRight
        }

        Label { text: "视频速度（倍速已失效）"; color: Theme.muted; font.pixelSize: 12 }
        Label { text: "并行章节数"; color: Theme.muted; font.pixelSize: 12 }
        // 倍速已失效：视频统一按 1 倍速观看，这里只显示固定值。
        AppComboBox {
            Layout.fillWidth: true
            enabled: false
            model: ["1× · 倍速已失效"]
            currentIndex: 0
            ToolTip.visible: hovered
            ToolTip.text: "倍速已失效，视频按 1 倍速观看；看到课程要求的比例（如 90%）平台确认后即完成"
        }
        AppSpinBox {
            Layout.fillWidth: true
            from: 1
            to: 8
            value: controller.jobs
            onValueModified: controller.jobs = value
        }

        Label { text: "未开放章节"; color: Theme.muted; font.pixelSize: 12; Layout.columnSpan: 2 }
        AppComboBox {
            Layout.columnSpan: 2
            Layout.fillWidth: true
            readonly property var values: ["retry", "continue"]
            model: ["等待后重试（适合前置章节未完成）", "跳过该章节，继续后续章节"]
            currentIndex: Math.max(0, values.indexOf(controller.notopenAction))
            onActivated: index => controller.notopenAction = values[index]
        }
    }
}
