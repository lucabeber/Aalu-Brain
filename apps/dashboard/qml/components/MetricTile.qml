import QtQuick

// Label + big value + unit. Pass an already formatted value (Fmt.num gives "—").
Column {
    id: root
    property string label
    property string value: "—"
    property string unit
    property int valueSize: Theme.fontL
    property color valueColor: Theme.text
    spacing: 2

    Text { text: root.label; color: Theme.textDim; font.pixelSize: Theme.fontS }
    Row {
        spacing: 6
        Text {
            id: valueText
            text: root.value
            color: root.valueColor
            font.pixelSize: root.valueSize
            font.bold: true
        }
        Text {
            text: root.unit
            visible: root.value !== "—" && root.unit !== ""
            color: Theme.textDim
            font.pixelSize: Math.max(Theme.fontS, root.valueSize * 0.45)
            anchors.baseline: valueText.baseline
        }
    }
}
