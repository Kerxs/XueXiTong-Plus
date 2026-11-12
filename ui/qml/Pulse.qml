import QtQuick

// A slow "breathing" of one property (opacity, scale) in coarse steps.
//
// An Animation redraws the whole window on every screen refresh for as long as it runs — 60 to
// 240 frames a second for a dot that fades over a second or two, and the status dot runs for
// the whole task (hours). Measured idle: 3-22% of a CPU core. Twelve steps a second look the
// same for something this slow and cost about a twentieth.
Timer {
    id: pulse
    property Item target: null
    property string prop: "opacity"
    property real from: 1.0          // the resting value; also where each cycle starts and ends
    property real to: 0.3
    property int period: 1400        // ms for there and back
    property bool active: false
    property real elapsed: 0

    interval: 80
    repeat: true
    running: active && target !== null
    onTriggered: {
        elapsed = (elapsed + interval) % period
        target[prop] = from + (to - from) * (0.5 - 0.5 * Math.cos(2 * Math.PI * elapsed / period))
    }
    onRunningChanged: {
        if (!running && target !== null) {
            elapsed = 0
            target[prop] = from
        }
    }
}
