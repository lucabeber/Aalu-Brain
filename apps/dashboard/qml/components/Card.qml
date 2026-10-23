import QtQuick
import QtQuick.Layouts

// Panel with title and data-quality badge. Content dims when the data is stale.
Rectangle {
    id: root
    property string title
    property var info: ({})          // a source view from Vehicle.<source>
    property bool showBadge: true
    default property alias content: body.data

    readonly property string quality: info && info.quality ? info.quality : "disconnected"

    color: Theme.surface
    radius: Theme.radius
    border.color: quality === "error" ? Theme.crit : Theme.border
    implicitHeight: header.height + (body.children.length ? body.children[0].implicitHeight : 0)
                    + 3 * Theme.gap

    RowLayout {
        id: header
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: Theme.gap }
        Text {
            text: root.title
            color: Theme.textDim
            font.pixelSize: Theme.fontS
            font.bold: true
            font.capitalization: Font.AllUppercase
            font.letterSpacing: 1
            Layout.fillWidth: true
            elide: Text.ElideRight
        }
        QualityBadge {
            visible: root.showBadge
            quality: root.quality
            simulated: root.info ? root.info.simulated === true : false
        }
    }
    Item {
        id: body
        anchors {
            left: parent.left; right: parent.right; top: header.bottom
            bottom: parent.bottom; margins: Theme.gap
        }
        opacity: root.quality === "stale" ? 0.5 : 1.0
        clip: true
    }
}
