"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

// Wide screens: one sticky bar with the sections. Phones: a compact top bar plus a bottom tab bar, the
// way iOS and Android apps put their main sections within thumb reach (styled per platform in globals.css).
const SECTIONS = [
  { href: "/", key: "navHome", icon: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" },
  { href: "/map", key: "navMap", icon: "M9 4 3 6v14l6-2 6 2 6-2V4l-6 2zm0 0v14m6-12v14" },
  { href: "/rules", key: "navRules", icon: "M4 5a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2zm0 16V5m4 2h6m-6 4h6" },
  { href: "/news", key: "navNews", icon: "M4 5h13v14a2 2 0 0 0 2 2H6a2 2 0 0 1-2-2zm13 4h3v10a2 2 0 0 1-4 0M8 9h5m-5 4h5m-5 4h3" },
] as const;

function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#0b6e4f" />
      <path d="M11 26 14.5 6h3L21 26" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinejoin="round" />
      <path d="M16 9v2.5m0 3v2.5m0 3V22" stroke="#facc15" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

type Variant = "top" | "tabs";

function Sections({ variant, path }: { variant: Variant; path: string }) {
  const { t } = useT();
  const current = (href: string) => (href === "/" ? path === "/" : path.startsWith(href)) ? ("page" as const) : undefined;
  if (variant === "top")
    return SECTIONS.slice(1).map((s) => (
      <Link key={s.href} className="nav-link" href={s.href} aria-current={current(s.href)}>
        {t(s.key)}
      </Link>
    ));
  return (
    <ul className="grid grid-cols-4 h-16">
      {SECTIONS.map((s) => (
        <li key={s.href}>
          <Link href={s.href} aria-current={current(s.href)} className="rw-tab h-full flex flex-col items-center justify-center gap-0.5 text-[11px] font-medium">
            <span className="rw-tab-icon">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d={s.icon} />
              </svg>
            </span>
            <span className="leading-tight text-center">{t(s.key)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

// The current path is only known per request on dynamic pages, so it streams in; until then no tab is marked.
function SectionLinks({ variant }: { variant: Variant }) {
  return <Sections variant={variant} path={usePathname()} />;
}
function Nav({ variant }: { variant: Variant }) {
  return (
    <Suspense fallback={<Sections variant={variant} path="" />}>
      <SectionLinks variant={variant} />
    </Suspense>
  );
}

export default function Header() {
  const { t, lang, setLang } = useT();
  const { me, loading } = useAuth();

  return (
    <>
      <header className="rw-header sticky top-0 z-40 border-b border-zinc-200/80">
        <div className="mx-auto max-w-5xl px-4 h-14 flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2 font-semibold text-[17px] text-zinc-900 shrink-0">
            <Logo />
            <span>{t("appName")}</span>
          </Link>
          <nav className="hidden md:flex items-center gap-1 ml-4" aria-label={t("navMain")}>
            <Nav variant="top" />
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              className="btn-secondary text-sm"
              onClick={() => setLang(lang === "en" ? "bn" : "en")}
              lang={lang === "en" ? "bn" : "en"}
            >
              {t("langSwitch")}
            </button>
            {!loading &&
              (me ? (
                <>
                  {me.role === "admin" && (
                    <Link className="btn-secondary text-sm hidden sm:inline-flex" href="/admin">
                      {t("role_admin")}
                    </Link>
                  )}
                  <Link className="btn-secondary text-sm max-w-36 truncate" href="/account">
                    {me.display_name}
                  </Link>
                </>
              ) : (
                <Link className="btn-primary text-sm !min-h-0 py-1.5" href="/login">
                  {t("login")}
                </Link>
              ))}
          </div>
        </div>
      </header>

      <nav className="rw-tabbar md:hidden fixed inset-x-0 bottom-0 z-40 border-t border-zinc-200/80" aria-label={t("navMain")}>
        <Nav variant="tabs" />
      </nav>
    </>
  );
}
