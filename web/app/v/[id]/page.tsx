import { Suspense } from "react";
import VideoView from "@/components/VideoView";

// params are runtime data under Cache Components: read them inside a Suspense boundary.
export default function VideoPage({ params }: PageProps<"/v/[id]">) {
  return (
    <Suspense fallback={<p>…</p>}>
      {params.then(({ id }) => (
        <VideoView id={id} />
      ))}
    </Suspense>
  );
}
