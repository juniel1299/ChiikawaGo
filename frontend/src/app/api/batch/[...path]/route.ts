import { NextRequest, NextResponse } from "next/server";
import { ACCESS_COOKIE, djangoFetch, validCsrf } from "@/lib/server/auth";

const uuid = "[0-9a-fA-F-]{36}";
const routes: Record<string, RegExp> = {
  GET: new RegExp(`^(capabilities|jobs|sources|schedules|schedules/${uuid}|executions|executions/${uuid})$`),
  POST: new RegExp(`^(schedules|jobs/${uuid}/runs|executions/${uuid}/(retry|confirm-failure))$`),
  PATCH: new RegExp(`^(jobs/${uuid}|schedules/${uuid})$`),
};

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const path = (await context.params).path.join("/");
  if (!routes[request.method]?.test(path)) return NextResponse.json({ error: "not_found" }, { status: 404 });
  if (request.method !== "GET" && !validCsrf(request)) return NextResponse.json({ error: "csrf_failed" }, { status: 403 });
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "authentication_failed" }, { status: 401 });
  const query = new URLSearchParams();
  for (const name of ["page", "page_size", "job", "status"]) {
    const value = request.nextUrl.searchParams.get(name);
    if (value !== null) query.set(name, value);
  }
  const headers: Record<string, string> = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  const key = request.headers.get("idempotency-key");
  if (key) headers["Idempotency-Key"] = key;
  try {
    const response = await djangoFetch(`/batch/${path}${query.size ? `?${query}` : ""}`, {
      method: request.method, headers,
      body: request.method === "GET" ? undefined : await request.text(),
    });
    return new NextResponse(await response.text(), {
      status: response.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json({ error: "upstream_unavailable" }, { status: 502 });
  }
}
export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
