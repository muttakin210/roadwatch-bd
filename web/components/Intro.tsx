"use client";

import { useT } from "@/lib/i18n";

export default function Intro() {
  const { t } = useT();
  return <p className="text-lg">{t("tagline")}</p>;
}
