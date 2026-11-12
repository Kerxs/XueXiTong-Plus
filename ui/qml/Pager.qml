import QtQuick
import "."

// "‹ 2/4 ›": steps through a short list (the videos being watched, the recent quizzes).
Row {
    id: pager
    property int index: 0          // 0-based
    property int count: 0
    signal step(int delta)

    spacing: 2
    visible: count > 1

    component Arrow: Rectangle {
        property string glyph: ""
        signal clicked()
        width: 22
        height: 22
        radius: 6
        color: area.pressed ? Theme.border : area.containsMouse ? Theme.surfaceAlt : "transparent"
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Text {
            anchors.centerIn: parent
            text: parent.glyph
            color: Theme.text
            font.family: Theme.uiFont
            font.pixelSize: 15
        }
        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: parent.clicked()
        }
    }

    Arrow { glyph: "‹"; onClicked: pager.step(-1) }
    Text {
        id: position
        anchors.verticalCenter: parent.verticalCenter
        // the number nudges in the direction of the step
        property int shown: pager.index
        transform: Translate { id: positionShift; x: 0 }
        NumberAnimation { id: positionIn; target: positionShift; property: "x"; to: 0; duration: Theme.normal; easing.type: Easing.OutCubic }
        Connections {
            target: pager
            function onIndexChanged() {
                if (Theme.motion) { positionShift.x = pager.index > position.shown ? 8 : -8; positionIn.restart() }
                position.shown = pager.index
            }
        }
        text: (pager.index + 1) + "/" + pager.count
        color: Theme.muted
        font.family: Theme.monoFont
        font.pixelSize: 11
        horizontalAlignment: Text.AlignHCenter
        width: Math.max(30, implicitWidth + 6)
    }
    Arrow { glyph: "›"; onClicked: pager.step(1) }
}
