import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// First-run guide: 欢迎 > 免责声明 > 账号/密码 > 开始使用
Rectangle {
    id: guide
    signal completed()

    property int step: 0
    property int direction: 1          // +1 forward, -1 back (drives the slide direction)
    property bool accountSkipped: false
    property bool answerSkipped: false
    readonly property string disclaimer: "1. 本软件基于开源项目 Samueli924/chaoxing，遵循 GPL-3.0 协议，仅供学习交流使用，禁止用于任何盈利用途，修改或衍生版本必须同样开源。\n"
        + "2. 本软件与超星、学习通官方无任何关联，不代表其立场。\n"
        + "3. 使用自动化工具可能违反学习通的用户协议及所在学校的课程或学术诚信规定，可能导致账号受限、封禁或成绩作废。是否使用、如何使用由你自行判断，相关后果由你自行承担。\n"
        + "4. 账号、密码、TOKEN、API Key 和 cookies 加密保存在本机 %APPDATA%\\ChaoxingDesktop 目录（只有当前 Windows 用户能解密），请保管好电脑，不要在公共电脑上使用。\n"
        + "5. 本软件按“现状”提供，不对运行结果、答题正确率或任何直接、间接损失作任何保证或承担责任。\n"
        + "6. 他人或组织使用本软件进行的任何违法违规行为，与作者无关。"
    // Whitespace is ignored when comparing what the user wrote with the statement.
    function normalize(text) { return text.replace(/\s+/g, "") }
    readonly property string target: normalize(disclaimer)
    readonly property string typed: normalize(agreeInput.text)
    readonly property int targetCount: target.length
    readonly property int typedCount: typed.length
    readonly property bool onTrack: target.startsWith(typed)
    readonly property int matchedCount: {
        let i = 0
        while (i < typed.length && i < target.length && typed[i] === target[i]) ++i
        return i
    }
    readonly property bool agreed: typed === target
    readonly property var steps: ["欢迎", "免责声明", "账号", "自动完成", "高级设置", "开始使用"]
    readonly property int lastStep: steps.length - 1
    readonly property bool accountReady: controller.useCookies
        || (controller.username.trim() !== "" && controller.password !== "")

    color: Theme.bg

    // Swallow input so nothing behind the guide reacts.
    MouseArea { anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.AllButtons }

    function reset() {
        step = 0
        direction = 1
        accountSkipped = false
        answerSkipped = false
        agreeInput.text = ""
        entrance.restart()
    }

    function go(target) {
        direction = target > step ? 1 : -1
        step = target
    }

    function next() {
        if (step >= 2 && step <= 4) {
            if (step === 2) accountSkipped = false
            else if (step === 4) answerSkipped = false
            if (!controller.saveConfig())
                return
        }
        if (step < steps.length - 1)
            go(step + 1)
    }

    // "自动完成：视频、章节检测、课件、作业（自动提交）" from the 自动完成 switches.
    function autoSummary() {
        const v = controller.advancedValues
        const on = id => ["true", "1", "yes", "on"].indexOf(String(v[id] !== undefined ? v[id] : "true").toLowerCase()) >= 0
        const parts = ["视频", "章节检测"]
        if (on("common.auto_documents")) parts.push("课件")
        if (on("common.auto_homework")) parts.push(on("common.homework_submit") ? "作业（自动提交）" : "作业（只保存）")
        return "自动完成：" + parts.join("、") + (on("common.watch_activities") ? "；随堂练习会提醒你。" : "。")
    }

    function skipAccount() {
        accountSkipped = true
        go(3)        // 自动完成 has defaults: nothing to fill in, so it is not skipped
    }

    function skipAnswer() {
        answerSkipped = true
        go(lastStep)
    }

    onVisibleChanged: if (visible) entrance.restart()

    // On a first start the splash logo lands on the welcome page's icon and title
    // (Main.qml introLogo). They are hidden while it is in flight and shown in the frame it lands.
    property bool brandHidden: false
    readonly property alias welcomeIconItem: welcomeIcon
    readonly property alias welcomeTitleItem: welcomeTitle
    readonly property real enterOffset: panelShift.y   // the card slides in by this much

    Rectangle {
        id: panel
        anchors.centerIn: parent
        width: Math.min(720, parent.width - 80)
        height: Math.min(600, parent.height - 80)
        radius: 16
        color: Theme.surface
        border.color: Theme.border
        opacity: 0
        transform: Translate { id: panelShift; y: 16 }

        ParallelAnimation {
            id: entrance
            NumberAnimation { target: panel; property: "opacity"; from: 0; to: 1; duration: Theme.slow; easing.type: Easing.OutCubic }
            NumberAnimation { target: panelShift; property: "y"; from: 16; to: 0; duration: Theme.slow; easing.type: Easing.OutCubic }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.leftMargin: 32
            anchors.rightMargin: 32
            anchors.topMargin: 30
            anchors.bottomMargin: 28
            spacing: 0

            // ---- step indicator ----
            RowLayout {
                Layout.fillWidth: true
                Layout.bottomMargin: 24
                spacing: 8
                Repeater {
                    model: guide.steps
                    RowLayout {
                        required property string modelData
                        required property int index
                        readonly property bool reached: index <= guide.step
                        spacing: 8
                        Rectangle {
                            width: 24; height: 24; radius: 12
                            color: parent.reached ? Theme.accent : Theme.surfaceAlt
                            border.color: parent.reached ? Theme.accent : Theme.border
                            scale: index === guide.step ? 1.08 : 1
                            Behavior on color { ColorAnimation { duration: Theme.normal } }
                            Behavior on scale { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutBack } }
                            Text {
                                anchors.centerIn: parent
                                text: index < guide.step ? "" : String(index + 1)
                                font.family: index < guide.step ? Theme.iconFont : Theme.uiFont
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                                color: parent.parent.reached ? Theme.accentText : Theme.muted
                            }
                        }
                        Text {
                            text: modelData
                            color: index === guide.step ? Theme.text : Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                            font.weight: index === guide.step ? Font.DemiBold : Font.Normal
                            Behavior on color { ColorAnimation { duration: Theme.normal } }
                        }
                        // Connector line that fills as the guide advances.
                        Rectangle {
                            visible: index < guide.steps.length - 1
                            Layout.preferredWidth: 28
                            height: 2
                            radius: 1
                            color: Theme.border
                            Rectangle {
                                height: parent.height
                                radius: 1
                                color: Theme.accent
                                width: index < guide.step ? parent.width : 0
                                Behavior on width { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
                            }
                        }
                    }
                }
                Item { Layout.fillWidth: true }
            }

            // ---- pages (slide + fade between steps) ----
            Item {
                id: pages
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.bottomMargin: 20
                clip: true

                component Page: Item {
                    property int pageIndex: 0
                    width: pages.width
                    height: pages.height
                    readonly property bool current: guide.step === pageIndex
                    opacity: current ? 1 : 0
                    visible: opacity > 0.01
                    x: current ? 0 : (pageIndex < guide.step ? -48 : 48)
                    Behavior on opacity { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                    Behavior on x { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
                }

                // 0 欢迎
                Page {
                    pageIndex: 0
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 16
                        Item { Layout.preferredHeight: 6 }
                        Image {
                            id: welcomeIcon
                            source: controller.iconUrl
                            // 256 px texture + mipmaps: sharp on 150 % / 200 % displays and sampled
                            // exactly like the flying splash logo that lands here.
                            sourceSize: Qt.size(256, 256)
                            Layout.preferredWidth: 84
                            Layout.preferredHeight: 84
                            smooth: true
                            mipmap: true
                            opacity: guide.brandHidden ? 0 : 1
                            // Breathing starts after the splash logo has landed here (exact landing).
                            SequentialAnimation on scale {
                                running: guide.visible && guide.step === 0 && Theme.motion && !guide.brandHidden
                                loops: Animation.Infinite
                                NumberAnimation { to: 1.04; duration: 1400; easing.type: Easing.InOutSine }
                                NumberAnimation { to: 1.0; duration: 1400; easing.type: Easing.InOutSine }
                            }
                        }
                        Text { id: welcomeTitle; opacity: guide.brandHidden ? 0 : 1; text: controller.appName; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 26; font.weight: Font.Bold }
                        Text {
                            Layout.fillWidth: true
                            text: "用几步完成初始设置。之后可以随时在“设置”页修改。"
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 14
                            wrapMode: Text.Wrap
                        }
                        Repeater {
                            model: [
                                { glyph: "", text: "运行面板：课程、章节、任务进度和日志一目了然" },
                                { glyph: "", text: "可视化面板：只读查看当前视频和章节检测内容" },
                                { glyph: "", text: "配置、cookies 和日志只保存在本机" }
                            ]
                            RowLayout {
                                id: feature
                                required property var modelData
                                required property int index
                                spacing: 12
                                opacity: 0
                                transform: Translate { id: featureShift; x: -12 }
                                SequentialAnimation {
                                    running: guide.visible && guide.step === 0
                                    PauseAnimation { duration: 220 + feature.index * 110 }
                                    ParallelAnimation {
                                        NumberAnimation { target: feature; property: "opacity"; to: 1; duration: Theme.normal }
                                        NumberAnimation { target: featureShift; property: "x"; to: 0; duration: Theme.normal; easing.type: Easing.OutCubic }
                                    }
                                }
                                Rectangle {
                                    width: 32; height: 32; radius: 8
                                    color: Theme.accentSoft
                                    Text { anchors.centerIn: parent; text: modelData.glyph; font.family: Theme.iconFont; font.pixelSize: 15; color: Theme.accent }
                                }
                                Text { text: modelData.text; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 13 }
                            }
                        }
                        Item { Layout.fillHeight: true }
                    }
                }

                // 1 免责声明 — the user writes the statement out (the text stays selectable).
                Page {
                    pageIndex: 1
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 10
                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: "免责声明"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 22; font.weight: Font.Bold }
                            Item { Layout.fillWidth: true }
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 120
                            radius: Theme.radius
                            color: Theme.sunken
                            ScrollView {
                                id: disclaimerScroll
                                anchors.fill: parent
                                anchors.margins: 12
                                clip: true
                                contentWidth: availableWidth
                                TextEdit {
                                    id: disclaimerText
                                    width: disclaimerScroll.availableWidth
                                    readOnly: true
                                    selectByMouse: true
                                    color: Theme.text
                                    selectionColor: Theme.accent
                                    selectedTextColor: Theme.accentText
                                    font.family: Theme.uiFont
                                    font.pixelSize: 12
                                    wrapMode: TextEdit.Wrap
                                    text: guide.disclaimer
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "请在下方完整写一遍上面的声明"
                                color: Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 12
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: guide.agreed ? "✓ 声明一致" : guide.typedCount + " / " + guide.targetCount + " 字"
                                font.family: Theme.uiFont
                                color: guide.agreed ? Theme.success : (guide.typedCount > 0 && !guide.onTrack ? Theme.danger : Theme.faint)
                                font.pixelSize: 12
                                font.weight: guide.agreed ? Font.DemiBold : Font.Normal
                                Behavior on color { ColorAnimation { duration: Theme.normal } }
                            }
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 116
                            radius: Theme.radius
                            color: Theme.surface
                            border.width: 1
                            border.color: guide.agreed ? Theme.success
                                : (guide.typedCount > 0 && !guide.onTrack ? Theme.danger : (agreeInput.activeFocus ? Theme.accent : Theme.border))
                            Behavior on border.color { ColorAnimation { duration: Theme.normal } }
                            ScrollView {
                                id: inputScroll
                                anchors.fill: parent
                                anchors.margins: 2
                                clip: true
                                TextArea {
                                    id: agreeInput
                                    objectName: "agreeInput"
                                    width: inputScroll.availableWidth
                                    wrapMode: TextEdit.Wrap
                                    selectByMouse: true
                                    color: Theme.text
                                    placeholderText: "在这里输入免责声明全文"
                                    placeholderTextColor: Theme.faint
                                    selectionColor: Theme.accent
                                    selectedTextColor: Theme.accentText
                                    font.family: Theme.uiFont
                                    font.pixelSize: 12
                                    background: null
                                }
                            }
                            // How much of the statement matches so far.
                            Rectangle {
                                anchors.left: parent.left
                                anchors.bottom: parent.bottom
                                anchors.leftMargin: 1
                                anchors.bottomMargin: 1
                                height: 2
                                radius: 1
                                width: (parent.width - 2) * Math.min(1, guide.matchedCount / Math.max(1, guide.targetCount))
                                color: guide.agreed ? Theme.success : Theme.accent
                                Behavior on width { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                            }
                        }
                    }
                }

                // 2 账号
                Page {
                    pageIndex: 2
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 14
                        Text { text: "登录信息"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 22; font.weight: Font.Bold }
                        Text {
                            Layout.fillWidth: true
                            text: "填写学习通账号和密码，或使用本地 cookies 登录。信息加密保存在本机配置目录。\n现在不方便的话，可以点“稍后配置”，之后在“设置 → 账号”里填写。"
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                            lineHeight: 1.3
                            wrapMode: Text.Wrap
                        }
                        AppSwitch {
                            text: "使用本地 cookies 登录"
                            checked: controller.useCookies
                            onToggled: controller.useCookies = checked
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: controller.useCookies
                            text: "请把 cookies.txt 放入配置目录：" + controller.dataDir
                            color: Theme.muted
                            font.pixelSize: 12
                            wrapMode: Text.WrapAnywhere
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: 14
                            rowSpacing: 10
                            enabled: !controller.useCookies
                            opacity: enabled ? 1 : 0.5
                            Behavior on opacity { NumberAnimation { duration: Theme.normal } }
                            Label { text: "账号"; color: Theme.muted }
                            TextField {
                                Layout.fillWidth: true
                                placeholderText: "手机号或学习通账号"
                                text: controller.username
                                onTextEdited: controller.username = text
                                selectByMouse: true
                            }
                            Label { text: "密码"; color: Theme.muted }
                            TextField {
                                Layout.fillWidth: true
                                placeholderText: "密码"
                                echoMode: TextInput.Password
                                text: controller.password
                                onTextEdited: controller.password = text
                                onAccepted: if (guide.accountReady) guide.next()
                            }
                        }
                        IconButton {
                            visible: controller.useCookies
                            glyph: ""
                            text: "打开配置目录"
                            flat: false
                            onClicked: controller.openDataDir()
                        }
                        Item { Layout.fillHeight: true }
                    }
                }

                // 3 自动完成: what is always automatic, and the switches for 课件 / 作业 / 课堂活动
                Page {
                    pageIndex: 3
                    ScrollView {
                        id: autoScroll
                        anchors.fill: parent
                        contentWidth: availableWidth
                        clip: true
                    ColumnLayout {
                        width: autoScroll.availableWidth
                        spacing: 10
                        Text { text: "自动完成哪些内容"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 22; font.weight: Font.Bold }
                        Text {
                            Layout.fillWidth: true
                            text: "运行时会逐门课程、逐个章节处理。下面两项总是自动完成，其余的可以按需要打开或关闭，之后也能在“设置 → 高级选项 → 自动完成”里修改。"
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                            lineHeight: 1.3
                            wrapMode: Text.Wrap
                        }
                        Repeater {
                            model: [
                                { glyph: "\uE714", title: "视频（含音频）", text: "按 1 倍速完整观看，平台确认后完成" },
                                { glyph: "\uE9D5", title: "章节检测", text: "用下一步设置的题库或 AI 查答案，达到覆盖率时提交" }
                            ]
                            RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 12
                                Rectangle {
                                    width: 34; height: 34; radius: Theme.radius
                                    color: Theme.accentSoft
                                    Text { anchors.centerIn: parent; text: modelData.glyph; font.family: Theme.iconFont; font.pixelSize: 16; color: Theme.accent }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 1
                                    Text { text: modelData.title; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 14; font.weight: Font.DemiBold }
                                    Text { Layout.fillWidth: true; text: modelData.text; color: Theme.muted; font.family: Theme.uiFont; font.pixelSize: 12; wrapMode: Text.Wrap }
                                }
                                Text { text: "总是"; color: Theme.success; font.family: Theme.uiFont; font.pixelSize: 12 }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
                        AdvancedOptions {
                            Layout.fillWidth: true
                            embedded: true
                            stacked: true
                            only: ["auto"]
                            title: ""
                            subtitle: ""
                            icon: ""
                            padding: 2
                            color: "transparent"
                            border.width: 0
                        }
                        Text {
                            Layout.fillWidth: true
                            text: "作业会用答题来源自动作答，打开“作业自动提交”时直接提交；随堂练习只在上课时开放几分钟，需要你自己完成，程序发现后会提醒。"
                            color: Theme.faint
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                            lineHeight: 1.3
                            wrapMode: Text.Wrap
                        }
                    }
                    }
                }

                // 4 高级设置: the rest of the 高级选项 card stacked (答题来源 / 答题 / 通知推送)
                Page {
                    pageIndex: 4
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 10
                        Text { text: "高级设置"; color: Theme.text; font.family: Theme.uiFont; font.pixelSize: 22; font.weight: Font.Bold }
                        Text {
                            Layout.fillWidth: true
                            text: "依次设置答题来源（题库或 AI 的 TOKEN、接口地址、API Key）、答题和通知推送，往下滚动可以看到全部。之后都可以在“设置 → 高级选项”里修改。"
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                            lineHeight: 1.3
                            wrapMode: Text.Wrap
                        }
                        ScrollView {
                            id: answerScroll
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            contentWidth: availableWidth
                            clip: true
                            AdvancedOptions {
                                width: answerScroll.availableWidth
                                embedded: true
                                stacked: true
                                except: ["auto"]
                                title: ""
                                subtitle: ""
                                icon: ""
                                padding: 2
                                color: "transparent"
                                border.width: 0
                            }
                        }
                    }
                }

                // 5 开始使用
                Page {
                    pageIndex: 5
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 14
                        Item { Layout.preferredHeight: 6 }
                        Rectangle {
                            id: doneBadge
                            width: 64; height: 64; radius: 32
                            color: guide.accountSkipped ? Theme.warningSoft : Theme.successSoft
                            scale: guide.step === guide.lastStep ? 1 : 0.5
                            Behavior on scale { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutBack; easing.overshoot: 2 } }
                            Text {
                                anchors.centerIn: parent
                                text: guide.accountSkipped ? "" : ""
                                font.family: Theme.iconFont
                                font.pixelSize: 28
                                color: guide.accountSkipped ? Theme.warning : Theme.success
                            }
                        }
                        Text {
                            text: guide.accountSkipped ? "差一步就好" : "设置完成"
                            color: Theme.text
                            font.family: Theme.uiFont
                            font.pixelSize: 26
                            font.weight: Font.Bold
                        }
                        Text {
                            Layout.fillWidth: true
                            text: guide.accountSkipped
                                ? "你选择了稍后配置账号。\n开始运行前，请先到“设置 → 账号”填写账号密码，或开启 cookies 登录。运行面板顶部也会一直提醒你。"
                                : (controller.useCookies ? "将使用本地 cookies 登录。" : "已保存账号 " + controller.username + "。")
                                    + (guide.answerSkipped || controller.answerSetupProblem !== ""
                                        ? "\n高级设置还没完成，章节检测找不到答案的题目会随机作答；可以在“设置 → 高级选项”里补上。"
                                        : "\n高级设置已保存。")
                                    + "\n" + guide.autoSummary()
                                    + "\n进入运行面板后，在左侧“基本参数”里选择课程，再点击“开始运行”。"
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 14
                            lineHeight: 1.3
                            wrapMode: Text.Wrap
                        }
                        // Honest expectations before the first run (same notice on the phone).
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: noticeText.implicitHeight + 24
                            radius: Theme.radius
                            color: Theme.warningSoft
                            Text {
                                id: noticeText
                                anchors.fill: parent
                                anchors.margins: 12
                                text: "自动化不能保证 100% 成功：视频可能因验证码、网络或平台规则中断，章节检测和作业可能答错；随堂练习、阅读、问卷、讨论等内容需要你手动完成。"
                                    + (controller.pushConfigured ? ""
                                        : "\n还没有配置通知推送：建议在“设置 → 高级选项 → 通知推送”配置，任务出错或需要手动处理时能及时知道，以免浪费时间。")
                                color: Theme.warning
                                font.family: Theme.uiFont
                                font.pixelSize: 13
                                lineHeight: 1.3
                                wrapMode: Text.Wrap
                            }
                        }
                        Item { Layout.fillHeight: true }
                    }
                }
            }

            // ---- footer ----
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                AppButton {
                    visible: guide.step > 0
                    text: "上一步"
                    kind: "ghost"
                    glyph: ""
                    onClicked: guide.go(guide.step - 1)
                }
                Item { Layout.fillWidth: true }
                Text {
                    visible: guide.step === 4 && controller.answerSetupProblem !== ""
                    Layout.maximumWidth: 300
                    text: " " + controller.answerSetupProblem
                    color: Theme.warning
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                    elide: Text.ElideRight
                }
                Text {
                    visible: guide.step === 1 && !guide.agreed
                    text: guide.typedCount > 0 && !guide.onTrack ? "从第 " + (guide.matchedCount + 1) + " 个字开始不一致" : "写完声明后才能继续"
                    color: Theme.faint
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                }
                AppButton {
                    visible: guide.step === 2 || guide.step === 4
                    text: "稍后配置"
                    onClicked: guide.step === 2 ? guide.skipAccount() : guide.skipAnswer()
                }
                AppButton {
                    objectName: "nextButton"
                    visible: guide.step < guide.steps.length - 1
                    text: guide.step === 0 ? "开始设置" : "下一步"
                    kind: "primary"
                    enabled: (guide.step !== 1 || guide.agreed) && (guide.step !== 2 || guide.accountReady)
                             && (guide.step !== 4 || controller.answerSetupProblem === "")
                    onClicked: guide.next()
                }
                AppButton {
                    visible: guide.step === guide.steps.length - 1
                    text: guide.accountSkipped ? "先进去看看" : "开始使用"
                    kind: "primary"
                    onClicked: {
                        controller.finishOnboarding()
                        guide.completed()
                    }
                }
            }
        }
    }
}
