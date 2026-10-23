pragma Singleton
import QtQuick

// Design tokens. Night palette is the default for driving: low luminance
// background, no pure white, saturated colours reserved for states.
QtObject {
    property bool night: true

    readonly property color bg:        night ? "#0b0e12" : "#eef1f4"
    readonly property color surface:   night ? "#151a21" : "#ffffff"
    readonly property color surface2:  night ? "#1e252e" : "#e2e7ec"
    readonly property color border:    night ? "#2a323d" : "#c9d1da"
    readonly property color text:      night ? "#d9dee4" : "#151a21"
    readonly property color textDim:   night ? "#7d8794" : "#5b6573"
    readonly property color accent:    night ? "#4fa3e0" : "#1769aa"
    readonly property color ok:        night ? "#3fb27f" : "#1d8a5a"
    readonly property color warn:      night ? "#e0a93b" : "#b37400"
    readonly property color crit:      night ? "#e5534b" : "#c62f27"
    readonly property color info:      night ? "#8b9bb0" : "#55657a"
    readonly property color sim:       night ? "#c678dd" : "#8e3fae"

    readonly property int radius: 14
    readonly property int gap: 12
    readonly property int touchMin: 64     // minimum touch target in px
    readonly property int fontS: 16
    readonly property int fontM: 20
    readonly property int fontL: 28
    readonly property int fontXL: 44

    function qualityColor(q) {
        switch (q) {
        case "valid": return ok
        case "simulated": return sim
        case "stale": return warn
        case "error": return crit
        default: return info          // disconnected / unknown
        }
    }
    function severityColor(s) {
        return s === "critical" ? crit : s === "warning" ? warn : info
    }
}
