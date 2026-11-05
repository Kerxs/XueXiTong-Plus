import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// 选择服务商 (二级菜单): the categories (国内 / 海外 / 自定义) on the left, the services of the
// chosen category on the right. Picking one fills 接口地址 and closes the dialog.
// Data comes from ui/cloudmodels.py through controller.aiRegions / aiProviders / customProviders.
BaseDialog {
    id: dlg
    title: "选择服务商"
    // Sized from the window (the dialog lives inside a settings field, whose own width is small).
    width: Math.min(720, (Overlay.overlay ? Overlay.overlay.width : 760) - 48)
    height: Math.min(520, (Overlay.overlay ? Overlay.overlay.height : 560) - 48)

    property string endpoint: ""                   // the address in use, without a trailing "/"
    property string category: "cn"
    property bool adding: false
    property string error: ""
    readonly property var custom: controller.customProviders
    readonly property var categories: controller.aiRegions.map(r => ({ id: r.id, label: r.label }))
        .concat([{ id: "custom", label: "自定义服务" }])
    readonly property var rows: category === "custom"
        ? custom.map(c => ({ name: c.name, endpoint: c.endpoint, console: "", removable: true }))
        : controller.aiProviders.filter(p => p.region === category)
            .map(p => ({ name: p.name, endpoint: p.endpoint, console: p.console, removable: false }))

    function countOf(id) {
        return id === "custom" ? custom.length : controller.aiProviders.filter(p => p.region === id).length
    }
    function categoryOf(address) {
        if (custom.some(c => c.endpoint === address)) return "custom"
        const p = controller.aiProviders.find(p => p.endpoint === address)
        return p ? p.region : (address !== "" && controller.providerName(address) === "" ? "custom" : "cn")
    }
    function openFor(address) {
        endpoint = address
        category = categoryOf(address)
        adding = false
        error = ""
        open()
    }
    function pick(address) {
        controller.useProvider(address)
        close()
    }
    function startAdding() {
        category = "custom"
        nameInput.text = ""
        // The address being typed, when it is not a known service yet.
        urlInput.text = controller.providerName(endpoint) === "" ? endpoint : ""
        error = ""
        adding = true
        nameInput.forceActiveFocus()
    }
    function save() {
        error = controller.addCustomProvider(nameInput.text, urlInput.text)
        if (error === "") { adding = false; close() }
    }

    contentItem: RowLayout {
        spacing: 16

        // ----- 一级：分类
        ColumnLayout {
            Layout.preferredWidth: 188
            Layout.maximumWidth: 188
            Layout.fillWidth: false
            Layout.fillHeight: true
            spacing: 4
            Repeater {
                model: dlg.categories
                Rectangle {
                    id: cat
                    required property var modelData
                    readonly property bool on: dlg.category === modelData.id
                    Layout.fillWidth: true
                    implicitHeight: catText.implicitHeight + 18
                    radius: Theme.radius
                    color: on ? Theme.accentSoft : (catHover.hovered ? Theme.surfaceAlt : "transparent")
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                    HoverHandler { id: catHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: { dlg.category = cat.modelData.id; dlg.adding = false } }
                    Rectangle {
                        visible: cat.on
                        width: 3; height: 16; radius: 2
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.accent
                    }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 10
                        spacing: 6
                        Text {
                            id: catText
                            Layout.fillWidth: true
                            text: cat.modelData.label.replace("（在国内通常需要代理）", "")
                            color: cat.on ? Theme.accent : Theme.text
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                            font.weight: cat.on ? Font.DemiBold : Font.Normal
                            elide: Text.ElideRight
                        }
                        Text {
                            text: dlg.countOf(cat.modelData.id)
                            color: Theme.faint
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                        }
                    }
                }
            }
            Item { Layout.fillHeight: true }
            Text {
                Layout.fillWidth: true
                text: "都需要兼容 OpenAI 接口。海外服务在国内通常要在“代理”里填写代理地址。"
                color: Theme.faint
                font.family: Theme.uiFont
                font.pixelSize: 11
                wrapMode: Text.Wrap
            }
        }

        Rectangle { Layout.fillHeight: true; implicitWidth: 1; color: Theme.border }

        // ----- 二级：服务
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            ListView {
                id: list
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 2
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                model: dlg.rows
                delegate: Rectangle {
                    id: row
                    required property var modelData
                    readonly property bool on: dlg.endpoint === modelData.endpoint
                    width: list.width
                    height: 52
                    radius: Theme.radius
                    color: on ? Theme.accentSoft : (rowHover.hovered ? Theme.surfaceAlt : "transparent")
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                    HoverHandler { id: rowHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: dlg.pick(row.modelData.endpoint) }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 8
                        spacing: 10
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                Layout.fillWidth: true
                                text: row.modelData.name
                                color: row.on ? Theme.accent : Theme.text
                                font.family: Theme.uiFont
                                font.pixelSize: 13
                                font.weight: row.on ? Font.DemiBold : Font.Normal
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                text: row.modelData.endpoint
                                color: Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 11
                                elide: Text.ElideMiddle
                            }
                        }
                        Text {
                            visible: row.modelData.console !== "" && (rowHover.hovered || row.on)
                            text: "获取 API Key ↗"
                            color: keyHover.hovered ? Theme.accentHover : Theme.accent
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                            font.underline: keyHover.hovered
                            HoverHandler { id: keyHover; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: controller.openUrl(row.modelData.console) }
                        }
                        IconButton {
                            visible: row.modelData.removable
                            glyph: ""
                            tip: "删除这个自定义服务"
                            onClicked: controller.removeCustomProvider(row.modelData.endpoint)
                        }
                        Text {
                            visible: row.on
                            text: ""
                            color: Theme.accent
                            font.family: Theme.iconFont
                            font.pixelSize: 14
                        }
                    }
                }

                Text {
                    anchors.centerIn: parent
                    width: parent.width - 40
                    visible: list.count === 0 && !dlg.adding
                    horizontalAlignment: Text.AlignHCenter
                    text: "还没有自定义服务。\n中转站、公司内部网关等兼容 OpenAI 接口的服务，可以在下面添加。"
                    color: Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                }
            }

            // 添加自定义服务
            Rectangle {
                visible: dlg.category === "custom" && dlg.adding
                Layout.fillWidth: true
                implicitHeight: addForm.implicitHeight + 24
                radius: Theme.radius
                color: Theme.sunken
                ColumnLayout {
                    id: addForm
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8
                    AppTextField {
                        id: nameInput
                        Layout.fillWidth: true
                        placeholderText: "名称，例如 我的中转站"
                        maximumLength: 24
                        onAccepted: urlInput.forceActiveFocus()
                    }
                    AppTextField {
                        id: urlInput
                        Layout.fillWidth: true
                        placeholderText: "接口地址，例如 https://api.example.com/v1"
                        onAccepted: dlg.save()
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            Layout.fillWidth: true
                            text: dlg.error !== "" ? dlg.error : "地址填到 /v1，不要带 /chat/completions"
                            color: dlg.error !== "" ? Theme.warning : Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                        }
                        AppButton { text: "取消"; kind: "ghost"; onClicked: dlg.adding = false }
                        AppButton { text: "保存并使用"; kind: "primary"; onClicked: dlg.save() }
                    }
                }
            }
            AppButton {
                visible: dlg.category === "custom" && !dlg.adding
                text: "添加自定义服务"
                glyph: ""
                onClicked: dlg.startAdding()
            }
        }
    }

    buttons: [
        AppButton { text: "关闭"; onClicked: dlg.close() }
    ]
}
