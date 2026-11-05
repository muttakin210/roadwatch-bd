"use client";

import { useEffect, useState } from "react";
import { call } from "@/lib/auth";
import { num, useT, type Lang } from "@/lib/i18n";

type Item = { title: string; url: string; source: string; lang: "en" | "bn"; published: number | null; traffic: boolean };
type Resp = { items: Item[]; updated: number | null; sources: string[]; unavailable: string[] };

const L = {
  en: {
    title: "Today's news",
    traffic: "Roads & traffic",
    top: "Top news",
    any: "Bangla + English",
    bn: "বাংলা only",
    en: "English only",
    empty: "No stories in the last day and a half yet. Feeds refresh every 2 hours.",
    loading: "Loading…",
    failed: "News couldn't be loaded. Check your connection.",
    updated: "Updated",
    from: "Headlines and links from",
    note: "Stories open on the newspaper's own website. RoadWatch shows only headlines.",
    down: "Not reachable right now:",
    ago: (m: number) => (m < 60 ? `${m} min ago` : `${Math.round(m / 60)} h ago`),
  },
  bn: {
    title: "আজকের খবর",
    traffic: "সড়ক ও যানজট",
    top: "শীর্ষ খবর",
    any: "বাংলা + ইংরেজি",
    bn: "শুধু বাংলা",
    en: "শুধু ইংরেজি",
    empty: "গত দেড় দিনে এখনো কোনো খবর নেই। প্রতি ২ ঘণ্টায় হালনাগাদ হয়।",
    loading: "লোড হচ্ছে…",
    failed: "খবর লোড করা যায়নি। ইন্টারনেট সংযোগ দেখুন।",
    updated: "হালনাগাদ",
    from: "শিরোনাম ও লিংক যেখান থেকে:",
    note: "খবর সংবাদপত্রের নিজস্ব ওয়েবসাইটে খোলে। RoadWatch শুধু শিরোনাম দেখায়।",
    down: "এখন পাওয়া যাচ্ছে না:",
    ago: (m: number) => (m < 60 ? `${num(m, "bn")} মিনিট আগে` : `${num(Math.round(m / 60), "bn")} ঘণ্টা আগে`),
  },
} satisfies Record<Lang, unknown>;

export default function NewsPage() {
  const { lang } = useT();
  const s = L[lang];
  const [kind, setKind] = useState<"traffic" | "top">("traffic");
  const [only, setOnly] = useState<"" | "bn" | "en">("");
  const [data, setData] = useState<Resp | null>(null);
  const [err, setErr] = useState(false);
  const [now, setNow] = useState(0);

  useEffect(() => {
    let live = true;
    call<Resp>(`/api/news?kind=${kind}&lang=${only}&limit=40`).then(
      (r) => {
        if (!live) return;
        setData(r);
        setErr(false);
        setNow(Date.now() / 1000);
      },
      () => live && setErr(true),
    );
    return () => {
      live = false;
    };
  }, [kind, only]);

  const tab = (on: boolean) =>
    `rounded-full border px-3 py-1 text-sm ${on ? "bg-brand text-white border-brand" : "bg-white border-zinc-300 hover:bg-zinc-50"}`;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{s.title}</h1>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label={s.title}>
        {(["traffic", "top"] as const).map((k) => (
          <button key={k} type="button" className={tab(kind === k)} aria-pressed={kind === k} onClick={() => setKind(k)}>
            {s[k]}
          </button>
        ))}
        <select className="input !w-auto !py-1 text-sm" value={only} onChange={(e) => setOnly(e.target.value as typeof only)} aria-label={s.any}>
          <option value="">{s.any}</option>
          <option value="bn">{s.bn}</option>
          <option value="en">{s.en}</option>
        </select>
      </div>

      {err && <p className="card text-red-700">{s.failed}</p>}
      {!err && !data && <p className="text-muted">{s.loading}</p>}
      {data && data.items.length === 0 && <p className="card text-muted">{s.empty}</p>}
      {data && data.items.length > 0 && (
        <ul className="space-y-2">
          {data.items.map((it) => (
            <li key={it.url} className="card !py-3">
              <a className="font-medium hover:underline" href={it.url} target="_blank" rel="noopener noreferrer" lang={it.lang}>
                {it.title}
              </a>
              <p className="text-xs text-muted mt-1">
                {it.source}
                {it.published && now > 0 && ` · ${s.ago(Math.max(1, Math.round((now - it.published) / 60)))}`}
              </p>
            </li>
          ))}
        </ul>
      )}

      {data && (
        <p className="text-xs text-muted">
          {data.updated && now > 0 && `${s.updated} ${s.ago(Math.max(1, Math.round((now - data.updated) / 60)))}. `}
          {s.from} {data.sources.join(", ")}. {s.note}
          {data.unavailable.length > 0 && ` ${s.down} ${data.unavailable.join(", ")}.`}
        </p>
      )}
    </div>
  );
}
