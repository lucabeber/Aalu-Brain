import QtQuick

// Coloured dot + short label, coloured by data quality (or explicit colour).
Row {
    property string label
    property string quality: "disconnected"
    property color tint: Theme.qualityColor(quality)
    spacing: 6
    Rectangle {
        width: 12; height: 12; radius: 6
        color: parent.tint
        anchors.verticalCenter: parent.verticalCenter
    }
    Text {
        text: parent.label
        color: Theme.text
        font.pixelSize: Theme.fontS
        anchors.verticalCenter: parent.verticalCenter
    }
}
