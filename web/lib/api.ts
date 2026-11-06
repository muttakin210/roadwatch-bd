// Client for the FastAPI backend (PLAN §8.4). All paths are proxied by next.config rewrites.

export type Hints = {
  camera_along_road?: boolean;
  oneway?: boolean | null;
  arrows?: [number, number, number, number][];
  /** [start, end] seconds: set only when the browser couldn't trim the file itself; the server trims instead */
  trim?: [number, number];
};

/** An HTTP error from the API, with its status code (the message is the server's explanation). */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

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
  /** a reviewer confirmed it */
  verified?: boolean;
  /** can be reported to police (offences only, not congestion) */
  reportable?: boolean;
  /** only returned to the uploader */
  case_status?: string | null;
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
  /** name is null when the uploader is anonymous; profile_id only if their profile is public */
  uploader?: { name: string | null; profile_id: string | null } | null;
  is_owner?: boolean;
};

export type Note = { k?: string; en: string } & Record<string, string | undefined>;

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `${r.status}`;
    try {
      const b = await r.json();
      msg = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail ?? b);
    } catch {}
    throw new ApiError(msg, r.status);
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
  const store = {   // localStorage can throw (private mode, blocked storage): resuming is a bonus, not required
    get: () => { try { return localStorage.getItem(fp); } catch { return null; } },
    set: (v: string) => { try { localStorage.setItem(fp, v); } catch {} },
    drop: () => { try { localStorage.removeItem(fp); } catch {} },
  };
  let uid = store.get();
  let chunk = 4 * 1024 * 1024;
  let offset = 0;
  if (uid) {
    const r = await fetch(`/api/uploads/${uid}`, { signal });
    if (r.ok) offset = (await r.json()).offset;
    else uid = null;
  }
  const startSession = async () => {
    const r = await json<{ id: string; chunk_size: number }>(
      await fetch("/api/uploads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ size: file.size }),
        signal,
      }),
    );
    store.set(r.id);
    chunk = r.chunk_size;
    offset = 0;
    return r.id;
  };
  if (!uid) uid = await startSession();
  let failures = 0;
  let restarted = false;
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
        if (offset > file.size) throw new ApiError("upload is corrupt", 409);
        continue;
      }
      offset = (await json<{ offset: number }>(r)).offset;
      failures = 0;
      onProgress(offset, file.size, false);
    } catch (e) {
      if (signal?.aborted) throw e;
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
        // The session is gone (expired, cleaned up) or broken: start over once, then give up.
        if (!restarted && (e.status === 404 || e.status === 409 || e.status === 413)) {
          restarted = true;
          store.drop();
          uid = await startSession();
          onProgress(0, file.size, true);
          continue;
        }
        throw e; // any other client error won't get better by retrying
      }
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
  store.drop();
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

export async function submitCase(eventId: string, note: string) {
  return json<{ id: string; status: string }>(
    await fetch(`/api/events/${eventId}/case`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
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
