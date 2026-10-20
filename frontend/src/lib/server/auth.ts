import "server-only";

import { randomBytes, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

export const ACCESS_COOKIE = "chii_access";
export const REFRESH_COOKIE = "chii_refresh";
export const CSRF_COOKIE = "chii_csrf";

const cookieOptions = () => ({
  httpOnly: true,
  secure: process.env.AUTH_COOKIE_SECURE !== "false",
  sameSite: "lax" as const,
  path: "/",
});

export function issueCsrf(response: NextResponse) {
  const token = randomBytes(32).toString("hex");
  response.cookies.set(CSRF_COOKIE, token, { ...cookieOptions(), maxAge: 3600 });
  return token;
}

export function validCsrf(request: NextRequest) {
  const origin = process.env.WEB_ORIGIN;
  const header = request.headers.get("x-csrf-token") ?? "";
  const cookie = request.cookies.get(CSRF_COOKIE)?.value ?? "";
  return Boolean(
    origin && request.headers.get("origin") === origin &&
    /^[a-f0-9]{64}$/.test(header) && /^[a-f0-9]{64}$/.test(cookie) &&
    timingSafeEqual(Buffer.from(header), Buffer.from(cookie)),
  );
}

export function setTokens(response: NextResponse, tokens: { access: string; refresh: string }) {
  response.cookies.set(ACCESS_COOKIE, tokens.access, { ...cookieOptions(), maxAge: 300 });
  response.cookies.set(REFRESH_COOKIE, tokens.refresh, { ...cookieOptions(), maxAge: 604800 });
}

export function clearTokens(response: NextResponse) {
  for (const name of [ACCESS_COOKIE, REFRESH_COOKIE]) {
    response.cookies.set(name, "", { ...cookieOptions(), maxAge: 0 });
  }
}

export async function djangoFetch(path: string, init: RequestInit = {}) {
  const base = process.env.API_INTERNAL_URL;
  if (!base) throw new Error("API_INTERNAL_URL is required");
  return fetch(`${base}/api/v1${path}`, {
    ...init,
    cache: "no-store",
    signal: AbortSignal.timeout(8000),
  });
}

export type Account = { id: string; email: string; display_name: string; date_joined: string };

export async function currentAccount(): Promise<Account | null> {
  const token = (await cookies()).get(ACCESS_COOKIE)?.value;
  if (!token) return null;
  const response = await djangoFetch("/me", { headers: { Authorization: `Bearer ${token}` } });
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("계정 정보를 불러오지 못했습니다.");
  return response.json();
}
