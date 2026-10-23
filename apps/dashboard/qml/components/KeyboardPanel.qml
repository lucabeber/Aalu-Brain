import QtQuick
import QtQuick.VirtualKeyboard

// On-screen keyboard for the touchscreen. Loaded only when enabled ([ui] virtual_keyboard).
InputPanel {
    id: panel
    y: active ? parent.height - height : parent.height
    Behavior on y { NumberAnimation { duration: 150 } }
}
