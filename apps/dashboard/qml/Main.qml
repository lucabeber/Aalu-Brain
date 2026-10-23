import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import "components"
import "screens"

// One top-level window per touchscreen, created by main.py with
// screenName = "drive", "camper" or "single" (one screen: both views, switchable).
Window {
    id: win
    required property string screenName
    property string camperPage: "energy"
    title: screenName === "camper" ? "AALU Camper" : "AALU"
    color: Theme.bg
    visible: false   // shown by main.py after the screen is assigned

    property string view: screenName === "camper" ? "camper" : "drive"

    Binding { target: Theme; property: "night"; value: Backend.nightMode }

    // Logical canvas: layouts reflow down to a minimum logical size; smaller panels
    // (e.g. 800x480) get the same layout scaled down instead of overflowing.
    Item {
        id: canvas
        readonly property bool portrait: win.height > win.width
        readonly property real minW: portrait ? 680 : 1100
        readonly property real minH: portrait ? 1100 : 680
        readonly property real s: Math.min(1, win.width / minW, win.height / minH)
        width: win.width / s
        height: win.height / s
        scale: s
        transformOrigin: Item.TopLeft

        // Both views stay alive in single-screen mode, so the map keeps its position
        // and the camper view its page while switching.
        StackLayout {
            anchors.fill: parent
            currentIndex: win.view === "camper" ? 1 : 0

            Loader {
                active: win.screenName !== "camper"
                sourceComponent: Component {
                    Drive {
                        canSwitchView: win.screenName === "single"
                        onSwitchView: win.view = "camper"
                    }
                }
            }
            Loader {
                active: win.screenName !== "drive"
                sourceComponent: Component {
                    Camper {
                        initialPage: win.camperPage
                        canSwitchView: win.screenName === "single"
                        onSwitchView: win.view = "drive"
                    }
                }
            }
        }
    }

    // On-screen keyboard (touchscreen without keyboard). Outside the scaled canvas so it
    // always spans the real screen width.
    Loader {
        active: Backend.virtualKeyboard
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; top: parent.top }
        z: 100
        source: "components/KeyboardPanel.qml"
    }

    // Any touch counts as activity (idle timeout / wake from STANDBY).
    TapHandler { onTapped: Backend.userActivity(); gesturePolicy: TapHandler.DragThreshold }
    Shortcut { sequence: "Ctrl+Q"; onActivated: Qt.quit() }
    Shortcut { sequence: "F11"; onActivated: win.visibility === Window.FullScreen ? win.showNormal() : win.showFullScreen() }
}
