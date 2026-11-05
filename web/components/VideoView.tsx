"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { getEvents, getVideo, reportVideo, sendFeedback, type Note, type RoadEvent, type VideoStatus } from "@/lib/api";
import { fmtTime, num, useT, type Lang } from "@/lib/i18n";

const STEPS = ["queued", "starting", "checking video", "detecting", "analysing", "rendering", "done"];

export default function VideoView({ id }: { id: string }) {
  const { t } = useT();
  const [v, setV] = useState<VideoStatus | null>(null);
  const [err, setErr] = useState(false);
  const [notify, setNotify] = useState(false);
  const notified = useRef(false);

  // Live progress: SSE first, polling as a fallback (some proxies buffer event streams).
  useEffect(() => {
    let stop = false;
    let es: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const s = await getVideo(id);
        if (stop) return;
        setV(s);
        setErr(false);
        if (s.status === "done" || s.status === "failed") return;
      } catch {
        if (!stop) setErr(true);
      }
      timer = setTimeout(poll, 2500);
    };
    void poll();
    try {
      es = new EventSource(`/api/videos/${id}/stream`);
      es.onmessage = (m) => {
        const p = JSON.parse(m.data);
        if (!p) return;
        setV((old) => (old ? { ...old, progress: p } : old));
        if (p.step === "done" || p.step === "failed") {
          es?.close();
          void getVideo(id).then((s) => !stop && setV(s));
        }
      };
      es.onerror = () => es?.close();
    } catch {}
    return () => {
      stop = true;
      es?.close();
      clearTimeout(timer);
    };
  }, [id]);

  useEffect(() => {
    if (v?.status === "done" && notify && !notified.current && "Notification" in window) {
      notified.current = true;
      new Notification(t("appName"), { body: t("st_done") });
    }
  }, [v?.status, notify, t]);

  if (err && !v) return <p className="text-red-700">{t("loadFailed")}</p>;
  if (!v) return <p className="text-muted">…</p>;
  if (v.status !== "done") return <Progress v={v} notify={notify} setNotify={setNotify} />;
  return <Results id={id} v={v} />;
}

function Progress({ v, notify, setNotify }: { v: VideoStatus; notify: boolean; setNotify: (b: boolean) => void }) {
  const { t, lang } = useT();
  const step = v.status === "failed" ? "failed" : v.progress?.step ?? v.status;
  const idx = STEPS.indexOf(step);
  return (
    <section className="card space-y-4" aria-live="polite">
      <h2 className="text-xl font-semibold">{t("processing")}</h2>
      <ol className="space-y-1">
        {STEPS.slice(0, -1).map((s, i) => (
          <li key={s} className={i < idx ? "text-muted line-through" : i === idx ? "font-semibold" : "text-muted"}>
            {i < idx ? "✓ " : i === idx ? "→ " : "· "}
            {t(`st_${s}`)}
            {i === idx && v.progress && v.progress.progress > 0 && v.progress.progress < 1 &&
              ` ${num(Math.round(v.progress.progress * 100), lang)}%`}
          </li>
        ))}
      </ol>
      {step === "failed" && (
        <p className="text-red-700">
          {t("st_failed")}
          {v.progress?.error ? `: ${v.progress.error}` : ""}
        </p>
      )}
      {step !== "failed" && (
        <>
          <p className="text-sm text-muted">{t("keepOpen")}</p>
          {"Notification" in globalThis &&
            (notify ? (
              <p className="text-sm">{t("notifyOn")}</p>
            ) : (
              <button
                type="button"
                className="btn-secondary"
                onClick={async () => setNotify((await Notification.requestPermission()) === "granted")}
              >
                {t("notifyMe")}
              </button>
            ))}
        </>
      )}
    </section>
  );
}

function Results({ id, v }: { id: string; v: VideoStatus }) {
  const { t, lang } = useT();
  const video = useRef<HTMLVideoElement>(null);
  const [uncertain, setUncertain] = useState(false);
  const [events, setEvents] = useState<RoadEvent[]>([]);
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => getEvents(id, uncertain).then((r) => setEvents(r.events)), [id, uncertain]);
  useEffect(() => void load(), [load]);

  const jump = (s: number) => {
    const el = video.current;
    if (!el) return;
    el.currentTime = s;
    void el.play();
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const share = async () => {
    const link = location.href;
    if (navigator.share) {
      try {
        await navigator.share({ title: t("appName"), url: link });
        return;
      } catch {}
    }
    await navigator.clipboard.writeText(link);
    setCopied(true);
  };

  const summary = Object.entries(v.summary ?? {});
  const cong = v.congestion_avg ?? 0;
  return (
    <section className="space-y-5">
      <h2 className="text-xl font-semibold">{t("results")}</h2>
      <video ref={video} src={`/api/videos/${id}/annotated`} controls playsInline className="w-full max-h-[70vh] rounded-lg bg-black" />

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="card">
          <p className="text-sm text-muted">{t("congestion")}</p>
          <p className="text-2xl font-semibold tabular-nums">{num(Math.round(cong), lang)}/{num(100, lang)}</p>
          <div className="h-2 rounded bg-zinc-200 mt-1" aria-hidden>
            <div className="h-2 rounded" style={{ width: `${cong}%`, background: cong > 60 ? "#c62828" : cong > 35 ? "#ef8f00" : "#2e7d32" }} />
          </div>
        </div>
        <div className="card">
          <p className="text-sm text-muted">{t("camera")}</p>
          <p className="font-semibold">{t(`cm_${v.camera_motion ?? "static"}`)}</p>
        </div>
        {summary.map(([type, s]) => (
          <div className="card" key={type}>
            <p className="text-sm text-muted">{t(`ev_${type}`)}</p>
            <p className="text-2xl font-semibold tabular-nums">{num(s.distinct_vehicles ?? s.events, lang)}</p>
            <p className="text-sm text-muted">
              {s.distinct_vehicles != null ? t("vehicles") : t("times")} · {fmtTime(s.total_s, lang)}
              {Object.keys(s.by_class).length > 0 &&
                ` · ${Object.entries(s.by_class).map(([c, n]) => `${num(n, lang)} ${t(`cls_${c}`)}`).join(", ")}`}
            </p>
          </div>
        ))}
      </div>

      {(v.notes?.length ?? 0) > 0 && (
        <div className="card border-l-4 border-l-amber-500">
          <p className="font-semibold mb-1">{t("notes")}</p>
          <ul className="list-disc pl-5 space-y-1 text-sm">
            {v.notes!.map((n, i) => (
              <li key={i}>{noteText(n, t, lang)}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-2">
        <label className="flex gap-2 items-center text-sm">
          <input type="checkbox" checked={uncertain} onChange={(e) => setUncertain(e.target.checked)} />
          {t("showUncertain")}
        </label>
        <p className="text-xs text-muted">{t("possible")}</p>
        {events.length === 0 && <p>{t("noEvents")}</p>}
        <ul className="space-y-2">
          {events.map((e) => (
            <EventItem key={e.id} e={e} onJump={() => jump(e.start_s)} />
          ))}
        </ul>
      </div>

      <div className="flex flex-wrap gap-2">
        <a className="btn-secondary" href={`/api/videos/${id}/annotated`} download={`roadwatch_${id.slice(0, 8)}.mp4`}>
          {t("downloadVideo")}
        </a>
        <a className="btn-secondary" href={`/api/videos/${id}/events.json`} download>
          {t("downloadJson")}
        </a>
        <button type="button" className="btn-secondary" onClick={share}>
          {copied ? t("copied") : t("share")}
        </button>
        <Link className="btn-secondary" href="/">
          {t("newUpload")}
        </Link>
      </div>
      <Report id={id} />
    </section>
  );
}

/** A road-level note in the user's language; the English text if this build has no template for it. */
function noteText(n: Note, t: (k: string) => string, lang: Lang): string {
  if (!n.k) return n.en;
  const tpl = t(`nt_${n.k}`);
  if (tpl === `nt_${n.k}`) return n.en;
  return tpl.replace(/\{(\w+)\}/g, (_, name: string) => num(n[name] ?? "", lang));
}

type ReasonPart = { k: string } & Record<string, string>;

/** The event's reason in the user's language, built from the pipeline's structured parts.
 *  Falls back to the English `reason` (older results, or a part this build doesn't know). */
function reasonText(e: RoadEvent, t: (k: string) => string, lang: Lang): string {
  const parts = e.details?.reason_parts as ReasonPart[] | undefined;
  let text = e.reason;
  if (Array.isArray(parts) && parts.length > 0) {
    const out: string[] = [];
    for (const p of parts) {
      const tpl = t(`rsn_${p.k}`);
      if (tpl === `rsn_${p.k}`) {
        out.length = 0;
        break;
      }
      out.push(tpl.replace(/\{(\w+)\}/g, (_, name: string) => num(p[name] ?? "", lang)));
    }
    if (out.length > 0) text = out.join(" · ");
  }
  if (e.details?.limited === "moving camera") text += ` · ${t("rsn_limited_moving")}`;
  return text;
}

function EventItem({ e, onJump }: { e: RoadEvent; onJump: () => void }) {
  const { t, lang } = useT();
  const [sent, setSent] = useState<string | null>(null);
  const uncertain = e.details?.shown === false;
  const sev = e.severity === "high" ? "border-l-red-600" : e.severity === "low" ? "border-l-zinc-400" : "border-l-amber-500";
  return (
    <li className={`card border-l-4 ${sev} ${uncertain ? "opacity-70" : ""}`}>
      <button type="button" onClick={onJump} className="text-left w-full">
        <span className="font-semibold underline underline-offset-2">
          {fmtTime(e.start_s, lang)}–{fmtTime(e.end_s, lang)} · {t(`ev_${e.type}`)}
        </span>
        {e.vehicle_class && <span className="text-muted"> ({t(`cls_${e.vehicle_class}`)})</span>}
        <span className="text-sm text-muted">
          {" "}· {t("confidence")} {num((e.confidence ?? 0).toFixed(2), lang)}
        </span>
      </button>
      <p className="text-sm text-muted mt-1">{reasonText(e, t, lang)}</p>
      <div className="flex flex-wrap gap-2 mt-2">
        {(["correct", "wrong", "wrong_type"] as const).map((verdict) => (
          <button
            key={verdict}
            type="button"
            className="btn-secondary text-sm"
            disabled={!!sent}
            onClick={async () => {
              await sendFeedback(e.id, verdict);
              setSent(verdict);
            }}
          >
            {t(verdict === "wrong_type" ? "wrongType" : verdict)}
            {sent === verdict && ` — ${t("thanks")}`}
          </button>
        ))}
      </div>
    </li>
  );
}

function Report({ id }: { id: string }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [done, setDone] = useState(false);
  if (done) return <p className="text-sm">{t("reported")}</p>;
  if (!open)
    return (
      <button type="button" className="text-sm underline text-muted" onClick={() => setOpen(true)}>
        {t("report")}
      </button>
    );
  return (
    <form
      className="flex flex-col sm:flex-row gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!reason.trim()) return;
        await reportVideo(id, reason.trim());
        setDone(true);
      }}
    >
      <input className="input flex-1" value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t("reportReason")} aria-label={t("reportReason")} maxLength={1000} />
      <button type="submit" className="btn-primary">
        {t("send")}
      </button>
    </form>
  );
}
