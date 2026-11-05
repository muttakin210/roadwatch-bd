"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n";

export default function Header() {
  const { t, lang, setLang } = useT();
  return (
    <header className="border-b border-zinc-200 bg-white">
      <div className="mx-auto max-w-3xl px-4 py-3 flex items-center justify-between gap-3">
        <Link href="/" className="font-bold text-lg text-brand">
          {t("appName")}
        </Link>
        <button
          type="button"
          className="btn-secondary text-sm"
          onClick={() => setLang(lang === "en" ? "bn" : "en")}
          lang={lang === "en" ? "bn" : "en"}
        >
          {t("langSwitch")}
        </button>
      </div>
    </header>
  );
}
