import { Suspense } from "react";
import PublicProfile from "@/components/PublicProfile";

// params are runtime data under Cache Components: read them inside a Suspense boundary.
export default function ProfilePage({ params }: PageProps<"/u/[id]">) {
  return (
    <Suspense fallback={<p>…</p>}>
      {params.then(({ id }) => (
        <PublicProfile id={id} />
      ))}
    </Suspense>
  );
}
