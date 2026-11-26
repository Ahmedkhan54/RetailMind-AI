import { expect, test } from "@playwright/test";
import { allNavigationItems } from "../../src/lib/navigation";

const viewports = [
  { name: "360px", width: 360, height: 800 },
  { name: "375px", width: 375, height: 812 },
  { name: "390px", width: 390, height: 844 },
  { name: "430px", width: 430, height: 932 },
  { name: "768px", width: 768, height: 1024 },
  { name: "1024px", width: 1024, height: 900 },
  { name: "1280px", width: 1280, height: 900 },
] as const;

for (const viewport of viewports) {
  test(`login is usable without horizontal page overflow at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/login", { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
    await expect(page.getByLabel("Work email")).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Password" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Show password" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Forgot password?" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

test("password visibility, registration, reset, and resend controls work in the real login UI", async ({ page }) => {
  await page.goto("/login", { waitUntil: "networkidle" });
  const password = page.getByRole("textbox", { name: "Password" });
  await expect(password).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(password).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Hide password" }).click();
  await expect(password).toHaveAttribute("type", "password");

  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByLabel("Full name")).toBeVisible();
  await expect(page.getByLabel("Phone (optional)")).toBeVisible();

  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("button", { name: "Forgot password?" }).click();
  await expect(page.getByRole("heading", { name: "Reset your password" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Send reset link" })).toBeVisible();
  await page.getByRole("button", { name: "Back to sign in" }).click();
  await page.getByRole("button", { name: "Resend confirmation email" }).click();
  await expect(page.getByRole("heading", { name: "Resend confirmation" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Resend confirmation" })).toBeVisible();
});

test("every workspace route resolves without a Next.js not-found response", async ({ page }) => {
  for (const item of allNavigationItems) {
    const response = await page.goto(item.href, { waitUntil: "domcontentloaded" });
    expect(response?.status(), `${item.href} should resolve`).toBe(200);
    await expect(page.locator("body")).toBeVisible();
  }
});
