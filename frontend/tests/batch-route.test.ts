// @vitest-environment node
import { afterEach, expect, test, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "@/app/api/batch/[...path]/route";

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });
const id = "11111111-1111-4111-8111-111111111111";
const context = (path: string) => ({ params: Promise.resolve({ path: path.split("/") }) });

test("Batch 변경은 CSRF를 요구하고 범용 중계를 허용하지 않는다", async () => {
  const outbound = vi.fn(); vi.stubGlobal("fetch", outbound);
  expect((await POST(new NextRequest(`http://localhost/api/batch/jobs/${id}/runs`, { method: "POST" }), context(`jobs/${id}/runs`))).status).toBe(403);
  expect((await GET(new NextRequest("http://localhost/api/batch/auth/token"), context("auth/token"))).status).toBe(404);
  outbound.mock.calls.forEach(() => { throw new Error("unexpected outbound"); });
});

test("Batch BFF는 쿠키 JWT와 접수 키만 허용된 API로 전달한다", async () => {
  vi.stubEnv("WEB_ORIGIN", "http://localhost:3000"); vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id }), { status: 202 }));
  vi.stubGlobal("fetch", fetcher);
  const csrf = "a".repeat(64);
  const request = new NextRequest(`http://localhost:3000/api/batch/jobs/${id}/runs`, { method: "POST", headers: { origin: "http://localhost:3000", "x-csrf-token": csrf, cookie: `chii_csrf=${csrf}; chii_access=private-token`, "idempotency-key": id }, body: "{}" });
  const response = await POST(request, context(`jobs/${id}/runs`));
  expect(response.status).toBe(202); expect(await response.json()).toEqual({ id });
  expect(fetcher.mock.calls[0][0]).toBe(`http://api:8000/api/v1/batch/jobs/${id}/runs`);
  expect(fetcher.mock.calls[0][1].headers).toMatchObject({ Authorization: "Bearer private-token", "Idempotency-Key": id });
});
