"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore } from "react";
import { call, safeNext, useAuth, type Me } from "@/lib/auth";
import { useT } from "@/lib/i18n";

const noop = () => () => {};

export default function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const { t } = useT();
  const { setMe } = useAuth();
  const router = useRouter();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // false in the server HTML, true once React runs. The inputs are uncontrolled so text typed while the page
  // is still loading survives hydration; the button waits until React can handle the submit itself.
  const ready = useSyncExternalStore(noop, () => true, () => false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const email = String(f.get("email") ?? "");
    const password = String(f.get("password") ?? "");
    const name = String(f.get("name") ?? "");
    setBusy(true);
    setErr(null);
    try {
      const me =
        mode === "login"
          ? await call<Me>("/api/auth/login", "POST", { email, password })
          : await call<Me>("/api/auth/signup", "POST", { email, password, display_name: name });
      setMe(me);
      router.push(safeNext(new URLSearchParams(location.search).get("next")));
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : t("authFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    // method=post: should the browser ever submit natively, credentials must not end up in the URL
    <form onSubmit={submit} method="post" className="card space-y-4 max-w-md mx-auto">
      <h1 className="text-xl font-semibold">{t(mode === "login" ? "login" : "signup")}</h1>
      {mode === "signup" && (
        <label className="block space-y-1">
          <span className="text-sm">{t("displayName")}</span>
          <input className="input" name="name" required maxLength={60} autoComplete="name" />
        </label>
      )}
      <label className="block space-y-1">
        <span className="text-sm">{t("email")}</span>
        <input className="input" name="email" type="email" required autoComplete="email" />
      </label>
      <label className="block space-y-1">
        <span className="text-sm">{t("password")}</span>
        <input
          className="input"
          type="password"
          name="password"
          required
          minLength={mode === "signup" ? 10 : undefined}
          maxLength={200}
          autoComplete={mode === "signup" ? "new-password" : "current-password"}
        />
        {mode === "signup" && <span className="text-xs text-muted">{t("passwordHint")}</span>}
      </label>
      {mode === "login" && (
        <p className="text-sm text-right -mt-2">
          <Link className="underline" href="/forgot">
            {t("forgotLink")}
          </Link>
        </p>
      )}
      {err && (
        <p className="text-red-700 text-sm" role="alert">
          {err}
        </p>
      )}
      <button type="submit" className="btn-primary w-full" disabled={busy || !ready}>
        {t(mode === "login" ? "login" : "signup")}
      </button>
      <p className="text-sm text-muted">
        {t(mode === "login" ? "noAccount" : "haveAccount")}{" "}
        <Link className="underline" href={mode === "login" ? "/signup" : "/login"}>
          {t(mode === "login" ? "signup" : "login")}
        </Link>
      </p>
    </form>
  );
}
