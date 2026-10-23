import QtQuick
import QtQuick.Layouts

// Next turn while navigating: arrow, distance to it and the instruction.
Rectangle {
    id: root
    readonly property var route: (Vehicle.navigation || {}).route || ({})
    readonly property var next: route.next || null
    visible: route.state === "active" && next !== null
    implicitWidth: 420
    implicitHeight: col.implicitHeight + 2 * Theme.gap
    radius: Theme.radius
    color: Theme.night ? "#10422f" : "#1d8a5a"

    function dist(m) {
        if (m == null) return ""
        if (m < 1000) return (m < 100 ? Math.round(m / 10) * 10 : Math.round(m / 50) * 50) + " m"
        return (m / 1000).toFixed(m < 10000 ? 1 : 0) + " km"
    }

    RowLayout {
        id: col
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: Theme.gap }
        spacing: Theme.gap
        ManeuverIcon { kind: root.next ? root.next.kind : "straight"; color: "white"; Layout.preferredWidth: 72; Layout.preferredHeight: 72 }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text { text: root.dist(root.next ? root.next.distance_m : null); color: "white"; font.pixelSize: 40; font.bold: true }
            Text {
                Layout.fillWidth: true
                text: root.next ? root.next.instruction : ""
                color: "white"; font.pixelSize: Theme.fontM
                wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
            }
        }
    }
}
