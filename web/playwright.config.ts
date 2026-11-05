import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// End-to-end: real FastAPI backend + real ML pipeline + production Next build (PLAN §7 platform tests).
// Run: npm run build && npx playwright test   (needs ffmpeg on PATH and ../ml/.venv set up)
const root = path.resolve(__dirname, "..");
const py = path.join(root, "ml", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");

export default defineConfig({
  testDir: "./e2e",
  timeout: 8 * 60_000, // CPU-only detection takes minutes
  use: { baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure" },
  projects: [
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      command: `"${py}" -m uvicorn app:app --port 8000`,
      cwd: path.join(root, "backend"),
      url: "http://127.0.0.1:8000/",
      env: { ROADWATCH_DATA: path.join(root, "data", "e2e"), PYTHONIOENCODING: "utf-8" },
      reuseExistingServer: true,
      timeout: 60_000,
      stdout: "pipe",
    },
    {
      command: "npx next start -p 3000",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
