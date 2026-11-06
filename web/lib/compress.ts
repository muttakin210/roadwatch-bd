// In-browser trim + 720p H.264 compression with WebCodecs (mediabunny), PLAN §8.1.
// Returns null when the browser can't do it; the caller then uploads the original.
import {
  ALL_FORMATS,
  BlobSource,
  BufferTarget,
  Conversion,
  Input,
  Mp4OutputFormat,
  Output,
  QUALITY_MEDIUM,
  canEncodeVideo,
} from "mediabunny";

const STALL_MS = 30_000;

export async function compressVideo(
  file: File,
  trim: { start: number; end: number } | null,
  onProgress: (p: number) => void,
  signal?: AbortSignal,
): Promise<File | null> {
  if (typeof window === "undefined" || !("VideoEncoder" in window)) return null;
  try {
    if (!(await canEncodeVideo("avc"))) return null;
    const input = new Input({ source: new BlobSource(file), formats: ALL_FORMATS });
    const track = await input.getPrimaryVideoTrack();
    if (!track) return null;
    const w = track.displayWidth;
    const h = track.displayHeight;
    const out = compressedSize(w, h);
    const output = new Output({ format: new Mp4OutputFormat({ fastStart: "in-memory" }), target: new BufferTarget() });
    const conversion = await Conversion.init({
      input,
      output,
      // Only resize/re-encode when above 720p; otherwise a trim can copy the stream as-is.
      video: out.w !== w || out.h !== h ? { width: out.w, height: out.h, fit: "fill", codec: "avc", quality: QUALITY_MEDIUM } : {},
      audio: { discard: true }, // audio isn't analysed; dropping it saves size and protects privacy
      trim: trim ?? undefined,
      showWarnings: false,
    });
    if (!conversion.isValid) return null;
    // Some browsers' encoders crawl or stall on 4K/60 fps input. If progress doesn't move for
    // STALL_MS, give up and let the caller upload the original (the server re-encodes with ffmpeg).
    // We never wait on cancel(): a stuck encoder may not settle execute() after cancelling, so
    // we race it against our own give-up promise and walk away (cancel is best-effort cleanup).
    let last = Date.now();
    conversion.onProgress = (p) => {
      last = Date.now();
      onProgress(p);
    };
    let watchdog: ReturnType<typeof setInterval> | undefined;
    let onAbort: (() => void) | undefined;
    const giveUp = new Promise<"stalled">((resolve, reject) => {
      watchdog = setInterval(() => Date.now() - last > STALL_MS && resolve("stalled"), 2000);
      onAbort = () => {
        void conversion.cancel().catch(() => {}); // best-effort; don't wait for it
        reject(signal?.reason ?? new DOMException("Aborted", "AbortError"));
      };
      if (signal?.aborted) onAbort();
      else signal?.addEventListener("abort", onAbort, { once: true });
    });
    let outcome: "done" | "stalled";
    try {
      outcome = await Promise.race([conversion.execute().then(() => "done" as const), giveUp]);
    } finally {
      clearInterval(watchdog);
      if (onAbort) signal?.removeEventListener("abort", onAbort);
    }
    if (outcome === "stalled") {
      void conversion.cancel().catch(() => {});
      console.warn("compression stalled, uploading original");
      return null;
    }
    const buf = (output.target as BufferTarget).buffer;
    if (!buf) return null;
    if (!trim && buf.byteLength >= file.size) return null; // didn't help: send the original
    const name = file.name.replace(/\.[^.]+$/, "") + "_720p.mp4";
    return new File([buf], name, { type: "video/mp4", lastModified: file.lastModified });
  } catch (e) {
    if (signal?.aborted) throw e;
    console.warn("compression failed, uploading original", e);
    return null;
  }
}

/** Frame size compressVideo produces for a w×h video: short side 720 (never upscaled), even numbers. */
export function compressedSize(w: number, h: number): { w: number; h: number } {
  const scale = Math.min(1, 720 / Math.min(w, h));
  if (scale >= 1) return { w, h };
  const even = (v: number) => Math.max(2, Math.round((v * scale) / 2) * 2);
  return { w: even(w), h: even(h) };
}

/** The server analyses at long side ≤ 1280 (ffmpeg, never upscaled): the factor from a w×h upload to that. */
export function analysisScale(w: number, h: number): number {
  return Math.min(1, 1280 / Math.max(w, h));
}

/** Compress only when it helps: big files, a trim, or more than 720p. */
export function shouldCompress(file: File, trimmed: boolean, w: number, h: number): boolean {
  return trimmed || file.size > 25 * 1024 * 1024 || Math.min(w, h) > 720;
}
