import QtQuick

// Camera view on top of the drive screen. It covers navigation without
// destroying it, so the route is intact when the overlay closes.
Rectangle {
    id: root
    property string camera: "rear"     // "rear" | "front"
    property bool byReverse: false
    signal closeRequested()
    signal switchCamera()
    color: "#000000"

    Column {
        anchors.centerIn: parent
        spacing: 16
        Icon { anchors.horizontalCenter: parent.horizontalCenter; name: "camera"; width: 96; height: 96; color: "#666" }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.camera === "rear" ? "Rear camera" : "Front camera"
            color: "#ddd"; font.pixelSize: Theme.fontL; font.bold: true
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: (Vehicle.video || {}).recording === true
                  ? "Recording. Live view comes with the real cameras (phase 6)"
                  : "Dashcam service not running"
            color: "#999"; font.pixelSize: Theme.fontS
        }
    }
    Rectangle {
        visible: root.byReverse
        anchors { top: parent.top; horizontalCenter: parent.horizontalCenter; topMargin: 16 }
        width: rText.implicitWidth + 32; height: 40; radius: 20
        color: Theme.warn
        Text { id: rText; anchors.centerIn: parent; text: "REVERSE"; color: "#000"; font.bold: true; font.pixelSize: Theme.fontM }
    }
    Row {
        visible: !root.byReverse
        anchors { top: parent.top; right: parent.right; margins: 16 }
        spacing: 12
        TouchButton {
            text: root.camera === "rear" ? "Front" : "Rear"
            icon: "camera"
            onClicked: root.switchCamera()
        }
        TouchButton { icon: "close"; onClicked: root.closeRequested() }
    }
    MouseArea { anchors.fill: parent; z: -1 }  // swallow touches meant for the screen below
}
