import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../js/Fmt.js" as Fmt

// Destination search over the map. Typing is disabled while the vehicle moves;
// search runs only when submitted (no search-as-you-type, per Nominatim policy).
Rectangle {
    id: root
    signal closeRequested()
    readonly property var search: (Vehicle.navigation || {}).search || ({})
    readonly property bool locked: Vehicle.driveLocked === true

    color: Qt.alpha(Theme.surface, 0.97)
    radius: Theme.radius
    border.color: Theme.border

    function submit() {
        if (field.text.trim() === "" || root.locked) return
        Backend.searchDestination(field.text)
        Qt.inputMethod.hide()
    }
    onVisibleChanged: if (visible && !locked) field.forceActiveFocus()

    ColumnLayout {
        anchors { fill: parent; margins: Theme.gap }
        spacing: Theme.gap

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.gap
            TextField {
                id: field
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.touchMin
                enabled: !root.locked
                placeholderText: root.locked ? "Stop to type a destination" : "Search destination"
                placeholderTextColor: Theme.textDim
                color: Theme.text
                font.pixelSize: Theme.fontM
                inputMethodHints: Qt.ImhNoPredictiveText
                onAccepted: root.submit()
                background: Rectangle {
                    radius: Theme.radius
                    color: Theme.surface2
                    border.color: field.activeFocus ? Theme.accent : Theme.border
                }
            }
            TouchButton {
                icon: "search"
                highlighted: field.text.trim() !== "" && !root.locked
                active: !root.locked
                onClicked: root.submit()
            }
            TouchButton { icon: "close"; onClicked: { Qt.inputMethod.hide(); root.closeRequested() } }
        }

        Text {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            visible: text !== ""
            font.pixelSize: Theme.fontS
            color: root.locked || root.search.state === "error" ? Theme.warn : Theme.textDim
            text: root.locked ? "Typing is disabled while driving. Stop the vehicle, or use the camper screen."
                : root.search.state === "searching" ? "Searching…"
                : root.search.state === "error" ? root.search.error
                : root.search.state === "empty" ? "No results for “" + root.search.query + "”"
                : ""
        }

        ListView {
            id: results
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 4
            model: root.search.results || []
            delegate: Rectangle {
                required property int index
                required property var modelData
                width: ListView.view.width
                height: 72
                radius: Theme.radius
                color: area.pressed ? Theme.surface2 : "transparent"
                RowLayout {
                    anchors { fill: parent; leftMargin: Theme.gap; rightMargin: Theme.gap }
                    spacing: Theme.gap
                    Icon { name: "pin"; width: 26; height: 30; color: Theme.crit }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            Layout.fillWidth: true
                            text: modelData.name
                            color: Theme.text; font.pixelSize: Theme.fontM; font.bold: true
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.detail
                            color: Theme.textDim; font.pixelSize: 14
                            elide: Text.ElideRight
                        }
                    }
                    Text {
                        visible: modelData.distance_m != null
                        text: modelData.distance_m < 10000 ? Fmt.num(modelData.distance_m / 1000, 1) + " km"
                                                           : Fmt.num(modelData.distance_m / 1000) + " km"
                        color: Theme.textDim; font.pixelSize: Theme.fontS
                    }
                }
                MouseArea {
                    id: area
                    anchors.fill: parent
                    onClicked: {
                        Backend.userActivity()
                        Backend.chooseDestination(index)
                        root.closeRequested()
                    }
                }
            }
        }
    }
}
