import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"
import "../js/Fmt.js" as Fmt

// Camper home (roadmap §11) and service pages. Page selection is independent
// from the drive view.
Rectangle {
    id: root
    color: Theme.bg

    property bool canSwitchView: false
    signal switchView()

    readonly property bool portrait: height > width
    readonly property var energy: Vehicle.energy || ({})
    readonly property var fresh: Vehicle.fresh_water || ({})
    readonly property var grey: Vehicle.grey_water || ({})
    readonly property var audio: Vehicle.audio_output || ({})
    readonly property var loads: Vehicle.loadsView || ({ outputs: {} })
    readonly property bool locked: Vehicle.driveLocked === true

    readonly property var pages: [
        { key: "energy", label: "Energy" },
        { key: "water", label: "Water" },
        { key: "lights", label: "Lights" },
        { key: "audio", label: "Audio" },
        { key: "dashcam", label: "Dashcam" },
        { key: "alarms", label: "Alarms" },
        { key: "diag", label: "Diagnostics" },
        { key: "sim", label: "Simulation" },
    ]
    property string initialPage: "energy"
    property int current: Math.max(0, pages.findIndex(p => p.key === initialPage))

    function loadState(name) { return root.loads.outputs ? root.loads.outputs[name] : null }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        StatusBar { Layout.fillWidth: true; title: "Camper" }

        GridLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            rows: root.portrait ? 2 : 1
            columns: root.portrait ? 1 : 2
            rowSpacing: 0
            columnSpacing: 0

            // --- page rail (left, or bottom on portrait screens) ----------------
            Rectangle {
                Layout.row: root.portrait ? 1 : 0
                Layout.column: 0
                Layout.fillHeight: !root.portrait
                Layout.fillWidth: root.portrait
                Layout.preferredWidth: root.portrait ? -1 : 170
                Layout.preferredHeight: root.portrait ? 84 : -1
                color: Theme.surface
                GridLayout {
                    anchors { fill: parent; margins: 8 }
                    rows: root.portrait ? 1 : -1
                    columns: root.portrait ? -1 : 1
                    rowSpacing: 6
                    columnSpacing: 6
                    TouchButton {
                        visible: root.canSwitchView
                        Layout.fillWidth: true
                        Layout.fillHeight: !root.portrait
                        Layout.minimumHeight: 48
                        Layout.maximumHeight: Theme.touchMin
                        text: "Drive"
                        icon: "car"
                        onClicked: root.switchView()
                    }
                    Repeater {
                        model: root.pages
                        delegate: TouchButton {
                            required property int index
                            required property var modelData
                            Layout.fillWidth: true
                            // Shrink to fit short screens instead of overflowing the rail.
                            Layout.fillHeight: !root.portrait
                            Layout.minimumHeight: 48
                            Layout.maximumHeight: Theme.touchMin
                            visible: modelData.key !== "sim" || Vehicle.simulated === true
                            text: modelData.label + (modelData.key === "alarms" && (Vehicle.alarms || []).length
                                                     ? " (" + Vehicle.alarms.length + ")" : "")
                            highlighted: root.current === index
                            onClicked: root.current = index
                        }
                    }
                    Item { Layout.fillHeight: !root.portrait; Layout.fillWidth: root.portrait }
                }
            }

            StackLayout {
                Layout.row: 0
                Layout.column: root.portrait ? 0 : 1
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: Theme.gap
                currentIndex: root.current

                // --- energy ----------------------------------------------------
                GridLayout {
                    columns: width > 900 ? 2 : 1
                    rowSpacing: Theme.gap
                    columnSpacing: Theme.gap

                    Card {
                        title: "House battery"
                        info: root.energy
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        ColumnLayout {
                            anchors.fill: parent
                            spacing: Theme.gap
                            RowLayout {
                                Layout.fillWidth: true
                                MetricTile {
                                    label: "State of charge"
                                    value: Fmt.num(root.energy.soc_pct)
                                    unit: "%"
                                    valueSize: 80
                                    valueColor: root.energy.soc_pct != null && root.energy.soc_pct <= 20 ? Theme.crit : Theme.text
                                }
                                Item { Layout.fillWidth: true }
                                MetricTile { label: "Voltage"; value: Fmt.num(root.energy.voltage_v, 2); unit: "V" }
                            }
                            LevelBar { Layout.fillWidth: true; implicitHeight: 26; value: root.energy.soc_pct; tint: Theme.ok; warnBelow: 20 }
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: statusCol.implicitHeight + 2 * Theme.gap
                                radius: Theme.radius
                                color: Qt.alpha(root.energy.state === "discharging" ? Theme.warn
                                                : root.energy.state === "charging" ? Theme.ok : Theme.info, 0.15)
                                ColumnLayout {
                                    id: statusCol
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: Theme.gap }
                                    spacing: 2
                                    Text {
                                        text: root.energy.state === "charging" ? "Charging"
                                            : root.energy.state === "discharging" ? "Discharging"
                                            : root.energy.state === "balanced" ? "Balanced"
                                            : root.energy.state === "full" ? "Full" : "No battery data"
                                        color: Theme.text; font.pixelSize: Theme.fontM; font.bold: true
                                    }
                                    Text {
                                        visible: root.energy.minutes != null
                                        Layout.fillWidth: true
                                        wrapMode: Text.Wrap
                                        text: root.energy.state === "charging"
                                              ? "Full in about " + Fmt.duration(root.energy.minutes)
                                              : "Down to " + Fmt.num(root.energy.reserve_soc_pct) + " % in about "
                                                + Fmt.duration(root.energy.minutes)
                                        color: Theme.text; font.pixelSize: Theme.fontL; font.bold: true
                                    }
                                    Text {
                                        visible: root.energy.minutes != null
                                        text: "Estimate from the average net current of the last minute"
                                        color: Theme.textDim; font.pixelSize: 13
                                    }
                                }
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }

                    Card {
                        title: "Charging and consumption"
                        info: root.energy
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        GridLayout {
                            anchors { left: parent.left; right: parent.right; top: parent.top }
                            columns: 2
                            rowSpacing: Theme.gap
                            columnSpacing: Theme.gap
                            FlowTile {
                                Layout.fillWidth: true; big: true
                                label: "Solar panels"; watts: root.energy.solar_w; amps: root.energy.solar_a
                                note: root.energy.solar_w != null && root.energy.solar_w < 5 ? "no sun" : ""
                            }
                            FlowTile {
                                Layout.fillWidth: true; big: true
                                label: "Engine (alternator)"; watts: root.energy.engine_w; amps: root.energy.engine_a
                                note: root.energy.engine_state === "off" ? "engine off" : ""
                            }
                            FlowTile {
                                Layout.fillWidth: true; big: true
                                label: "Consumption"; watts: root.energy.consumption_w
                                amps: root.energy.consumption_a; outgoing: true
                            }
                            FlowTile {
                                Layout.fillWidth: true; big: true
                                label: "Net into battery"; watts: root.energy.net_w; amps: root.energy.net_a
                            }
                            Text {
                                Layout.columnSpan: 2
                                Layout.fillWidth: true
                                text: "Solar + Engine − Consumption = Net"
                                color: Theme.textDim; font.pixelSize: Theme.fontS
                                horizontalAlignment: Text.AlignHCenter
                            }
                            AlarmList {
                                Layout.columnSpan: 2
                                Layout.fillWidth: true
                                maxItems: 2
                                showEmpty: false
                            }
                        }
                    }
                }

                // --- water -----------------------------------------------------
                ColumnLayout {
                    spacing: Theme.gap
                    Repeater {
                        model: [
                            { label: "Fresh water", d: root.fresh, tint: Theme.accent, warn: 15 },
                            { label: "Grey water", d: root.grey, tint: Theme.info, warn: -1 },
                        ]
                        delegate: Card {
                            required property var modelData
                            title: modelData.label
                            info: modelData.d
                            Layout.fillWidth: true
                            Layout.preferredHeight: 140
                            ColumnLayout {
                                anchors.fill: parent
                                MetricTile {
                                    label: modelData.d.capacity_l != null && modelData.d.level_pct != null
                                           ? "about " + Fmt.num(modelData.d.capacity_l * modelData.d.level_pct / 100) + " l"
                                           : "Level"
                                    value: Fmt.num(modelData.d.level_pct)
                                    unit: "%"
                                }
                                LevelBar { Layout.fillWidth: true; value: modelData.d.level_pct; tint: modelData.tint; warnBelow: modelData.warn }
                            }
                        }
                    }
                    ToggleTile {
                        Layout.fillWidth: true
                        label: "Water pump"
                        load: root.loadState("water_pump")
                        available: root.loads.available === true
                        onToggled: (on) => Backend.setLoad("water_pump", on)
                    }
                    Item { Layout.fillHeight: true }
                }

                // --- lights ----------------------------------------------------
                ColumnLayout {
                    spacing: Theme.gap
                    Text {
                        visible: root.loads.available !== true
                        text: "Load control unavailable: I/O controller not connected. Use the manual switches."
                        color: Theme.warn
                        font.pixelSize: Theme.fontS
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        rowSpacing: Theme.gap
                        columnSpacing: Theme.gap
                        Repeater {
                            model: [
                                { key: "light_living", label: "Living area" },
                                { key: "light_kitchen", label: "Kitchen" },
                                { key: "light_awning", label: "Awning" },
                            ]
                            delegate: ToggleTile {
                                required property var modelData
                                Layout.fillWidth: true
                                label: modelData.label
                                load: root.loadState(modelData.key)
                                available: root.loads.available === true
                                onToggled: (on) => Backend.setLoad(modelData.key, on)
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }

                // --- audio -----------------------------------------------------
                ColumnLayout {
                    spacing: Theme.gap
                    MediaMiniPlayer { Layout.fillWidth: true; Layout.preferredHeight: 230; showDetails: false }
                    Card {
                        title: "Audio output"
                        info: root.audio
                        Layout.fillWidth: true
                        Layout.preferredHeight: 230
                        ColumnLayout {
                            anchors.fill: parent
                            spacing: Theme.gap
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.gap
                                Text { text: "Volume"; color: Theme.text; font.pixelSize: Theme.fontM }
                                Slider {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Theme.touchMin
                                    from: 0; to: 100; stepSize: 1
                                    enabled: Fmt.isLive(root.audio.quality)
                                    value: root.audio.volume_pct != null ? root.audio.volume_pct : 0
                                    onMoved: Backend.setVolume(value)
                                }
                                Text { text: Fmt.num(root.audio.volume_pct) + " %"; color: Theme.text; font.pixelSize: Theme.fontM; Layout.preferredWidth: 70 }
                                TouchButton {
                                    text: root.audio.muted ? "Muted" : "Mute"
                                    highlighted: root.audio.muted === true
                                    active: Fmt.isLive(root.audio.quality)
                                    onClicked: Backend.setMuted(!root.audio.muted)
                                }
                            }
                            Text {
                                text: root.locked ? "Equaliser locked while driving" : "Equaliser"
                                color: root.locked ? Theme.warn : Theme.textDim
                                font.pixelSize: Theme.fontS
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.gap
                                Repeater {
                                    model: [["flat", "Flat"], ["voice", "Voice"], ["drive", "Drive"], ["night", "Night"]]
                                    delegate: TouchButton {
                                        required property var modelData
                                        Layout.fillWidth: true
                                        text: modelData[1]
                                        highlighted: root.audio.eq_preset === modelData[0]
                                        active: !root.locked && Fmt.isLive(root.audio.quality)
                                        onClicked: Backend.setEqPreset(modelData[0])
                                    }
                                }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }

                // --- dashcam --------------------------------------------------
                ColumnLayout {
                    spacing: Theme.gap
                    readonly property var v: Vehicle.video || ({})
                    Card {
                        title: "Dashcam"
                        info: parent.v
                        Layout.fillWidth: true
                        Layout.preferredHeight: 320
                        GridLayout {
                            anchors { left: parent.left; right: parent.right; top: parent.top }
                            columns: 3
                            columnSpacing: Theme.gap * 2
                            rowSpacing: Theme.gap
                            readonly property var v: Vehicle.video || ({})
                            MetricTile {
                                label: "Recording"
                                value: parent.v.recording === true ? "Yes" : parent.v.recording === false ? "No" : Fmt.DASH
                                valueColor: parent.v.recording === true ? Theme.crit : Theme.text
                            }
                            MetricTile { label: "Kept"; value: Fmt.num(parent.v.oldest_age_h, 1); unit: "h of " + Fmt.num(parent.v.retention_h, 0) + " h" }
                            MetricTile { label: "Recordings"; value: Fmt.num(parent.v.used_gb, 1); unit: "GB" }
                            MetricTile { label: "Free space"; value: Fmt.num(parent.v.disk_free_gb); unit: "GB" }
                            MetricTile {
                                label: "Saved clips"
                                value: Fmt.num(parent.v.protected_segments)
                                unit: Fmt.num(parent.v.protected_gb, 1) + " / " + Fmt.num(parent.v.protected_max_gb) + " GB"
                            }
                            ColumnLayout {
                                spacing: Theme.gap / 2
                                readonly property var v: Vehicle.video || ({})
                                TouchButton {
                                    Layout.fillWidth: true
                                    text: "Save clip (−1 / +1 min)"
                                    icon: "rec"
                                    active: parent.v.recording === true
                                    onClicked: Backend.protectClip()
                                }
                                TouchButton {
                                    Layout.fillWidth: true
                                    text: "Save 15 min (−5 / +10 min)"
                                    icon: "rec"
                                    active: parent.v.recording === true
                                    onClicked: Backend.protectLongClip()
                                }
                                Text {
                                    visible: parent.v.protecting === true
                                    text: Fmt.saving(parent.v) + " more"
                                    color: Theme.crit
                                    font.pixelSize: Theme.fontS
                                    font.bold: true
                                }
                            }
                        }
                    }
                    Repeater {
                        model: parent.v.cameras || []
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 64
                            radius: Theme.radius
                            color: Theme.surface
                            border.color: modelData.state === "recording" ? Theme.border : Theme.warn
                            RowLayout {
                                anchors { fill: parent; margins: Theme.gap }
                                StatusIndicator {
                                    label: modelData.name + (modelData.audio ? " · video + audio" : " · video")
                                    tint: modelData.state === "recording" ? Theme.crit : Theme.warn
                                }
                                QualityBadge { simulated: modelData.simulated; quality: "valid" }
                                Item { Layout.fillWidth: true }
                                Text {
                                    text: modelData.state === "recording" ? "recording"
                                          : modelData.state + (modelData.last_error ? ": " + modelData.last_error : "")
                                    color: modelData.state === "recording" ? Theme.textDim : Theme.warn
                                    font.pixelSize: Theme.fontS
                                    elide: Text.ElideRight
                                    Layout.maximumWidth: 520
                                }
                            }
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        color: Theme.textDim
                        font.pixelSize: 13
                        text: (Vehicle.video || {}).retention_h == null
                              ? "Dashcam service not running: nothing is being recorded."
                              : "Recordings older than " + Fmt.num(Vehicle.video.retention_h) + " h are deleted automatically. "
                                + "Saved clips are kept until you delete them. The cabin microphone is recorded: tell your passengers."
                    }
                    Item { Layout.fillHeight: true }
                }

                // --- alarms ----------------------------------------------------
                ScrollView {
                    clip: true
                    AlarmList { width: parent ? parent.width : 0 }
                }

                // --- diagnostics -----------------------------------------------
                GridLayout {
                    columns: root.portrait ? 1 : 2
                    rowSpacing: Theme.gap
                    columnSpacing: Theme.gap
                    Card {
                        title: "Data sources"
                        showBadge: false
                        info: ({ quality: "valid" })
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        ListView {
                            anchors.fill: parent
                            clip: true
                            model: Vehicle.diagnostics || []
                            delegate: RowLayout {
                                required property var modelData
                                width: ListView.view.width
                                height: 40
                                StatusIndicator { label: modelData.label; quality: modelData.quality; Layout.fillWidth: true }
                                QualityBadge { quality: modelData.quality; simulated: modelData.simulated }
                                Text {
                                    text: modelData.age_s == null ? "never" : Fmt.num(modelData.age_s, 1) + " s"
                                    color: Theme.textDim; font.pixelSize: Theme.fontS
                                    Layout.preferredWidth: 70
                                    horizontalAlignment: Text.AlignRight
                                }
                            }
                        }
                    }
                    Card {
                        title: "Events"
                        showBadge: false
                        info: ({ quality: "valid" })
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        ListView {
                            anchors.fill: parent
                            clip: true
                            model: Vehicle.events || []
                            delegate: Text {
                                required property var modelData
                                width: ListView.view.width
                                text: modelData.time + "  " + modelData.text
                                color: Theme.text; font.pixelSize: Theme.fontS
                                elide: Text.ElideRight
                                height: 28
                            }
                        }
                    }
                }

                // --- simulation (only with fake adapters) ----------------------
                Flickable {
                    clip: true
                    contentHeight: simCol.implicitHeight
                    ColumnLayout {
                        id: simCol
                        width: parent.width
                        spacing: Theme.gap
                        Text {
                            text: "Fault injection for the simulated data. Not shown with real adapters."
                            color: Theme.sim
                            font.pixelSize: Theme.fontS
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            columns: root.portrait ? 1 : 2
                            rowSpacing: Theme.gap
                            columnSpacing: Theme.gap
                            Repeater {
                                model: [
                                    ["acc_on", "Ignition (ACC)"], ["engine_running", "Engine running"],
                                    ["sunny", "Sunny"], ["reverse", "Reverse gear"],
                                    ["gnss_connected", "GNSS connected"], ["gnss_fix", "GNSS fix"],
                                    ["victron_connected", "Victron connected"], ["low_soc", "Low battery"],
                                    ["phone_connected", "Phone connected"], ["mcu_connected", "I/O controller connected"],
                                ]
                                delegate: ToggleTile {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    implicitHeight: 72
                                    label: modelData[1]
                                    available: true
                                    load: ({ on: Vehicle.scenario ? Vehicle.scenario[modelData[0]] : null, pending: false })
                                    onToggled: (on) => Backend.setScenario(modelData[0], on)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
