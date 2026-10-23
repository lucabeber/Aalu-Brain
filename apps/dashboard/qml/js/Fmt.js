.pragma library

var DASH = "—"

function isLive(q) { return q === "valid" || q === "simulated" }

// Number with fixed decimals, or a dash when unknown. Never shows a stale 0.
function num(v, decimals) {
    if (v == null || isNaN(v)) return DASH
    return Number(v).toFixed(decimals === undefined ? 0 : decimals)
}

function signed(v, decimals) {
    if (v == null || isNaN(v)) return DASH
    var s = Number(v).toFixed(decimals === undefined ? 0 : decimals)
    return v > 0 ? "+" + s : s
}

// Watts above 1 kW as kW with one decimal.
function power(w) {
    if (w == null || isNaN(w)) return DASH
    return Math.abs(w) >= 1000 ? (w / 1000).toFixed(1) + " kW" : Math.round(w) + " W"
}

function mmss(ms) {
    if (ms == null) return "--:--"
    var t = Math.floor(ms / 1000)
    var m = Math.floor(t / 60), s = t % 60
    return m + ":" + (s < 10 ? "0" : "") + s
}

// 125 -> "2 h 05 min", 3000 -> "2 d 2 h"
function duration(min) {
    if (min == null || isNaN(min)) return DASH
    min = Math.round(min)
    if (min >= 2880) return Math.floor(min / 1440) + " d " + Math.floor((min % 1440) / 60) + " h"
    var h = Math.floor(min / 60), m = min % 60
    return h > 0 ? h + " h " + (m < 10 ? "0" : "") + m + " min" : m + " min"
}

// One-line summary of the battery state for the energy views.
function energyStatus(e) {
    if (!e) return DASH
    switch (e.state) {
    case "charging": return "Full in " + duration(e.minutes)
    case "discharging": return "Reserve (" + num(e.reserve_soc_pct) + " %) in " + duration(e.minutes)
    case "balanced": return "Balanced"
    case "full": return "Full"
    default: return "No battery data"
    }
}

function qualityLabel(q) {
    switch (q) {
    case "valid": return ""
    case "simulated": return ""
    case "stale": return "STALE"
    case "error": return "ERROR"
    default: return "NO DATA"
    }
}

function modeLabel(m) {
    return { drive: "DRIVE", camp: "CAMP", standby: "STANDBY",
             shutdown: "SHUTDOWN", fault: "FAULT" }[m] || DASH
}
