import QtQuick

// Large touch target with optional icon. Feedback on press, no long animations.
Rectangle {
    id: root
    property string text
    property string icon
    property bool highlighted: false
    property bool active: true      // false = visibly disabled but still a layout item
    signal clicked()

    implicitWidth: Math.max(Theme.touchMin, row.implicitWidth + 2 * Theme.gap)
    implicitHeight: Theme.touchMin
    radius: Theme.radius
    color: !active ? Theme.surface2
         : area.pressed ? Qt.darker(highlighted ? Theme.accent : Theme.surface2, 1.4)
         : highlighted ? Theme.accent : Theme.surface2
    opacity: active ? 1.0 : 0.45
    border.color: Theme.border

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 8
        Icon {
            visible: root.icon !== ""
            name: root.icon
            color: root.highlighted ? Theme.bg : Theme.text
            width: 28; height: 28
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            visible: root.text !== ""
            text: root.text
            color: root.highlighted ? Theme.bg : Theme.text
            font.pixelSize: Theme.fontM
            font.bold: true
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    MouseArea {
        id: area
        anchors.fill: parent
        enabled: root.active
        onClicked: { Backend.userActivity(); root.clicked() }
    }
}
