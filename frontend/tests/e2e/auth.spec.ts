import { expect, test } from "@playwright/test";

test("회원가입, HttpOnly 로그인, 갱신, 만료 화면 복구, 로그아웃", async ({ page, context }) => {
  const email = `e2e-${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("표시 이름").fill("산책자");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill("A-walk-in-the-park-2026!");
  await page.getByRole("button", { name: "가입하기" }).click();
  await expect(page).toHaveURL(/\/login\?registered=1/);
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill("A-walk-in-the-park-2026!");
  const loginResponse = page.waitForResponse("**/api/auth/login");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  expect(await (await loginResponse).json()).toEqual({ ok: true });
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByText(email)).toBeVisible();
  let cookies = await context.cookies();
  const oldRefresh = cookies.find(c => c.name === "chii_refresh")!.value;
  expect(cookies.find(c => c.name === "chii_access")!.httpOnly).toBe(true);
  expect(cookies.find(c => c.name === "chii_refresh")!.httpOnly).toBe(true);
  expect(await page.evaluate(() => document.cookie)).not.toContain("chii_access");
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  await page.getByRole("button", { name: "로그인 연장" }).click();
  await expect(page.getByRole("status")).toContainText("로그인을 연장했습니다.");
  cookies = await context.cookies();
  expect(cookies.find(c => c.name === "chii_refresh")!.value).not.toEqual(oldRefresh);

  // Expiration is represented by the browser removing the short-lived access cookie.
  await context.clearCookies({ name: "chii_access" });
  await page.reload();
  await expect(page.getByRole("heading", { name: "다시 이어가 볼까요?" })).toBeVisible();
  await page.getByRole("button", { name: "로그인 연장" }).click();
  await expect(page.getByText(email)).toBeVisible();

  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect((await context.cookies()).some(c => ["chii_access", "chii_refresh"].includes(c.name))).toBe(false);
  await page.goto("/account");
  await expect(page).toHaveURL(/\/login$/);
});

test("CSRF 없는 요청과 다른 Origin의 변경 요청을 차단한다", async ({ request }) => {
  expect((await request.post("/api/auth/login", { data: {} })).status()).toBe(403);
  const csrf = await (await request.get("/api/auth/csrf")).json();
  const response = await request.post("/api/auth/login", {
    headers: { Origin: "https://attacker.example", "X-CSRF-Token": csrf.csrf_token }, data: {},
  });
  expect(response.status()).toBe(403);
});
