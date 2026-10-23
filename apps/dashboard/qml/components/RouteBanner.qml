import QtQuick
import QtQuick.Layouts
import "../js/Fmt.js" as Fmt

// Active route summary: destination, remaining distance and time, arrival clock.
Rectangle {
    id: root
    signal searchRequested()
    readonly property var route: (Vehicle.navigation || {}).route || ({})
    readonly property string state_: route.state || "none"

    visible: state_ !== "none"
    implicitHeight: 76
    radius: Theme.radius
    color: Qt.alpha(Theme.surface, 0.95)
    border.color: state_ === "error" ? Theme.warn : state_ === "arrived" ? Theme.ok : Theme.border

    function arrival(seconds) {
        if (seconds == null) return Fmt.DASH
        var d = new Date(Date.now() + seconds * 1000)
        return d.getFullYear() < 2024 ? Fmt.DASH : Qt.formatTime(d, "HH:mm")
    }
    function km(m) {
        if (m == null) return Fmt.DASH
        return m < 1000 ? Math.round(m / 10) * 10 + " m" : m < 10000 ? (m / 1000).toFixed(1) + " km"
                                                                    : Math.round(m / 1000) + " km"
    }

    RowLayout {
        anchors { fill: parent; leftMargin: Theme.gap; rightMargin: 8 }
        spacing: Theme.gap
        Icon { name: "pin"; width: 30; height: 36; color: root.state_ === "arrived" ? Theme.ok : Theme.crit }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                Layout.fillWidth: true
                elide: Text.ElideRight
                color: Theme.text; font.pixelSize: Theme.fontM; font.bold: true
                text: root.state_ === "arrived" ? "Arrived: " + root.route.destination.name
                    : root.route.destination ? root.route.destination.name : "Route"
            }
            Text {
                Layout.fillWidth: true
                elide: Text.ElideRight
                font.pixelSize: Theme.fontS
                color: root.state_ === "error" || root.route.off_route ? Theme.warn : Theme.textDim
                text: root.state_ === "routing" ? "Calculating route…"
                    : root.state_ === "error" ? (root.route.error || "Route not available")
                    : root.state_ === "arrived" ? "You have reached your destination"
                    : root.route.off_route ? "Off route: recalculating…"
                    : root.km(root.route.remaining_m) + " · " + Fmt.duration(root.route.remaining_s / 60)
                      + " · arrive " + root.arrival(root.route.remaining_s)
            }
        }
        TouchButton { icon: "search"; onClicked: root.searchRequested() }
        TouchButton { icon: "close"; onClicked: Backend.cancelRoute() }
    }
}
