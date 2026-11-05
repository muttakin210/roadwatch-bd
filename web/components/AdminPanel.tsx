"use client";

// Admin panel. Every action is checked and audit-logged by the backend (backend/admin.py); this page only
// hides itself from non-admins.
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CaseBadge, fmtDate, LoginNeeded, taka } from "@/components/AccountPanel";
import { call, useAuth, type Case, type Role } from "@/lib/auth";
import { fmtTime, num, useT, type Lang } from "@/lib/i18n";

const TABS = ["overview", "users", "videos", "reports", "cases", "rewards", "log", "system"] as const;
type Tab = (typeof TABS)[number];
const ROLES: Role[] = ["user", "reviewer", "police", "admin"];

type Stats = {
  users: Record<string, number>;
  disabled_users: number;
  videos: Record<string, number>;
  hidden_videos: number;
  open_reports: number;
  cases: Record<string, number>;
  rewards_credited_bdt: number;
  events: Record<string, number>;
};
type AUser = {
  id: string;
  email: string;
  display_name: string;
  phone: string | null;
  role: Role;
  disabled: boolean;
  created_at: number;
  uploads: number;
  cases: number;
  credited_bdt: number;
};
type AVideo = {
  id: string;
  status: string;
  moderation_status: string | null;
  camera_type: string;
  created_at: number;
  duration_s: number | null;
  uploader_email: string | null;
  uploader_name: string | null;
  events: number;
  open_reports: number;
  last_error: string | null;
};
type AReport = { id: string; video_id: string; reason: string; created_at: number; resolved_at: number | null; moderation_status: string | null };
type AReward = { id: string; case_id: string; email: string | null; display_name: string | null; fine_bdt: number; amount_bdt: number; status: string; void_reason: string | null; created_at: number };
type ALog = { id: string; admin_email: string | null; action: string; target: string | null; detail: string | null; created_at: number };
type System = {
  detector: string;
  daily_upload_limit_per_ip: number;
  max_upload_mb: number;
  queue: number;
  model_version: string | null;
  rules_version: string | null;
  disk_bytes: { uploads: number; results: number };
  failed_jobs: { video_id: string; error: string; finished_at: number }[];
};

const fmtDT = (s: number, lang: Lang) =>
  new Date(s * 1000).toLocaleString(lang === "bn" ? "bn-BD" : "en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const mb = (b: number, lang: Lang) => `${num((b / 1024 / 1024).toFixed(1), lang)} MB`;

/** Runs an admin action; returns false (and shows the error) if the server refused. */
function useAction(onDone: () => void) {
  const [err, setErr] = useState<string | null>(null);
  const run = useCallback(
    async (path: string, body: unknown = {}) => {
      setErr(null);
      try {
        await call(path, "POST", body);
        onDone();
        return true;
      } catch (e) {
        setErr(e instanceof Error ? e.message : "error");
        return false;
      }
    },
    [onDone],
  );
  return { run, err };
}

function useLoad<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    let live = true;
    call<T>(path).then((d) => live && setData(d), () => {});
    return () => {
      live = false;
    };
  }, [path, n]);
  return { data, reload: useCallback(() => setN((x) => x + 1), []) };
}

export default function AdminPanel() {
  const { t } = useT();
  const { me, loading } = useAuth();
  const [tab, setTab] = useState<Tab>("overview");
  if (loading) return <p className="text-muted">…</p>;
  if (!me) return <LoginNeeded />;
  if (me.role !== "admin") return <p className="card">{t("forbidden")}</p>;
  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">{t("adminPanel")}</h1>
      <div role="tablist" className="flex flex-wrap gap-1.5">
        {TABS.map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            className={tab === k ? "btn-primary !py-1.5 !px-3 text-sm" : "btn-secondary text-sm"}
            onClick={() => setTab(k)}
          >
            {t(`adm_${k}`)}
          </button>
        ))}
      </div>
      {tab === "overview" && <Overview onGo={setTab} />}
      {tab === "users" && <Users myId={me.id} />}
      {tab === "videos" && <Videos />}
      {tab === "reports" && <Reports />}
      {tab === "cases" && <Cases />}
      {tab === "rewards" && <Rewards />}
      {tab === "log" && <Log />}
      {tab === "system" && <SystemTab />}
    </section>
  );
}

function Stat({ label, value, onClick }: { label: string; value: string; onClick?: () => void }) {
  return (
    <button type="button" className="card text-left hover:bg-zinc-50 disabled:hover:bg-white" onClick={onClick} disabled={!onClick}>
      <p className="text-sm text-muted">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
    </button>
  );
}

const sum = (r: Record<string, number>) => Object.values(r).reduce((a, b) => a + b, 0);

function Overview({ onGo }: { onGo: (t: Tab) => void }) {
  const { t, lang } = useT();
  const { data: s } = useLoad<Stats>("/api/admin/stats");
  if (!s) return <p className="text-muted">…</p>;
  const breakdown = (r: Record<string, number>, prefix: string) =>
    Object.entries(r)
      .map(([k, v]) => `${t(`${prefix}${k}`)} ${num(v, lang)}`)
      .join(" · ");
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Stat label={t("adm_users")} value={num(sum(s.users), lang)} onClick={() => onGo("users")} />
        <Stat label={t("adm_videos")} value={num(sum(s.videos), lang)} onClick={() => onGo("videos")} />
        <Stat label={t("adm_reports")} value={num(s.open_reports, lang)} onClick={() => onGo("reports")} />
        <Stat label={t("adm_cases")} value={num(sum(s.cases), lang)} onClick={() => onGo("cases")} />
        <Stat label={t("rewards")} value={taka(s.rewards_credited_bdt, lang)} onClick={() => onGo("rewards")} />
        <Stat label={t("adm_hidden")} value={num(s.hidden_videos, lang)} onClick={() => onGo("videos")} />
      </div>
      <div className="card text-sm space-y-1">
        <p>
          <b>{t("adm_users")}:</b> {breakdown(s.users, "role_")}
          {s.disabled_users > 0 && ` · ${t("adm_disabled")} ${num(s.disabled_users, lang)}`}
        </p>
        <p>
          <b>{t("adm_videos")}:</b> {breakdown(s.videos, "st_")}
        </p>
        {sum(s.cases) > 0 && (
          <p>
            <b>{t("adm_cases")}:</b> {breakdown(s.cases, "cs_")}
          </p>
        )}
        {sum(s.events) > 0 && (
          <p>
            <b>{t("adm_events")}:</b> {breakdown(s.events, "ev_")}
          </p>
        )}
      </div>
    </div>
  );
}

function Users({ myId }: { myId: string }) {
  const { t, lang } = useT();
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const { data, reload } = useLoad<{ users: AUser[] }>(`/api/admin/users?q=${encodeURIComponent(q)}&role=${role}`);
  const { run, err } = useAction(reload);
  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row gap-2">
        <input className="input flex-1" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("adm_search")} aria-label={t("adm_search")} />
        <select className="input sm:w-44" value={role} onChange={(e) => setRole(e.target.value)} aria-label={t("adm_role")}>
          <option value="">{t("adm_all")}</option>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {t(`role_${r}`)}
            </option>
          ))}
        </select>
      </div>
      {err && <p className="text-red-700 text-sm">{err}</p>}
      {data?.users.length === 0 && <p className="text-muted">{t("adm_empty")}</p>}
      <ul className="space-y-2">
        {data?.users.map((u) => (
          <li key={u.id} className={`card space-y-2 ${u.disabled ? "opacity-60" : ""}`}>
            <div className="flex flex-wrap justify-between gap-2">
              <div>
                <p className="font-semibold">
                  {u.display_name} {u.disabled && <span className="text-red-700 text-sm">· {t("adm_disabled")}</span>}
                </p>
                <p className="text-sm text-muted break-all">
                  {u.email}
                  {u.phone && ` · ${u.phone}`}
                </p>
                <p className="text-sm text-muted">
                  {fmtDate(u.created_at, lang)} · {t("uploads")} {num(u.uploads, lang)} · {t("adm_cases")} {num(u.cases, lang)} ·{" "}
                  {t("adm_credited")} {taka(u.credited_bdt, lang)}
                </p>
              </div>
              {u.id === myId ? (
                <span className="text-sm text-muted self-start">{t("adm_cantSelf")}</span>
              ) : (
                <div className="flex flex-wrap gap-2 self-start">
                  <select
                    className="input !w-auto !py-1.5"
                    value={u.role}
                    aria-label={`${t("adm_role")} ${u.email}`}
                    onChange={(e) => void run(`/api/admin/users/${u.id}/role`, { role: e.target.value })}
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {t(`role_${r}`)}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      const reason = u.disabled ? "" : prompt(t("adm_reasonPrompt"));
                      if (reason === null) return;
                      void run(`/api/admin/users/${u.id}/disable`, { disabled: !u.disabled, reason });
                    }}
                  >
                    {t(u.disabled ? "adm_enable" : "adm_disable")}
                  </button>
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Videos() {
  const { t, lang } = useT();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [moderation, setModeration] = useState("");
  const { data, reload } = useLoad<{ videos: AVideo[] }>(
    `/api/admin/videos?q=${encodeURIComponent(q)}&status=${status}&moderation=${moderation}`,
  );
  const { run, err } = useAction(reload);
  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row gap-2">
        <input className="input flex-1" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("adm_searchVideos")} aria-label={t("adm_searchVideos")} />
        <select className="input sm:w-40" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="status">
          <option value="">{t("adm_all")}</option>
          {["queued", "processing", "done", "failed"].map((s) => (
            <option key={s} value={s}>
              {t(`st_${s === "processing" ? "detecting" : s}`)}
            </option>
          ))}
        </select>
        <select className="input sm:w-40" value={moderation} onChange={(e) => setModeration(e.target.value)} aria-label={t("adm_hidden")}>
          <option value="">{t("adm_all")}</option>
          <option value="hidden">{t("adm_hidden")}</option>
          <option value="pending">{t("adm_openReports")}</option>
        </select>
      </div>
      {err && <p className="text-red-700 text-sm">{err}</p>}
      {data?.videos.length === 0 && <p className="text-muted">{t("adm_empty")}</p>}
      <ul className="space-y-2">
        {data?.videos.map((v) => {
          const hidden = v.moderation_status === "hidden";
          return (
            <li key={v.id} className={`card space-y-2 ${hidden ? "border-l-4 border-l-red-600" : ""}`}>
              <p className="text-sm">
                <Link className="underline font-semibold" href={`/v/${v.id}`} target="_blank">
                  {fmtDT(v.created_at, lang)} · {t(`cam_${v.camera_type}`).split(" (")[0]}
                </Link>{" "}
                · {t(`st_${v.status === "processing" ? "detecting" : v.status === "uploaded" ? "queued" : v.status}`)}
                {v.duration_s != null && ` · ${fmtTime(v.duration_s, lang)}`}
                {hidden && <span className="text-red-700"> · {t("adm_hidden")}</span>}
              </p>
              <p className="text-sm text-muted break-all">
                {v.uploader_email ?? t("adm_anonUpload")} · {num(v.events, lang)} {t("adm_events")}
                {v.open_reports > 0 && <span className="text-amber-800"> · {num(v.open_reports, lang)} {t("adm_openReports")}</span>}
              </p>
              {v.last_error && <p className="text-sm text-red-700 break-all">{v.last_error}</p>}
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-secondary text-sm"
                  onClick={() => {
                    const reason = hidden ? "" : prompt(t("adm_reasonPrompt"));
                    if (reason === null) return;
                    void run(`/api/admin/videos/${v.id}/moderation`, { status: hidden ? "ok" : "hidden", reason });
                  }}
                >
                  {t(hidden ? "adm_unhide" : "adm_hide")}
                </button>
                <button type="button" className="btn-secondary text-sm" onClick={() => void run(`/api/admin/videos/${v.id}/reanalyse`)}>
                  {t("adm_reanalyse")}
                </button>
                <button
                  type="button"
                  className="btn-secondary text-sm text-red-700"
                  onClick={() => {
                    const reason = prompt(t("adm_deleteConfirm"));
                    if (!reason || reason.trim().length < 3) return;
                    void run(`/api/admin/videos/${v.id}/delete`, { confirm: true, reason: reason.trim() });
                  }}
                >
                  {t("adm_delete")}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Reports() {
  const { t, lang } = useT();
  const [all, setAll] = useState(false);
  const { data, reload } = useLoad<{ reports: AReport[] }>(`/api/admin/reports?include_resolved=${all ? 1 : 0}`);
  const { run, err } = useAction(reload);
  return (
    <div className="space-y-3">
      <label className="flex gap-2 items-center text-sm">
        <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />
        {t("adm_showResolved")}
      </label>
      {err && <p className="text-red-700 text-sm">{err}</p>}
      {data?.reports.length === 0 && <p className="text-muted">{t("adm_empty")}</p>}
      <ul className="space-y-2">
        {data?.reports.map((r) => (
          <li key={r.id} className="card space-y-2">
            <p>“{r.reason}”</p>
            <p className="text-sm text-muted">
              {fmtDT(r.created_at, lang)} ·{" "}
              <Link className="underline" href={`/v/${r.video_id}`} target="_blank">
                {t("watchVideo")}
              </Link>
              {r.moderation_status === "hidden" && <span className="text-red-700"> · {t("adm_hidden")}</span>}
            </p>
            <div className="flex flex-wrap gap-2">
              {r.resolved_at ? (
                <span className="text-sm text-green-800">✓ {t("adm_resolved")}</span>
              ) : (
                <>
                  {r.moderation_status !== "hidden" && (
                    <button
                      type="button"
                      className="btn-secondary text-sm"
                      onClick={() => void run(`/api/admin/videos/${r.video_id}/moderation`, { status: "hidden", reason: r.reason })}
                    >
                      {t("adm_hide")}
                    </button>
                  )}
                  <button type="button" className="btn-secondary text-sm" onClick={() => void run(`/api/admin/reports/${r.id}/resolve`)}>
                    {t("adm_resolve")}
                  </button>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Cases() {
  const { t, lang } = useT();
  const [status, setStatus] = useState("");
  const { data } = useLoad<{ cases: Case[] }>(`/api/admin/cases?status=${status}`);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <select className="input sm:w-56" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="status">
          <option value="">{t("adm_all")}</option>
          {["submitted", "confirmed", "rejected", "fined", "dismissed"].map((s) => (
            <option key={s} value={s}>
              {t(`cs_${s}`)}
            </option>
          ))}
        </select>
        <Link className="btn-secondary self-center" href="/review">
          {t("reviewQueue")}
        </Link>
        <Link className="btn-secondary self-center" href="/police">
          {t("policeQueue")}
        </Link>
      </div>
      {data?.cases.length === 0 && <p className="text-muted">{t("adm_empty")}</p>}
      <ul className="space-y-2">
        {data?.cases.map((c) => (
          <li key={c.id} className="card text-sm space-y-1">
            <p>
              <Link className="underline font-semibold" href={`/v/${c.video_id}`} target="_blank">
                {c.event ? `${t(`ev_${c.event.type}`)} · ${fmtTime(c.event.start_s, lang)}` : c.event_id.slice(0, 8)}
              </Link>{" "}
              · <CaseBadge status={c.status} />
              {c.fine_bdt ? ` · ${t("fine")} ${taka(c.fine_bdt, lang)}` : ""}
              {c.police_ref && ` · ${c.police_ref}`}
            </p>
            <p className="text-muted">
              {fmtDT(c.created_at, lang)} · {t("uploadedBy")}: {c.uploader?.name ?? t("anonymous")}
            </p>
            {c.uploader_note && <p>“{c.uploader_note}”</p>}
            {c.review_note && (
              <p className="text-muted">
                {t("reviewNote")}: {c.review_note}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Rewards() {
  const { t, lang } = useT();
  const { data, reload } = useLoad<{ rewards: AReward[] }>("/api/admin/rewards");
  const { run, err } = useAction(reload);
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">{t("rewardsHint")}</p>
      {err && <p className="text-red-700 text-sm">{err}</p>}
      {data?.rewards.length === 0 && <p className="text-muted">{t("adm_empty")}</p>}
      <ul className="space-y-2">
        {data?.rewards.map((r) => (
          <li key={r.id} className={`card text-sm flex flex-wrap justify-between gap-2 ${r.status === "void" ? "opacity-60" : ""}`}>
            <div>
              <p className="font-semibold">
                {taka(r.amount_bdt, lang)} → {r.display_name ?? "?"} <span className="text-muted font-normal break-all">({r.email})</span>
              </p>
              <p className="text-muted">
                {fmtDT(r.created_at, lang)} · {t("fine")} {taka(r.fine_bdt, lang)}
                {r.status === "void" && ` · ${t("adm_voided")}: ${r.void_reason}`}
              </p>
            </div>
            {r.status === "credited" && (
              <button
                type="button"
                className="btn-secondary text-sm self-start"
                onClick={() => {
                  const reason = prompt(t("adm_reasonPrompt"));
                  if (!reason || reason.trim().length < 3) return;
                  void run(`/api/admin/rewards/${r.id}/void`, { reason: reason.trim() });
                }}
              >
                {t("adm_void")}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Log() {
  const { t, lang } = useT();
  const { data } = useLoad<{ log: ALog[] }>("/api/admin/log");
  if (data?.log.length === 0) return <p className="text-muted">{t("adm_empty")}</p>;
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted">
            <th className="py-1 pr-3">{t("adm_when")}</th>
            <th className="py-1 pr-3">{t("adm_who")}</th>
            <th className="py-1 pr-3">{t("adm_what")}</th>
          </tr>
        </thead>
        <tbody>
          {data?.log.map((l) => (
            <tr key={l.id} className="border-t border-zinc-100 align-top">
              <td className="py-1 pr-3 whitespace-nowrap">{fmtDT(l.created_at, lang)}</td>
              <td className="py-1 pr-3 break-all">{l.admin_email}</td>
              <td className="py-1 pr-3">
                <code>{l.action}</code> {l.target && <span className="text-muted">{l.target.slice(0, 8)}</span>}
                {l.detail && <span className="block text-muted">{l.detail}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SystemTab() {
  const { t, lang } = useT();
  const { data: s } = useLoad<System>("/api/admin/system");
  if (!s) return <p className="text-muted">…</p>;
  const rows: [string, string][] = [
    [t("adm_queue"), num(s.queue, lang)],
    [t("adm_detector"), s.detector],
    [t("adm_model"), s.model_version ?? "—"],
    [t("adm_rules"), s.rules_version ?? "—"],
    [t("adm_dailyLimit"), num(s.daily_upload_limit_per_ip, lang)],
    [t("adm_maxUpload"), `${num(s.max_upload_mb, lang)} MB`],
    [`${t("adm_disk")} (uploads)`, mb(s.disk_bytes.uploads, lang)],
    [`${t("adm_disk")} (results)`, mb(s.disk_bytes.results, lang)],
  ];
  return (
    <div className="space-y-3">
      <dl className="card grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd className="break-all">{v}</dd>
          </div>
        ))}
      </dl>
      {s.failed_jobs.length > 0 && (
        <div className="card text-sm space-y-1">
          <p className="font-semibold">{t("adm_failedJobs")}</p>
          {s.failed_jobs.map((j, i) => (
            <p key={i} className="break-all">
              <Link className="underline" href={`/v/${j.video_id}`} target="_blank">
                {j.video_id.slice(0, 8)}
              </Link>{" "}
              · {fmtDT(j.finished_at, lang)} · <span className="text-red-700">{j.error}</span>
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
