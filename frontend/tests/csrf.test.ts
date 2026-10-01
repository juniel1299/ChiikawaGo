// @vitest-environment node
import { afterEach, expect, test, vi } from "vitest";
import { NextRequest, NextResponse } from "next/server";
import { issueCsrf, setTokens, validCsrf } from "@/lib/server/auth";

afterEach(() => vi.unstubAllEnvs());

test("출처와 CSRF 토큰이 모두 일치해야 변경 요청을 허용한다", () => {
  vi.stubEnv("WEB_ORIGIN", "http://localhost:3000");
  const token = "a".repeat(64);
  const make = (origin: string, header: string) => new NextRequest("http://localhost:3000/api/auth/login", {
    method: "POST", headers: { origin, "x-csrf-token": header, cookie: `chii_csrf=${token}` },
  });
  expect(validCsrf(make("http://localhost:3000", token))).toBe(true);
  expect(validCsrf(make("http://attacker.example", token))).toBe(false);
  expect(validCsrf(make("http://localhost:3000", "b".repeat(64)))).toBe(false);
  expect(validCsrf(make("http://localhost:3000", ""))).toBe(false);
});

test("토큰 쿠키는 운영 기본값에서 HttpOnly, Secure, SameSite=Lax다", () => {
  vi.stubEnv("AUTH_COOKIE_SECURE", "true");
  const response = NextResponse.json({ ok: true });
  setTokens(response, { access: "private-access", refresh: "private-refresh" });
  expect(issueCsrf(response)).toMatch(/^[a-f0-9]{64}$/);
  for (const cookie of response.cookies.getAll()) {
    expect(cookie.httpOnly).toBe(true);
    expect(cookie.secure).toBe(true);
    expect(cookie.sameSite).toBe("lax");
    expect(cookie.domain).toBeUndefined();
  }
});
