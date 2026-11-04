import QtQuick
import QtQuick.Controls
import "."

// Self-drawn button so it looks the same whatever Quick Controls style loads.
// kind: "primary" | "secondary" | "danger" | "warning" | "ghost"
AbstractButton {
    id: control
    property string kind: "secondary"
    property string glyph: ""
    property string tip: ""

    readonly property color baseColor: kind === "primary" ? Theme.accent
        : kind === "danger" ? Theme.dangerSoft
        : kind === "warning" ? Theme.warningSoft
        : kind === "ghost" ? "transparent" : Theme.surface
    readonly property color hoverColor: kind === "primary" ? Theme.accentHover
        : kind === "danger" ? Qt.darker(Theme.dangerSoft, Theme.dark ? 0.85 : 1.04)
        : kind === "warning" ? Qt.darker(Theme.warningSoft, Theme.dark ? 0.85 : 1.04)
        : Theme.surfaceAlt
    readonly property color pressColor: kind === "primary" ? Theme.accentPressed
        : kind === "danger" ? Qt.darker(Theme.dangerSoft, Theme.dark ? 0.75 : 1.08)
        : kind === "warning" ? Qt.darker(Theme.warningSoft, Theme.dark ? 0.75 : 1.08)
        : Theme.sunken
    readonly property color fg: !enabled ? Theme.faint
        : kind === "primary" ? Theme.accentText
        : kind === "danger" ? Theme.danger
        : kind === "warning" ? Theme.warning : Theme.text

    implicitHeight: 36
    implicitWidth: Math.max(kind === "ghost" ? 36 : 88, row.implicitWidth + (text !== "" ? 32 : 18))
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    font.pixelSize: 13
    opacity: enabled ? 1 : 0.55
    Behavior on opacity { NumberAnimation { duration: Theme.fast } }

    ToolTip.visible: tip !== "" && hovered
    ToolTip.text: tip
    ToolTip.delay: 400

    scale: pressed ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }

    background: Rectangle {
        radius: Theme.radius
        color: control.pressed ? control.pressColor : (control.hovered ? control.hoverColor : control.baseColor)
        border.width: control.kind === "secondary" ? 1 : 0
        border.color: control.hovered ? Theme.borderStrong : Theme.border
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Behavior on border.color { ColorAnimation { duration: Theme.fast } }

        // Fluent-style bottom edge for the primary button.
        Rectangle {
            visible: control.kind === "primary"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: 1
            height: 1
            color: Qt.darker(control.baseColor, 1.25)
            opacity: 0.6
        }

        // Keyboard focus ring.
        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: Theme.radius + 3
            color: "transparent"
            border.width: 2
            border.color: Theme.accent
            visible: control.visualFocus
        }
    }

    contentItem: Item {
        implicitWidth: row.implicitWidth
        implicitHeight: row.implicitHeight
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 7
            Text {
                visible: control.glyph !== ""
                text: control.glyph
                font.family: Theme.iconFont
                font.pixelSize: 14
                color: control.fg
                anchors.verticalCenter: parent.verticalCenter
                Behavior on color { ColorAnimation { duration: Theme.fast } }
            }
            Text {
                visible: control.text !== ""
                text: control.text
                font.family: Theme.uiFont
                font.pixelSize: control.font.pixelSize
                font.weight: control.kind === "primary" ? Font.DemiBold : Font.Medium
                color: control.fg
                anchors.verticalCenter: parent.verticalCenter
                Behavior on color { ColorAnimation { duration: Theme.fast } }
            }
        }
    }
}
