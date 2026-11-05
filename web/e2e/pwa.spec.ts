import { expect, test } from "@playwright/test";

// The site is installable: valid manifest, icons served, service worker active, offline fallback works.
test("installable app: manifest, icons, service worker, offline page", async ({ page, context, browserName }) => {
  const res = await page.request.get("/manifest.webmanifest");
  expect(res.ok()).toBeTruthy();
  const m = await res.json();
  expect(m.display).toBe("standalone");
  expect(m.start_url).toBe("/");
  const sizes = m.icons.map((i: { sizes: string; purpose: string }) => `${i.sizes}/${i.purpose}`);
  expect(sizes).toEqual(expect.arrayContaining(["192x192/any", "512x512/any", "512x512/maskable"]));
  for (const src of [...m.icons.map((i: { src: string }) => i.src), "/apple-touch-icon.png"]) {
    const r = await page.request.get(src);
    expect(r.ok(), src).toBeTruthy();
    expect(r.headers()["content-type"]).toContain("image/png");
  }

  await page.goto("/");
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", /manifest/);
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute("href", "/apple-touch-icon.png");
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute("content", "#0b6e4f");

  // service worker takes control (Firefox in Playwright doesn't run service workers)
  test.skip(browserName === "firefox", "Playwright's Firefox has no service worker support");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);

  // API responses are never cached by the service worker
  const cached = await page.evaluate(async () => {
    const keys = await caches.keys();
    const urls: string[] = [];
    for (const k of keys) for (const r of await (await caches.open(k)).keys()) urls.push(new URL(r.url).pathname);
    return urls;
  });
  expect(cached.some((u) => u.startsWith("/api/"))).toBe(false);

  await context.setOffline(true);
  await page.goto("/account").catch(() => {});
  await expect(page.getByText(/RoadWatch/).first()).toBeVisible();
  await context.setOffline(false);
});
