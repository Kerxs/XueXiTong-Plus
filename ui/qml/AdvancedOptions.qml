import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// 高级选项: the rest of config.ini (题库 / 答题 / 通知推送) as real controls instead of a
// text file. Fields come from controller.advancedGroups (ui/advanced.py); values are the
// strings config.ini stores and are written back on 保存 like every other setting.
Card {
    id: adv
    title: "高级选项"
    subtitle: "答题来源（题库 / AI）、答题和通知推送，对应配置文件 config.ini"
    icon: ""

    property int tab: 0
    // Group ids to show ([] = all) and to leave out: the 开始引导 shows 自动完成 on its own step.
    property var only: []
    property var except: []
    readonly property var groups: controller.advancedGroups.filter(g =>
        (only.length === 0 || only.indexOf(g.id) >= 0) && except.indexOf(g.id) < 0)
    readonly property var values: controller.advancedValues

    function value(id) { return values[id] !== undefined ? values[id] : "" }
    function isOn(id) { return ["true", "1", "yes", "on"].indexOf(String(value(id)).toLowerCase()) >= 0 }
    function listOf(id) { return String(value(id)).split(",").map(s => s.trim()).filter(s => s !== "") }
    // show: one condition or a list that must all hold (see ui/advanced.py).
    function shown(f) {
        const c = f.show
        if (!c) return true
        if (c.key === undefined && c.length !== undefined)       // a list from Python is not a JS Array
            return Array.prototype.every.call(c, one => shown({ show: one }))
        if (c.has !== undefined) { const l = listOf(c.key); return c.has.some(v => l.indexOf(v) >= 0) }
        if (c.eq !== undefined) return value(c.key) === c.eq
        if (c.ne !== undefined) return value(c.key) !== c.ne
        if (c.on !== undefined) return isOn(c.key) === c.on
        return true
    }

    // Embedded in the 开始引导: no header row (title, icon, edit button).
    property bool embedded: false
    // All groups one after another (with their own headings) instead of tabs: the 开始引导 uses this.
    property bool stacked: false

    actions: [
        IconButton {
            visible: !adv.embedded
            glyph: ""
            tip: "用编辑器打开 config.ini"
            onClicked: controller.openConfigFile()
        }
    ]

    Segmented {
        visible: !adv.stacked
        Layout.fillWidth: false
        model: adv.groups.map((g, i) => ({ value: String(i), label: g.title }))
        current: String(adv.tab)
        onPicked: value => adv.tab = parseInt(value)
    }
    Text {
        visible: !adv.stacked
        Layout.fillWidth: true
        text: adv.groups.length ? adv.groups[adv.tab].subtitle : ""
        color: Theme.muted
        font.family: Theme.uiFont
        font.pixelSize: 12
        wrapMode: Text.Wrap
    }

    // One page per group; the active one slides in like the app's pages.
    Item {
        id: pages
        visible: !adv.stacked
        Layout.fillWidth: true
        implicitHeight: !adv.stacked && adv.groups.length ? stack.children[adv.tab].implicitHeight : 0
        Behavior on implicitHeight { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        clip: true
        enabled: !controller.running

        Item {
            id: stack
            anchors.fill: parent
            Repeater {
                model: adv.stacked ? [] : adv.groups
                ColumnLayout {
                    id: groupPage
                    required property var modelData
                    required property int index
                    readonly property bool current: adv.tab === index
                    width: pages.width
                    spacing: 10
                    opacity: current ? 1 : 0
                    visible: opacity > 0.01
                    x: current ? 0 : (index < adv.tab ? -30 : 30)
                    Behavior on opacity { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                    Behavior on x { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }

                    GroupFields { Layout.fillWidth: true; group: groupPage.modelData }
                }
            }
        }
    }

    // Stacked: every group with its heading.
    ColumnLayout {
        visible: adv.stacked
        Layout.fillWidth: true
        spacing: 18
        enabled: !controller.running
        Repeater {
            model: adv.stacked ? adv.groups : []
            ColumnLayout {
                id: section
                required property var modelData
                required property int index
                Layout.fillWidth: true
                spacing: 10
                Rectangle { visible: section.index > 0; Layout.fillWidth: true; height: 1; color: Theme.border }
                RowLayout {
                    spacing: 10
                    Text { text: section.modelData.icon; font.family: Theme.iconFont; font.pixelSize: 16; color: Theme.accent }
                    ColumnLayout {
                        spacing: 1
                        Text { text: section.modelData.title; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 15; font.weight: Font.DemiBold }
                        Text { text: section.modelData.subtitle; color: Theme.muted; font.family: Theme.uiFont; font.pixelSize: 12 }
                    }
                }
                GroupFields { Layout.fillWidth: true; group: section.modelData }
            }
        }
    }

    // The fields of one group, each through a Loader that picks the control by type.
    component GroupFields: ColumnLayout {
        id: gf
        property var group: ({ fields: [] })
        spacing: 10
        Repeater {
            model: gf.group.fields
            Loader {
                required property var modelData
                Layout.fillWidth: true
                active: modelData.type !== "hidden" && adv.shown(modelData)
                visible: active
                property var field: modelData
                sourceComponent: ({
                    heading: headingField, switch: switchField, number: numberField,
                    percent: percentField, choice: choiceField, providers: providersField,
                    text: textField, secret: textField, localmodels: localModelsField,
                    aiprovider: aiProviderField, modelpicker: modelPickerField
                })[modelData.type]
            }
        }
    }

    // ---------- field components (each reads `field` from its Loader) ----------

    // Label + hint on the left, control on the right.
    component FieldRow: RowLayout {
        id: row
        property var f
        default property alias control: holder.data
        spacing: 16
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text { Layout.fillWidth: true; text: row.f.label; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 13 }
            Text {
                visible: row.f.hint !== ""
                Layout.fillWidth: true
                text: row.f.hint
                color: Theme.muted
                font.family: Theme.uiFont
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }
        }
        Item {
            id: holder
            implicitWidth: childrenRect.width
            implicitHeight: childrenRect.height
        }
    }

    Component {
        id: headingField
        ColumnLayout {
            readonly property var field: parent ? parent.field : ({})
            spacing: 8
            Rectangle { Layout.fillWidth: true; Layout.topMargin: 4; height: 1; color: Theme.border }
            Text {
                text: field.label
                color: Theme.accent
                font.family: Theme.uiFont
                font.pixelSize: 12
                font.weight: Font.DemiBold
            }
        }
    }

    // 自动检测本机模型: finds llama.cpp / Ollama / LM Studio ... on this computer and fills
    // 接口地址 and 模型名称 with one click (ui/localmodels.py).
    Component {
        id: localModelsField
        ColumnLayout {
            id: lm
            readonly property var field: parent ? parent.field : ({})
            readonly property string state: controller.localModelState
            readonly property var found: controller.localModels
            spacing: 8
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                AppButton {
                    text: lm.state === "running" ? "正在检测…" : "自动检测本机模型"
                    glyph: ""
                    enabled: lm.state !== "running"
                    onClicked: controller.detectLocalModels()
                }
                Text {
                    Layout.fillWidth: true
                    text: lm.state === "running" ? "正在查找本机运行的模型服务"
                        : lm.state !== "done" ? "在本机运行 llama.cpp、Ollama、LM Studio 等时，可自动填写接口地址和模型名称"
                        : lm.found.length === 0 ? "没有找到本机模型服务，请先启动模型服务再检测"
                        : "找到 " + lm.found.length + " 个模型，点“使用”自动填写"
                    color: lm.state === "done" && lm.found.length === 0 ? Theme.warning : Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                }
            }
            Repeater {
                model: lm.found
                Rectangle {
                    id: modelRow
                    required property var modelData
                    readonly property bool inUse: adv.value("tiku.endpoint") === modelData.endpoint
                                                 && adv.value("tiku.model") === modelData.model
                    Layout.fillWidth: true
                    implicitHeight: 46
                    radius: Theme.radius
                    color: inUse ? Theme.accentSoft : Theme.sunken
                    border.color: inUse ? Theme.accent : "transparent"
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 8
                        spacing: 10
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Text {
                                Layout.fillWidth: true
                                text: modelRow.modelData.model
                                color: Theme.text
                                font.family: Theme.uiFont
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                                elide: Text.ElideMiddle
                            }
                            Text {
                                text: modelRow.modelData.endpoint + (modelRow.modelData.server ? " · " + modelRow.modelData.server : "")
                                color: Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 11
                            }
                        }
                        AppButton {
                            text: modelRow.inUse ? "已使用" : "使用"
                            glyph: modelRow.inUse ? "" : ""
                            kind: modelRow.inUse ? "ghost" : "primary"
                            enabled: !modelRow.inUse
                            implicitHeight: 30
                            onClicked: controller.useLocalModel(modelRow.modelData.endpoint, modelRow.modelData.model)
                        }
                    }
                }
            }
        }
    }

    // 服务商: one row showing the service in use; clicking it opens 选择服务商 (二级菜单:
    // 国内 / 海外 / 自定义 → the services), ProviderPickerDialog.qml.
    Component {
        id: aiProviderField
        ColumnLayout {
            id: ap
            readonly property var field: parent ? parent.field : ({})
            readonly property string endpoint: adv.value("tiku.endpoint").trim().replace(/\/+$/, "")
            // customProviders is read so a newly saved / removed custom name is recognised at once.
            readonly property string company: { controller.customProviders; return controller.providerName(ap.endpoint) }
            readonly property string keyPage: controller.providerConsole(endpoint)
            spacing: 6

            Text { text: "服务商"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 13 }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 56
                radius: Theme.radius
                color: rowHover.hovered ? Theme.surfaceAlt : Theme.surface
                border.color: rowHover.hovered ? Theme.borderStrong : Theme.border
                Behavior on color { ColorAnimation { duration: Theme.fast } }
                HoverHandler { id: rowHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: picker.openFor(ap.endpoint) }
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 12
                    spacing: 12
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            Layout.fillWidth: true
                            text: ap.endpoint === "" ? "未选择" : (ap.company !== "" ? ap.company : "未识别的服务")
                            color: ap.company !== "" ? Theme.text : Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: ap.endpoint === "" ? "国内、海外常用服务，或你自己的服务" : ap.endpoint
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 11
                            elide: Text.ElideMiddle
                        }
                    }
                    Text {
                        visible: ap.keyPage !== ""
                        text: "获取 API Key ↗"
                        color: keyLinkHover.hovered ? Theme.accentHover : Theme.accent
                        font.family: Theme.uiFont
                        font.pixelSize: 12
                        font.underline: keyLinkHover.hovered
                        HoverHandler { id: keyLinkHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: controller.openUrl(ap.keyPage) }
                    }
                    Text {
                        text: "更换"
                        color: Theme.muted
                        font.family: Theme.uiFont
                        font.pixelSize: 12
                    }
                    Text {
                        text: ""
                        color: Theme.faint
                        font.family: Theme.iconFont
                        font.pixelSize: 12
                    }
                }
            }
            Text {
                visible: ap.endpoint !== "" && ap.company === ""
                Layout.fillWidth: true
                text: "只要兼容 OpenAI 接口即可使用；也可以在“自定义服务”里给它起个名字保存。"
                color: Theme.muted
                font.family: Theme.uiFont
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }
            ProviderPickerDialog { id: picker }
        }
    }

    // 选择模型: GET <接口地址>/models with the key, then pick from the list (searchable).
    Component {
        id: modelPickerField
        ColumnLayout {
            id: mp
            readonly property var field: parent ? parent.field : ({})
            readonly property string state: controller.cloudModelState
            readonly property var models: controller.cloudModels
            readonly property string current: adv.value("tiku.model")
            readonly property var shownModels: {
                const q = filter.text.trim().toLowerCase()
                return q === "" ? models : models.filter(m => m.toLowerCase().indexOf(q) >= 0)
            }
            spacing: 8
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                AppButton {
                    text: mp.state === "running" ? "正在获取…" : mp.state === "done" ? "重新获取" : "获取模型列表"
                    glyph: ""
                    enabled: mp.state !== "running" && adv.value("tiku.endpoint").trim() !== ""
                    onClicked: controller.fetchCloudModels()
                }
                Text {
                    Layout.fillWidth: true
                    text: mp.state === "running" ? "正在向服务查询可用的模型"
                        : mp.state === "error" ? controller.cloudModelError
                        : mp.state === "done" ? "共 " + mp.models.length + " 个模型，点一个即可使用"
                        : "填好接口地址和 API Key 后，可以获取这个服务的全部模型"
                    color: mp.state === "error" ? Theme.warning : Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                }
            }
            AppTextField {
                id: filter
                visible: mp.state === "done" && mp.models.length > 8
                Layout.fillWidth: true
                placeholderText: "搜索模型，例如 deepseek、qwen、glm"
            }
            Rectangle {
                visible: mp.state === "done" && mp.models.length > 0
                Layout.fillWidth: true
                implicitHeight: Math.min(modelColumn.implicitHeight + 8, 236)
                radius: Theme.radius
                color: Theme.sunken
                clip: true
                Flickable {
                    anchors.fill: parent
                    anchors.margins: 4
                    contentHeight: modelColumn.implicitHeight
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {}
                    Column {
                        id: modelColumn
                        width: parent.width
                        spacing: 2
                        Repeater {
                            model: mp.shownModels
                            Rectangle {
                                id: mrow
                                required property string modelData
                                readonly property bool on: modelData === mp.current
                                width: modelColumn.width
                                height: 32
                                radius: 6
                                color: on ? Theme.accentSoft : (mhover.hovered ? Theme.surface : "transparent")
                                HoverHandler { id: mhover; cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: controller.useCloudModel(mrow.modelData) }
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 10
                                    anchors.right: tick.left
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: mrow.modelData
                                    color: mrow.on ? Theme.accent : Theme.text
                                    font.family: Theme.uiFont
                                    font.pixelSize: 13
                                    font.weight: mrow.on ? Font.DemiBold : Font.Normal
                                    elide: Text.ElideMiddle
                                }
                                Text {
                                    id: tick
                                    anchors.right: parent.right
                                    anchors.rightMargin: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    visible: mrow.on
                                    text: ""
                                    font.family: Theme.iconFont
                                    font.pixelSize: 12
                                    color: Theme.accent
                                }
                            }
                        }
                    }
                }
            }
            Text {
                visible: mp.state === "done" && mp.models.length > 0 && mp.shownModels.length === 0
                text: "没有匹配的模型"
                color: Theme.faint
                font.family: Theme.uiFont
                font.pixelSize: 12
            }
        }
    }

    Component {
        id: switchField
        FieldRow {
            readonly property var field: parent ? parent.field : ({})
            f: field
            AppSwitch {
                checked: adv.isOn(field.id)
                onToggled: controller.setAdvanced(field.id, checked)
            }
        }
    }

    Component {
        id: numberField
        FieldRow {
            readonly property var field: parent ? parent.field : ({})
            f: field
            AppSpinBox {
                readonly property real scale: Math.pow(10, field.decimals || 0)
                from: Math.round(field.min * scale)
                to: Math.round(field.max * scale)
                stepSize: Math.max(1, Math.round(field.step * scale))
                value: Math.round((parseFloat(adv.value(field.id)) || 0) * scale)
                textFromValue: (v, locale) => (v / scale).toFixed(field.decimals || 0) + (field.suffix ? " " + field.suffix : "")
                valueFromText: (t, locale) => Math.round((parseFloat(t) || 0) * scale)
                onValueModified: controller.setAdvanced(field.id, String(value / scale))
            }
        }
    }

    Component {
        id: percentField
        FieldRow {
            readonly property var field: parent ? parent.field : ({})
            f: field
            AppSpinBox {
                from: 0
                to: 100
                stepSize: 5
                value: Math.round((parseFloat(adv.value(field.id)) || 0) * 100)
                textFromValue: (v, locale) => v + " %"
                valueFromText: (t, locale) => Math.round(parseFloat(t) || 0)
                onValueModified: controller.setAdvanced(field.id, String(value / 100))
            }
        }
    }

    Component {
        id: choiceField
        FieldRow {
            readonly property var field: parent ? parent.field : ({})
            f: field
            Segmented {
                model: field.options
                current: adv.value(field.id)
                onPicked: value => controller.setAdvanced(field.id, value)
            }
        }
    }

    Component {
        id: textField
        ColumnLayout {
            readonly property var field: parent ? parent.field : ({})
            spacing: 6
            Text { text: field.label; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 13 }
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                AppTextField {
                    Layout.fillWidth: true
                    placeholderText: field.default !== "" ? field.default : (field.type === "secret" ? "未填写" : "")
                    echoMode: field.type === "secret" && !reveal.checked ? TextInput.Password : TextInput.Normal
                    text: adv.value(field.id)
                    onTextEdited: controller.setAdvanced(field.id, text)
                }
                IconButton {
                    id: reveal
                    visible: field.type === "secret"
                    checkable: true
                    glyph: checked ? "" : ""
                    tip: checked ? "隐藏" : "显示"
                }
            }
            Text {
                visible: field.hint !== ""
                Layout.fillWidth: true
                text: field.hint
                color: Theme.muted
                font.family: Theme.uiFont
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }
        }
    }

    // 答题方式: 不查找 / 题库 / AI 大模型 / 题库 + AI, then the matching sources as chips.
    // Everything is stored in tiku.provider; the mode is derived from it (ui/advanced.py).
    component ProviderChip: Rectangle {
        id: chip
        property var field
        property var option
        readonly property var picked: adv.listOf(field.id)
        readonly property int order: picked.indexOf(option.value)
        readonly property bool on: order >= 0
        // Same-kind picks; the last one of a kind the mode needs cannot be removed.
        readonly property int sameKind: field.options.filter(o => o.kind === option.kind && picked.indexOf(o.value) >= 0).length
        width: chipRow.implicitWidth + 24
        height: 34
        radius: 17
        color: on ? Theme.accentSoft : (chipHover.hovered ? Theme.surfaceAlt : Theme.surface)
        border.color: on ? Theme.accent : (chipHover.hovered ? Theme.borderStrong : Theme.border)
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Behavior on border.color { ColorAnimation { duration: Theme.fast } }
        HoverHandler { id: chipHover; cursorShape: Qt.PointingHandCursor }
        ToolTip.visible: chipHover.hovered
        ToolTip.delay: 500
        ToolTip.text: chip.on && chip.sameKind === 1 ? option.hint + "（至少保留一个；不需要可切换答题方式）" : option.hint
        TapHandler {
            onTapped: {
                const l = chip.picked.slice()
                if (chip.on) {
                    if (chip.sameKind === 1)
                        return
                    l.splice(chip.order, 1)
                } else {
                    l.push(chip.option.value)
                }
                controller.setProviders(chip.field.id, l)
            }
        }
        Row {
            id: chipRow
            anchors.centerIn: parent
            spacing: 6
            Rectangle {
                width: 18; height: 18; radius: 9
                anchors.verticalCenter: parent.verticalCenter
                color: chip.on ? Theme.accent : "transparent"
                border.color: chip.on ? Theme.accent : Theme.borderStrong
                scale: chip.on ? 1 : 0.85
                Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutBack } }
                Text {
                    anchors.centerIn: parent
                    text: chip.on ? String(chip.order + 1) : ""
                    color: Theme.accentText
                    font.family: Theme.uiFont
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: chip.option.label
                color: chip.on ? Theme.accent : Theme.text
                font.family: Theme.uiFont
                font.pixelSize: 13
                font.weight: chip.on ? Font.DemiBold : Font.Normal
            }
        }
    }

    Component {
        id: providersField
        ColumnLayout {
            id: pf
            readonly property var field: parent ? parent.field : ({})
            readonly property string mode: controller.answerMode(adv.value(field.id))
            readonly property var modeInfo: field.modes.find(m => m.value === mode) || field.modes[0]
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                spacing: 16
                Text { Layout.fillWidth: true; text: pf.field.label; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 13 }
                Segmented {
                    model: pf.field.modes
                    current: pf.mode
                    onPicked: value => controller.setAnswerMode(pf.field.id, value)
                }
            }
            // What the chosen mode does.
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: modeText.implicitHeight + 18
                radius: Theme.radius
                color: pf.mode === "none" ? Theme.warningSoft : Theme.accentSoft
                Behavior on color { ColorAnimation { duration: Theme.normal } }
                Row {
                    anchors.fill: parent
                    anchors.margins: 9
                    anchors.leftMargin: 12
                    spacing: 8
                    Text {
                        text: pf.mode === "none" ? "" : pf.mode === "tiku" ? "" : pf.mode === "ai" ? "" : ""
                        font.family: Theme.iconFont
                        font.pixelSize: 14
                        color: pf.mode === "none" ? Theme.warning : Theme.accent
                    }
                    Text {
                        id: modeText
                        width: parent.width - 30
                        text: pf.modeInfo.hint
                        color: pf.mode === "none" ? Theme.warning : Theme.text
                        font.family: Theme.uiFont
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                    }
                }
            }

            Repeater {
                model: [
                    { kind: "tiku", title: "题库", shown: pf.mode === "tiku" || pf.mode === "both" },
                    { kind: "ai", title: "AI 服务", shown: pf.mode === "ai" || pf.mode === "both" }
                ]
                ColumnLayout {
                    required property var modelData
                    visible: modelData.shown
                    Layout.fillWidth: true
                    spacing: 6
                    Text { text: modelData.title; color: Theme.muted; font.family: Theme.uiFont; font.pixelSize: 12 }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: pf.field.options.filter(o => o.kind === modelData.kind)
                            ProviderChip {
                                required property var modelData
                                field: pf.field
                                option: modelData
                            }
                        }
                    }
                }
            }
            Text {
                visible: pf.mode !== "none"
                Layout.fillWidth: true
                text: pf.mode === "both" ? "数字是查询顺序：先按顺序查题库，都找不到再交给 AI" : pf.field.hint
                color: Theme.muted
                font.family: Theme.uiFont
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }
        }
    }
}
