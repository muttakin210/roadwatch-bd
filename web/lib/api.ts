// Client for the FastAPI backend (PLAN §8.4). All paths are proxied by next.config rewrites.

export type Hints = {
  camera_along_road?: boolean;
  oneway?: boolean | null;
  arrows?: [number, number, number, number][];
};

export type RoadEvent = {
  id: string;
  type: string;
  subtype?: string | null;
  vehicle_class?: string | null;
  track_id?: number | null;
  start_s: number;
  end_s: number;
  confidence?: number | null;
  severity?: string | null;
  reason: string;
  details: Record<string, unknown> & { shown?: boolean };
};

export type Summary = Record<string, { events: number; distinct_vehicles: number | null; by_class: Record<string, number>; total_s: number }>;

export type VideoStatus = {
  id: string;
  status: "uploaded" | "queued" | "processing" | "done" | "failed";
  duration_s?: number | null;
  camera_type?: string;
  progress?: { step: string; progress: number; error?: string } | null;
  congestion_avg?: number;
  camera_motion?: string;
  summary?: Summary;
  /** Road-level notes: translatable key + args, with the English text as fallback. */
  notes?: Note[];
};

export type Note = { k?: string; en: string } & Record<string, string | undefined>;

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `${r.status}`;
    try {
      const b = await r.json();
      msg = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail ?? b);
    } catch {}
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

const sleep = (ms: number) => new Promise((res) => setTimeout(res, ms));

/** Resumable chunked upload. Survives dropped connections and page reloads (same file → same session). */
export async function uploadResumable(
  file: Blob & { name?: string; lastModified?: number },
  onProgress: (sent: number, total: number, retrying: boolean) => void,
  signal?: AbortSignal,
): Promise<string> {
  const fp = `upload:${file.name ?? "blob"}:${file.size}:${file.lastModified ?? 0}`;
  let uid = localStorage.getItem(fp);
  let chunk = 4 * 1024 * 1024;
  let offset = 0;
  if (uid) {
    const r = await fetch(`/api/uploads/${uid}`, { signal });
    if (r.ok) offset = (await r.json()).offset;
    else uid = null;
  }
  if (!uid) {
    const r = await json<{ id: string; chunk_size: number }>(
      await fetch("/api/uploads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ size: file.size }),
        signal,
      }),
    );
    uid = r.id;
    chunk = r.chunk_size;
    localStorage.setItem(fp, uid);
  }
  let failures = 0;
  onProgress(offset, file.size, false);
  while (offset < file.size) {
    try {
      const r = await fetch(`/api/uploads/${uid}?offset=${offset}`, {
        method: "PUT",
        headers: { "Content-Type": "application/octet-stream" },
        body: file.slice(offset, offset + chunk),
        signal,
      });
      if (r.status === 409) {
        offset = (await r.json()).detail.offset; // server tells us where it really is
        continue;
      }
      offset = (await json<{ offset: number }>(r)).offset;
      failures = 0;
      onProgress(offset, file.size, false);
    } catch (e) {
      if (signal?.aborted) throw e;
      if (e instanceof Error && /^4\d\d/.test(e.message) && !e.message.startsWith("409")) throw e;
      failures += 1;
      if (failures > 30) throw e;
      onProgress(offset, file.size, true);
      await sleep(Math.min(30_000, 1000 * 2 ** Math.min(failures, 5)));
      try {
        const s = await fetch(`/api/uploads/${uid}`, { signal });
        if (s.ok) offset = (await s.json()).offset;
      } catch {}
    }
  }
  localStorage.removeItem(fp);
  return uid;
}

export async function createVideo(body: {
  upload_id: string;
  hints: Hints;
  camera_type: string;
  consent_training: boolean;
  lat?: number | null;
  lng?: number | null;
}): Promise<{ id: string }> {
  return json(
    await fetch("/api/videos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export const getVideo = async (id: string) => json<VideoStatus>(await fetch(`/api/videos/${id}`, { cache: "no-store" }));

export const getEvents = async (id: string, uncertain: boolean) =>
  json<{ events: RoadEvent[] }>(await fetch(`/api/videos/${id}/events?include_uncertain=${uncertain ? 1 : 0}`, { cache: "no-store" }));

export async function sendFeedback(eventId: string, verdict: "correct" | "wrong" | "wrong_type") {
  return json(
    await fetch(`/api/events/${eventId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verdict }),
    }),
  );
}

export async function reportVideo(id: string, reason: string) {
  return json(
    await fetch(`/api/videos/${id}/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    }),
  );
}
