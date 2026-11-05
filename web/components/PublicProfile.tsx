"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";
import { fmtDate } from "@/components/AccountPanel";
import { call } from "@/lib/auth";
import { num, useT } from "@/lib/i18n";

const PinMap = dynamic(() => import("@/components/PinMap"), { ssr: false });

type Profile = {
  id: string;
  display_name: string;
  member_since: number;
  uploads: number;
  confirmed_reports: number;
  videos: { id: string; created_at: number; camera_type: string; lat?: number; lng?: number }[];
};

export default function PublicProfile({ id }: { id: string }) {
  const { t, lang } = useT();
  const [p, setP] = useState<Profile | null>(null);
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    call<Profile>(`/api/users/${encodeURIComponent(id)}`).then(setP, () => setMissing(true));
  }, [id]);
  if (missing) return <p className="card">{t("profileHidden")}</p>;
  if (!p) return <p className="text-muted">…</p>;
  const pins = p.videos.filter((v) => v.lat != null && v.lng != null) as { id: string; lat: number; lng: number }[];
  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">{p.display_name}</h1>
      <div className="grid grid-cols-3 gap-3">
        <div className="card">
          <p className="text-sm text-muted">{t("memberSince")}</p>
          <p className="font-semibold">{fmtDate(p.member_since, lang)}</p>
        </div>
        <div className="card">
          <p className="text-sm text-muted">{t("uploads")}</p>
          <p className="text-2xl font-semibold">{num(p.uploads, lang)}</p>
        </div>
        <div className="card">
          <p className="text-sm text-muted">{t("confirmedReports")}</p>
          <p className="text-2xl font-semibold">{num(p.confirmed_reports, lang)}</p>
        </div>
      </div>
      {pins.length > 0 && <PinMap pins={pins} />}
      <ul className="card space-y-1">
        {p.videos.map((v) => (
          <li key={v.id} className="text-sm">
            <Link className="underline" href={`/v/${v.id}`}>
              {fmtDate(v.created_at, lang)} · {t(`cam_${v.camera_type}`).split(" (")[0]}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
