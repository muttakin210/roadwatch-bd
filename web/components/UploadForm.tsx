"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import ArrowCanvas from "@/components/ArrowCanvas";
import type { LatLng } from "@/components/LocationPicker";
import { createVideo, uploadResumable } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { analysisScale, compressedSize, compressVideo, shouldCompress } from "@/lib/compress";
import { fmtTime, num, useT } from "@/lib/i18n";

const LocationPicker = dynamic(() => import("@/components/LocationPicker"), {
  ssr: false,
  loading: () => <div className="h-64 w-full rounded-lg bg-zinc-100 animate-pulse" />,
});

type Arrow = [number, number, number, number];
type Phase =
  | { k: "idle" }
  | { k: "compressing"; p: number }
  | { k: "uploading"; sent: number; total: number; retrying: boolean; note?: string }
  | { k: "error"; msg: string };

const MIN_S = 10;
const MAX_S = 300;
const CAMERAS = ["footbridge", "roadside", "cctv", "vehicle"] as const;

export default function UploadForm() {
  const { t, lang } = useT();
  const { me, loading: authLoading } = useAuth();
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [meta, setMeta] = useState<{ duration: number; w: number; h: number } | null>(null);
  // The browser can't decode this file (e.g. an iPhone HEVC .mov in Chrome/Firefox on Windows or Linux).
  // The server decodes it with ffmpeg, so it can still be uploaded, just without trim and arrows.
  const [noPreview, setNoPreview] = useState(false);
  const [trim, setTrim] = useState<[number, number]>([0, 0]);
  const [frame, setFrame] = useState<ImageBitmap | null>(null);
  const [camera, setCamera] = useState<(typeof CAMERAS)[number]>("footbridge");
  const [along, setAlong] = useState(true);
  const [oneway, setOneway] = useState(false);
  const [arrows, setArrows] = useState<Arrow[]>([]);
  const [loc, setLoc] = useState<LatLng>(null);
  const [consent, setConsent] = useState(false);
  const [phase, setPhase] = useState<Phase>({ k: "idle" });
  const vid = useRef<HTMLVideoElement>(null);
  const abort = useRef<AbortController | null>(null);
  const skip = useRef<AbortController | null>(null);

  useEffect(() => () => void (url && URL.revokeObjectURL(url)), [url]);

  function pick(f: File | null) {
    setFile(f);
    setMeta(null);
    setNoPreview(false);
    setFrame(null);
    setArrows([]);
    setPhase({ k: "idle" });
    setUrl(f ? URL.createObjectURL(f) : null);
  }

  async function grabFrame(at: number) {
    const v = vid.current;
    if (!v) return;
    await new Promise<void>((res) => {
      const done = () => res();
      v.addEventListener("seeked", done, { once: true });
      v.currentTime = Math.min(at + 0.5, Math.max(0, v.duration - 0.1));
    });
    setFrame(await createImageBitmap(v));
  }

  const len = trim[1] - trim[0];
  const trimmed = !!meta && (trim[0] > 0.5 || trim[1] < meta.duration - 0.5);
  const lenError = meta && len < MIN_S ? t("tooShort") : meta && len > MAX_S ? t("tooLong") : null;
  const busy = phase.k === "compressing" || phase.k === "uploading";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !(meta || noPreview) || lenError) return;
    abort.current = new AbortController();
    const signal = abort.current.signal;
    try {
      let toSend: File = file;
      let note: string | undefined;
      let compressed = false;
      if (shouldCompress(file, trimmed, meta?.w ?? 0, meta?.h ?? 0)) {
        setPhase({ k: "compressing", p: 0 });
        skip.current = new AbortController();
        const skipSignal = skip.current.signal;
        let c: File | null = null;
        try {
          c = await compressVideo(file, trimmed ? { start: trim[0], end: trim[1] } : null,
            (p) => setPhase({ k: "compressing", p }), AbortSignal.any([signal, skipSignal]));
        } catch (err) {
          if (signal.aborted || !skipSignal.aborted) throw err; // a real cancel/error, not "skip"
        }
        if (c) {
          toSend = c;
          compressed = true;
        } else note = t("compressSkipped");
      }
      // Arrows were drawn in analysis pixels of the ORIGINAL size (long side ≤ 1280). The server analyses the
      // file we actually send, so rescale: e.g. a 4:3 video compressed to 960×720 is analysed at 960, not 1280.
      let sentArrows = arrows;
      if (meta && compressed && arrows.length) {
        const up = compressedSize(meta.w, meta.h);
        const k = (analysisScale(up.w, up.h) * up.w) / (analysisScale(meta.w, meta.h) * meta.w);
        sentArrows = arrows.map((a) => a.map((v) => Math.round(v * k)) as Arrow);
      }
      setPhase({ k: "uploading", sent: 0, total: toSend.size, retrying: false, note });
      const uploadId = await uploadResumable(toSend, (sent, total, retrying) =>
        setPhase({ k: "uploading", sent, total, retrying, note }), signal);
      const { id } = await createVideo({
        upload_id: uploadId,
        camera_type: camera,
        consent_training: consent,
        lat: loc?.lat ?? null,
        lng: loc?.lng ?? null,
        hints: {
          camera_along_road: along,
          oneway: oneway || null,
          arrows: sentArrows,
          // the browser couldn't cut the clip: the server trims it, so the chosen part is still what's analysed
          ...(trimmed && !compressed ? { trim: [trim[0], trim[1]] as [number, number] } : {}),
        },
      });
      // Cache Components keeps this page mounted (hidden) after navigating away; reset it so
      // "Analyse another video" starts from a clean form instead of a finished upload.
      pick(null);
      setLoc(null);
      setConsent(false);
      router.push(`/v/${id}`);
    } catch (err) {
      if (signal.aborted) return setPhase({ k: "idle" });
      setPhase({ k: "error", msg: err instanceof Error ? err.message : String(err) });
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <fieldset className="card">
        <legend className="legend">{t("step1")}</legend>
        <label className="btn-primary inline-block cursor-pointer">
          {t("chooseFile")}
          <input
            type="file"
            accept="video/mp4,video/quicktime,video/webm"
            className="sr-only"
            disabled={busy}
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
          />
        </label>
        <p className="text-sm text-muted mt-2">{t("fileHint")}</p>
        <p className="text-sm text-muted">{t("tips")}</p>
        {url && (
          <div className="mt-3 space-y-3">
            <video
              ref={vid}
              src={url}
              muted
              playsInline
              controls
              preload="metadata"
              className="w-full max-h-[50vh] rounded-lg bg-black"
              onLoadedMetadata={(e) => {
                const v = e.currentTarget;
                setMeta({ duration: v.duration, w: v.videoWidth, h: v.videoHeight });
                setTrim([0, Math.min(v.duration, MAX_S)]);
                void grabFrame(0);
              }}
              onError={() => setNoPreview(true)}
            />
            {noPreview && (
              <p className="text-sm rounded-lg bg-amber-50 border border-amber-300 p-2" role="status">
                {t("noPreview")}
              </p>
            )}
            {meta && file && (
              <div className="space-y-2">
                <p className="font-medium">{t("trim")}</p>
                <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2 text-sm">
                  <span>{t("trimStart")}</span>
                  <input
                    type="range" min={0} max={meta.duration} step={0.5} value={trim[0]} disabled={busy}
                    aria-label={t("trimStart")}
                    onChange={(e) => setTrim([Math.min(Number(e.target.value), trim[1] - 1), trim[1]])}
                    onMouseUp={() => void grabFrame(trim[0])}
                    onTouchEnd={() => void grabFrame(trim[0])}
                    onKeyUp={() => void grabFrame(trim[0])}
                  />
                  <span className="tabular-nums">{fmtTime(trim[0], lang)}</span>
                  <span>{t("trimEnd")}</span>
                  <input
                    type="range" min={0} max={meta.duration} step={0.5} value={trim[1]} disabled={busy}
                    aria-label={t("trimEnd")}
                    onChange={(e) => setTrim([trim[0], Math.max(Number(e.target.value), trim[0] + 1)])}
                  />
                  <span className="tabular-nums">{fmtTime(trim[1], lang)}</span>
                </div>
                <p className="text-sm">
                  {fmtTime(len, lang)} · {num((file.size / 1048576).toFixed(0), lang)} MB
                  {lenError && <span className="text-red-700 ml-2">{lenError}</span>}
                </p>
              </div>
            )}
          </div>
        )}
      </fieldset>

      <fieldset className="card space-y-3">
        <legend className="legend">{t("step2")}</legend>
        <label className="block">
          <span className="block mb-1">{t("cameraType")}</span>
          <select className="input" value={camera} onChange={(e) => setCamera(e.target.value as typeof camera)} disabled={busy}>
            {CAMERAS.map((c) => (
              <option key={c} value={c}>{t(`cam_${c}`)}</option>
            ))}
          </select>
        </label>
        <label className="flex gap-2 items-start">
          <input type="checkbox" className="mt-1" checked={along} onChange={(e) => setAlong(e.target.checked)} disabled={busy} />
          <span>{t("alongRoad")}</span>
        </label>
        <label className="flex gap-2 items-start">
          <input type="checkbox" className="mt-1" checked={oneway} onChange={(e) => setOneway(e.target.checked)} disabled={busy} />
          <span>{t("oneway")}</span>
        </label>
      </fieldset>

      {frame && (
        <fieldset className="card space-y-2">
          <legend className="legend">{t("step3")}</legend>
          <p className="text-sm text-muted">{t("arrowsHint")}</p>
          <ArrowCanvas frame={frame} arrows={arrows} onChange={setArrows} />
        </fieldset>
      )}

      <fieldset className="card">
        <legend className="legend">{t("step4")}</legend>
        <LocationPicker value={loc} onChange={setLoc} />
      </fieldset>

      <fieldset className="card">
        <legend className="legend">{t("step5")}</legend>
        <label className="flex gap-2 items-start">
          <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} disabled={busy} />
          <span>{t("consent")}</span>
        </label>
      </fieldset>

      <div aria-live="polite" className="space-y-2">
        {phase.k === "compressing" && (
          <>
            <p>{t("compressing")} {num(Math.round(phase.p * 100), lang)}%</p>
            <progress className="w-full" max={1} value={phase.p} />
            <button type="button" className="btn-secondary text-sm" onClick={() => skip.current?.abort()}>
              {t("skipCompress")}
            </button>
          </>
        )}
        {phase.k === "uploading" && (
          <>
            {phase.note && <p className="text-sm text-muted">{phase.note}</p>}
            <p>
              {phase.retrying ? t("uploadRetry") : t("uploading")}{" "}
              {num(Math.round((100 * phase.sent) / Math.max(phase.total, 1)), lang)}%
            </p>
            <progress className="w-full" max={phase.total} value={phase.sent} />
          </>
        )}
        {phase.k === "error" && (
          <p className="text-red-700">
            {t("uploadFailed")}: {phase.msg}
          </p>
        )}
      </div>

      <div className="flex gap-3">
        <button type="submit" className="btn-primary" disabled={!file || !(meta || noPreview) || !!lenError || busy}>
          {phase.k === "error" ? t("tryAgain") : t("submit")}
        </button>
      </div>
      {!authLoading && !me && (
        <p className="text-sm">
          <Link className="underline" href="/login?next=/">
            {t("loginToOwn")}
          </Link>
        </p>
      )}
      <p className="text-sm text-muted">{t("disclaimer")}</p>
    </form>
  );
}
