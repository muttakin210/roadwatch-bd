"use client";

import { useMemo, useState } from "react";
import { num, useT, type Lang } from "@/lib/i18n";
import { CATS, CHECKED, rulesFor, SOURCE_URL, type Cat, type Penalty, type Rule } from "@/lib/rules";

const L = {
  en: {
    title: "Traffic rules & fines in Bangladesh",
    intro:
      "What the Road Transport Act 2018 requires, and the maximum punishment for breaking each rule. A court or mobile court decides the actual fine; it can be lower. Many offences allow prison or a fine or both.",
    all: "All rules",
    cat_everyone: "Everyone",
    cat_pedestrian: "Pedestrians",
    cat_car: "Cars & private vehicles",
    cat_motorcycle: "Motorcycles",
    cat_bus: "Buses & public transport",
    cat_truck: "Trucks & goods",
    cat_cng: "CNG, taxi, easy-bike",
    cat_papers: "Licence & papers",
    search: "Search rules (e.g. helmet, phone, parking)",
    upTo: "up to",
    fine: "Fine",
    jail: "Prison",
    or: "or both",
    points: "demerit point",
    pointsMany: "demerit points",
    rule: "Rule",
    penalty: "Penalty",
    detects: "RoadWatch can flag this in a video",
    none: "No rule matches.",
    count: "rules",
    keyTitle: "Good to know",
    k1: "Every driving licence starts with 12 points (s.11). Offences cut demerit points; when they run out the licence can be suspended or cancelled.",
    k2: "Repeat offence: up to double the maximum punishment, and never less than double the previous one (s.100).",
    k3: "Helping, encouraging or conspiring in an offence gets the same punishment as committing it (s.99).",
    k4: "Pedal rickshaws and vans are mostly governed by city corporation and local rules, but signs, signals and crossings (s.42) bind every road user.",
    source: "Source: Road Transport Act 2018 (Act No. 47 of 2018), official text on bdlaws.minlaw.gov.bd, checked",
    warn: "Not legal advice. A 2024 cabinet proposal to cut some of these fines (Daily Star, 13 March 2024) had not changed the official text when we checked. Check the official site for later amendments.",
    month: "month",
    months: "months",
    year: "year",
    years: "years",
    lakh: "lakh",
    tk: "Tk",
    min: "at least",
  },
  bn: {
    title: "বাংলাদেশের ট্রাফিক আইন ও জরিমানা",
    intro:
      "সড়ক পরিবহণ আইন, ২০১৮ অনুযায়ী কী মানতে হবে এবং প্রতিটি নিয়ম ভাঙলে সর্বোচ্চ কত শাস্তি। প্রকৃত জরিমানা আদালত বা ভ্রাম্যমাণ আদালত ঠিক করেন, যা কম হতে পারে। অনেক অপরাধে কারাদণ্ড, অর্থদণ্ড বা উভয় দণ্ড হতে পারে।",
    all: "সব নিয়ম",
    cat_everyone: "সবার জন্য",
    cat_pedestrian: "পথচারী",
    cat_car: "প্রাইভেট কার ও ব্যক্তিগত গাড়ি",
    cat_motorcycle: "মোটরসাইকেল",
    cat_bus: "বাস ও গণপরিবহণ",
    cat_truck: "ট্রাক ও পণ্যবাহী",
    cat_cng: "সিএনজি, ট্যাক্সি, ইজি-বাইক",
    cat_papers: "লাইসেন্স ও কাগজপত্র",
    search: "নিয়ম খুঁজুন (যেমন হেলমেট, মোবাইল, পার্কিং)",
    upTo: "সর্বোচ্চ",
    fine: "জরিমানা",
    jail: "কারাদণ্ড",
    or: "বা উভয় দণ্ড",
    points: "দোষসূচক পয়েন্ট",
    pointsMany: "দোষসূচক পয়েন্ট",
    rule: "নিয়ম",
    penalty: "শাস্তি",
    detects: "RoadWatch ভিডিওতে এটি শনাক্ত করতে পারে",
    none: "কোনো নিয়ম মেলেনি।",
    count: "টি নিয়ম",
    keyTitle: "জেনে রাখুন",
    k1: "প্রতিটি ড্রাইভিং লাইসেন্সে ১২ পয়েন্ট থাকে (ধারা ১১)। অপরাধে দোষসূচক পয়েন্ট কাটা যায়; পয়েন্ট শেষ হলে লাইসেন্স স্থগিত বা বাতিল হতে পারে।",
    k2: "একই অপরাধ আবার করলে সর্বোচ্চ দণ্ডের দ্বিগুণ পর্যন্ত, এবং আগের দণ্ডের দ্বিগুণের কম নয় (ধারা ১০০)।",
    k3: "অপরাধে সহায়তা, প্ররোচনা বা ষড়যন্ত্র করলে একই দণ্ড (ধারা ৯৯)।",
    k4: "প্যাডেল রিকশা ও ভ্যান মূলত সিটি কর্পোরেশন ও স্থানীয় বিধিতে নিয়ন্ত্রিত, তবে ট্রাফিক সাইন, সংকেত ও পারাপারের নিয়ম (ধারা ৪২) সব সড়ক ব্যবহারকারীর জন্য প্রযোজ্য।",
    source: "উৎস: সড়ক পরিবহণ আইন, ২০১৮ (২০১৮ সনের ৪৭ নং আইন), bdlaws.minlaw.gov.bd-এর সরকারি পাঠ, যাচাই",
    warn: "এটি আইনি পরামর্শ নয়। কিছু জরিমানা কমানোর ২০২৪ সালের মন্ত্রিসভার প্রস্তাব (ডেইলি স্টার, ১৩ মার্চ ২০২৪) যাচাইয়ের সময় সরকারি পাঠে যুক্ত হয়নি; পরবর্তী সংশোধনের জন্য সরকারি সাইট দেখুন।",
    month: "মাস",
    months: "মাস",
    year: "বছর",
    years: "বছর",
    lakh: "লক্ষ",
    tk: "টাকা",
    min: "কমপক্ষে",
  },
} as const;

type S = (typeof L)[Lang];

function money(n: number, lang: Lang, s: S) {
  if (n >= 100_000 && n % 100_000 === 0) {
    const v = num(n / 100_000, lang);
    return lang === "bn" ? `${v} ${s.lakh} ${s.tk}` : `${s.tk} ${v} ${s.lakh}`;
  }
  const v = num(n.toLocaleString("en-IN"), lang);
  return lang === "bn" ? `${v} ${s.tk}` : `${s.tk} ${v}`;
}

function period(m: number, lang: Lang, s: S) {
  if (m >= 12 && m % 12 === 0) return `${num(m / 12, lang)} ${m === 12 ? s.year : s.years}`;
  return `${num(m, lang)} ${m === 1 ? s.month : s.months}`;
}

function PenaltyBadges({ p, lang, s }: { p: Penalty; lang: Lang; s: S }) {
  const range = (r: { min?: number; max: number }, f: (n: number) => string) =>
    r.min ? `${s.min} ${f(r.min)}, ${s.upTo} ${f(r.max)}` : `${s.upTo} ${f(r.max)}`;
  return (
    <div className="flex flex-wrap gap-1.5 text-sm">
      {p.fineBdt && (
        <span className="rounded-full bg-red-50 border border-red-200 text-red-800 px-2.5 py-0.5 font-medium">
          {s.fine}: {range(p.fineBdt, (n) => money(n, lang, s))}
        </span>
      )}
      {p.jailMonths && (
        <span className="rounded-full bg-zinc-100 border border-zinc-300 px-2.5 py-0.5">
          {s.jail}: {range(p.jailMonths, (n) => period(n, lang, s))}
          {p.fineBdt && ` · ${s.or}`}
        </span>
      )}
      {p.points && (
        <span className="rounded-full bg-amber-50 border border-amber-300 text-amber-900 px-2.5 py-0.5">
          −{num(p.points, lang)} {p.points === 1 ? s.points : s.pointsMany}
        </span>
      )}
    </div>
  );
}

function RuleCard({ r, lang, s }: { r: Rule; lang: Lang; s: S }) {
  const sec = (x: string) => (lang === "bn" ? `ধারা ${num(x, lang)}` : `s.${x}`);
  return (
    <li className="card space-y-2" id={r.id}>
      <h3 className="font-semibold">{r.title[lang]}</h3>
      <p className="text-sm">{r.detail[lang]}</p>
      <PenaltyBadges p={r.p} lang={lang} s={s} />
      <p className="text-xs text-muted">
        {s.rule}: {sec(r.rule)} · {s.penalty}: {sec(r.penalty)}
        {r.detects && <span className="ml-2 text-brand font-medium">● {s.detects}</span>}
      </p>
    </li>
  );
}

export default function RulesPage() {
  const { lang } = useT();
  const s = L[lang];
  const [cat, setCat] = useState<Cat | "all">("all");
  const [q, setQ] = useState("");
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rulesFor(cat).filter(
      (r) => !needle || [r.title.en, r.title.bn, r.detail.en, r.detail.bn].some((x) => x.toLowerCase().includes(needle)),
    );
  }, [cat, q]);

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold">{s.title}</h1>
        <p className="text-sm">{s.intro}</p>
      </div>

      <div role="group" aria-label={s.title} className="flex flex-wrap gap-1.5">
        {(["all", ...CATS] as const).map((c) => (
          <button
            key={c}
            type="button"
            aria-pressed={cat === c}
            onClick={() => setCat(c)}
            className={`rounded-full border px-3 py-1 text-sm ${cat === c ? "bg-brand text-white border-brand" : "bg-white border-zinc-300 hover:bg-zinc-50"}`}
          >
            {c === "all" ? s.all : s[`cat_${c}`]}
          </button>
        ))}
      </div>

      <input className="input" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={s.search} aria-label={s.search} />
      <p className="text-sm text-muted" aria-live="polite">
        {lang === "bn" ? `${num(shown.length, lang)}${s.count}` : `${shown.length} ${s.count}`}
      </p>

      {shown.length === 0 ? <p className="card text-muted">{s.none}</p> : (
        <ul className="space-y-2">
          {shown.map((r) => (
            <RuleCard key={r.id} r={r} lang={lang} s={s} />
          ))}
        </ul>
      )}

      <section className="card space-y-2 text-sm">
        <h2 className="font-semibold">{s.keyTitle}</h2>
        <ul className="list-disc pl-5 space-y-1">
          <li>{s.k1}</li>
          <li>{s.k2}</li>
          <li>{s.k3}</li>
          <li>{s.k4}</li>
        </ul>
      </section>

      <p className="text-xs text-muted">
        {s.source} {num(CHECKED, lang)}:{" "}
        <a className="underline break-all" href={SOURCE_URL} target="_blank" rel="noopener noreferrer">
          {SOURCE_URL}
        </a>
        . {s.warn}
      </p>
    </div>
  );
}
