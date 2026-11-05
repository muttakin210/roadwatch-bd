import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

// Forgot password: the login page links to /forgot (same answer for any email), and a one-time reset link
// sets a new password, logs the user in and can't be used twice.
const root = path.resolve(__dirname, "..", "..");
const py = path.join(root, "ml", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");

test("forgot password → reset link → new password works, old one doesn't", async ({ page, browser }) => {
  const email = `e2e-reset-${Date.now()}@example.com`;
  const oldPw = "correct horse battery";
  const newPw = "a brand new password";
  const form = () => page.locator("form:visible");

  await page.goto("/signup");
  await form().getByLabel("Your name").fill("Forgetful");
  await form().getByLabel("Email").fill(email);
  await form().getByLabel("Password").fill(oldPw);
  await form().getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "My account" })).toBeVisible();

  // a fresh browser (not logged in) asks for a reset
  const ctx = await browser.newContext();
  const p = await ctx.newPage();
  await p.goto("/login");
  await p.getByRole("link", { name: "Forgot password?" }).click();
  await expect(p.getByRole("heading", { name: "Reset your password" })).toBeVisible();
  await p.locator("form:visible").getByLabel("Email").fill(email);
  await p.getByRole("button", { name: "Send reset link" }).click();
  await expect(p.getByRole("status").filter({ hasText: /reset link/ })).toBeVisible();

  const link = execFileSync(py, ["manage.py", "reset-link", email], { cwd: path.join(root, "backend") })
    .toString()
    .trim();
  expect(link).toMatch(/^\/reset\?token=/);

  await p.goto(link);
  const f = p.locator("form:visible");
  await f.getByLabel("New password", { exact: true }).fill(newPw);
  await f.getByLabel("Repeat the new password").fill("something else entirely");
  await f.getByRole("button", { name: "Save new password" }).click();
  await expect(p.getByRole("alert").filter({ hasText: "not the same" })).toBeVisible();
  await f.getByLabel("Repeat the new password").fill(newPw);
  await f.getByRole("button", { name: "Save new password" }).click();
  await expect(p.getByRole("heading", { name: "My account" })).toBeVisible(); // logged in
  expect(new URL(p.url()).search).toBe(""); // token gone from the address bar

  // the link was one-time
  await p.goto(link);
  await p.locator("form:visible").getByLabel("New password", { exact: true }).fill("yet another password");
  await p.locator("form:visible").getByLabel("Repeat the new password").fill("yet another password");
  await p.getByRole("button", { name: "Save new password" }).click();
  await expect(p.getByText("invalid or has expired")).toBeVisible();
  await ctx.close();

  // the first browser was logged out by the reset; the old password no longer works, the new one does
  await page.goto("/login");
  await form().getByLabel("Email").fill(email);
  await form().getByLabel("Password").fill(oldPw);
  await form().getByRole("button", { name: "Log in" }).click();
  await expect(page.getByText("email or password is wrong")).toBeVisible();
  await form().getByLabel("Password").fill(newPw);
  await form().getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "My account" })).toBeVisible();
});
