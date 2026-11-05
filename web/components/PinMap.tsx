"use client";

// Upload locations on a public profile (only when the user turned "show map pins" on). Loaded with ssr: false.
import "leaflet/dist/leaflet.css";
import { CircleMarker, MapContainer, TileLayer } from "react-leaflet";

export default function PinMap({ pins }: { pins: { id: string; lat: number; lng: number }[] }) {
  return (
    <MapContainer center={[pins[0].lat, pins[0].lng]} zoom={12} className="h-64 w-full rounded-lg z-0" scrollWheelZoom={false}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {pins.map((p) => (
        <CircleMarker key={p.id} center={[p.lat, p.lng]} radius={8} pathOptions={{ color: "#0b6e4f" }} />
      ))}
    </MapContainer>
  );
}
