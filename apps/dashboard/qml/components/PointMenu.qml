import QtQuick
import QtQuick.Layouts
import "../js/Fmt.js" as Fmt

// After a long press on the map: use the point as destination or start.
Rectangle {
    id: root
    property var point: null   // {lat, lon}
    signal closed()
    visible: point !== null
    implicitWidth: row.implicitWidth + 2 * Theme.gap
    implicitHeight: 76
    radius: Theme.radius
    color: Qt.alpha(Theme.surface, 0.97)
    border.color: Theme.accent

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: Theme.gap
        Icon { name: "pin"; width: 28; height: 34; color: Theme.crit }
        Text {
            text: root.point ? Fmt.num(root.point.lat, 4) + ", " + Fmt.num(root.point.lon, 4) : ""
            color: Theme.textDim; font.pixelSize: Theme.fontS
        }
        TouchButton {
            text: "Go here"; icon: "nav"; highlighted: true
            onClicked: { Backend.pickPoint("destination", root.point.lat, root.point.lon); root.closed() }
        }
        TouchButton {
            text: "Set as start"
            onClicked: { Backend.pickPoint("start", root.point.lat, root.point.lon); root.closed() }
        }
        TouchButton { icon: "close"; onClicked: root.closed() }
    }
}
