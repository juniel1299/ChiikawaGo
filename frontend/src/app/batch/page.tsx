import { cookies } from "next/headers";
import { ACCESS_COOKIE, djangoFetch } from "@/lib/server/auth";
import { SessionControls } from "@/features/auth/session-controls";
import { BatchConsole } from "@/features/batch/console";
import type { Initial } from "@/features/batch/types";

export const metadata = { title: "Batch 운영 | CHII WORLD" };
export default async function BatchPage() {
  const token = (await cookies()).get(ACCESS_COOKIE)?.value;
  if (!token) return <main><h1>Batch 운영</h1><SessionControls expired /></main>;
  const headers = { Authorization: `Bearer ${token}` };
  const caps = await djangoFetch("/batch/capabilities", { headers });
  if (caps.status === 401) return <main><SessionControls expired /></main>;
  if (caps.status === 403) return <main><h1>접근 권한이 없습니다.</h1><p>운영자에게 Batch 조회 권한을 요청하세요.</p></main>;
  if (!caps.ok) throw new Error("운영 정보를 불러오지 못했습니다.");
  const responses = await Promise.all(["jobs", "sources", "schedules", "executions"].map(path => djangoFetch(`/batch/${path}`, { headers })));
  if (responses.some(r => !r.ok)) throw new Error("운영 정보를 불러오지 못했습니다.");
  const [jobs, sources, schedules, executions] = await Promise.all(responses.map(r => r.json()));
  const initial: Initial = { capabilities: await caps.json(), jobs, sources, schedules, executions };
  return <main><h1>Batch 운영</h1><p>접수는 실행 성공을 뜻하지 않습니다. 실행 원장에서 결과를 확인하세요.</p><BatchConsole initial={initial} /><SessionControls /></main>;
}
