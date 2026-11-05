"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { call, safeNext, useAuth, type Me } from "@/lib/auth";
import { useT } from "@/lib/i18n";

export default function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const { t } = useT();
  const { setMe } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
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
    <form onSubmit={submit} className="card space-y-4 max-w-md mx-auto">
      <h1 className="text-xl font-semibold">{t(mode === "login" ? "login" : "signup")}</h1>
      {mode === "signup" && (
        <label className="block space-y-1">
          <span className="text-sm">{t("displayName")}</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} required maxLength={60} autoComplete="name" />
        </label>
      )}
      <label className="block space-y-1">
        <span className="text-sm">{t("email")}</span>
        <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
      </label>
      <label className="block space-y-1">
        <span className="text-sm">{t("password")}</span>
        <input
          className="input"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={mode === "signup" ? 10 : undefined}
          maxLength={200}
          autoComplete={mode === "signup" ? "new-password" : "current-password"}
        />
        {mode === "signup" && <span className="text-xs text-muted">{t("passwordHint")}</span>}
      </label>
      {err && (
        <p className="text-red-700 text-sm" role="alert">
          {err}
        </p>
      )}
      <button type="submit" className="btn-primary w-full" disabled={busy}>
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
