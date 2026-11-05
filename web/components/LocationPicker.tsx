"use client";

// Leaflet touches `window`, so this file is loaded with next/dynamic({ ssr: false }).
import "leaflet/dist/leaflet.css";
import { useEffect, useState } from "react";
import { CircleMarker, MapContainer, TileLayer, useMap, useMapEvents } from "react-leaflet";
import { useT } from "@/lib/i18n";

export type LatLng = { lat: number; lng: number } | null;
const DHAKA: [number, number] = [23.7808, 90.4];

function ClickToPin({ onPick }: { onPick: (p: LatLng) => void }) {
  useMapEvents({ click: (e) => onPick({ lat: e.latlng.lat, lng: e.latlng.lng }) });
  return null;
}

function FlyTo({ p }: { p: LatLng }) {
  const map = useMap();
  useEffect(() => {
    if (p) map.flyTo([p.lat, p.lng], Math.max(map.getZoom(), 16), { duration: 0.6 });
  }, [p, map]);
  return null;
}

export default function LocationPicker({ value, onChange }: { value: LatLng; onChange: (p: LatLng) => void }) {
  const { t } = useT();
  const [fly, setFly] = useState<LatLng>(null);
  const [err, setErr] = useState(false);
  return (
    <div className="space-y-2">
      <p className="text-sm text-muted">{t("locationHint")}</p>
      <MapContainer center={DHAKA} zoom={12} className="h-64 w-full rounded-lg z-0" scrollWheelZoom={false}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ClickToPin onPick={onChange} />
        <FlyTo p={fly} />
        {value && <CircleMarker center={[value.lat, value.lng]} radius={10} pathOptions={{ color: "#0b6e4f" }} />}
      </MapContainer>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-secondary"
          onClick={() => {
            setErr(false);
            navigator.geolocation?.getCurrentPosition(
              (pos) => {
                const p = { lat: pos.coords.latitude, lng: pos.coords.longitude };
                onChange(p);
                setFly(p);
              },
              () => setErr(true),
              { enableHighAccuracy: true, timeout: 10_000 },
            );
          }}
        >
          {t("useMyLocation")}
        </button>
        {value && (
          <button type="button" className="btn-secondary" onClick={() => onChange(null)}>
            {t("clearLocation")}
          </button>
        )}
        {value && (
          <span className="text-sm self-center tabular-nums">
            {value.lat.toFixed(5)}, {value.lng.toFixed(5)}
          </span>
        )}
      </div>
      {err && <p className="text-sm text-red-700">{t("locationFailed")}</p>}
    </div>
  );
}
