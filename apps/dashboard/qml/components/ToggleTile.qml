import QtQuick

// Load toggle that shows the *confirmed* state from the MCU and a pending marker
// while a request is in flight. Unknown state (null) is shown as such.
Rectangle {
    id: root
    property string label
    property var load: ({})          // {on: bool|null, pending: bool, requested: bool|null}
    property bool available: false
    signal toggled(bool on)

    readonly property var on: load ? load.on : null
    readonly property bool pending: load ? load.pending === true : false

    implicitHeight: 96
    radius: Theme.radius
    color: on === true ? Qt.alpha(Theme.accent, 0.25) : Theme.surface2
    border.color: on === true ? Theme.accent : Theme.border
    border.width: on === true ? 2 : 1
    opacity: available ? 1 : 0.45

    Column {
        anchors { left: parent.left; verticalCenter: parent.verticalCenter; leftMargin: Theme.gap }
        spacing: 4
        Text { text: root.label; color: Theme.text; font.pixelSize: Theme.fontM; font.bold: true }
        Text {
            color: root.pending ? Theme.warn : Theme.textDim
            font.pixelSize: Theme.fontS
            text: !root.available ? "Control unavailable"
                : root.pending ? "Requested " + (root.load.requested ? "ON" : "OFF") + "…"
                : root.on === true ? "On" : root.on === false ? "Off" : "State unknown"
        }
    }
    MouseArea {
        anchors.fill: parent
        enabled: root.available && !root.pending
        onClicked: { Backend.userActivity(); root.toggled(root.on !== true) }
    }
}
