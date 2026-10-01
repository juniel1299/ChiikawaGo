import { NextResponse } from "next/server";
import { issueCsrf } from "@/lib/server/auth";

export async function GET() {
  const response = new NextResponse(null);
  const token = issueCsrf(response);
  const result = NextResponse.json({ csrf_token: token }, { headers: { "Cache-Control": "no-store" } });
  for (const cookie of response.cookies.getAll()) result.cookies.set(cookie);
  return result;
}
