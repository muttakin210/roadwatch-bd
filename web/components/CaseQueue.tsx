"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CaseBadge, fmtDate, LoginNeeded, taka } from "@/components/AccountPanel";
import { call, isStaff, useAuth, type Case } from "@/lib/auth";
import { fmtTime, num, useT } from "@/lib/i18n";

/** Reviewer queue (submitted → confirm/reject) or police queue (confirmed → fined/no fine).
 *  The server enforces the role; this page only hides itself for everyone else. */
export default function CaseQueue({ kind }: { kind: "review" | "police" }) {
  const { t } = useT();
  const { me, loading } = useAuth();
  const [cases, setCases] = useState<Case[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const allowed = isStaff(me, kind === "review" ? "reviewer" : "police");

  const load = useCallback(() => {
    call<{ cases: Case[] }>(`/api/${kind}/cases`).then(
      (r) => setCases(r.cases),
      (e) => setErr(e.message),
    );
  }, [kind]);
  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  if (loading) return <p className="text-muted">…</p>;
  if (!me) return <LoginNeeded />;
  if (!allowed) return <p className="card">{t("forbidden")}</p>;
  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">{t(kind === "review" ? "reviewQueue" : "policeQueue")}</h1>
      <p className="text-sm text-muted">{t(kind === "review" ? "reportCaseHint" : "rewardsHint")}</p>
      {err && <p className="text-red-700">{err}</p>}
      {cases?.length === 0 && <p className="text-muted">{t("noCases")}</p>}
      <ul className="space-y-3">
        {cases?.map((c) => (
          <CaseItem key={c.id} c={c} kind={kind} onDone={load} />
        ))}
      </ul>
    </section>
  );
}

function CaseItem({ c, kind, onDone }: { c: Case; kind: "review" | "police"; onDone: () => void }) {
  const { t, lang } = useT();
  const [note, setNote] = useState("");
  // pre-filled with the legal maximum for this offence; police may lower it (never raise it above the law)
  const [fine, setFine] = useState(c.law ? String(c.law.max_bdt) : "");
  const [ref, setRef] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const act = async (body: Record<string, unknown>) => {
    setBusy(true);
    setErr(null);
    try {
      await call(`/api/${kind}/cases/${c.id}`, "POST", body);
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
    } finally {
      setBusy(false);
    }
  };

  const e = c.event;
  return (
    <li className="card space-y-2">
      <p className="font-semibold">
        {e ? `${t(`ev_${e.type}`)}${e.vehicle_class ? ` (${t(`cls_${e.vehicle_class}`)})` : ""}` : c.event_id}
        {e && ` · ${fmtTime(e.start_s, lang)}–${fmtTime(e.end_s, lang)} · ${t("confidence")} ${num((e.confidence ?? 0).toFixed(2), lang)}`}
      </p>
      <p className="text-sm text-muted">
        {fmtDate(c.created_at, lang)} · <CaseBadge status={c.status} />
      </p>
      {c.uploader_note && <p className="text-sm">“{c.uploader_note}”</p>}
      {c.review_note && kind === "police" && <p className="text-sm text-muted">{t("reviewNote")}: {c.review_note}</p>}
      <p className="text-sm">
        {t("uploadedBy")}: {c.uploader?.name ?? t("anonymous")} · {t("contact")}:{" "}
        {c.uploader?.contact ? [c.uploader.contact.email, c.uploader.contact.phone].filter(Boolean).join(", ") : t("notShared")}
      </p>
      {c.law && (
        <p className="text-sm rounded-lg bg-amber-50 border border-amber-300 p-2">
          {t("lawBroken")}: <b>{c.law[lang]}</b> ·{" "}
          {lang === "bn" ? `ধারা ${num(c.law.rule, lang)} → ধারা ${num(c.law.penalty, lang)}` : `s.${c.law.rule} → s.${c.law.penalty}`} ·{" "}
          {t("legalMax")} {taka(c.law.max_bdt, lang)} ·{" "}
          <Link className="underline" href={`/rules#${c.law.rule_id}`} target="_blank">
            {t("navRules")}
          </Link>
          <span className="block text-xs text-muted">{t("lawSuggestNote")}</span>
        </p>
      )}
      <Link className="btn-secondary text-sm" href={`/v/${c.video_id}`} target="_blank">
        {t("watchVideo")}
      </Link>
      {c.own ? (
        <p className="text-sm text-muted">{t("ownCase")}</p>
      ) : kind === "review" ? (
        <div className="flex flex-col sm:flex-row gap-2">
          <input className="input flex-1" value={note} onChange={(x) => setNote(x.target.value)} placeholder={t("reviewNote")} aria-label={t("reviewNote")} maxLength={1000} />
          <button type="button" className="btn-primary" disabled={busy} onClick={() => act({ decision: "confirm", note })}>
            {t("confirm")}
          </button>
          <button type="button" className="btn-secondary" disabled={busy} onClick={() => act({ decision: "reject", note })}>
            {t("reject")}
          </button>
        </div>
      ) : (
        <form
          className="flex flex-col sm:flex-row gap-2"
          onSubmit={(x) => {
            x.preventDefault();
            void act({ decision: "fined", fine_bdt: Number(fine), police_ref: ref });
          }}
        >
          <input className="input sm:w-32" type="number" min={1} max={c.law?.max_bdt ?? 100000} required value={fine} onChange={(x) => setFine(x.target.value)} placeholder={t("fineAmount")} aria-label={t("fineAmount")} />
          <input className="input flex-1" value={ref} onChange={(x) => setRef(x.target.value)} placeholder={t("policeRef")} aria-label={t("policeRef")} maxLength={100} />
          <button type="submit" className="btn-primary" disabled={busy}>
            {t("issueFine")}
            {fine && Number(fine) > 0 && ` · ${t("reward")} ${taka(Math.round(Number(fine) * 0.2), lang)}`}
          </button>
          <button type="button" className="btn-secondary" disabled={busy} onClick={() => act({ decision: "dismissed", police_ref: ref })}>
            {t("noFine")}
          </button>
        </form>
      )}
      {err && <p className="text-red-700 text-sm">{err}</p>}
    </li>
  );
}
