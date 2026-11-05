import type { MetadataRoute } from "next";

// Makes the site installable as an app on Android, iOS/iPadOS, Windows, macOS, Linux and ChromeOS.
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "RoadWatch BD",
    short_name: "RoadWatch",
    description: "Find possible traffic jams, mid-road bus stops and wrong-way driving in road videos.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    display_override: ["window-controls-overlay", "standalone"],
    orientation: "any",
    background_color: "#f6f7f6",
    theme_color: "#0b6e4f",
    lang: "en",
    dir: "ltr",
    categories: ["navigation", "utilities"],
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
      { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Upload a video", url: "/", icons: [{ src: "/icon-192.png", sizes: "192x192" }] },
      { name: "My account", url: "/account", icons: [{ src: "/icon-192.png", sizes: "192x192" }] },
    ],
  };
}
