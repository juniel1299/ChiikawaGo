import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

// Run against the local Compose stack used by this project's E2E suite.
function backend(code: string) {
  return execFileSync("docker", ["compose", "exec", "-T", "api", "python", "manage.py", "shell", "-c", code], { cwd: "..", encoding: "utf8" });
}

test("Batch 운영자 RSC, 권한별 버튼과 실제 스케줄 입력 오류", async ({ page }) => {
  const email = `batch-e2e-${Date.now()}@example.com`;
  const password = "Batch-test-only-password-2026!";
  backend(`from apps.accounts.models import User; from django.contrib.auth.models import Permission; u=User.objects.create_user(${JSON.stringify(email)}, ${JSON.stringify(password)}, display_name='Batch 테스트', is_staff=True); u.user_permissions.add(*Permission.objects.filter(content_type__app_label='batch', codename__in=['view_batch','manage_batch']))`);
  try {
    await page.goto("/login");
    await page.getByLabel("이메일").fill(email);
    await page.getByLabel("비밀번호").fill(password);
    await page.getByRole("button", { name: "로그인", exact: true }).click();
    await expect(page).toHaveURL(/\/account$/);
    await page.goto("/batch");
    await expect(page.getByRole("heading", { name: "Batch 운영", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: /만료 토큰 정리/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Run Now/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "작업 저장" })).toHaveCount(2);
    await page.getByLabel("Cron (분 시 일 월 요일)").first().fill("@daily");
    await page.getByRole("button", { name: "스케줄 저장" }).first().click();
    await expect(page.getByRole("status")).toContainText("5필드 Cron");
    await page.getByRole("button", { name: "로그아웃", exact: true }).click();
    await expect(page).toHaveURL(/\/login$/);
  } finally {
    backend(`from apps.accounts.models import User; from rest_framework_simplejwt.token_blacklist.models import OutstandingToken; OutstandingToken.objects.filter(user__email=${JSON.stringify(email)}).delete(); User.objects.filter(email=${JSON.stringify(email)}).delete()`);
  }
});
