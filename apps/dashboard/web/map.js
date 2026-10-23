// AALU map view: MapLibre GL with offline vector map packs (Protomaps schema).
// The dashboard (QML) calls window.aalu.*; the page reports events with
// console.log("AALU:" + JSON) which QML reads from the console stream.
import * as maplibregl from "./vendor/maplibre-gl.mjs";

const base = new URL("..", window.location.href).href;  // http://127.0.0.1:<port>/
const emit = (type, data = {}) => console.log("AALU:" + JSON.stringify({ type, ...data }));

let map = null;
let packs = [];
let night = true;
let lang = "en";
let osmFallback = true;
let vehicle = null;
let destination = null;
let programmatic = false;
const empty = { type: "FeatureCollection", features: [] };
const data = { route: empty, track: empty, gpx: empty };

function style() {
  const flavor = basemaps.namedFlavor(night ? "dark" : "light");
  const sources = {};
  const layers = [];
  if (osmFallback) {
    // Online raster under the vector packs: only visible where no pack has data.
    sources.osm = { type: "raster", tiles: [base + "osm/{z}/{x}/{y}.png"], tileSize: 256,
                    maxzoom: 19, attribution: "© OpenStreetMap contributors" };
    layers.push({ id: "osm", type: "raster", source: "osm",
                  paint: { "raster-brightness-max": night ? 0.55 : 1.0 } });
  } else {
    layers.push({ id: "bg", type: "background",
                  paint: { "background-color": night ? "#1f2124" : "#e8e6e1" } });
  }
  packs.forEach((p, i) => {
    const id = "pack" + i;
    sources[id] = { type: "vector", tiles: [base + `tiles/${p.name}/{z}/{x}/{y}.mvt`],
                    minzoom: p.minzoom, maxzoom: p.maxzoom, bounds: p.bbox,
                    attribution: "© OpenStreetMap contributors, Protomaps" };
    for (const layer of basemaps.layers(id, flavor, { lang })) {
      if (layer.type === "background") continue;  // would hide the online fallback
      layers.push({ ...layer, id: `${id}-${layer.id}` });
    }
  });
  return {
    version: 8,
    glyphs: base + "assets/fonts/{fontstack}/{range}.pbf",
    sprite: base + "assets/sprites/v4/" + (night ? "dark" : "light"),
    sources, layers,
  };
}

function addOverlays() {
  for (const name of ["gpx", "track", "route"]) {
    if (!map.getSource(name)) map.addSource(name, { type: "geojson", data: data[name] });
  }
  const add = (layer) => { if (!map.getLayer(layer.id)) map.addLayer(layer); };
  add({ id: "gpx-road", type: "line", source: "gpx", filter: ["==", ["get", "kind"], "road"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#8e5bd8", "line-width": 6, "line-opacity": 0.8 } });
  add({ id: "gpx-offroad", type: "line", source: "gpx", filter: ["==", ["get", "kind"], "offroad"],
        layout: { "line-cap": "round" },
        paint: { "line-color": "#e08a2c", "line-width": 6, "line-dasharray": [1.2, 1.2] } });
  add({ id: "track", type: "line", source: "track",
        paint: { "line-color": "#4fa3e0", "line-width": 4, "line-opacity": 0.5 } });
  add({ id: "route-casing", type: "line", source: "route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#0b3d91", "line-width": 12 } });
  add({ id: "route", type: "line", source: "route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": ["case", ["==", ["get", "kind"], "offroad"], "#e08a2c", "#3d8bfd"],
                 "line-width": 8 } });
}

// The online raster is only needed where no pack covers the view: hide it otherwise, so
// no tiles are downloaded inside the offline area.
function updateFallback() {
  if (!map || !map.getLayer("osm")) return;
  const b = map.getBounds();
  const covered = packs.some(p => b.getWest() >= p.bbox[0] && b.getSouth() >= p.bbox[1]
                                  && b.getEast() <= p.bbox[2] && b.getNorth() <= p.bbox[3]);
  map.setLayoutProperty("osm", "visibility", covered ? "none" : "visible");
}

function vehicleElement() {
  const el = document.createElement("div");
  el.className = "vehicle";
  el.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 2 L20 21 L12 16 L4 21 Z" fill="#4fa3e0"/></svg>';
  return el;
}

function pinElement() {
  const el = document.createElement("div");
  el.innerHTML = '<svg class="pin" viewBox="0 0 24 32"><path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 20 12 20s12-11 12-20C24 5.4 18.6 0 12 0z" fill="#e5534b"/><circle cx="12" cy="12" r="4.5" fill="#fff"/></svg>';
  return el;
}

function quietly(fn) { programmatic = true; try { fn(); } finally { setTimeout(() => { programmatic = false; }, 50); } }

window.aalu = {
  async init(opts) {
    night = !!opts.night; lang = opts.lang || "en"; osmFallback = opts.osmFallback !== false;
    try { packs = await (await fetch(base + "packs.json")).json(); } catch (e) { packs = []; }
    map = new maplibregl.Map({
      container: "map", style: style(), center: [opts.lon ?? 11.12, opts.lat ?? 46.07],
      zoom: opts.zoom ?? 15, attributionControl: { compact: true }, pitchWithRotate: false,
      dragRotate: false, fadeDuration: 0,
    });
    map.touchZoomRotate.disableRotation();
    map.on("load", () => { addOverlays(); updateFallback(); emit("ready", { packs: packs.map(p => p.name) }); });
    map.on("moveend", updateFallback);
    // A few POI icons are not in the sprite: use an invisible placeholder instead of warnings.
    map.on("styleimagemissing", (e) => {
      if (!map.hasImage(e.id)) map.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) });
    });
    map.on("styledata", () => { if (map.isStyleLoaded()) { addOverlays(); updateFallback(); } });
    map.on("movestart", (e) => { if (!programmatic && e.originalEvent) emit("userPan"); });
    map.on("error", (e) => emit("error", { message: String(e.error?.message || e.error) }));
    map.on("contextmenu", (e) => emit("longPress", { lat: e.lngLat.lat, lon: e.lngLat.lng }));
    // Touch long press (contextmenu is mouse-only on some builds).
    let pressTimer = null, start = null;
    const canvas = map.getCanvasContainer();
    canvas.addEventListener("touchstart", (ev) => {
      if (ev.touches.length !== 1) { clearTimeout(pressTimer); return; }
      const t = ev.touches[0]; start = [t.clientX, t.clientY];
      pressTimer = setTimeout(() => {
        const r = canvas.getBoundingClientRect();
        const ll = map.unproject([start[0] - r.left, start[1] - r.top]);
        emit("longPress", { lat: ll.lat, lon: ll.lng });
      }, 650);
    }, { passive: true });
    canvas.addEventListener("touchmove", (ev) => {
      const t = ev.touches[0];
      if (start && Math.hypot(t.clientX - start[0], t.clientY - start[1]) > 10) clearTimeout(pressTimer);
    }, { passive: true });
    canvas.addEventListener("touchend", () => clearTimeout(pressTimer), { passive: true });
  },
  setNight(value) {
    if (!map || !!value === night) return;
    night = !!value; map.setStyle(style());
  },
  setVehicle(lat, lon, heading, follow) {
    if (!map) return;
    if (lat == null) { if (vehicle) { vehicle.remove(); vehicle = null; } return; }
    if (!vehicle) vehicle = new maplibregl.Marker({ element: vehicleElement(), rotationAlignment: "map" })
                              .setLngLat([lon, lat]).addTo(map);
    vehicle.setLngLat([lon, lat]).setRotation(heading || 0);
    if (follow) quietly(() => map.easeTo({ center: [lon, lat], duration: 900, easing: (t) => t }));
  },
  recenter(lat, lon, zoom) { if (map) quietly(() => map.easeTo({ center: [lon, lat], zoom: zoom ?? map.getZoom() })); },
  zoomBy(delta) { if (map) quietly(() => map.easeTo({ zoom: map.getZoom() + delta })); },
  setLayer(name, geojson) {
    data[name] = geojson || empty;
    const src = map && map.getSource(name);
    if (src) src.setData(data[name]);
  },
  setDestination(lat, lon) {
    if (!map) return;
    if (destination) { destination.remove(); destination = null; }
    if (lat != null) destination = new maplibregl.Marker({ element: pinElement(), anchor: "bottom" })
                                     .setLngLat([lon, lat]).addTo(map);
  },
  fit(minLon, minLat, maxLon, maxLat) {
    if (map) quietly(() => map.fitBounds([[minLon, minLat], [maxLon, maxLat]],
                                         { padding: 80, duration: 800, maxZoom: 16 }));
  },
};
emit("loaded");
