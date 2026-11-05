"use client";

// Road situation map for all of Bangladesh.
// - Online with a Google Maps key (NEXT_PUBLIC_GOOGLE_MAPS_KEY): Google Maps with its live traffic layer.
// - Otherwise MapLibre; online with a TomTom key (NEXT_PUBLIC_TOMTOM_KEY, free tier) it overlays TomTom's live
//   traffic-flow tiles, refreshed every 2 minutes. Live road speeds always come from one of these providers:
//   no keyless source exists.
// - Offline, or when the user picks "offline map": MapLibre with the OpenStreetMap pack of Bangladesh
//   (PMTiles), read from the browser's saved copy when there is one, so it works with no internet at all.
// Both show RoadWatch incidents (AI-found jams, reviewer-confirmed violations) and use the same offline place search.
// Google's terms don't allow saving Google map data for offline use, so the offline map is always OpenStreetMap.
import { layers, namedFlavor } from "@protomaps/basemaps";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import Link from "next/link";
import { FileSource, PMTiles, Protocol } from "pmtiles";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { call } from "@/lib/auth";
import { num, useT, type Lang } from "@/lib/i18n";
import { loadPlaces, majorPlaces, searchPlaces, type Place } from "@/lib/places";

const GOOGLE_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY ?? "";
const TOMTOM_KEY = process.env.NEXT_PUBLIC_TOMTOM_KEY ?? "";
const REFRESH_MS = 2 * 60_000; // live traffic and RoadWatch incidents
const tomtomTiles = (stamp: number) =>
  [`https://api.tomtom.com/traffic/map/4/tile/flow/relative0/{z}/{x}/{y}.png?key=${encodeURIComponent(TOMTOM_KEY)}&tileSize=256&t=${stamp}`];
const PACK_URL = "/api/map/offline/bd.pmtiles";
const PACK_CACHE = "rw-offline-map"; // kept by the service worker across updates
const BD_CENTER: [number, number] = [90.35, 23.7]; // lng, lat
const BD_BOUNDS: [[number, number], [number, number]] = [[87.5, 20.2], [93.2, 27.0]];
const COLORS: Record<string, string> = {
  congestion_jam: "#dc2626",
  wrong_way: "#7c3aed",
  bus_midroad_stop: "#ea580c",
  u_turn: "#2563eb",
};

type Incident = { id: string; type: string; vehicle_class: string | null; verified: boolean; lat: number; lng: number; video_id: string; at: number };
type PackInfo = { available: false } | { available: true; bytes: number; built: number; url: string };

const L = {
  en: {
    title: "Road situation map",
    intro: "Live traffic across Bangladesh, plus what RoadWatch found in uploaded videos.",
    search: "Search a place (town, upazila, market, station…)",
    noMatch: "No place found.",
    locate: "My location",
    days: "Incidents from the last",
    d1: "day", d7: "7 days", d30: "30 days",
    legendLive: "Live traffic",
    legendSpeeds: ["Moving", "Slow", "Jammed"],
    live: "Live",
    updated: (t: string) => `Updated ${t}`,
    noLive: "Live road speeds aren't switched on yet (needs a Google Maps or TomTom key). The map shows RoadWatch reports from uploaded videos.",
    legendRw: "RoadWatch:",
    aiJam: "AI estimate: not checked by a person",
    verified: "confirmed by a reviewer",
    open: "Open the video",
    modeLive: "Live traffic",
    reportsOnly: "RoadWatch reports",
    modeOffline: "Offline map (OpenStreetMap)",
    offlineTitle: "Use the map without internet",
    offlineText: (mb: string) => `Save the whole Bangladesh road map on this device (${mb}). Afterwards the map and place search work with no internet. Live traffic needs internet.`,
    save: "Save map for offline",
    saving: "Saving…",
    saved: (mb: string) => `Saved on this device (${mb}). The map works offline.`,
    remove: "Remove saved map",
    noPack: "The offline map pack hasn't been prepared on the server yet. Place search already works offline.",
    youOffline: "You're offline. Showing the saved map.",
    offlineNoSave: "You're offline and no map is saved on this device. Place search still works. Save the map next time you're online.",
    quota: "Not enough storage space on this device to save the map.",
    loadFailed: "The map couldn't load.",
    incidents: "incidents",
    attribution: "Places: GeoNames (CC BY 4.0). Offline map: © OpenStreetMap contributors, Protomaps. Live traffic: Google or TomTom.",
  },
  bn: {
    title: "সড়ক পরিস্থিতির মানচিত্র",
    intro: "সারা বাংলাদেশের লাইভ যানজট, আর আপলোড করা ভিডিওতে RoadWatch যা পেয়েছে।",
    search: "জায়গা খুঁজুন (শহর, উপজেলা, বাজার, স্টেশন…)",
    noMatch: "কোনো জায়গা পাওয়া যায়নি।",
    locate: "আমার অবস্থান",
    days: "ঘটনা: গত",
    d1: "১ দিন", d7: "৭ দিন", d30: "৩০ দিন",
    legendLive: "লাইভ ট্রাফিক",
    legendSpeeds: ["চলছে", "ধীর", "যানজট"],
    live: "লাইভ",
    updated: (t: string) => `হালনাগাদ ${t}`,
    noLive: "লাইভ সড়ক-গতি এখনো চালু হয়নি (গুগল ম্যাপস বা টমটম কী দরকার)। মানচিত্রে আপলোড করা ভিডিও থেকে RoadWatch-এর রিপোর্ট দেখানো হচ্ছে।",
    legendRw: "RoadWatch:",
    aiJam: "এআই অনুমান: কেউ যাচাই করেননি",
    verified: "রিভিউয়ার নিশ্চিত করেছেন",
    open: "ভিডিও দেখুন",
    modeLive: "লাইভ ট্রাফিক",
    reportsOnly: "RoadWatch রিপোর্ট",
    modeOffline: "অফলাইন মানচিত্র (OpenStreetMap)",
    offlineTitle: "ইন্টারনেট ছাড়া মানচিত্র ব্যবহার",
    offlineText: (mb: string) => `পুরো বাংলাদেশের সড়ক মানচিত্র এই ডিভাইসে সংরক্ষণ করুন (${mb})। এরপর ইন্টারনেট ছাড়াই মানচিত্র ও জায়গা খোঁজা চলবে। লাইভ ট্রাফিকের জন্য ইন্টারনেট লাগবে।`,
    save: "অফলাইনের জন্য মানচিত্র সংরক্ষণ",
    saving: "সংরক্ষণ হচ্ছে…",
    saved: (mb: string) => `এই ডিভাইসে সংরক্ষিত (${mb})। মানচিত্র অফলাইনে চলবে।`,
    remove: "সংরক্ষিত মানচিত্র মুছুন",
    noPack: "সার্ভারে অফলাইন মানচিত্র এখনো তৈরি হয়নি। জায়গা খোঁজা এখনই অফলাইনে চলে।",
    youOffline: "আপনি অফলাইনে। সংরক্ষিত মানচিত্র দেখানো হচ্ছে।",
    offlineNoSave: "আপনি অফলাইনে এবং এই ডিভাইসে কোনো মানচিত্র সংরক্ষিত নেই। জায়গা খোঁজা চলবে। পরের বার অনলাইনে মানচিত্র সংরক্ষণ করুন।",
    quota: "মানচিত্র সংরক্ষণের জন্য ডিভাইসে যথেষ্ট জায়গা নেই।",
    loadFailed: "মানচিত্র লোড করা যায়নি।",
    incidents: "টি ঘটনা",
    attribution: "জায়গা: GeoNames (CC BY 4.0)। অফলাইন মানচিত্র: © OpenStreetMap contributors, Protomaps। লাইভ ট্রাফিক: Google বা TomTom।",
  },
} as const;

const mb = (bytes: number, lang: Lang) => `${num((bytes / 1048576).toFixed(0), lang)} MB`;

function subscribeOnline(cb: () => void) {
  window.addEventListener("online", cb);
  window.addEventListener("offline", cb);
  return () => {
    window.removeEventListener("online", cb);
    window.removeEventListener("offline", cb);
  };
}

// ------------------------------------------------------------------ Google Maps (online, live traffic)
// Minimal typings for the parts of the Maps JavaScript API used here.
type GLatLng = { lat: number; lng: number };
type GMap = { panTo(p: GLatLng): void; setZoom(z: number): void };
type GOverlay = { setMap(m: GMap | null): void };
type GMarker = GOverlay & { addListener(ev: string, f: () => void): void };
type GInfo = { setContent(c: Node): void; open(o: { map: GMap; anchor: GMarker }): void };
type GApi = {
  Map: new (el: HTMLElement, o: object) => GMap;
  TrafficLayer: new () => GOverlay;
  Marker: new (o: object) => GMarker;
  InfoWindow: new () => GInfo;
  SymbolPath: { CIRCLE: number };
};
declare global {
  interface Window {
    google?: { maps: GApi };
    __rwGoogleReady?: () => void;
  }
}
let googleLoading: Promise<GApi> | null = null;
function loadGoogle(): Promise<GApi> {
  googleLoading ??= new Promise<GApi>((resolve, reject) => {
    if (window.google?.maps) return resolve(window.google.maps);
    window.__rwGoogleReady = () => resolve(window.google!.maps);
    const s = document.createElement("script");
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(GOOGLE_KEY)}&v=weekly&loading=async&region=BD&callback=__rwGoogleReady`;
    s.async = true;
    s.onerror = () => {
      googleLoading = null;
      reject(new Error("google maps failed to load"));
    };
    document.head.appendChild(s);
  });
  return googleLoading;
}

// ------------------------------------------------------------------ offline pack (Cache API)
async function savedPack(): Promise<Blob | null> {
  if (!("caches" in window)) return null;
  const hit = await (await caches.open(PACK_CACHE)).match(PACK_URL);
  return hit ? hit.blob() : null;
}

let protocol: Protocol | null = null;
function pmtilesProtocol(): Protocol {
  if (!protocol) {
    protocol = new Protocol();
    maplibregl.addProtocol("pmtiles", protocol.tile);
  }
  return protocol;
}

function vectorStyle(url: string, withLabels: boolean): maplibregl.StyleSpecification {
  const base = layers("protomaps", namedFlavor("light"), { lang: "en" }) as maplibregl.LayerSpecification[];
  return {
    version: 8,
    // labels need font files from the internet; offline we label towns ourselves (HTML markers render Bangla)
    ...(withLabels ? { glyphs: "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf" } : {}),
    sources: { protomaps: { type: "vector", url, attribution: "© OpenStreetMap contributors, Protomaps" } },
    layers: withLabels ? base : base.filter((l) => l.type !== "symbol"),
  };
}

const OSM_RASTER: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 19,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

// ------------------------------------------------------------------ component
type Focus = (p: { lat: number; lng: number }, zoom?: number) => void;

export default function RoadMap() {
  const { t, lang } = useT();
  const s = L[lang];
  const online = useSyncExternalStore(subscribeOnline, () => navigator.onLine, () => true);
  const [wantOffline, setWantOffline] = useState(false);
  const useGoogle = !!GOOGLE_KEY && online && !wantOffline;
  const liveOn = online && !wantOffline && (!!GOOGLE_KEY || !!TOMTOM_KEY);

  const [days, setDays] = useState(7);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [pack, setPack] = useState<PackInfo | null>(null);
  const [saved, setSaved] = useState<number | null>(null); // bytes saved on this device
  const [progress, setProgress] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [places, setPlaces] = useState<Place[]>([]);
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState(false); // close the result list once a place is chosen
  const [mapError, setMapError] = useState(false);

  const el = useRef<HTMLDivElement>(null);
  const focus = useRef<Focus>(() => {});
  // The map is built once per mode. Incidents and live-traffic tiles are updated in place, so the 2-minute
  // refresh never resets where the user has panned or zoomed.
  const showIncidents = useRef<(list: Incident[]) => void>(() => {});
  const refreshLive = useRef<() => void>(() => {});
  const incidentsNow = useRef<Incident[]>([]);

  useEffect(() => {
    loadPlaces().then(setPlaces, () => {});
    savedPack().then((b) => setSaved(b ? b.size : null), () => {});
  }, []);
  useEffect(() => {
    if (!online) return;
    call<PackInfo>("/api/map/offline").then(setPack, () => setPack({ available: false }));
  }, [online]);

  // RoadWatch incidents and live traffic: now, then every 2 minutes while the page is visible
  useEffect(() => {
    if (!online) return;
    let live = true;
    const tick = () => {
      if (document.visibilityState !== "visible") return;
      call<{ incidents: Incident[] }>(`/api/map/incidents?days=${days}`).then(
        (r) => {
          if (!live) return;
          setIncidents(r.incidents);
          setUpdatedAt(Date.now());
        },
        () => {},
      );
      refreshLive.current();
    };
    tick();
    const id = window.setInterval(tick, REFRESH_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      live = false;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [days, online]);
  useEffect(() => {
    incidentsNow.current = incidents;
    showIncidents.current(incidents);
  }, [incidents]);

  const popup = useCallback(
    (i: Incident) => {
      const box = document.createElement("div");
      box.style.fontSize = "13px";
      box.style.lineHeight = "1.45";
      const title = document.createElement("b");
      title.textContent = t(`ev_${i.type}`) + (i.vehicle_class ? ` (${t(`cls_${i.vehicle_class}`)})` : "");
      const note = document.createElement("div");
      note.textContent = `${new Date(i.at * 1000).toLocaleString(lang === "bn" ? "bn-BD" : "en-GB")} · ${i.type.startsWith("congestion") ? s.aiJam : s.verified}`;
      const a = document.createElement("a");
      a.href = `/v/${i.video_id}`;
      a.textContent = s.open;
      a.style.textDecoration = "underline";
      box.append(title, note, a);
      return box;
    },
    [t, lang, s],
  );
  const popupRef = useRef(popup);
  useEffect(() => {
    popupRef.current = popup;
  }, [popup]);

  // ---- Google map (built once; markers follow the incident list)
  useEffect(() => {
    if (!useGoogle || !el.current) return;
    let alive = true;
    let overlays: GOverlay[] = [];
    let traffic: GOverlay | null = null;
    loadGoogle().then(
      (g) => {
        if (!alive || !el.current) return;
        setMapError(false);
        const map = new g.Map(el.current, {
          center: { lat: BD_CENTER[1], lng: BD_CENTER[0] },
          zoom: 7,
          minZoom: 6,
          restriction: { latLngBounds: { west: BD_BOUNDS[0][0], south: BD_BOUNDS[0][1], east: BD_BOUNDS[1][0], north: BD_BOUNDS[1][1] } },
          streetViewControl: false,
          mapTypeControl: false,
          fullscreenControl: false,
          gestureHandling: "greedy",
        });
        traffic = new g.TrafficLayer();
        traffic.setMap(map);
        // Google also refreshes the layer by itself; re-attaching fetches the newest picture now
        refreshLive.current = () => {
          traffic?.setMap(null);
          traffic?.setMap(map);
        };
        const info = new g.InfoWindow();
        showIncidents.current = (list) => {
          overlays.forEach((o) => o.setMap(null));
          overlays = list.map((i) => {
            const m = new g.Marker({
              map,
              position: { lat: i.lat, lng: i.lng },
              title: t(`ev_${i.type}`),
              icon: { path: g.SymbolPath.CIRCLE, scale: 8, fillColor: COLORS[i.type] ?? "#52525b", fillOpacity: 0.9, strokeColor: "#fff", strokeWeight: 2 },
            });
            m.addListener("click", () => {
              info.setContent(popupRef.current(i));
              info.open({ map, anchor: m });
            });
            return m;
          });
        };
        showIncidents.current(incidentsNow.current);
        let pin: GOverlay | null = null;
        focus.current = (p, zoom = 14) => {
          map.panTo(p);
          map.setZoom(zoom);
          pin?.setMap(null);
          pin = new g.Marker({ map, position: p });
        };
      },
      () => alive && setMapError(true),
    );
    return () => {
      alive = false;
      overlays.forEach((o) => o.setMap(null));
      traffic?.setMap(null);
      showIncidents.current = () => {};
      refreshLive.current = () => {};
    };
  }, [useGoogle, t]);

  // ---- MapLibre map (offline pack, or OpenStreetMap online, plus TomTom live traffic when there's a key)
  useEffect(() => {
    if (useGoogle || !el.current) return;
    let map: maplibregl.Map | null = null;
    let alive = true;
    const markers: maplibregl.Marker[] = [];
    const geo = (list: Incident[]): GeoJSON.FeatureCollection => ({
      type: "FeatureCollection",
      features: list.map((i) => ({
        type: "Feature",
        properties: { id: i.id, color: COLORS[i.type] ?? "#52525b" },
        geometry: { type: "Point", coordinates: [i.lng, i.lat] },
      })),
    });
    (async () => {
      const blob = await savedPack().catch(() => null);
      let style: maplibregl.StyleSpecification | null = null;
      if (blob) {
        const p = new PMTiles(new FileSource(new File([blob], "bd.pmtiles")));
        pmtilesProtocol().add(p);
        style = vectorStyle("pmtiles://bd.pmtiles", false);
      } else if (online && pack?.available) {
        pmtilesProtocol();
        style = vectorStyle(`pmtiles://${location.origin}${PACK_URL}`, true);
      } else if (online) {
        style = OSM_RASTER;
      }
      if (!alive || !el.current || !style) return;
      setMapError(false);
      map = new maplibregl.Map({
        container: el.current,
        style,
        center: BD_CENTER,
        zoom: 6.3,
        minZoom: 5.5,
        maxBounds: BD_BOUNDS,
        attributionControl: { compact: true },
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.on("error", (e) => console.warn("map", e.error?.message));
      map.on("load", () => {
        if (!map) return;
        if (online && TOMTOM_KEY && !wantOffline) {
          map.addSource("live", { type: "raster", tiles: tomtomTiles(Date.now()), tileSize: 256, attribution: "Traffic © TomTom" });
          map.addLayer({ id: "live", type: "raster", source: "live", paint: { "raster-opacity": 0.85, "raster-fade-duration": 400 } });
          refreshLive.current = () => (map?.getSource("live") as maplibregl.RasterTileSource | undefined)?.setTiles(tomtomTiles(Date.now()));
        }
        map.addSource("incidents", { type: "geojson", data: geo(incidentsNow.current) });
        map.addLayer({
          id: "incidents",
          type: "circle",
          source: "incidents",
          paint: { "circle-radius": 7, "circle-stroke-width": 2, "circle-stroke-color": "#ffffff", "circle-color": ["get", "color"] },
        });
        showIncidents.current = (list) => (map?.getSource("incidents") as maplibregl.GeoJSONSource | undefined)?.setData(geo(list));
        map.on("click", "incidents", (e) => {
          const id = e.features?.[0]?.properties?.id;
          const i = incidentsNow.current.find((x) => x.id === id);
          if (i && map) new maplibregl.Popup().setLngLat([i.lng, i.lat]).setDOMContent(popupRef.current(i)).addTo(map);
        });
        map.on("mouseenter", "incidents", () => map && (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", "incidents", () => map && (map.getCanvas().style.cursor = ""));
      });
      if (blob) {
        // no label fonts offline: name the big towns with HTML (the browser shapes Bangla correctly)
        for (const p of majorPlaces(places)) {
          const label = document.createElement("span");
          label.textContent = lang === "bn" && p.bn ? p.bn.replace(/ জিলা$/, "") : p.name;
          label.className = "rw-town";
          markers.push(new maplibregl.Marker({ element: label }).setLngLat([p.lng, p.lat]).addTo(map));
        }
      }
      let pin: maplibregl.Marker | null = null;
      focus.current = (p, zoom = 13) => {
        // a calm flight; people who reduce motion get an instant jump
        const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
        if (calm) map?.jumpTo({ center: [p.lng, p.lat], zoom });
        else map?.flyTo({ center: [p.lng, p.lat], zoom, speed: 0.8, curve: 1.3 });
        pin?.remove();
        if (map) pin = new maplibregl.Marker({ color: "#0b6e4f" }).setLngLat([p.lng, p.lat]).addTo(map);
      };
    })().catch(() => alive && setMapError(true));
    return () => {
      alive = false;
      markers.forEach((m) => m.remove());
      map?.remove();
      showIncidents.current = () => {};
      refreshLive.current = () => {};
    };
  }, [useGoogle, wantOffline, online, pack, saved, places, lang]);

  // ---- save / remove the offline pack
  async function saveOffline() {
    if (!pack?.available) return;
    setMsg(null);
    setProgress(0);
    try {
      await navigator.storage?.persist?.(); // ask the browser not to evict it when space is low
      const est = await navigator.storage?.estimate?.();
      if (est?.quota && est.usage !== undefined && est.quota - est.usage < pack.bytes * 1.1) throw new Error("quota");
      const res = await fetch(PACK_URL);
      if (!res.ok || !res.body) throw new Error(String(res.status));
      const reader = res.body.getReader();
      const parts: Uint8Array[] = [];
      let got = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        parts.push(value);
        got += value.length;
        setProgress(got / pack.bytes);
      }
      const blob = new Blob(parts as BlobPart[], { type: "application/vnd.pmtiles" });
      await (await caches.open(PACK_CACHE)).put(PACK_URL, new Response(blob, { headers: { "Content-Length": String(blob.size) } }));
      setSaved(blob.size);
    } catch (e) {
      setMsg(e instanceof Error && (e.message === "quota" || e.name === "QuotaExceededError") ? s.quota : s.loadFailed);
    } finally {
      setProgress(null);
    }
  }
  async function removeOffline() {
    await caches.delete(PACK_CACHE);
    setSaved(null);
  }

  const results = useMemo(() => searchPlaces(places, q), [places, q]);
  const pick = (p: Place) => {
    focus.current({ lat: p.lat, lng: p.lng }, p.kind.startsWith("ADM") ? 10 : 13);
    setQ(lang === "bn" && p.bn ? p.bn : p.name);
    setPicked(true);
  };
  const locate = () =>
    navigator.geolocation?.getCurrentPosition(
      (pos) => focus.current({ lat: pos.coords.latitude, lng: pos.coords.longitude }, 15),
      () => {},
      { enableHighAccuracy: true, timeout: 10_000 },
    );

  const note = !online ? (saved ? s.youOffline : s.offlineNoSave) : !GOOGLE_KEY && !TOMTOM_KEY ? s.noLive : null;
  const clock = updatedAt
    ? new Date(updatedAt).toLocaleTimeString(lang === "bn" ? "bn-BD" : "en-GB", { hour: "2-digit", minute: "2-digit" })
    : null;
  const count = lang === "bn" ? `${num(incidents.length, lang)}${s.incidents}` : `${incidents.length} ${s.incidents}`;

  return (
    <div className="rw-bleed space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold">{s.title}</h1>
          <p className="text-sm text-muted mt-1">{s.intro}</p>
        </div>
        {online && (
          <p className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs font-medium shadow-sm">
            {liveOn ? <span className="rw-live-dot" aria-hidden="true" /> : <span className="h-2 w-2 rounded-full bg-zinc-400" aria-hidden="true" />}
            {liveOn ? s.live : s.reportsOnly}
            {clock && <span className="text-muted font-normal">· {s.updated(clock)}</span>}
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {(GOOGLE_KEY || TOMTOM_KEY) && online && (
          <div className="inline-flex rounded-full border border-zinc-300 bg-white p-0.5" role="group" aria-label={s.title}>
            <button type="button" className="chip !border-0" aria-pressed={!wantOffline} onClick={() => setWantOffline(false)}>{s.modeLive}</button>
            <button type="button" className="chip !border-0" aria-pressed={wantOffline} onClick={() => setWantOffline(true)}>{s.modeOffline}</button>
          </div>
        )}
        <button type="button" className="btn-secondary text-sm" onClick={locate}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <circle cx="12" cy="12" r="3" />
            <circle cx="12" cy="12" r="7" />
            <path d="M12 2v3m0 14v3M2 12h3m14 0h3" />
          </svg>
          {s.locate}
        </button>
        <label className="text-sm flex items-center gap-2 ml-auto">
          <span className="text-muted">{s.days}</span>
          <select className="input !w-auto !min-h-0 !py-1 text-sm" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={1}>{s.d1}</option>
            <option value={7}>{s.d7}</option>
            <option value={30}>{s.d30}</option>
          </select>
        </label>
      </div>

      {note && <p className="text-sm rounded-lg bg-amber-50 border border-amber-200 px-3 py-2" role="status">{note}</p>}
      {mapError && <p className="text-sm text-red-700" role="alert">{s.loadFailed}</p>}

      <div className="relative">
        <div
          ref={el}
          className="h-[calc(100dvh-20rem)] min-h-[420px] w-full overflow-hidden rounded-[var(--radius)] border border-zinc-200 bg-zinc-100 shadow-sm"
          aria-label={s.title}
          role="region"
        />

        {/* search floats over the map, as in native map apps */}
        <div className="absolute left-3 right-14 top-3 z-10 sm:right-auto sm:w-96">
          <div className="rw-float bg-white">
            <input
              className="input !border-0"
              type="search"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPicked(false);
              }}
              placeholder={s.search}
              aria-label={s.search}
            />
          </div>
          {q.trim().length >= 2 && places.length > 0 && !picked && (
            <ul className="rw-float mt-2 max-h-72 overflow-auto border border-zinc-200 bg-white py-1" role="listbox" aria-label={s.search}>
              {results.length === 0 && <li className="px-3 py-2 text-sm text-muted">{s.noMatch}</li>}
              {results.map((p) => (
                <li key={`${p.name}${p.lat}${p.lng}`}>
                  <button type="button" role="option" aria-selected={false} className="w-full text-left px-3 py-2 hover:bg-zinc-50 text-sm transition-colors" onClick={() => pick(p)}>
                    <b className="font-medium">{lang === "bn" && p.bn ? p.bn : p.name}</b>
                    <span className="text-muted"> · {[lang === "bn" ? p.name : p.bn, p.division].filter(Boolean).join(" · ")}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* legend floats bottom-left */}
        <div className="rw-float absolute left-3 bottom-8 z-[5] max-w-[calc(100%-1.5rem)] bg-white/95 px-3 py-2 text-xs space-y-1.5">
          {liveOn && (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="font-semibold">{s.legendLive}</span>
              {["#16a34a", "#f59e0b", "#dc2626"].map((c, k) => (
                <span key={c} className="inline-flex items-center gap-1">
                  <span className="inline-block h-1.5 w-5 rounded-full" style={{ background: c }} />
                  {s.legendSpeeds[k]}
                </span>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-semibold">{s.legendRw}</span>
            {Object.entries(COLORS).map(([k, c]) => (
              <span key={k} className="inline-flex items-center gap-1">
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: c, boxShadow: "0 0 0 2px #fff, 0 0 0 3px #d4d4d8" }} />
                {t(`ev_${k}`)}
              </span>
            ))}
            <span className="text-muted">· {count}</span>
          </div>
        </div>
      </div>

      <p className="text-xs text-muted">
        {t("ev_congestion_jam")}: {s.aiJam}. {s.verified}: {t("ev_wrong_way")}, {t("ev_bus_midroad_stop")}, {t("ev_u_turn")}.
      </p>

      <section className="card space-y-2 max-w-3xl">
        <h2 className="font-semibold">{s.offlineTitle}</h2>
        {saved ? (
          <>
            <p className="text-sm">{s.saved(mb(saved, lang))}</p>
            <button type="button" className="btn-secondary text-sm" onClick={() => void removeOffline()}>{s.remove}</button>
          </>
        ) : pack?.available ? (
          <>
            <p className="text-sm">{s.offlineText(mb(pack.bytes, lang))}</p>
            {progress === null ? (
              <button type="button" className="btn-primary" onClick={() => void saveOffline()} disabled={!online}>{s.save}</button>
            ) : (
              <>
                <p className="text-sm">{s.saving} {num(Math.round(progress * 100), lang)}%</p>
                <progress className="w-full accent-[#0b6e4f]" max={1} value={progress} />
              </>
            )}
          </>
        ) : (
          <p className="text-sm text-muted">{s.noPack}</p>
        )}
        {msg && <p className="text-sm text-red-700">{msg}</p>}
      </section>

      <p className="text-xs text-muted">
        {s.attribution} <Link className="underline" href="/rules">{t("navRules")}</Link>
      </p>
    </div>
  );
}
