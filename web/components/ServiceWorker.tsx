"use client";

// Registers the service worker and offers "Install app":
// - Chrome/Edge on Android, Windows, macOS, Linux, ChromeOS: the browser's own install prompt
// - iPhone/iPad Safari (no prompt API): a hint to use Share → Add to Home Screen
import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";

type InstallEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: string }>;
};

const isStandalone = () =>
  window.matchMedia("(display-mode: standalone)").matches ||
  (navigator as { standalone?: boolean }).standalone === true;
const isIOS = () =>
  /iPad|iPhone|iPod/.test(navigator.userAgent) ||
  (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

export default function ServiceWorker() {
  const { t } = useT();
  const [prompt, setPrompt] = useState<InstallEvent | null>(null);
  const [iosHint, setIosHint] = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/sw.js").catch(() => {}); // the site works without it
    }
    if (isStandalone() || localStorage.getItem("installDismissed")) return;
    const onPrompt = (e: Event) => {
      e.preventDefault();
      setPrompt(e as InstallEvent);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    const ios = setTimeout(() => isIOS() && setIosHint(true), 0);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      clearTimeout(ios);
    };
  }, []);

  if (!prompt && !iosHint) return null;
  const dismiss = () => {
    localStorage.setItem("installDismissed", "1");
    setPrompt(null);
    setIosHint(false);
  };
  // Fixed at the bottom so it never shifts the page under the user's finger when it appears;
  // the spacer keeps the end of the page reachable above it.
  return (
    <>
      <div aria-hidden className="h-24" />
      <div
        role="region"
        aria-label={t("install")}
        className="fixed inset-x-0 bottom-0 z-50 bg-brand text-white text-sm shadow-lg"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="mx-auto max-w-3xl px-4 py-2 flex flex-wrap items-center gap-2">
          <span className="flex-1">
            {t(prompt ? "installApp" : "installIos")}
          </span>
          {prompt && (
            <button
              type="button"
              className="rounded-lg bg-white text-brand px-3 py-1 font-medium"
              onClick={async () => {
                await prompt.prompt();
                await prompt.userChoice;
                setPrompt(null);
              }}
            >
              {t("install")}
            </button>
          )}
          <button type="button" className="underline" onClick={dismiss}>
            {t("notNow")}
          </button>
        </div>
      </div>
    </>
  );
}
