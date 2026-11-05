import { expect, test } from "@playwright/test";

// Road map: header link, offline place search (English + Bangla), works offline; news page; common fines table.
test("road map: search places, and it still works offline", async ({ page, context }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Road map" }).click();
  await expect(page.getByRole("heading", { name: "Road situation map" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Road situation map" })).toBeVisible();

  const search = page.getByRole("searchbox", { name: /Search a place/ });
  await search.fill("Sylhet");
  await page.getByRole("option", { name: /Sylhet/ }).first().click();
  await expect(search).toHaveValue("Sylhet");

  await search.fill("সিলেট");                                   // Bangla names work too
  await expect(page.getByRole("option", { name: /সিলেট/ }).first()).toBeVisible();

  await context.setOffline(true);                               // no internet: search still answers
  await expect(page.getByRole("status").filter({ hasText: "You're offline" })).toBeVisible();
  await search.fill("Cox");
  await expect(page.getByRole("option", { name: /Cox's Bazar/ }).first()).toBeVisible();
  await context.setOffline(false);
});

test("news page and the common fines table", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "News" }).click();
  await expect(page.getByRole("heading", { name: "Today's news" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Roads & traffic" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText(/Headlines and links from/)).toBeVisible();   // test backend fetches no feeds

  await page.goto("/rules");
  const common = page.getByRole("region", { name: "Most common fines" });
  await expect(common.getByRole("row", { name: /Helmets for rider/ })).toContainText("Tk 10,000");
  await expect(common.getByRole("row", { name: /mobile phone/ })).toContainText("Tk 5,000");
});
