"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore } from "react";
import { call, useAuth, type Me } from "@/lib/auth";
import { useT } from "@/lib/i18n";

const noop = () => () => {};
// false in the server HTML, true once React runs (inputs are uncontrolled so early typing survives hydration)
const useReady = () => useSyncExternalStore(noop, () => true, () => false);

export function ForgotForm() {
  const { t } = useT();
  const ready = useReady();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<null | { email_enabled: boolean }>(null);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const email = String(new FormData(e.currentTarget).get("email") ?? "");
    setBusy(true);
    setErr(null);
    try {
      setDone(await call<{ ok: boolean; email_enabled: boolean }>("/api/auth/forgot", "POST", { email }));
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} method="post" className="card space-y-4 max-w-md mx-auto">
      <h1 className="text-xl font-semibold">{t("forgotTitle")}</h1>
      {done ? (
        <p role="status" className="rounded-lg bg-amber-50 border border-amber-300 p-3 text-sm">
          {t(done.email_enabled ? "forgotSent" : "forgotNoEmail")}
        </p>
      ) : (
        <>
          <p className="text-sm text-muted">{t("forgotIntro")}</p>
          <label className="block space-y-1">
            <span className="text-sm">{t("email")}</span>
            <input className="input" name="email" type="email" required autoComplete="email" />
          </label>
          {err && (
            <p className="text-red-700 text-sm" role="alert">
              {err}
            </p>
          )}
          <button type="submit" className="btn-primary w-full" disabled={busy || !ready}>
            {t("forgotSend")}
          </button>
        </>
      )}
      <p className="text-sm">
        <Link className="underline" href="/login">
          {t("login")}
        </Link>
      </p>
    </form>
  );
}

const readToken = () => new URLSearchParams(location.search).get("token");

export function ResetForm() {
  const { t } = useT();
  const { setMe } = useAuth();
  const router = useRouter();
  const ready = useReady();
  const token = useSyncExternalStore(noop, readToken, () => null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [bad, setBad] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const pw = String(f.get("new") ?? "");
    if (pw !== String(f.get("confirm") ?? "")) return setErr(t("resetMismatch"));
    setBusy(true);
    setErr(null);
    try {
      const me = await call<Me>("/api/auth/reset", "POST", { token, new: pw });
      setMe(me);
      router.replace("/account"); // also drops the used token from the address bar and history
    } catch (ex) {
      if ((ex as { status?: number }).status === 400) setBad(true);
      else setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  }

  if (ready && (!token || bad)) {
    return (
      <div className="card space-y-3 max-w-md mx-auto">
        <h1 className="text-xl font-semibold">{t("resetTitle")}</h1>
        <p role="alert" className="text-sm">{t(bad ? "resetBad" : "resetNoToken")}</p>
        <Link className="btn-primary inline-block" href="/forgot">
          {t("resetAgain")}
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={submit} method="post" className="card space-y-4 max-w-md mx-auto">
      <h1 className="text-xl font-semibold">{t("resetTitle")}</h1>
      <label className="block space-y-1">
        <span className="text-sm">{t("resetNew")}</span>
        <input className="input" type="password" name="new" required minLength={10} maxLength={200} autoComplete="new-password" />
        <span className="text-xs text-muted">{t("passwordHint")}</span>
      </label>
      <label className="block space-y-1">
        <span className="text-sm">{t("resetConfirm")}</span>
        <input className="input" type="password" name="confirm" required minLength={10} maxLength={200} autoComplete="new-password" />
      </label>
      {err && (
        <p className="text-red-700 text-sm" role="alert">
          {err}
        </p>
      )}
      <button type="submit" className="btn-primary w-full" disabled={busy || !ready}>
        {t("resetSave")}
      </button>
    </form>
  );
}
