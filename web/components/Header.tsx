"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

export default function Header() {
  const { t, lang, setLang } = useT();
  const { me, loading } = useAuth();
  return (
    <header className="border-b border-zinc-200 bg-white">
      <div className="mx-auto max-w-3xl px-4 py-3 flex items-center justify-between gap-3">
        <Link href="/" className="font-bold text-lg text-brand">
          {t("appName")}
        </Link>
        <nav className="flex flex-wrap items-center justify-end gap-2">
          <Link className="btn-secondary text-sm" href="/map">
            {t("navMap")}
          </Link>
          <Link className="btn-secondary text-sm" href="/rules">
            {t("navRules")}
          </Link>
          <Link className="btn-secondary text-sm" href="/news">
            {t("navNews")}
          </Link>
          {!loading &&
            (me ? (
              <>
                {me.role === "admin" && (
                  <Link className="btn-secondary text-sm" href="/admin">
                    {t("role_admin")}
                  </Link>
                )}
                <Link className="btn-secondary text-sm max-w-40 truncate" href="/account">
                  {me.display_name}
                </Link>
              </>
            ) : (
              <Link className="btn-secondary text-sm" href="/login">
                {t("login")}
              </Link>
            ))}
          <button
            type="button"
            className="btn-secondary text-sm"
            onClick={() => setLang(lang === "en" ? "bn" : "en")}
            lang={lang === "en" ? "bn" : "en"}
          >
            {t("langSwitch")}
          </button>
        </nav>
      </div>
    </header>
  );
}
