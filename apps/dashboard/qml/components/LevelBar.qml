import QtQuick

// Horizontal level 0..100. Unknown value -> empty track with dashed look.
Item {
    id: root
    property var value              // number or null
    property color tint: Theme.accent
    property real warnBelow: -1
    implicitHeight: 18

    readonly property bool known: value != null && !isNaN(value)

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: Theme.surface2
        border.color: root.known ? "transparent" : Theme.border
    }
    Rectangle {
        visible: root.known
        width: root.known ? parent.width * Math.max(0, Math.min(100, root.value)) / 100 : 0
        height: parent.height
        radius: height / 2
        color: root.known && root.value <= root.warnBelow ? Theme.crit : root.tint
        Behavior on width { NumberAnimation { duration: 250 } }
    }
}
