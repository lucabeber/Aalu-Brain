import QtQuick
import QtQuick.Layouts
import "../js/Fmt.js" as Fmt

// Android Auto-style dock: drive layouts, cameras, navigation app and
// (single-screen mode) the switch to the camper view. Vertical on landscape
// screens, horizontal at the bottom on portrait ones.
Rectangle {
    id: root
    property bool vertical: true
    property string layout: "map"           // map | media | energy
    property bool canSwitchView: false
    signal layoutSelected(string name)
    signal cameraRequested()
    signal switchView()

    color: Theme.surface
    implicitWidth: vertical ? 104 : 0
    implicitHeight: vertical ? 0 : 104

    GridLayout {
        anchors { fill: parent; margins: 8 }
        flow: root.vertical ? GridLayout.TopToBottom : GridLayout.LeftToRight
        rows: root.vertical ? -1 : 1
        columns: root.vertical ? 1 : -1
        rowSpacing: 8
        columnSpacing: 8

        DockButton { icon: "map"; label: "Map"; checked: root.layout === "map"; onClicked: root.layoutSelected("map") }
        DockButton { icon: "music"; label: "Music"; checked: root.layout === "media"; onClicked: root.layoutSelected("media") }
        DockButton { icon: "battery"; label: "Energy"; checked: root.layout === "energy"; onClicked: root.layoutSelected("energy") }
        DockButton { icon: "camera"; label: "Camera"; onClicked: root.cameraRequested() }
        // Dashcam: quick clip (last/next minute) and long clip (last 5 + next 10 minutes).
        // While a clip is still being extended, both show the remaining time.
        DockButton {
            readonly property var v: Vehicle.video || ({})
            icon: "rec"; label: v.protecting ? Fmt.saving(v) : "Save clip"
            checked: v.protecting === true
            active: v.recording === true
            onClicked: Backend.protectClip()
        }
        DockButton {
            readonly property var v: Vehicle.video || ({})
            icon: "rec"; label: "Save 15 min"
            active: v.recording === true
            onClicked: Backend.protectLongClip()
        }
        DockButton {
            icon: "nav"; label: "Navigate"
            active: Vehicle.navigationAvailable === true
            onClicked: Backend.launchNavigation()
        }

        Item { Layout.fillHeight: root.vertical; Layout.fillWidth: !root.vertical }

        DockButton {
            visible: root.canSwitchView
            icon: "camper"; label: "Camper"
            onClicked: root.switchView()
        }
    }

    component DockButton: Rectangle {
        id: btn
        property string icon
        property string label
        property bool checked: false
        property bool active: true
        signal clicked()
        Layout.preferredWidth: 88
        Layout.preferredHeight: 80
        // Shrink on short screens instead of overflowing the dock.
        Layout.fillHeight: root.vertical
        Layout.minimumHeight: 60
        Layout.maximumHeight: 80
        Layout.alignment: Qt.AlignCenter
        radius: Theme.radius
        opacity: active ? 1 : 0.4
        color: checked ? Qt.alpha(Theme.accent, 0.3) : area.pressed ? Theme.surface2 : "transparent"
        border.color: checked ? Theme.accent : "transparent"
        Column {
            anchors.centerIn: parent
            spacing: 4
            Icon { anchors.horizontalCenter: parent.horizontalCenter; name: btn.icon; width: 34; height: 34; color: btn.checked ? Theme.accent : Theme.text }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: btn.label; color: Theme.textDim; font.pixelSize: 13 }
        }
        MouseArea {
            id: area
            anchors.fill: parent
            enabled: btn.active
            onClicked: { Backend.userActivity(); btn.clicked() }
        }
    }
}
