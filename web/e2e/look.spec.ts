import { expect, test } from "@playwright/test";

// Per-platform look: <html data-os> is set before paint; phones get the bottom tab bar, wide screens the top nav.
test("platform tag and navigation fit the device", async ({ page, isMobile }, info) => {
  await page.goto("/");
  const os = await page.locator("html").getAttribute("data-os");
  expect(["ios", "android", "mac", "windows", "linux", "other"]).toContain(os);
  if (info.project.name === "android") expect(os).toBe("android");
  if (info.project.name === "iphone") expect(os).toBe("ios");

  const tabs = page.getByRole("navigation", { name: "Main sections" });
  await expect(tabs).toHaveCount(1); // only one of the two navs is shown at a time
  const map = tabs.getByRole("link", { name: "Road map" });
  await map.click();
  await expect(page).toHaveURL(/\/map$/);
  await expect(tabs.getByRole("link", { name: "Road map" })).toHaveAttribute("aria-current", "page");

  if (isMobile && (await page.viewportSize())!.width < 768) {
    // tab bar sits at the bottom of the screen
    const box = (await tabs.boundingBox())!;
    expect(box.y + box.height).toBeGreaterThan((await page.viewportSize())!.height - 2);
  }
});
