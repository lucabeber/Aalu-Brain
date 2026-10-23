import QtQuick
import QtLocation
import QtPositioning
import "../js/Fmt.js" as Fmt

// Moving map following the GNSS position. Raster tiles (OSM by default) are cached
// on disk, so areas already seen stay available offline. Dragging the map stops
// following; the re-centre button resumes it.
Item {
    id: root
    property bool follow: true
    property int trackLength: 600           // breadcrumb points kept
    readonly property var gnss: Vehicle.gnss || ({})
    readonly property var cfg: Vehicle.mapConfig || ({})
    readonly property bool hasFix: Fmt.isLive(gnss.quality) && (gnss.fix === "3d" || gnss.fix === "2d")
    readonly property var position: hasFix ? QtPositioning.coordinate(gnss.lat, gnss.lon) : null
    property bool _programmatic: false

    clip: true

    Plugin {
        id: osm
        name: "osm"
        PluginParameter { name: "osm.useragent"; value: root.cfg.user_agent || "AALU-dashboard" }
        PluginParameter { name: "osm.mapping.custom.host"; value: root.cfg.tile_url || "https://tile.openstreetmap.org/" }
        PluginParameter { name: "osm.mapping.providersrepository.disabled"; value: true }
        PluginParameter { name: "osm.mapping.cache.directory"; value: root.cfg.cache_dir || "" }
        PluginParameter { name: "osm.mapping.cache.disk.size"; value: (root.cfg.cache_size_mb || 500) * 1024 * 1024 }
        PluginParameter { name: "osm.mapping.offline.directory"; value: root.cfg.offline_dir || "" }
    }

    MapView {
        id: view
        anchors.fill: parent
        map.plugin: osm
        map.zoomLevel: 16
        map.center: QtPositioning.coordinate(46.0679, 11.1211)
        map.copyrightsVisible: false   // own attribution label below
        Component.onCompleted: {
            // "Custom URL Map" is the last type exposed by the osm plugin.
            map.activeMapType = map.supportedMapTypes[map.supportedMapTypes.length - 1]
            map.addMapItem(track)
            map.addMapItem(vehicle)
        }

        Connections {
            target: view.map
            function onCenterChanged() { if (!root._programmatic) root.follow = false }
        }

        MapPolyline {
            id: track
            line.width: 6
            line.color: Qt.alpha(Theme.accent, 0.55)
        }

        MapQuickItem {
            id: vehicle
            visible: root.hasFix
            coordinate: root.position || QtPositioning.coordinate()
            anchorPoint.x: marker.width / 2
            anchorPoint.y: marker.height / 2
            sourceItem: Rectangle {
                id: marker
                width: 46; height: 46; radius: 23
                color: Qt.alpha(Theme.accent, 0.25)
                border.color: "white"; border.width: 3
                Icon {
                    anchors.centerIn: parent
                    width: 30; height: 30
                    name: "nav"
                    color: Theme.accent
                    rotation: root.gnss.heading_deg || 0
                }
            }
        }
    }

    function recenter() {
        if (!root.position) return
        root._programmatic = true
        view.map.center = root.position
        root._programmatic = false
    }

    onPositionChanged: {
        if (!root.position) return
        track.addCoordinate(root.position)
        if (track.pathLength() > root.trackLength) track.removeCoordinate(0)
        if (root.follow) recenter()
    }
    onFollowChanged: if (follow) recenter()

    // Night: dim the (light) raster tiles instead of blinding the driver.
    Rectangle {
        anchors.fill: parent
        color: "black"
        opacity: Theme.night ? 0.35 : 0
        enabled: false
    }

    // --- overlays ------------------------------------------------------------
    Rectangle {
        visible: !root.hasFix
        anchors { top: parent.top; horizontalCenter: parent.horizontalCenter; topMargin: Theme.gap }
        radius: height / 2
        height: 40; width: noFix.implicitWidth + 32
        color: Qt.alpha(Theme.surface, 0.92)
        border.color: Theme.warn
        Text {
            id: noFix
            anchors.centerIn: parent
            text: root.gnss.quality === "disconnected" ? "GPS not connected" : "Searching for satellites…"
            color: Theme.warn; font.pixelSize: Theme.fontS; font.bold: true
        }
    }

    Column {
        anchors { right: parent.right; bottom: parent.bottom; margins: Theme.gap }
        spacing: Theme.gap
        MapButton { label: "+"; onClicked: view.map.zoomLevel = Math.min(19, view.map.zoomLevel + 1) }
        MapButton { label: "−"; onClicked: view.map.zoomLevel = Math.max(3, view.map.zoomLevel - 1) }
        MapButton {
            icon: "nav"
            highlighted: root.follow
            visible: root.hasFix
            onClicked: root.follow = true
        }
    }

    Text {
        anchors { left: parent.left; bottom: parent.bottom; margins: 4 }
        text: root.cfg.attribution || "© OpenStreetMap contributors"
        color: "#333"
        font.pixelSize: 11
        Rectangle { anchors.fill: parent; anchors.margins: -2; color: "#ccffffff"; z: -1 }
    }

    component MapButton: Rectangle {
        property string label
        property string icon
        property bool highlighted: false
        signal clicked()
        width: Theme.touchMin; height: Theme.touchMin; radius: Theme.radius
        color: highlighted ? Theme.accent : Qt.alpha(Theme.surface, 0.92)
        border.color: Theme.border
        Text {
            visible: parent.label !== ""
            anchors.centerIn: parent
            text: parent.label
            color: Theme.text; font.pixelSize: 32; font.bold: true
        }
        Icon {
            visible: parent.icon !== ""
            anchors.centerIn: parent
            width: 30; height: 30
            name: parent.icon
            color: parent.highlighted ? Theme.bg : Theme.text
        }
        MouseArea { anchors.fill: parent; onClicked: { Backend.userActivity(); parent.clicked() } }
    }
}
