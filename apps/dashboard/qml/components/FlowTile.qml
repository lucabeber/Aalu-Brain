import QtQuick
import QtQuick.Layouts
import "../js/Fmt.js" as Fmt

// One energy flow: label, signed power, current. Sign colour: in = green, out = amber.
Rectangle {
    id: root
    property string label
    property var watts                  // signed, null = unknown
    property var amps
    property string note                // e.g. "engine off"
    property bool outgoing: false       // consumption is shown as a negative flow
    property bool big: false

    readonly property bool known: watts != null && !isNaN(watts)
    readonly property real shown: known ? (outgoing ? -Math.abs(watts) : watts) : 0
    readonly property color tint: !known || Math.abs(shown) < 1 ? Theme.textDim
                                  : shown > 0 ? Theme.ok : Theme.warn

    radius: Theme.radius
    color: Theme.surface2
    border.color: Theme.border
    implicitHeight: col.implicitHeight + 2 * Theme.gap
    implicitWidth: 160

    ColumnLayout {
        id: col
        anchors { fill: parent; margins: Theme.gap }
        spacing: 2
        Text { text: root.label; color: Theme.textDim; font.pixelSize: Theme.fontS; Layout.fillWidth: true; elide: Text.ElideRight }
        Text {
            text: !root.known ? Fmt.DASH : (root.shown > 0 ? "+" : root.shown < 0 ? "−" : "") + Fmt.power(Math.abs(root.shown))
            color: root.tint
            font.pixelSize: root.big ? Theme.fontXL : Theme.fontL
            font.bold: true
        }
        Text {
            text: root.note !== "" ? root.note : (root.amps == null ? "" : Fmt.num(Math.abs(root.amps), 1) + " A")
            visible: text !== ""
            color: Theme.textDim
            font.pixelSize: Theme.fontS
        }
    }
}
