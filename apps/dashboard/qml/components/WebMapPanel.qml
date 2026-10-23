import QtQuick
import QtWebEngine
import "../js/Fmt.js" as Fmt

// Offline vector map (MapLibre GL in a web view, tiles from the local map server).
// Same role as MapPanel: follows the vehicle, shows the route, destination and GPX.
// A long press on the map reports the point (pointPicked) to choose start/destination.
Item {
    id: root
    property bool follow: true
    signal pointPicked(real lat, real lon)

    readonly property var gnss: Vehicle.gnss || ({})
    readonly property bool hasFix: Fmt.isLive(gnss.quality) && (gnss.fix === "3d" || gnss.fix === "2d")
    readonly property var nav: Vehicle.navigation || ({})
    readonly property var destination: nav.route && nav.route.destination ? nav.route.destination : null
    readonly property var routePath: Vehicle.navigationPath || []
    readonly property var gpxOverlay: Vehicle.gpxOverlay || null
    property bool ready: false
    property var trackPoints: []

    function js(code) { if (ready) web.runJavaScript(code) }
    function num(v) { return v == null || isNaN(v) ? "null" : Number(v).toFixed(7) }

    function pushVehicle() {
        if (!hasFix) { js("aalu.setVehicle(null)"); return }
        js("aalu.setVehicle(" + num(gnss.lat) + "," + num(gnss.lon) + "," + num(gnss.heading_deg || 0)
           + "," + (follow ? "true" : "false") + ")")
    }
    function pushRoute() {
        // Consecutive points with the same kind (road / offroad) become one line feature.
        var features = [], current = null
        for (var i = 0; i < routePath.length; i++) {
            var p = routePath[i], kind = p.kind || "road"
            if (!current || current.properties.kind !== kind) {
                var coords = current ? [current.geometry.coordinates[current.geometry.coordinates.length - 1]] : []
                current = { type: "Feature", properties: { kind: kind },
                            geometry: { type: "LineString", coordinates: coords } }
                features.push(current)
            }
            current.geometry.coordinates.push([p.lon, p.lat])
        }
        js("aalu.setLayer('route'," + JSON.stringify({ type: "FeatureCollection", features: features }) + ")")
        if (routePath.length > 1) {
            var x0 = 180, y0 = 90, x1 = -180, y1 = -90
            for (var j = 0; j < routePath.length; j++) {
                x0 = Math.min(x0, routePath[j].lon); x1 = Math.max(x1, routePath[j].lon)
                y0 = Math.min(y0, routePath[j].lat); y1 = Math.max(y1, routePath[j].lat)
            }
            root.follow = false
            js("aalu.fit(" + [x0, y0, x1, y1].join(",") + ")")
            overviewTimer.restart()
        }
    }
    function pushDestination() {
        js(destination ? "aalu.setDestination(" + num(destination.lat) + "," + num(destination.lon) + ")"
                       : "aalu.setDestination(null)")
    }
    function pushGpx() { js("aalu.setLayer('gpx'," + JSON.stringify(gpxOverlay || { type: "FeatureCollection", features: [] }) + ")") }
    function pushAll() { pushVehicle(); pushRoute(); pushDestination(); pushGpx() }

    onGnssChanged: {
        pushVehicle()
        if (hasFix) {
            trackPoints.push([gnss.lon, gnss.lat])
            if (trackPoints.length > 600) trackPoints.shift()
            if (trackPoints.length > 1)
                js("aalu.setLayer('track'," + JSON.stringify({ type: "Feature", properties: {},
                   geometry: { type: "LineString", coordinates: trackPoints } }) + ")")
        }
    }
    onRoutePathChanged: pushRoute()
    onDestinationChanged: pushDestination()
    onGpxOverlayChanged: pushGpx()
    onFollowChanged: if (follow && hasFix) js("aalu.recenter(" + num(gnss.lat) + "," + num(gnss.lon) + ",16)")
    Connections { target: Theme; function onNightChanged() { root.js("aalu.setNight(" + Theme.night + ")") } }

    // After showing a new route whole, go back to following the car — only when navigating;
    // a planned route (preview) stays in overview.
    Timer { id: overviewTimer; interval: 6000; onTriggered: if (root.nav.route && root.nav.route.state === "active") root.follow = true }

    WebEngineView {
        id: web
        anchors.fill: parent
        url: Backend.mapUrl
        backgroundColor: Theme.bg
        settings.showScrollBars: false
        settings.focusOnNavigationEnabled: false
        onJavaScriptConsoleMessage: (level, message, line, source) => {
            if (message.indexOf("AALU:") !== 0) {
                // Missing POI icons are replaced by a blank image: not worth a warning.
                if (level >= WebEngineView.WarningMessageLevel && message.indexOf("could not be loaded") < 0)
                    console.warn("map:", message)
                return
            }
            var ev = JSON.parse(message.substring(5))
            if (ev.type === "loaded") {
                web.runJavaScript("aalu.init(" + JSON.stringify({
                    night: Theme.night, lang: "en", osmFallback: Backend.mapOnlineFallback,
                    lat: root.hasFix ? root.gnss.lat : 46.0679, lon: root.hasFix ? root.gnss.lon : 11.1211,
                    zoom: 15 }) + ")")
            } else if (ev.type === "ready") {
                root.ready = true
                root.pushAll()
            } else if (ev.type === "userPan") {
                root.follow = false
            } else if (ev.type === "longPress") {
                root.pointPicked(ev.lat, ev.lon)
            } else if (ev.type === "error") {
                console.warn("map error:", ev.message)
            }
        }
        onRenderProcessTerminated: (status, code) => {
            // The map must never take the dashboard down: reload it.
            console.warn("map renderer stopped (" + status + "), reloading")
            root.ready = false
            reloadTimer.start()
        }
        Timer { id: reloadTimer; interval: 2000; onTriggered: web.reload() }
    }

    // --- overlays (same as MapPanel) ----------------------------------------
    Rectangle {
        visible: !root.hasFix
        anchors { top: parent.top; horizontalCenter: parent.horizontalCenter; topMargin: 84 }
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
        anchors { right: parent.right; bottom: parent.bottom; margins: Theme.gap; bottomMargin: 28 }
        spacing: Theme.gap
        MapButton { label: "+"; onClicked: root.js("aalu.zoomBy(1)") }
        MapButton { label: "−"; onClicked: root.js("aalu.zoomBy(-1)") }
        MapButton { icon: "nav"; highlighted: root.follow; visible: root.hasFix; onClicked: root.follow = true }
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
