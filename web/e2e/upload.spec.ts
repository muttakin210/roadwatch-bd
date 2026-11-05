import { expect, test } from "@playwright/test";
import path from "node:path";

const CLIP = path.join(__dirname, "fixtures", "clip12s.mp4");

test("upload → processing → results, in Bangla and English", async ({ page }) => {
  const log: string[] = [];
  page.on("console", (m) => log.push(`[${m.type()}] ${m.text()}`));

  await page.goto("/");
  await expect(page.getByText("RoadWatch BD").first()).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles(CLIP);
  // metadata loaded → trim controls + first frame for arrows
  const start = page.getByLabel("Start", { exact: true });
  await expect(start).toBeVisible();
  await expect(page.locator("canvas").first()).toBeVisible();

  // trim the first second → forces the in-browser compression path
  await start.fill("1");
  // Draw a direction arrow matching the real traffic: this sample is a right-hand-traffic road,
  // so the left carriageway comes TOWARDS the camera (top → bottom).
  const canvas = page.locator("canvas").first();
  await canvas.scrollIntoViewIfNeeded(); // on a phone-sized viewport it's below the fold
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.3, box.y + box.height * 0.4);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.3, box.y + box.height * 0.9, { steps: 8 });
  await page.mouse.up();
  await expect(page.getByText("1 arrows drawn")).toBeVisible();

  await page.getByRole("button", { name: "Upload and analyse" }).click();
  await page.waitForURL(/\/v\/[0-9a-f]{32}$/, { timeout: 120_000 });
  await expect(page.getByRole("heading", { name: "Processing" })).toBeVisible();
  console.log("compression:", log.filter((l) => /compression/i.test(l)).join(" | ") || "ran (no fallback warning)");

  // the real pipeline runs on CPU: wait for results
  await expect(page.getByRole("heading", { name: "Results" })).toBeVisible({ timeout: 7 * 60_000 });
  const video = page.locator("section video"); // the results player
  await expect(video).toHaveAttribute("src", /\/annotated$/);
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState), { timeout: 30_000 }).toBeGreaterThan(0);
  const dims = await video.evaluate((v: HTMLVideoElement) => [v.videoWidth, v.videoHeight]);
  expect(dims[0]).toBeGreaterThan(0); // the browser could decode the H.264 output

  // JSON download is served
  const json = await page.request.get(page.url().replace("/v/", "/api/videos/") + "/events.json");
  expect(json.ok()).toBeTruthy();
  const report = await json.json();
  expect(report.rules_version).toBeTruthy();
  // a correct arrow must not produce wrong-way accusations against normal traffic
  const ww = report.events.filter((e: { type: string }) => e.type === "wrong_way");
  expect(ww).toHaveLength(0);
  console.log("notes:", JSON.stringify(report.notes), "events:", report.events.length);

  await page.screenshot({ path: "e2e/out/results-en.png", fullPage: true });
  await page.getByRole("button", { name: "বাংলা" }).click();
  await expect(page.getByRole("heading", { name: "ফলাফল" })).toBeVisible();
  await page.screenshot({ path: "e2e/out/results-bn.png", fullPage: true });

  // "Analyse another video" returns to a clean form (Cache Components keeps the old page mounted)
  await page.getByRole("link", { name: "আরেকটি ভিডিও বিশ্লেষণ করুন" }).click();
  await expect(page.getByRole("button", { name: "আপলোড ও বিশ্লেষণ করুন" })).toBeDisabled(); // no file chosen
  await expect(page.locator("form video")).toHaveCount(0);
  await page.goBack();

  // language choice survives a reload
  await page.reload();
  await expect(page.getByRole("heading", { name: "ফলাফল" })).toBeVisible();
});
