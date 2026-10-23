import QtQuick
import QtQuick.Layouts
import "../js/Fmt.js" as Fmt

// Persistent Bluetooth player. Disabled (not hidden) when no phone is connected.
Card {
    id: root
    title: "Music"
    info: Vehicle.media || ({})

    readonly property bool connected: info.link === "connected" && Fmt.isLive(info.quality)
    readonly property bool playing: connected && info.status === "playing"
    property bool showDetails: true    // device line and volume buttons

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        Text {
            Layout.fillWidth: true
            text: root.connected ? (root.info.title || "Unknown title")
                                 : "No phone connected"
            color: root.connected ? Theme.text : Theme.textDim
            font.pixelSize: Theme.fontM
            font.bold: root.connected
            elide: Text.ElideRight
        }
        Text {
            Layout.fillWidth: true
            visible: root.connected
            text: root.info.artist || ""
            color: Theme.textDim
            font.pixelSize: Theme.fontS
            elide: Text.ElideRight
        }
        Text {
            Layout.fillWidth: true
            visible: root.connected && root.showDetails && !!root.info.album
            text: root.info.album || ""
            color: Theme.textDim
            font.pixelSize: Theme.fontS
            elide: Text.ElideRight
        }
        RowLayout {
            Layout.fillWidth: true
            visible: root.connected && root.info.duration_ms > 0
            Text { text: Fmt.mmss(root.info.position_ms); color: Theme.textDim; font.pixelSize: 13 }
            LevelBar {
                Layout.fillWidth: true
                implicitHeight: 6
                value: root.info.duration_ms > 0 ? 100 * root.info.position_ms / root.info.duration_ms : null
            }
            Text { text: Fmt.mmss(root.info.duration_ms); color: Theme.textDim; font.pixelSize: 13 }
        }
        Item { Layout.fillHeight: true }
        Text {
            Layout.fillWidth: true
            visible: root.showDetails
            text: root.connected ? "Bluetooth · " + (root.info.device_name || "phone")
                                 : "Pair the phone from Bluetooth settings"
            color: Theme.textDim
            font.pixelSize: 13
            elide: Text.ElideRight
        }
        RowLayout {
            Layout.fillWidth: true
            visible: root.showDetails
            spacing: Theme.gap
            readonly property var out: Vehicle.audio_output || ({})
            readonly property bool live: Fmt.isLive(out.quality)
            TouchButton {
                Layout.fillWidth: true; text: "−"; active: parent.live
                onClicked: Backend.setVolume(Math.max(0, (parent.out.volume_pct || 0) - 5))
            }
            Text {
                text: parent.out.muted ? "Muted" : "Vol " + Fmt.num(parent.out.volume_pct)
                color: Theme.text; font.pixelSize: Theme.fontM
                horizontalAlignment: Text.AlignHCenter
                Layout.preferredWidth: 90
            }
            TouchButton {
                Layout.fillWidth: true; text: "+"; active: parent.live
                onClicked: Backend.setVolume(Math.min(100, (parent.out.volume_pct || 0) + 5))
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.gap
            TouchButton { Layout.fillWidth: true; icon: "prev"; active: root.connected; onClicked: Backend.mediaPrevious() }
            TouchButton {
                Layout.fillWidth: true
                icon: root.playing ? "pause" : "play"
                highlighted: root.connected
                active: root.connected
                onClicked: root.playing ? Backend.mediaPause() : Backend.mediaPlay()
            }
            TouchButton { Layout.fillWidth: true; icon: "next"; active: root.connected; onClicked: Backend.mediaNext() }
        }
    }
}
