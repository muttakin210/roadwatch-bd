import Intro from "@/components/Intro";
import UploadForm from "@/components/UploadForm";

export default function Home() {
  return (
    <div className="space-y-5">
      <Intro />
      <UploadForm />
    </div>
  );
}
