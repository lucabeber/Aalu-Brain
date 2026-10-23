import QtQuick

// Turn arrow for a maneuver kind (left, slight_right, roundabout, offroad, ...).
Canvas {
    id: c
    property string kind: "straight"
    property color color: Theme.text
    implicitWidth: 64; implicitHeight: 64
    onKindChanged: requestPaint()
    onColorChanged: requestPaint()

    readonly property var angles: ({ straight: 0, start: 0, merge: 0, slight_right: 40, right: 90,
                                     sharp_right: 135, slight_left: -40, left: -90, sharp_left: -135 })

    onPaint: {
        var g = getContext("2d"), w = width, h = height
        g.reset()
        g.strokeStyle = color; g.fillStyle = color
        g.lineWidth = w * 0.11; g.lineCap = "round"; g.lineJoin = "round"
        function head(x, y, ang) {   // arrow head at (x, y) pointing to angle (radians, 0 = up)
            var s = w * 0.17
            g.save(); g.translate(x, y); g.rotate(ang)
            g.beginPath(); g.moveTo(0, -s); g.lineTo(s * 0.9, s * 0.4); g.lineTo(-s * 0.9, s * 0.4)
            g.closePath(); g.fill(); g.restore()
        }
        if (kind === "destination") {
            g.beginPath(); g.arc(w * .5, h * .38, w * .24, Math.PI, 0); g.lineTo(w * .5, h * .9); g.closePath(); g.fill()
            return
        }
        if (kind === "uturn") {
            g.beginPath(); g.moveTo(w * .66, h * .88); g.lineTo(w * .66, h * .4)
            g.arc(w * .48, h * .4, w * .18, 0, Math.PI, true); g.lineTo(w * .3, h * .62); g.stroke()
            head(w * .3, h * .7, Math.PI)
            return
        }
        if (kind === "roundabout") {
            g.beginPath(); g.arc(w * .5, h * .45, w * .2, 0, 2 * Math.PI); g.stroke()
            g.beginPath(); g.moveTo(w * .5, h * .92); g.lineTo(w * .5, h * .65); g.stroke()
            g.beginPath(); g.moveTo(w * .68, h * .36); g.lineTo(w * .86, h * .2); g.stroke()
            head(w * .88, h * .18, Math.PI / 4)
            return
        }
        if (kind === "offroad") {
            g.setLineDash([w * .1, w * .09])
            g.beginPath(); g.moveTo(w * .3, h * .9)
            g.bezierCurveTo(w * .2, h * .6, w * .8, h * .55, w * .6, h * .22); g.stroke()
            g.setLineDash([])
            head(w * .58, h * .16, -0.3)
            return
        }
        // Generic turn: stem up from the bottom, then a branch at the turn angle.
        var a = (angles[kind] !== undefined ? angles[kind] : 0) * Math.PI / 180
        var x0 = w * .5, y0 = h * .92, x1 = w * .5, y1 = h * .5
        var len = w * .3
        var x2 = x1 + Math.sin(a) * len, y2 = y1 - Math.cos(a) * len
        g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.lineTo(x2, y2); g.stroke()
        head(x2 + Math.sin(a) * w * .04, y2 - Math.cos(a) * w * .04, a)
    }
}
