import QtQuick

// Small vector icons drawn with Canvas (no icon-font dependency on the Pi).
Canvas {
    id: c
    property string name: "play"
    property color color: Theme.text
    implicitWidth: 28; implicitHeight: 28
    onNameChanged: requestPaint()
    onColorChanged: requestPaint()

    onPaint: {
        var g = getContext("2d"), w = width, h = height
        g.reset()
        g.fillStyle = color; g.strokeStyle = color
        g.lineWidth = Math.max(2, w / 12); g.lineCap = "round"; g.lineJoin = "round"
        function tri(x0, x1) { g.beginPath(); g.moveTo(x0, h*.2); g.lineTo(x1, h*.5); g.lineTo(x0, h*.8); g.closePath(); g.fill() }
        switch (name) {
        case "play": tri(w*.28, w*.8); break
        case "pause": g.fillRect(w*.25, h*.2, w*.17, h*.6); g.fillRect(w*.58, h*.2, w*.17, h*.6); break
        case "next": tri(w*.15, w*.6); g.fillRect(w*.64, h*.2, w*.12, h*.6); break
        case "prev": g.fillRect(w*.24, h*.2, w*.12, h*.6); g.beginPath(); g.moveTo(w*.85, h*.2); g.lineTo(w*.4, h*.5); g.lineTo(w*.85, h*.8); g.closePath(); g.fill(); break
        case "close": g.beginPath(); g.moveTo(w*.25, h*.25); g.lineTo(w*.75, h*.75); g.moveTo(w*.75, h*.25); g.lineTo(w*.25, h*.75); g.stroke(); break
        case "camera":
            g.strokeRect(w*.12, h*.3, w*.56, h*.42)
            g.beginPath(); g.moveTo(w*.68, h*.42); g.lineTo(w*.9, h*.3); g.lineTo(w*.9, h*.72); g.lineTo(w*.68, h*.6); g.closePath(); g.fill(); break
        case "nav":
            g.beginPath(); g.moveTo(w*.5, h*.12); g.lineTo(w*.82, h*.86); g.lineTo(w*.5, h*.68); g.lineTo(w*.18, h*.86); g.closePath(); g.fill(); break
        case "map":
            g.beginPath(); g.moveTo(w*.12, h*.25); g.lineTo(w*.38, h*.15); g.lineTo(w*.62, h*.25); g.lineTo(w*.88, h*.15)
            g.lineTo(w*.88, h*.75); g.lineTo(w*.62, h*.85); g.lineTo(w*.38, h*.75); g.lineTo(w*.12, h*.85); g.closePath(); g.stroke()
            g.beginPath(); g.moveTo(w*.38, h*.15); g.lineTo(w*.38, h*.75); g.moveTo(w*.62, h*.25); g.lineTo(w*.62, h*.85); g.stroke(); break
        case "music":
            g.beginPath(); g.arc(w*.3, h*.74, w*.13, 0, 2*Math.PI); g.fill()
            g.beginPath(); g.arc(w*.74, h*.64, w*.13, 0, 2*Math.PI); g.fill()
            g.beginPath(); g.moveTo(w*.42, h*.74); g.lineTo(w*.42, h*.2); g.lineTo(w*.86, h*.1); g.lineTo(w*.86, h*.64); g.stroke(); break
        case "battery":
            g.strokeRect(w*.12, h*.3, w*.68, h*.4); g.fillRect(w*.8, h*.42, w*.08, h*.16)
            g.fillRect(w*.18, h*.36, w*.4, h*.28); break
        case "camper":
            g.beginPath(); g.moveTo(w*.08, h*.7); g.lineTo(w*.08, h*.3); g.lineTo(w*.7, h*.3); g.lineTo(w*.92, h*.5)
            g.lineTo(w*.92, h*.7); g.closePath(); g.stroke()
            g.beginPath(); g.arc(w*.28, h*.75, w*.08, 0, 2*Math.PI); g.fill()
            g.beginPath(); g.arc(w*.72, h*.75, w*.08, 0, 2*Math.PI); g.fill()
            g.fillRect(w*.16, h*.38, w*.16, h*.14); break
        case "car":
            g.beginPath(); g.moveTo(w*.1, h*.68); g.lineTo(w*.1, h*.5); g.lineTo(w*.25, h*.3); g.lineTo(w*.75, h*.3)
            g.lineTo(w*.9, h*.5); g.lineTo(w*.9, h*.68); g.closePath(); g.stroke()
            g.beginPath(); g.arc(w*.3, h*.72, w*.08, 0, 2*Math.PI); g.fill()
            g.beginPath(); g.arc(w*.7, h*.72, w*.08, 0, 2*Math.PI); g.fill(); break
        case "rec":
            g.beginPath(); g.arc(w*.5, h*.5, w*.36, 0, 2*Math.PI); g.stroke()
            g.beginPath(); g.arc(w*.5, h*.5, w*.2, 0, 2*Math.PI); g.fill(); break
        case "search":
            g.beginPath(); g.arc(w*.42, h*.42, w*.24, 0, 2*Math.PI); g.stroke()
            g.beginPath(); g.moveTo(w*.6, h*.6); g.lineTo(w*.84, h*.84); g.stroke(); break
        case "pin":
            g.beginPath(); g.arc(w*.5, h*.38, w*.26, Math.PI, 0); g.lineTo(w*.5, h*.92); g.closePath(); g.fill()
            g.fillStyle = "white"; g.beginPath(); g.arc(w*.5, h*.38, w*.1, 0, 2*Math.PI); g.fill(); break
        case "theme":
            g.beginPath(); g.arc(w*.5, h*.5, w*.32, 0, 2*Math.PI); g.stroke()
            g.beginPath(); g.arc(w*.5, h*.5, w*.32, -Math.PI/2, Math.PI/2); g.closePath(); g.fill(); break
        }
    }
}
