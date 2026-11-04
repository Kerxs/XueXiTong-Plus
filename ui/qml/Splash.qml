import QtQuick
import QtQuick.Window

// Startup splash: icon on the left, "学习通 PLUS" typed out like streamed AI text.
// The real app loads behind it (see ui/startup.py); the splash closes only once
// the text has finished typing AND startup.loaded is true.
Window {
    id: splash
    signal finished()

    readonly property string fullText: "学习通 PLUS"
    property int shown: 0
    readonly property bool typed: shown >= fullText.length

    width: 600
    height: 250
    flags: Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    color: "transparent"
    title: startup.appName

    onTypedChanged: maybeFinish()
    Connections {
        target: startup
        function onLoadedChanged() { splash.maybeFinish() }
    }

    function maybeFinish() {
        if (typed && startup.loaded && !outro.running && !hold.running)
            hold.start()
    }

    Rectangle {
        id: card
        anchors.fill: parent
        anchors.margins: 10
        radius: 20
        color: "#ffffff"
        border.color: "#e6e8ee"
        opacity: 0
        scale: 0.96

        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -12
            spacing: 28

            Image {
                id: icon
                source: startup.iconUrl
                sourceSize: Qt.size(256, 256)   // sharp on high-DPI displays (same texture as Main.qml)
                width: 112
                height: 112
                smooth: true
                mipmap: true
                anchors.verticalCenter: parent.verticalCenter
                opacity: 0
                scale: 0.8
            }

            Row {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4
                width: 300

                Text {
                    text: splash.fullText.substring(0, splash.shown)
                    color: "#000000"
                    font.family: "Microsoft YaHei UI"
                    font.pixelSize: 44
                    font.weight: Font.Black
                    anchors.verticalCenter: parent.verticalCenter
                }

                // Blinking caret, like a streaming AI response.
                Rectangle {
                    width: 4
                    height: 46
                    radius: 2
                    color: "#000000"
                    anchors.verticalCenter: parent.verticalCenter
                    SequentialAnimation on opacity {
                        running: true
                        loops: Animation.Infinite
                        NumberAnimation { to: 0; duration: 420 }
                        NumberAnimation { to: 1; duration: 420 }
                    }
                }
            }
        }

        // Real loading status from the startup sequence (no progress bar).
        Text {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            anchors.leftMargin: 34
            anchors.bottomMargin: 22
            text: startup.status + (startup.loaded ? "" : "…")
            color: "#7a7f8c"
            font.family: "Microsoft YaHei UI"
            font.pixelSize: 12
        }
    }

    Timer {
        id: typer
        // Uneven intervals read more like streamed tokens than a metronome.
        interval: 120
        repeat: true
        onTriggered: {
            if (!splash.typed) {
                splash.shown += 1
                // The space and the Latin letters stream a little faster than the hanzi.
                const next = splash.fullText.charAt(splash.shown)
                interval = (next === " " || /[A-Z]/.test(next) ? 70 : 110) + Math.round(Math.random() * 50)
            } else {
                stop()
            }
        }
    }

    Timer {
        id: hold
        interval: 250
        onTriggered: outro.start()
    }

    SequentialAnimation {
        id: intro
        ParallelAnimation {
            NumberAnimation { target: card; property: "opacity"; to: 1; duration: 160; easing.type: Easing.OutCubic }
            NumberAnimation { target: card; property: "scale"; to: 1; duration: 180; easing.type: Easing.OutCubic }
        }
        ParallelAnimation {
            NumberAnimation { target: icon; property: "opacity"; to: 1; duration: 180 }
            NumberAnimation { target: icon; property: "scale"; to: 1; duration: 240; easing.type: Easing.OutBack }
        }
        ScriptAction { script: typer.start() }
    }

    // The main window opens behind the splash with the same logo at the screen centre
    // (Main.qml), so the card dissolves into it; the logo then moves to the top-left.
    // Revealing before closing also keeps the app from quitting on "last window closed".
    SequentialAnimation {
        id: outro
        ScriptAction { script: splash.finished() }
        PauseAnimation { duration: 60 }
        NumberAnimation { target: card; property: "opacity"; to: 0; duration: 200; easing.type: Easing.InCubic }
        ScriptAction { script: splash.close() }
    }

    Component.onCompleted: {
        x = Screen.virtualX + (Screen.width - width) / 2
        y = Screen.virtualY + (Screen.height - height) / 2
        show()
        intro.start()
    }
}
