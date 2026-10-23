import QtQuick
import QtQuick.Layouts

// Active alarms, most severe first. `maxItems` limits it for the drive screen.
ColumnLayout {
    id: root
    property int maxItems: 100
    property bool showEmpty: true
    property var severities: ["critical", "warning", "info"]
    readonly property var alarms: (Vehicle.alarms || []).filter(a => severities.indexOf(a.severity) >= 0)
    spacing: 6

    Text {
        visible: root.showEmpty && root.alarms.length === 0
        text: "No active alarms"
        color: Theme.textDim
        font.pixelSize: Theme.fontS
    }
    Repeater {
        model: root.alarms.slice(0, root.maxItems)
        delegate: Rectangle {
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: 44
            radius: 10
            color: Qt.alpha(Theme.severityColor(modelData.severity), 0.15)
            border.color: Theme.severityColor(modelData.severity)
            Text {
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 12 }
                text: modelData.message
                color: Theme.text
                font.pixelSize: Theme.fontS
                font.bold: modelData.severity !== "info"
                elide: Text.ElideRight
            }
        }
    }
}
