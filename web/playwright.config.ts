import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// End-to-end: real FastAPI backend + real ML pipeline + production Next build (PLAN §7 platform tests).
// Run: npm run build && npx playwright test   (needs ffmpeg on PATH and ../ml/.venv set up)
const root = path.resolve(__dirname, "..");
const py = path.join(root, "ml", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
// Other ports when the live site's backend already holds 8000: E2E_API_PORT=8100 E2E_WEB_PORT=3100 npx playwright test
const apiPort = process.env.E2E_API_PORT ?? "8000";
const webPort = process.env.E2E_WEB_PORT ?? "3000";

export default defineConfig({
  testDir: "./e2e",
  timeout: 8 * 60_000, // CPU-only detection takes minutes
  use: { baseURL: `http://127.0.0.1:${webPort}`, trace: "retain-on-failure" },
  // One project per platform family. The slow upload test (real ML on CPU) runs on the two phones only.
  projects: [
    { name: "android", use: { ...devices["Pixel 7"] } },
    { name: "iphone", use: { ...devices["iPhone 15"] } },
    { name: "ipad", use: { ...devices["iPad (gen 11)"] }, testIgnore: /upload\.spec/ },
    { name: "windows-linux-chrome", use: { ...devices["Desktop Chrome"] }, testIgnore: /upload\.spec/ },
    { name: "edge", use: { ...devices["Desktop Edge"] }, testIgnore: /upload\.spec/ },
    { name: "mac-safari", use: { ...devices["Desktop Safari"] }, testIgnore: /upload\.spec/ },
    { name: "firefox", use: { ...devices["Desktop Firefox"] }, testIgnore: /upload\.spec/ },
  ],
  webServer: [
    {
      command: `"${py}" -m uvicorn app:app --port ${apiPort}`,
      cwd: path.join(root, "backend"),
      url: `http://127.0.0.1:${apiPort}/`,
      env: { ROADWATCH_DATA: path.join(root, "data", "e2e"), PYTHONIOENCODING: "utf-8", ROADWATCH_NEWS: "0", ROADWATCH_AUTH_LIMIT: "500" },
      reuseExistingServer: true,
      timeout: 60_000,
      stdout: "pipe",
    },
    {
      command: `npx next start -p ${webPort}`,
      url: `http://127.0.0.1:${webPort}`,
      env: { ROADWATCH_API: `http://127.0.0.1:${apiPort}` },
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
