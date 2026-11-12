import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: pill
    property string text: ""
    property string kind: "idle"   // idle | running | done | error
    property string shownText: text
    onTextChanged: {
        if (!Theme.motion || shownText === "") { shownText = text; return }
        swap.restart()
    }
    SequentialAnimation {
        id: swap
        NumberAnimation { target: label; property: "opacity"; to: 0; duration: Theme.fast }
        ScriptAction { script: pill.shownText = pill.text }
        NumberAnimation { target: label; property: "opacity"; to: 1; duration: Theme.fast }
    }

    readonly property color fg: kind === "running" ? Theme.success
        : kind === "paused" ? Theme.accent
        : kind === "error" ? Theme.danger
        : kind === "done" ? Theme.success : Theme.muted
    readonly property color bgc: kind === "running" ? Theme.successSoft
        : kind === "paused" ? Theme.accentSoft
        : kind === "error" ? Theme.dangerSoft
        : kind === "done" ? Theme.successSoft : Theme.surfaceAlt

    color: bgc
    Behavior on color { ColorAnimation { duration: Theme.normal } }
    radius: height / 2
    implicitHeight: 28
    implicitWidth: row.implicitWidth + 24
    Behavior on implicitWidth { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 7
        Rectangle {
            width: 8; height: 8; radius: 4
            color: pill.fg
            Behavior on color { ColorAnimation { duration: Theme.normal } }
            id: dot
            Pulse {
                target: dot
                from: 1.0
                to: 0.25
                period: 1400
                active: pill.kind === "running" && Theme.loopMotion
            }
        }
        Text {
            id: label
            text: pill.shownText
            color: pill.fg
            Behavior on color { ColorAnimation { duration: Theme.normal } }
            font.family: Theme.uiFont
            font.pixelSize: 12
            font.weight: Font.DemiBold
        }
    }
}
