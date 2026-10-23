import QtQuick
import "../js/Fmt.js" as Fmt

// Shows SIMULATED for simulated sources and the degradation state, if any.
Row {
    id: root
    property string quality: "disconnected"
    property bool simulated: false
    spacing: 6

    component Pill: Rectangle {
        property alias label: t.text
        property color tint
        visible: label !== ""
        radius: height / 2
        height: t.implicitHeight + 6
        width: t.implicitWidth + 14
        color: Qt.alpha(tint, 0.18)
        border.color: tint
        Text {
            id: t
            anchors.centerIn: parent
            color: parent.tint
            font.pixelSize: 12
            font.bold: true
            font.letterSpacing: 0.8
        }
    }

    Pill { label: root.simulated ? "SIMULATED" : ""; tint: Theme.sim }
    Pill { label: Fmt.qualityLabel(root.quality); tint: Theme.qualityColor(root.quality) }
}
