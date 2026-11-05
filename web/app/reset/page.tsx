import type { Metadata } from "next";
import { ResetForm } from "@/components/PasswordReset";

// The reset token is in the address: never send it on to other sites (map tiles, links) in a Referer header.
export const metadata: Metadata = { referrer: "no-referrer", robots: { index: false } };

export default function ResetPage() {
  return <ResetForm />;
}
