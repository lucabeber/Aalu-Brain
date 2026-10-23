import QtQuick
import QtQuick.Layouts
import "../js/Fmt.js" as Fmt

// Top bar shared by both dashboards: mode, connection states, clock.
Rectangle {
    id: root
    property string title
    implicitHeight: 52
    color: Theme.surface
    border.color: Theme.border

    readonly property var gnss: Vehicle.gnss || ({})
    readonly property var battery: Vehicle.house_battery || ({})
    readonly property var media: Vehicle.media || ({})
    readonly property var sys: Vehicle.system || ({})
    readonly property bool compact: width < 820   // narrow/portrait: drop secondary items

    function clockText() {
        var d = new Date()
        // Without RTC battery/NTP the Pi may boot at 1970: show nothing rather than a wrong time.
        return d.getFullYear() < 2024 ? "--:--" : Qt.formatTime(d, "HH:mm")
    }

    RowLayout {
        anchors { fill: parent; leftMargin: Theme.gap; rightMargin: Theme.gap }
        spacing: Theme.gap * 1.5

        Rectangle {
            radius: 8
            color: Vehicle.mode === "fault" ? Theme.crit : Theme.surface2
            Layout.preferredHeight: 34
            Layout.preferredWidth: modeText.implicitWidth + 20
            Text {
                id: modeText
                anchors.centerIn: parent
                text: Fmt.modeLabel(Vehicle.mode)
                color: Theme.text
                font.pixelSize: Theme.fontS
                font.bold: true
            }
        }
        Text { text: root.title; visible: !root.compact; color: Theme.textDim; font.pixelSize: Theme.fontS }

        Item { Layout.fillWidth: true }

        Rectangle {
            visible: Vehicle.simulated === true
            radius: 8
            color: Qt.alpha(Theme.sim, 0.2)
            border.color: Theme.sim
            Layout.preferredHeight: 30
            Layout.preferredWidth: simText.implicitWidth + 18
            Text {
                id: simText
                anchors.centerIn: parent
                text: root.compact ? "SIM" : "SIMULATED DATA"
                color: Theme.sim
                font.pixelSize: 13
                font.bold: true
            }
        }
        StatusIndicator {
            label: root.gnss.fix === "3d" || root.gnss.fix === "2d"
                   ? "GPS " + Fmt.num(root.gnss.satellites) + " sat"
                   : root.gnss.quality === "disconnected" ? "GPS —" : "GPS searching"
            quality: root.gnss.fix === "no_fix" && Fmt.isLive(root.gnss.quality)
                     ? "stale" : (root.gnss.quality || "disconnected")
        }
        StatusIndicator {
            label: Fmt.num(root.battery.voltage_v, 1) + " V"
            quality: root.battery.quality || "disconnected"
        }
        StatusIndicator {
            label: root.media.link === "connected" ? "BT" : "BT —"
            quality: root.media.link === "connected" ? root.media.quality : "disconnected"
        }
        StatusIndicator {
            visible: !root.compact
            // Video service arrives in phase 6; until then recording is honestly "not available".
            label: "REC —"
            quality: "disconnected"
        }
        StatusIndicator {
            label: Fmt.num(root.sys.cpu_temp_c) + "°C"
            tint: root.sys.cpu_temp_c > 80 ? Theme.crit
                  : root.sys.cpu_temp_c > 70 ? Theme.warn
                  : Theme.qualityColor(root.sys.quality || "disconnected")
        }
        Text {
            id: clock
            text: root.clockText()
            color: Theme.text
            font.pixelSize: Theme.fontM
            font.bold: true
            Timer { interval: 5000; running: true; repeat: true; onTriggered: clock.text = root.clockText() }
        }
        Rectangle {
            Layout.preferredWidth: 44; Layout.preferredHeight: 44
            radius: 22
            color: themeArea.pressed ? Theme.surface2 : "transparent"
            Icon { anchors.centerIn: parent; name: "theme"; width: 26; height: 26; color: Theme.textDim }
            MouseArea {
                id: themeArea
                anchors.fill: parent
                onClicked: Backend.nightMode = !Backend.nightMode
            }
        }
    }
}
