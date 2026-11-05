import type { Metadata } from "next";
import NewsPage from "@/components/NewsPage";

export const metadata: Metadata = { title: "Today's road & traffic news · RoadWatch BD" };

export default function Page() {
  return <NewsPage />;
}
