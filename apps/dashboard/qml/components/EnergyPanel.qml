import QtQuick
import QtQuick.Layouts
import "../js/Fmt.js" as Fmt

// Compact battery + charging summary for the drive split view. Tall panel (landscape
// side column): stacked. Wide panel (portrait bottom strip): battery left, flows right.
Card {
    id: root
    title: "Energy"
    info: Vehicle.energy || ({})
    readonly property var e: info
    readonly property bool wide: width > height * 1.6

    GridLayout {
        anchors.fill: parent
        columns: root.wide ? 2 : 1
        columnSpacing: Theme.gap * 2
        rowSpacing: Theme.gap

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            spacing: Theme.gap
            MetricTile {
                label: "Battery"
                value: Fmt.num(root.e.soc_pct)
                unit: "%"
                valueSize: 56
                valueColor: root.e.soc_pct != null && root.e.soc_pct <= 20 ? Theme.crit : Theme.text
            }
            LevelBar { Layout.fillWidth: true; value: root.e.soc_pct; tint: Theme.ok; warnBelow: 20 }
            Text {
                Layout.fillWidth: true
                text: Fmt.energyStatus(root.e)
                color: root.e.state === "discharging" ? Theme.warn : root.e.state === "charging" ? Theme.ok : Theme.textDim
                font.pixelSize: Theme.fontM
                font.bold: true
                wrapMode: Text.Wrap
            }
        }
        GridLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            columns: 2
            rowSpacing: Theme.gap / 2
            columnSpacing: Theme.gap / 2
            FlowTile { Layout.fillWidth: true; label: "Solar"; watts: root.e.solar_w; amps: root.e.solar_a }
            FlowTile {
                Layout.fillWidth: true; label: "Engine"; watts: root.e.engine_w; amps: root.e.engine_a
                note: root.e.engine_state === "off" ? "off" : ""
            }
            FlowTile { Layout.fillWidth: true; label: "Consumption"; watts: root.e.consumption_w; amps: root.e.consumption_a; outgoing: true }
            FlowTile { Layout.fillWidth: true; label: "Net"; watts: root.e.net_w; amps: root.e.net_a }
        }
        Item { Layout.fillHeight: true; visible: !root.wide }
    }
}
