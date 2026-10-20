import { NextRequest, NextResponse } from "next/server";
import { clearTokens, djangoFetch, REFRESH_COOKIE, setTokens, validCsrf } from "@/lib/server/auth";

function error(message: string, status: number) {
  return NextResponse.json({ error: { message } }, { status, headers: { "Cache-Control": "no-store" } });
}

export async function POST(request: NextRequest, context: { params: Promise<{ action: string }> }) {
  if (!validCsrf(request)) return error("요청 출처 또는 CSRF 토큰을 확인하세요.", 403);
  const { action } = await context.params;
  if (!["login", "register", "refresh", "logout"].includes(action)) return error("없는 경로입니다.", 404);

  const refresh = request.cookies.get(REFRESH_COOKIE)?.value;
  if ((action === "refresh" || action === "logout") && !refresh) {
    const response = action === "logout" ? new NextResponse(null, { status: 204 }) : error("다시 로그인하세요.", 401);
    clearTokens(response);
    return response;
  }

  let payload: unknown;
  if (action === "login" || action === "register") {
    try {
      payload = await request.json();
    } catch {
      return error("올바른 JSON을 보내주세요.", 400);
    }
  } else payload = { refresh };

  const paths: Record<string, string> = {
    login: "/auth/token", register: "/auth/register", refresh: "/auth/token/refresh", logout: "/auth/logout",
  };
  try {
    const upstream = await djangoFetch(paths[action], {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    if (action === "logout") {
      // A rejected token is already unusable. Network/server failures keep cookies for retry.
      if (upstream.status >= 500) return error("로그아웃을 완료하지 못했습니다. 다시 시도하세요.", 503);
      const response = new NextResponse(null, { status: 204 });
      clearTokens(response);
      return response;
    }
    const data = await upstream.json();
    if (!upstream.ok) {
      const response = NextResponse.json(data, { status: upstream.status, headers: { "Cache-Control": "no-store" } });
      if (action === "refresh" && upstream.status === 401) clearTokens(response);
      return response;
    }
    if (action === "register") {
      return NextResponse.json(data, { status: 201, headers: { "Cache-Control": "no-store" } });
    }
    // JWTs are never included in browser-visible response bodies.
    const response = NextResponse.json({ ok: true }, { headers: { "Cache-Control": "no-store" } });
    setTokens(response, data);
    return response;
  } catch {
    return error("서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.", 503);
  }
}
