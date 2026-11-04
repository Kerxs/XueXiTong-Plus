import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// "发现新版本" dialog: release notes, download progress, install.
BaseDialog {
    id: dialog
    readonly property var updater: controller.updater
    readonly property string st: updater.state
    signal installRequested()

    title: st === "ready" ? "更新已下载" : "发现新版本 " + updater.latestVersion
    width: 520
    closePolicy: st === "downloading" ? Popup.NoAutoClose : Popup.CloseOnEscape

    contentItem: ColumnLayout {
        spacing: 12
        Text {
            Layout.fillWidth: true
            text: dialog.st === "ready"
                ? "安装程序会关闭学习通 PLUS 并升级到 " + dialog.updater.latestVersion + "，你的配置和账号不受影响。"
                : "当前版本 " + controller.version + "，新版本 " + dialog.updater.latestVersion
                  + (dialog.updater.downloadMb > 0 ? "（约 " + dialog.updater.downloadMb + " MB）" : "") + "。"
            color: Theme.muted
            font.family: Theme.uiFont
            font.pixelSize: 13
            wrapMode: Text.Wrap
        }
        Rectangle {
            visible: dialog.updater.releaseNotes !== "" && dialog.st !== "ready"
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(220, notes.implicitHeight + 24)
            radius: Theme.radius
            color: Theme.sunken
            ScrollView {
                id: notesScroll
                anchors.fill: parent
                anchors.margins: 12
                clip: true
                contentWidth: availableWidth
                Text {
                    id: notes
                    width: notesScroll.availableWidth
                    text: dialog.updater.releaseNotes
                    textFormat: Text.MarkdownText
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                    onLinkActivated: link => controller.openUrl(link)
                }
            }
        }
        ColumnLayout {
            visible: dialog.st === "downloading"
            Layout.fillWidth: true
            spacing: 6
            Rectangle {
                Layout.fillWidth: true
                height: 6
                radius: 3
                color: Theme.sunken
                Rectangle {
                    width: parent.width * dialog.updater.progress
                    height: parent.height
                    radius: 3
                    color: Theme.accent
                    Behavior on width { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
                }
            }
            Text {
                text: "正在下载 " + Math.round(dialog.updater.progress * 100) + "%"
                color: Theme.faint
                font.family: Theme.uiFont
                font.pixelSize: 12
            }
        }
        Text {
            visible: dialog.st === "error"
            Layout.fillWidth: true
            text: dialog.updater.errorText
            color: Theme.danger
            font.family: Theme.uiFont
            font.pixelSize: 12
            wrapMode: Text.Wrap
        }
        Text {
            visible: controller.running && (dialog.st === "available" || dialog.st === "ready")
            Layout.fillWidth: true
            text: "任务正在运行，安装更新会结束当前任务。"
            color: Theme.warning
            font.family: Theme.uiFont
            font.pixelSize: 12
            wrapMode: Text.Wrap
        }
    }

    buttons: [
        AppButton {
            text: dialog.st === "downloading" ? "取消下载" : "稍后"
            onClicked: {
                if (dialog.st === "downloading") dialog.updater.cancel()
                else dialog.close()
            }
        },
        AppButton {
            visible: dialog.st === "available" || dialog.st === "error"
            text: dialog.st === "error" ? "重试" : "下载并安装"
            glyph: ""
            kind: "primary"
            onClicked: dialog.st === "error" ? dialog.updater.check(false) : dialog.updater.download()
        },
        AppButton {
            visible: dialog.st === "ready"
            text: "立即安装"
            kind: "primary"
            onClicked: dialog.installRequested()
        }
    ]
}
