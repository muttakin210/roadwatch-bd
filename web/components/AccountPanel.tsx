"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { call, isStaff, useAuth, type Case, type Me, type Privacy } from "@/lib/auth";
import { fmtTime, num, useT, type Lang } from "@/lib/i18n";

type MyVideo = { id: string; status: string; camera_type: string; created_at: number; cases: number };
type Rewards = {
  rewards: { id: string; case_id: string; fine_bdt: number; amount_bdt: number; status: string; created_at: number }[];
  total_credited_bdt: number;
  paid_out_bdt: number;
};

export const fmtDate = (s: number, lang: Lang) =>
  new Date(s * 1000).toLocaleDateString(lang === "bn" ? "bn-BD" : "en-GB", { day: "numeric", month: "short", year: "numeric" });

export const taka = (n: number, lang: Lang) => `৳${num(n.toLocaleString("en-IN"), lang)}`;

export function LoginNeeded() {
  const { t } = useT();
  return (
    <div className="card space-y-3 max-w-md mx-auto">
      <p>{t("loginToOwn")}</p>
      <div className="flex gap-2">
        <Link className="btn-primary" href={`/login?next=${encodeURIComponent(typeof location === "undefined" ? "/account" : location.pathname)}`}>
          {t("login")}
        </Link>
        <Link className="btn-secondary" href="/signup">
          {t("signup")}
        </Link>
      </div>
    </div>
  );
}

export default function AccountPanel() {
  const { t } = useT();
  const { me, loading, logout } = useAuth();
  if (loading) return <p className="text-muted">…</p>;
  if (!me) return <LoginNeeded />;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">{t("myAccount")}</h1>
        <div className="flex flex-wrap gap-2">
          {me.role === "admin" && (
            <Link className="btn-primary" href="/admin">
              {t("adminPanel")}
            </Link>
          )}
          {isStaff(me, "reviewer") && (
            <Link className="btn-secondary" href="/review">
              {t("reviewQueue")}
            </Link>
          )}
          {isStaff(me, "police") && (
            <Link className="btn-secondary" href="/police">
              {t("policeQueue")}
            </Link>
          )}
          <button type="button" className="btn-secondary" onClick={() => void logout()}>
            {t("logout")}
          </button>
        </div>
      </div>
      <ProfileCard me={me} />
      <PrivacyCard me={me} />
      <RewardsCard />
      <ReportsCard />
      <UploadsCard />
      <PasswordCard />
    </div>
  );
}

function ProfileCard({ me }: { me: Me }) {
  const { t } = useT();
  const { setMe } = useAuth();
  const [name, setName] = useState(me.display_name);
  const [phone, setPhone] = useState(me.phone ?? "");
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <form
      className="card space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          setMe(await call<Me>("/api/me", "PATCH", { display_name: name, phone }));
          setMsg(t("saved"));
        } catch (ex) {
          setMsg(ex instanceof Error ? ex.message : "error");
        }
      }}
    >
      <h2 className="font-semibold">{t("profile")}</h2>
      <p className="text-sm text-muted">
        {me.email} · {t(`role_${me.role}`)}
      </p>
      <label className="block space-y-1">
        <span className="text-sm">{t("displayName")}</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} required maxLength={60} />
      </label>
      <label className="block space-y-1">
        <span className="text-sm">{t("phone")}</span>
        <input className="input" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={20} autoComplete="tel" />
      </label>
      <div className="flex items-center gap-3">
        <button type="submit" className="btn-primary">
          {t("save")}
        </button>
        {msg && <span className="text-sm" role="status">{msg}</span>}
      </div>
    </form>
  );
}

const PRIVACY_KEYS: (keyof Privacy)[] = ["show_name", "profile_public", "share_contact", "show_locations"];

function PrivacyCard({ me }: { me: Me }) {
  const { t } = useT();
  const { setMe } = useAuth();
  const [busy, setBusy] = useState(false);
  const [pv, setPv] = useState<Privacy>(me.privacy); // optimistic: the box flips at once, reverts on error
  const [err, setErr] = useState(false);
  return (
    <section className="card space-y-3">
      <h2 className="font-semibold">{t("privacy")}</h2>
      <p className="text-sm text-muted">{t("privacyHint")}</p>
      {PRIVACY_KEYS.map((k) => (
        <label key={k} className="flex gap-2 items-start">
          <input
            type="checkbox"
            className="mt-1"
            checked={pv[k]}
            disabled={busy}
            onChange={async (e) => {
              const on = e.target.checked;
              setPv((old) => ({ ...old, [k]: on }));
              setBusy(true);
              setErr(false);
              try {
                const m = await call<Me>("/api/me", "PATCH", { privacy: { [k]: on } });
                setMe(m);
                setPv(m.privacy);
              } catch {
                setPv((old) => ({ ...old, [k]: !on }));
                setErr(true);
              } finally {
                setBusy(false);
              }
            }}
          />
          <span>{t(`pv_${k}`)}</span>
        </label>
      ))}
      {err && <p className="text-sm text-red-700">{t("saveFailed")}</p>}
      {me.privacy.profile_public && (
        <Link className="underline text-sm" href={`/u/${me.id}`}>
          {t("viewProfile")}
        </Link>
      )}
    </section>
  );
}

function RewardsCard() {
  const { t, lang } = useT();
  const [r, setR] = useState<Rewards | null>(null);
  useEffect(() => void call<Rewards>("/api/me/rewards").then(setR, () => {}), []);
  return (
    <section className="card space-y-2">
      <h2 className="font-semibold">{t("rewards")}</h2>
      <p className="text-sm text-muted">{t("rewardsHint")}</p>
      {r && (
        <>
          <div className="flex gap-6">
            <div>
              <p className="text-sm text-muted">{t("totalCredited")}</p>
              <p className="text-2xl font-semibold tabular-nums" data-testid="reward-total">
                {taka(r.total_credited_bdt, lang)}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted">{t("paidOut")}</p>
              <p className="text-2xl font-semibold tabular-nums">{taka(r.paid_out_bdt, lang)}</p>
            </div>
          </div>
          {r.rewards.length > 0 && (
            <ul className="text-sm space-y-1">
              {r.rewards.map((x) => (
                <li key={x.id}>
                  {fmtDate(x.created_at, lang)} · {t("fine")} {taka(x.fine_bdt, lang)} → {t("reward")} {taka(x.amount_bdt, lang)}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

function ReportsCard() {
  const { t, lang } = useT();
  const [cases, setCases] = useState<Case[] | null>(null);
  useEffect(() => void call<{ cases: Case[] }>("/api/me/cases").then((r) => setCases(r.cases), () => {}), []);
  return (
    <section className="card space-y-2">
      <h2 className="font-semibold">{t("myReports")}</h2>
      {cases?.length === 0 && <p className="text-sm text-muted">{t("noReports")}</p>}
      <ul className="space-y-2">
        {cases?.map((c) => (
          <li key={c.id} className="text-sm">
            <Link className="underline" href={`/v/${c.video_id}`}>
              {c.event ? `${t(`ev_${c.event.type}`)} · ${fmtTime(c.event.start_s, lang)}` : c.event_id.slice(0, 8)}
            </Link>{" "}
            · <CaseBadge status={c.status} />
            {c.fine_bdt ? ` · ${t("fine")} ${taka(c.fine_bdt, lang)}` : ""}
            {c.review_note && <span className="block text-muted">“{c.review_note}”</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function CaseBadge({ status }: { status: string }) {
  const { t } = useT();
  const color =
    status === "fined" || status === "confirmed"
      ? "bg-green-100 text-green-900"
      : status === "rejected" || status === "dismissed"
        ? "bg-zinc-200 text-zinc-800"
        : "bg-amber-100 text-amber-900";
  return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${color}`}>{t(`cs_${status}`)}</span>;
}

function UploadsCard() {
  const { t, lang } = useT();
  const [vids, setVids] = useState<MyVideo[] | null>(null);
  useEffect(() => void call<{ videos: MyVideo[] }>("/api/me/videos").then((r) => setVids(r.videos), () => {}), []);
  return (
    <section className="card space-y-2">
      <h2 className="font-semibold">{t("myUploads")}</h2>
      {vids?.length === 0 && (
        <p className="text-sm text-muted">
          {t("noUploads")}{" "}
          <Link className="underline" href="/">
            {t("newUpload")}
          </Link>
        </p>
      )}
      <ul className="space-y-1">
        {vids?.map((v) => (
          <li key={v.id} className="text-sm">
            <Link className="underline" href={`/v/${v.id}`}>
              {fmtDate(v.created_at, lang)} · {t(`cam_${v.camera_type}`).split(" (")[0]}
            </Link>{" "}
            · {t(`st_${v.status === "uploaded" ? "queued" : v.status === "processing" ? "detecting" : v.status}`)}
          </li>
        ))}
      </ul>
    </section>
  );
}

function PasswordCard() {
  const { t } = useT();
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const submit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      try {
        await call("/api/me/password", "POST", { current: cur, new: next });
        setCur("");
        setNext("");
        setMsg(t("saved"));
      } catch (ex) {
        setMsg(ex instanceof Error ? ex.message : "error");
      }
    },
    [cur, next, t],
  );
  return (
    <form className="card space-y-3" onSubmit={submit}>
      <h2 className="font-semibold">{t("changePassword")}</h2>
      <input className="input" type="password" placeholder={t("currentPassword")} aria-label={t("currentPassword")} value={cur} onChange={(e) => setCur(e.target.value)} required autoComplete="current-password" />
      <input className="input" type="password" placeholder={t("newPassword")} aria-label={t("newPassword")} value={next} onChange={(e) => setNext(e.target.value)} required minLength={10} autoComplete="new-password" />
      <div className="flex items-center gap-3">
        <button type="submit" className="btn-secondary">
          {t("save")}
        </button>
        {msg && <span className="text-sm" role="status">{msg}</span>}
      </div>
    </form>
  );
}
