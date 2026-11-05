import { expect, test } from "@playwright/test";

// Sign up → account panel → privacy toggles persist → log out → log in again. No ML needed.
test("account: sign up, privacy settings, log out and back in", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  const pw = "correct horse battery";
  // Cache Components keeps the previous page mounted (hidden): only use the visible form
  const form = () => page.locator("form:visible");

  await page.goto("/");
  await page.getByRole("link", { name: "Log in" }).first().click();
  await page.getByRole("link", { name: "Create account" }).click();
  await form().getByLabel("Your name").fill("Test Rahim");
  await form().getByLabel("Email").fill(email);
  await form().getByLabel("Password").fill(pw);
  await form().getByRole("button", { name: "Create account" }).click();

  await expect(page.getByRole("heading", { name: "My account" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Test Rahim" })).toBeVisible(); // header shows the user
  await expect(page.getByTestId("reward-total")).toHaveText("৳0");

  const showName = page.getByLabel(/Show my name on my uploads/);
  await expect(showName).not.toBeChecked(); // hidden by default
  await showName.check();
  await expect(showName).toBeEnabled();
  await page.getByLabel(/Public profile page/).check();
  await expect(page.getByRole("link", { name: "View my public profile" })).toBeVisible();

  await page.reload();
  await expect(page.getByLabel(/Show my name on my uploads/)).toBeChecked(); // saved server-side

  // the session cookie is HttpOnly: page scripts can't read it
  expect(await page.evaluate(() => document.cookie)).not.toContain("rw_session");

  await page.getByRole("link", { name: "View my public profile" }).click();
  await expect(page.getByRole("heading", { name: "Test Rahim" })).toBeVisible();
  await expect(page.getByText(email).filter({ visible: true })).toHaveCount(0); // contact never on the public profile

  await page.goto("/account");
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page.getByRole("link", { name: "Log in" }).first()).toBeVisible();
  await page.goto("/review");
  await expect(page.getByRole("link", { name: "Log in" }).last()).toBeVisible(); // staff page needs login

  await page.goto("/login?next=//evil.example");
  await form().getByLabel("Email").fill(email);
  await form().getByLabel("Password").fill("wrong password!");
  await form().getByRole("button", { name: "Log in" }).click();
  await expect(form().getByRole("alert")).toHaveText("email or password is wrong");
  await form().getByLabel("Password").fill(pw);
  await form().getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/account$/); // off-site ?next= ignored
  await page.goto("/review");
  await expect(page.getByText("You don't have access to this page.")).toBeVisible();

  await page.getByRole("button", { name: "বাংলা" }).click();
  await page.goto("/account");
  await expect(page.getByRole("heading", { name: "আমার অ্যাকাউন্ট" })).toBeVisible();
  await page.screenshot({ path: "e2e/out/account-bn.png", fullPage: true });
});
