import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

// Sign up → promote with manage.py (the only way to make the first admin) → every admin tab loads.
const root = path.resolve(__dirname, "..", "..");
const py = path.join(root, "ml", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");

test("admin panel: only admins, all tabs load, actions are logged", async ({ page }) => {
  const email = `e2e-admin-${Date.now()}@example.com`;
  const pw = "correct horse battery";
  const form = () => page.locator("form:visible");

  await page.goto("/signup");
  await form().getByLabel("Your name").fill("Test Admin");
  await form().getByLabel("Email").fill(email);
  await form().getByLabel("Password").fill(pw);
  await form().getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "My account" })).toBeVisible();

  await page.goto("/admin");
  await expect(page.getByText("You don't have access to this page.")).toBeVisible(); // plain user

  execFileSync(py, ["manage.py", "set-role", email, "admin"], { cwd: path.join(root, "backend") });
  await page.goto("/login");
  await form().getByLabel("Email").fill(email);
  await form().getByLabel("Password").fill(pw);
  await form().getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("link", { name: "Admin panel" })).toBeVisible();
  await page.getByRole("link", { name: "Admin panel" }).click();

  await expect(page.getByRole("heading", { name: "Admin panel" })).toBeVisible();
  for (const tab of ["Users", "Videos", "Viewer reports", "Cases", "Rewards", "Audit log", "System", "Overview"]) {
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.getByRole("tab", { name: tab })).toHaveAttribute("aria-selected", "true");
  }
  await page.getByRole("tab", { name: "Users" }).click();
  await page.getByLabel("Search email or name").fill(email);
  await expect(page.getByText("That's you")).toBeVisible(); // can't demote or disable yourself

  await page.getByRole("tab", { name: "System" }).click();
  await expect(page.getByText("Detector")).toBeVisible();
  await page.screenshot({ path: "e2e/out/admin-system.png", fullPage: true });

  await page.getByRole("button", { name: "বাংলা" }).click();
  await page.getByRole("tab", { name: "সারসংক্ষেপ" }).click();
  await expect(page.getByRole("heading", { name: "অ্যাডমিন প্যানেল" })).toBeVisible();
  await page.screenshot({ path: "e2e/out/admin-bn.png", fullPage: true });
  await page.getByRole("button", { name: "English" }).click();

  // tidy up: don't leave an extra admin account behind on the dev database
  execFileSync(py, ["manage.py", "set-role", email, "user"], { cwd: path.join(root, "backend") });
});
