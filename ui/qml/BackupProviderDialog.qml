import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Add or change one 备用服务商 (core/aiproviders.py): service (through 选择服务商), API Key, model
// (typed, or picked from the service's own list). Saved into tiku.backup_providers by the controller.
BaseDialog {
    id: dlg
    title: index < 0 ? "添加备用服务商" : "编辑备用服务商 " + (index + 2)
    width: Math.min(560, (Overlay.overlay ? Overlay.overlay.width : 600) - 48)

    property int index: -1
    property string endpoint: ""
    property string error: ""
    readonly property string company: { controller.customProviders; return controller.providerName(dlg.endpoint) }
    readonly property string keyPage: controller.providerConsole(dlg.endpoint)
    readonly property var models: controller.backupModels
    readonly property string modelState: controller.backupModelState
    readonly property var shownModels: {
        const q = modelInput.text.trim().toLowerCase()
        const all = dlg.models
        return q === "" || all.indexOf(modelInput.text.trim()) >= 0 ? all : all.filter(m => m.toLowerCase().indexOf(q) >= 0)
    }

    function edit(i, entry) {
        index = i
        endpoint = entry ? entry.endpoint : ""
        keyInput.text = entry ? entry.key : ""
        modelInput.text = entry ? entry.model : ""
        error = ""
        controller.resetBackupModels()
        controller.resetAiTest()
        open()
    }
    function save() {
        error = controller.saveBackupProvider(index, endpoint, keyInput.text, modelInput.text)
        if (error === "") close()
    }

    contentItem: ColumnLayout {
        spacing: 10

        Text { text: "服务商"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 13 }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 52
            radius: Theme.radius
            color: pickHover.hovered ? Theme.surfaceAlt : Theme.surface
            border.color: pickHover.hovered ? Theme.borderStrong : Theme.border
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            HoverHandler { id: pickHover; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: picker.openFor(dlg.endpoint) }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 12
                spacing: 10
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        Layout.fillWidth: true
                        text: dlg.endpoint === "" ? "选择服务商" : (dlg.company !== "" ? dlg.company : "未识别的服务")
                        color: dlg.endpoint === "" ? Theme.muted : Theme.text
                        font.family: Theme.uiFont
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        text: dlg.endpoint === "" ? "国内、海外常用服务，或你自己的服务" : dlg.endpoint
                        color: Theme.muted
                        font.family: Theme.uiFont
                        font.pixelSize: 11
                        elide: Text.ElideMiddle
                    }
                }
                Text {
                    visible: dlg.keyPage !== ""
                    text: "获取 API Key ↗"
                    color: Theme.accent
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: controller.openUrl(dlg.keyPage) }
                }
                Text { text: "选择"; color: Theme.muted; font.family: Theme.uiFont; font.pixelSize: 12 }
            }
        }

        Text { text: "API Key"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 13 }
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            AppTextField {
                id: keyInput
                Layout.fillWidth: true
                placeholderText: "本机运行的模型服务可以留空"
                echoMode: reveal.checked ? TextInput.Normal : TextInput.Password
            }
            IconButton { id: reveal; checkable: true; glyph: checked ? "" : ""; tip: checked ? "隐藏" : "显示" }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Text { Layout.fillWidth: true; text: "模型"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 13 }
            AppButton {
                text: dlg.modelState === "running" ? "正在获取…" : (dlg.modelState === "done" ? "重新获取" : "获取模型列表")
                glyph: ""
                enabled: dlg.endpoint !== "" && dlg.modelState !== "running"
                onClicked: controller.fetchBackupModels(dlg.endpoint, keyInput.text)
            }
        }
        AppTextField {
            id: modelInput
            Layout.fillWidth: true
            placeholderText: dlg.models.length > 0 ? "搜索或直接填写模型名称" : "模型名称，例如 deepseek-chat、qwen-plus"
        }
        Text {
            visible: dlg.modelState === "error"
            Layout.fillWidth: true
            text: controller.backupModelError
            color: Theme.warning
            font.family: Theme.uiFont
            font.pixelSize: 12
            wrapMode: Text.Wrap
        }
        Rectangle {
            visible: dlg.modelState === "done" && dlg.shownModels.length > 0
            Layout.fillWidth: true
            implicitHeight: Math.min(modelColumn.implicitHeight + 8, 200)
            radius: Theme.radius
            color: Theme.sunken
            clip: true
            Flickable {
                id: modelList
                anchors.fill: parent
                anchors.margins: 4
                contentHeight: modelColumn.implicitHeight
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                // Scrolling here moves only this list, never the page behind it (Issue #1).
                WheelHandler {
                    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                    onWheel: event => {
                        const step = event.pixelDelta.y !== 0 ? event.pixelDelta.y : event.angleDelta.y / 120 * 64
                        modelList.contentY = Math.max(0, Math.min(modelList.contentHeight - modelList.height,
                                                                  modelList.contentY - step))
                        event.accepted = true
                    }
                }
                Column {
                    id: modelColumn
                    width: parent.width
                    spacing: 2
                    Repeater {
                        model: dlg.shownModels
                        Rectangle {
                            id: mrow
                            required property string modelData
                            readonly property bool on: modelData === modelInput.text.trim()
                            width: modelColumn.width
                            height: 30
                            radius: 6
                            color: on ? Theme.accentSoft : (mh.hovered ? Theme.surface : "transparent")
                            HoverHandler { id: mh; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: modelInput.text = mrow.modelData }
                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 10
                                anchors.right: parent.right
                                anchors.rightMargin: 10
                                anchors.verticalCenter: parent.verticalCenter
                                text: mrow.modelData
                                color: mrow.on ? Theme.accent : Theme.text
                                font.family: Theme.uiFont
                                font.pixelSize: 13
                                elide: Text.ElideMiddle
                            }
                        }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            AppButton {
                text: controller.aiTestState === "running" ? "正在测试…" : "测试一下"
                glyph: "\uE768"
                enabled: controller.aiTestState !== "running" && dlg.endpoint !== "" && modelInput.text.trim() !== ""
                onClicked: controller.testAi(dlg.endpoint, keyInput.text, modelInput.text)
            }
            Text {
                Layout.fillWidth: true
                text: controller.aiTestState === "idle" ? "" : (controller.aiTestState === "ok" ? "\u2713 " : "") + controller.aiTestMessage
                color: controller.aiTestState === "ok" ? Theme.success : controller.aiTestState === "error" ? Theme.danger : Theme.muted
                font.family: Theme.uiFont
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }
        }
        Text {
            visible: dlg.error !== ""
            Layout.fillWidth: true
            text: dlg.error
            color: Theme.warning
            font.family: Theme.uiFont
            font.pixelSize: 12
            wrapMode: Text.Wrap
        }

        ProviderPickerDialog {
            id: picker
            forBackup: true
            onChosen: address => {
                if (address !== dlg.endpoint) { controller.resetBackupModels(); controller.resetAiTest() }
                dlg.endpoint = address
                if (keyInput.text.trim() !== "") controller.fetchBackupModels(address, keyInput.text)
            }
        }
    }

    buttons: [
        AppButton { text: "取消"; onClicked: dlg.close() },
        AppButton { text: "保存"; kind: "primary"; onClicked: dlg.save() }
    ]
}
