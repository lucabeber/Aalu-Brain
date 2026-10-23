import QtQuick
import QtQuick.Layouts
import QtCore
import "../components"
import "../js/Fmt.js" as Fmt

// Drive view, Android Auto style: a dock plus a moving map that is either full
// screen or shares the screen (3/4 + 1/4) with music or energy. On portrait
// screens the side panel moves below the map and the dock to the bottom.
Rectangle {
    id: root
    color: Theme.bg

    property bool canSwitchView: false
    signal switchView()

    readonly property bool portrait: height > width
    readonly property var gnss: Vehicle.gnss || ({})
    readonly property bool hasFix: Fmt.isLive(gnss.quality) && (gnss.fix === "3d" || gnss.fix === "2d")
    property string manualCamera: ""       // "" | "rear" | "front"

    Settings {
        id: prefs
        category: "drive"
        property string layout: "media"    // map | media | energy (remembered across restarts)
    }

    GridLayout {
        anchors.fill: parent
        flow: root.portrait ? GridLayout.TopToBottom : GridLayout.LeftToRight
        rows: root.portrait ? 2 : 1
        columns: root.portrait ? 1 : 2
        rowSpacing: 0
        columnSpacing: 0

        DockBar {
            id: dock
            vertical: !root.portrait
            layout: prefs.layout
            canSwitchView: root.canSwitchView
            Layout.fillHeight: !root.portrait
            Layout.fillWidth: root.portrait
            Layout.row: root.portrait ? 1 : 0
            Layout.column: 0
            onLayoutSelected: (name) => prefs.layout = name
            onCameraRequested: root.manualCamera = "rear"
            onSwitchView: root.switchView()
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.row: 0
            Layout.column: root.portrait ? 0 : 1
            spacing: 0

            StatusBar { Layout.fillWidth: true; title: "" }

            Item {
                id: content
                Layout.fillWidth: true
                Layout.fillHeight: true

                readonly property bool split: prefs.layout !== "map"
                readonly property real gap: Theme.gap
                // Side panel: a quarter of the screen, but never too narrow to read.
                readonly property real sideW: Math.max(300, width * 0.25)
                readonly property real sideH: Math.max(320, height * 0.25)

                // Offline vector map (MapLibre) when map packs are installed, else Qt Location.
                Loader {
                    id: map
                    x: 0; y: 0
                    width: content.split && !root.portrait ? content.width - content.sideW - content.gap : content.width
                    height: content.split && root.portrait ? content.height - content.sideH - content.gap : content.height
                    source: Backend.mapEngine === "maplibre" ? "../components/WebMapPanel.qml"
                                                             : "../components/MapPanel.qml"
                }
                Connections {
                    target: map.item
                    ignoreUnknownSignals: true
                    function onPointPicked(lat, lon) { content.picked = { lat: lat, lon: lon } }
                }
                property var picked: null

                // --- overlays: next turn + speed (top-left), alarms (top-right) ----------
                ManeuverBanner {
                    id: maneuver
                    anchors { left: map.left; top: map.top; margins: Theme.gap }
                    width: Math.min(460, map.width * 0.45)
                }
                Rectangle {
                    anchors { left: map.left; top: maneuver.visible ? maneuver.bottom : map.top; margins: Theme.gap }
                    width: speedRow.implicitWidth + 28; height: 76
                    radius: Theme.radius
                    color: Qt.alpha(Theme.surface, 0.92)
                    border.color: Theme.border
                    Row {
                        id: speedRow
                        anchors.centerIn: parent
                        spacing: 6
                        Text {
                            id: speedText
                            text: root.hasFix ? Fmt.num(root.gnss.speed_kmh) : Fmt.DASH
                            color: Theme.text; font.pixelSize: 48; font.bold: true
                        }
                        Text {
                            text: "km/h"; color: Theme.textDim; font.pixelSize: Theme.fontS
                            anchors.baseline: speedText.baseline
                        }
                    }
                }
                // Important alarms float over the map (info notices stay in the camper view).
                AlarmList {
                    anchors { right: map.right; top: map.top; margins: Theme.gap }
                    width: Math.min(400, map.width * 0.35)
                    showEmpty: false
                    maxItems: 2
                    severities: ["critical", "warning"]
                }

                // --- navigation ------------------------------------------------------
                readonly property string routeState: ((Vehicle.navigation || {}).route || {}).state || "none"
                readonly property bool hasRoute: routeState !== "none"
                property bool panelOpen: false
                // A search started anywhere (or from the command line) opens the panel;
                // once a route is being computed, the map is shown again.
                readonly property string searchState: ((Vehicle.navigation || {}).search || {}).state || "idle"
                onSearchStateChanged: if (searchState === "searching") panelOpen = true
                onRouteStateChanged: if (routeState === "routing" || routeState === "active") panelOpen = false

                Rectangle {
                    id: searchPill
                    visible: !content.panelOpen && !content.hasRoute && content.picked === null
                    anchors { top: map.top; horizontalCenter: map.horizontalCenter; topMargin: Theme.gap }
                    width: Math.min(340, map.width - 2 * 230); height: 60
                    radius: height / 2
                    color: Qt.alpha(Theme.surface, 0.95)
                    border.color: Theme.border
                    Row {
                        anchors.centerIn: parent
                        spacing: 10
                        Icon { name: "search"; width: 28; height: 28; color: Theme.text; anchors.verticalCenter: parent.verticalCenter }
                        Text {
                            text: "Where to?"
                            color: Theme.textDim; font.pixelSize: Theme.fontM
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                    MouseArea { anchors.fill: parent; onClicked: { Backend.userActivity(); content.panelOpen = true } }
                }

                PointMenu {
                    point: content.picked
                    anchors { top: map.top; horizontalCenter: map.horizontalCenter; topMargin: Theme.gap }
                    onClosed: content.picked = null
                }

                RouteBanner {
                    visible: !content.panelOpen && content.hasRoute
                    anchors { bottom: map.bottom; horizontalCenter: map.horizontalCenter; bottomMargin: 28 }
                    width: Math.min(640, map.width - 2 * (Theme.touchMin + 2 * Theme.gap))
                    onSearchRequested: content.panelOpen = true
                }

                NavPanel {
                    id: navPanel
                    visible: content.panelOpen
                    Component.onCompleted: if (Backend.initialPanel !== "") {
                        tab = Backend.initialPanel
                        content.panelOpen = true
                        if (tab === "gpx") Backend.searchGpx("")
                    }
                    anchors { top: map.top; left: map.left; bottom: map.bottom; margins: Theme.gap }
                    width: Math.min(560, map.width - 2 * Theme.gap - Theme.touchMin - Theme.gap)
                    onCloseRequested: content.panelOpen = false
                }

                Loader {
                    id: side
                    active: content.split
                    visible: active
                    x: root.portrait ? 0 : content.width - content.sideW
                    y: root.portrait ? content.height - content.sideH : 0
                    width: root.portrait ? content.width : content.sideW
                    height: root.portrait ? content.sideH : content.height
                    sourceComponent: prefs.layout === "energy" ? energyPanel : mediaPanel
                }
                Component { id: mediaPanel; MediaMiniPlayer {} }
                Component { id: energyPanel; EnergyPanel {} }

            }
        }
    }

    // Reverse input takes priority over a manually opened camera. The overlay covers the
    // map without destroying it, so position and zoom are intact afterwards.
    ReverseOverlay {
        anchors.fill: parent
        visible: Vehicle.reverse === true || root.manualCamera !== ""
        byReverse: Vehicle.reverse === true
        camera: Vehicle.reverse === true ? "rear" : root.manualCamera
        onCloseRequested: root.manualCamera = ""
        onSwitchCamera: root.manualCamera = root.manualCamera === "rear" ? "front" : "rear"
    }
}
