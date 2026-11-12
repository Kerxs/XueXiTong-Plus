import QtQuick
import "."

BaseDialog {
    id: dialog
    property string message: ""
    property string acceptText: "确定"
    property string rejectText: "取消"
    property bool destructive: false
    // Seconds until the dialog answers itself (0: it waits for the user). The run goes on meanwhile,
    // so a dialog nobody is looking at must not stay open for ever.
    property int countdown: 0
    property bool timeoutAccepts: false     // what the timeout does: accept() or reject()
    property int remaining: 0
    readonly property string tick: countdown > 0 && remaining > 0 ? "（" + remaining + "）" : ""
    width: 440

    onOpened: remaining = countdown
    onClosed: remaining = 0
    Timer {
        interval: 1000
        repeat: true
        running: dialog.visible && dialog.countdown > 0
        onTriggered: {
            dialog.remaining -= 1
            if (dialog.remaining <= 0) {
                if (dialog.timeoutAccepts) dialog.accept()
                else dialog.reject()
            }
        }
    }

    contentItem: Text {
        text: dialog.message
        color: Theme.text
        font.family: Theme.uiFont
        font.pixelSize: 13
        lineHeight: 1.3
        wrapMode: Text.Wrap
    }

    buttons: [
        AppButton { text: dialog.rejectText + (dialog.timeoutAccepts ? "" : dialog.tick); onClicked: dialog.reject() },
        AppButton {
            text: dialog.acceptText + (dialog.timeoutAccepts ? dialog.tick : "")
            kind: dialog.destructive ? "danger" : "primary"
            onClicked: dialog.accept()
        }
    ]
}
