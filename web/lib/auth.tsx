"use client";

// Accounts client. The session is an HttpOnly cookie set by the backend; JS never sees the token.
import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Privacy = { show_name: boolean; profile_public: boolean; share_contact: boolean; show_locations: boolean };
export type Role = "user" | "reviewer" | "police" | "admin";
export type Me = { id: string; email: string; display_name: string; phone: string | null; role: Role; privacy: Privacy };

export type CaseStatus = "submitted" | "confirmed" | "rejected" | "fined" | "dismissed";
export type Case = {
  id: string;
  event_id: string;
  video_id: string;
  status: CaseStatus;
  uploader_note: string | null;
  created_at: number;
  review_note: string | null;
  fine_bdt: number | null;
  event: { type: string; vehicle_class: string | null; start_s: number; end_s: number; confidence: number | null; reason: string } | null;
  police_ref?: string | null;
  own?: boolean;
  uploader?: { name: string | null; contact: { email: string; phone: string | null } | null };
};

export async function call<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    cache: "no-store",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let msg = `${r.status}`;
    try {
      const b = await r.json();
      msg = typeof b.detail === "string" ? b.detail : Array.isArray(b.detail) ? b.detail[0]?.msg ?? msg : msg;
    } catch {}
    const e = new Error(msg) as Error & { status: number };
    e.status = r.status;
    throw e;
  }
  return r.json() as Promise<T>;
}

/** Only same-site paths: an attacker-supplied ?next=https://evil.example must not redirect off-site. */
export function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") && !raw.startsWith("/\\") ? raw : "/account";
}

type Ctx = {
  me: Me | null;
  loading: boolean;
  refresh: () => Promise<void>;
  setMe: (m: Me | null) => void;
  logout: () => Promise<void>;
};
const AuthCtx = createContext<Ctx>({ me: null, loading: true, refresh: async () => {}, setMe: () => {}, logout: async () => {} });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(
    () =>
      call<{ user: Me | null }>("/api/me").then(
        (r) => setMe(r.user),
        () => setMe(null),
      ).finally(() => setLoading(false)),
    [],
  );
  useEffect(() => {
    let live = true;
    call<{ user: Me | null }>("/api/me")
      .then((r) => live && setMe(r.user), () => live && setMe(null))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, []);
  const logout = useCallback(async () => {
    await call("/api/auth/logout", "POST", {});
    setMe(null);
  }, []);
  return <AuthCtx.Provider value={{ me, loading, refresh, setMe, logout }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
export const isStaff = (m: Me | null, role: "reviewer" | "police") => !!m && (m.role === role || m.role === "admin");
