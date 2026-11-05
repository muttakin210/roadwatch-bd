import type { Metadata } from "next";
import RulesPage from "@/components/RulesPage";

export const metadata: Metadata = {
  title: "Traffic rules & fines in Bangladesh · RoadWatch BD",
  description: "Road Transport Act 2018: rules and maximum fines for cars, motorcycles, buses, trucks, CNGs and pedestrians.",
};

export default function Page() {
  return <RulesPage />;
}
