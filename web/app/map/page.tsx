"use client";

import dynamic from "next/dynamic";

// The map libraries need the browser (window, WebGL): load them only on the client.
const RoadMap = dynamic(() => import("@/components/RoadMap"), {
  ssr: false,
  loading: () => <div className="h-[60vh] min-h-80 w-full rounded-xl bg-zinc-100 animate-pulse" />,
});

export default function MapPage() {
  return <RoadMap />;
}
