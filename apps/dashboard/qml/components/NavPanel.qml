import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../js/Fmt.js" as Fmt

// Navigation panel over the map: Route (from / to / options), Trips, GPX.
// Typing is disabled while driving; picking results, trips and GPX files is allowed.
Rectangle {
    id: root
    signal closeRequested()
    property string tab: "route"          // route | trips | gpx
    property string editing: "destination" // which field the search box fills: start | destination

    readonly property var nav: Vehicle.navigation || ({})
    readonly property var search: nav.search || ({})
    readonly property var route: nav.route || ({})
    readonly property var opts: nav.options || ({})
    readonly property bool locked: Vehicle.driveLocked === true
    readonly property var gpxLib: Vehicle.gpxLibrary || ({})
    readonly property var gpxLoad: Vehicle.gpxLoad || ({})

    color: Qt.alpha(Theme.surface, 0.97)
    radius: Theme.radius
    border.color: Theme.border

    function km(m) { return m == null ? Fmt.DASH : m < 10000 ? (m / 1000).toFixed(1) + " km" : Math.round(m / 1000) + " km" }
    function submit() {
        if (field.text.trim() === "" || root.locked) return
        Backend.searchPlace(field.text, root.editing)
        Qt.inputMethod.hide()
    }
    function editField(which) { root.editing = which; root.tab = "route"; field.text = ""; Backend.clearSearch(); if (!locked) field.forceActiveFocus() }
    onVisibleChanged: if (visible && tab === "gpx" && !gpxLib.state) Backend.searchGpx("")

    ColumnLayout {
        anchors { fill: parent; margins: Theme.gap }
        spacing: Theme.gap

        // --- tabs ---------------------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            Repeater {
                model: [["route", "Route"], ["trips", "Trips"], ["gpx", "GPX"]]
                delegate: TouchButton {
                    required property var modelData
                    Layout.fillWidth: true
                    text: modelData[1]
                    highlighted: root.tab === modelData[0]
                    onClicked: {
                        root.tab = modelData[0]
                        if (root.tab === "gpx") Backend.searchGpx(gpxField.text)
                    }
                }
            }
            TouchButton { icon: "close"; onClicked: { Qt.inputMethod.hide(); root.closeRequested() } }
        }

        // --- Route tab ----------------------------------------------------------
        ColumnLayout {
            visible: root.tab === "route"
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.gap

            Repeater {
                model: [
                    { key: "start", label: "From", value: root.nav.start ? root.nav.start.name : "Current location", custom: !!root.nav.start },
                    { key: "destination", label: "To", value: root.route.destination ? root.route.destination.name : "Choose destination", custom: false },
                ]
                delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: 60
                    radius: Theme.radius
                    color: root.editing === modelData.key ? Qt.alpha(Theme.accent, 0.18) : Theme.surface2
                    border.color: root.editing === modelData.key ? Theme.accent : Theme.border
                    RowLayout {
                        anchors { fill: parent; leftMargin: Theme.gap; rightMargin: 6 }
                        Text { text: modelData.label; color: Theme.textDim; font.pixelSize: Theme.fontS; Layout.preferredWidth: 46 }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.value
                            color: Theme.text; font.pixelSize: Theme.fontM; font.bold: true
                            elide: Text.ElideRight
                        }
                        TouchButton {
                            visible: modelData.custom
                            implicitHeight: 48
                            text: "Here"
                            onClicked: Backend.startFromCurrentLocation()
                        }
                    }
                    MouseArea { anchors.fill: parent; z: -1; onClicked: root.editField(modelData.key) }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.gap
                TextField {
                    id: field
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.touchMin
                    enabled: !root.locked
                    placeholderText: root.locked ? "Stop to type"
                                   : root.editing === "start" ? "Search start" : "Search destination"
                    placeholderTextColor: Theme.textDim
                    color: Theme.text
                    font.pixelSize: Theme.fontM
                    inputMethodHints: Qt.ImhNoPredictiveText
                    onAccepted: root.submit()
                    background: Rectangle { radius: Theme.radius; color: Theme.surface2; border.color: field.activeFocus ? Theme.accent : Theme.border }
                }
                TouchButton { icon: "search"; active: !root.locked; highlighted: field.text.trim() !== ""; onClicked: root.submit() }
            }

            Text {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                font.pixelSize: Theme.fontS
                color: root.locked || root.search.state === "error" ? Theme.warn : Theme.textDim
                text: root.locked ? "Typing is disabled while driving. Trips and GPX files can still be chosen."
                    : root.search.state === "searching" ? "Searching…"
                    : root.search.state === "error" ? root.search.error
                    : root.search.state === "empty" ? "No results for “" + root.search.query + "”"
                    : (root.search.results || []).length ? ""
                    : "Tip: long-press the map to use a point as start or destination."
            }

            // Results of the search, or the route summary and options when nothing is searched.
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: (root.search.results || []).length > 0
                clip: true
                spacing: 4
                model: root.search.results || []
                delegate: Rectangle {
                    required property int index
                    required property var modelData
                    width: ListView.view.width
                    height: 66
                    radius: Theme.radius
                    color: resArea.pressed ? Theme.surface2 : "transparent"
                    RowLayout {
                        anchors { fill: parent; leftMargin: Theme.gap; rightMargin: Theme.gap }
                        spacing: Theme.gap
                        Icon { name: "pin"; width: 24; height: 28; color: root.editing === "start" ? Theme.ok : Theme.crit }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text { Layout.fillWidth: true; text: modelData.name; color: Theme.text; font.pixelSize: Theme.fontM; font.bold: true; elide: Text.ElideRight }
                            Text { Layout.fillWidth: true; text: modelData.detail; color: Theme.textDim; font.pixelSize: 14; elide: Text.ElideRight }
                        }
                        Text { visible: modelData.distance_m != null; text: root.km(modelData.distance_m); color: Theme.textDim; font.pixelSize: Theme.fontS }
                    }
                    MouseArea {
                        id: resArea
                        anchors.fill: parent
                        onClicked: {
                            Backend.userActivity()
                            Backend.chooseDestination(index)
                            Backend.clearSearch()
                            if (root.editing === "start") root.editing = "destination"
                        }
                    }
                }
            }

            ColumnLayout {
                visible: !(root.search.results || []).length
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: Theme.gap

                Text { text: "Route options"; color: Theme.textDim; font.pixelSize: Theme.fontS }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    rowSpacing: 6; columnSpacing: 6
                    Repeater {
                        model: [["avoid_motorways", "No motorways"], ["avoid_tolls", "No tolls"],
                                ["avoid_ferries", "No ferries"], ["avoid_unpaved", "No unpaved"]]
                        delegate: TouchButton {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 52
                            text: modelData[1]
                            highlighted: root.opts[modelData[0]] === true
                            onClicked: Backend.setRouteOption(modelData[0], !root.opts[modelData[0]])
                        }
                    }
                }
                Item { Layout.fillHeight: true }
                Text {
                    Layout.fillWidth: true
                    visible: root.route.distance_m != null && root.route.state !== "error"
                    text: root.km(root.route.distance_m) + " · " + Fmt.duration((root.route.duration_s || 0) / 60)
                          + (root.route.state === "preview" ? " · planned route" : "")
                    color: Theme.text; font.pixelSize: Theme.fontM; font.bold: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.gap
                    visible: root.route.state === "preview" || root.route.state === "active"
                    TouchButton {
                        Layout.fillWidth: true
                        visible: root.route.state === "preview"
                        text: "Start"; icon: "nav"; highlighted: true
                        onClicked: { Backend.startNavigation(); root.closeRequested() }
                    }
                    TouchButton { Layout.fillWidth: true; text: "Save trip"; onClicked: Backend.savePlannedTrip() }
                    TouchButton { Layout.fillWidth: true; text: "Cancel route"; onClicked: Backend.cancelRoute() }
                }
            }
        }

        // --- Trips tab ------------------------------------------------------------
        ListView {
            visible: root.tab === "trips"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 6
            model: Vehicle.trips || []
            Text {
                anchors.centerIn: parent
                visible: parent.count === 0
                text: "No trips yet. They are saved automatically when you navigate."
                color: Theme.textDim; font.pixelSize: Theme.fontS
            }
            delegate: Rectangle {
                required property var modelData
                width: ListView.view.width
                height: 110
                radius: Theme.radius
                color: Theme.surface2
                ColumnLayout {
                    anchors { fill: parent; margins: Theme.gap }
                    spacing: 4
                    Text { Layout.fillWidth: true; text: modelData.name; color: Theme.text; font.pixelSize: Theme.fontM; font.bold: true; elide: Text.ElideRight }
                    Text {
                        Layout.fillWidth: true
                        color: Theme.textDim; font.pixelSize: 14; elide: Text.ElideRight
                        text: (modelData.created || "").replace("T", " ").substring(0, 16) + " · " + modelData.status
                              + " · " + root.km(modelData.driven && modelData.driven.distance_m ? modelData.driven.distance_m
                                                                                               : modelData.planned.distance_m)
                              + (modelData.source ? " · GPX" : "")
                    }
                    RowLayout {
                        spacing: Theme.gap
                        TouchButton { implicitHeight: 44; text: "Drive from here"; onClicked: { Backend.driveTrip(modelData.id, true); root.tab = "route" } }
                        TouchButton { implicitHeight: 44; text: "Show"; onClicked: { Backend.driveTrip(modelData.id, false); root.tab = "route" } }
                    }
                }
            }
        }

        // --- GPX tab ----------------------------------------------------------------
        ColumnLayout {
            visible: root.tab === "gpx"
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.gap
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.gap
                TextField {
                    id: gpxField
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.touchMin
                    enabled: !root.locked
                    placeholderText: "Search your GPX files (name, place, date)"
                    placeholderTextColor: Theme.textDim
                    color: Theme.text
                    font.pixelSize: Theme.fontM
                    onAccepted: { Backend.searchGpx(text); Qt.inputMethod.hide() }
                    background: Rectangle { radius: Theme.radius; color: Theme.surface2; border.color: gpxField.activeFocus ? Theme.accent : Theme.border }
                }
                TouchButton { icon: "search"; onClicked: Backend.searchGpx(gpxField.text) }
            }
            Text {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                font.pixelSize: Theme.fontS
                color: root.gpxLoad.state === "error" || root.gpxLib.state === "error" ? Theme.warn : Theme.textDim
                text: root.gpxLoad.state === "loading" ? "Matching the track to the roads…"
                    : root.gpxLoad.state === "error" ? "Cannot use this GPX: " + root.gpxLoad.error
                    : root.gpxLib.state === "searching" ? "Scanning GPX files…"
                    : root.gpxLib.state === "error" ? root.gpxLib.error
                    : root.gpxLib.state === "done" && !(root.gpxLib.results || []).length
                      ? "No GPX files found. Put them in the GPX folder (subfolders are scanned)." : ""
            }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 4
                model: root.gpxLib.results || []
                delegate: Rectangle {
                    required property var modelData
                    width: ListView.view.width
                    height: 72
                    radius: Theme.radius
                    color: gpxArea.pressed ? Theme.surface2 : "transparent"
                    opacity: modelData.error ? 0.5 : 1
                    RowLayout {
                        anchors { fill: parent; leftMargin: Theme.gap; rightMargin: Theme.gap }
                        spacing: Theme.gap
                        Icon { name: "map"; width: 28; height: 28; color: "#e08a2c" }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text { Layout.fillWidth: true; text: modelData.name; color: Theme.text; font.pixelSize: Theme.fontM; font.bold: true; elide: Text.ElideRight }
                            Text {
                                Layout.fillWidth: true
                                color: Theme.textDim; font.pixelSize: 14; elide: Text.ElideRight
                                text: modelData.error ? "unreadable: " + modelData.error
                                      : root.km(modelData.length_m) + (modelData.loop ? " loop" : "")
                                        + (modelData.start_name ? " · " + modelData.start_name : "")
                                        + (modelData.end_name && !modelData.loop ? " → " + modelData.end_name : "")
                                        + (modelData.date ? " · " + modelData.date : "")
                            }
                        }
                        Text { visible: modelData.distance_m != null; text: root.km(modelData.distance_m); color: Theme.textDim; font.pixelSize: Theme.fontS }
                    }
                    MouseArea {
                        id: gpxArea
                        anchors.fill: parent
                        enabled: !modelData.error && root.gpxLoad.state !== "loading"
                        onClicked: { Backend.userActivity(); Backend.loadGpx(modelData.id, true); root.tab = "route" }
                    }
                }
            }
        }
    }
}
