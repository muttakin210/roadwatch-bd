import { expect, test } from "@playwright/test";

// The traffic-rules page: reachable from the header, filters by vehicle type, searchable, bilingual, cites the act.
test("traffic rules page: header link, vehicle filters, search, Bangla", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Traffic rules" }).click();
  await expect(page.getByRole("heading", { name: "Traffic rules & fines in Bangladesh" })).toBeVisible();
  const cards = page.locator("main li.card:visible, li.card:visible");

  await page.getByRole("button", { name: "Motorcycles" }).click();
  await expect(page.getByRole("button", { name: "Motorcycles" })).toHaveAttribute("aria-pressed", "true");
  const helmet = page.locator("li#helmet:visible");
  await expect(helmet).toContainText("Tk 10,000");
  await expect(helmet).toContainText("3 months");
  await expect(helmet).toContainText("s.49(1) চ");
  await expect(page.locator("li#fare-chart:visible")).toHaveCount(0); // a bus rule, not shown for motorcycles

  await page.getByRole("button", { name: "Buses & public transport" }).click();
  await expect(page.locator("li#parking:visible")).toContainText("RoadWatch can flag this");
  await expect(page.locator("li#fare-chart:visible")).toBeVisible();

  await page.getByRole("button", { name: "All rules" }).click();
  await page.getByLabel(/Search rules/).fill("mobile phone");
  await expect(cards).toHaveCount(1);
  await expect(cards.first()).toContainText("Tk 5,000");

  await page.getByLabel(/Search rules/).fill("");
  await page.getByRole("button", { name: "বাংলা" }).click();
  await expect(page.getByRole("heading", { name: "বাংলাদেশের ট্রাফিক আইন ও জরিমানা" })).toBeVisible();
  await expect(page.locator("li#helmet:visible")).toContainText("১০,০০০ টাকা");
  await expect(page.getByRole("link", { name: /bdlaws\.minlaw\.gov\.bd/ })).toBeVisible();
  await page.getByRole("button", { name: "English" }).click();
});
