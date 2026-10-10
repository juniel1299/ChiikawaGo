import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { BatchConsole } from "@/features/batch/console";
import type { Initial } from "@/features/batch/types";
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), replace: vi.fn() }) }));
afterEach(() => vi.unstubAllGlobals());
const data: Initial = {
  capabilities: { view: true, run: true, manage: false },
  jobs: [{ id: "j", code: "expired_token_cleanup", name: "Cleanup", enabled: true, source_id: null, execution_policy: { soft_limit: 600, hard_limit: 660, max_retries: 0 } }],
  sources: [], schedules: [], executions: { count: 0, next: null, previous: null, results: [] },
};
function response(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status }); }
function reads(url: string) {
  if (url === "/api/auth/csrf") return response({ csrf_token: "csrf" });
  const key = url.replace("/api/batch/", "").split("?")[0] as keyof Initial;
  return response(data[key]);
}

test("응답 유실과 중복 클릭 후 같은 접수 키를 유지한다", async () => {
  const keys: string[] = [];
  let reject: (reason: Error) => void = () => {};
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      keys.push((init.headers as Record<string, string>)["Idempotency-Key"]);
      return new Promise<Response>((_, failure) => { reject = failure; });
    }
    return Promise.resolve(reads(url));
  }));
  render(<BatchConsole initial={data} />);
  const button = screen.getByRole("button", { name: /Run Now/ });
  fireEvent.click(button); fireEvent.click(button);
  await waitFor(() => expect(keys).toHaveLength(1));
  reject(new Error("연결 실패"));
  await screen.findByText("연결 실패");
  fireEvent.click(button);
  await waitFor(() => expect(keys).toHaveLength(2));
  expect(keys[0]).toBe(keys[1]);
  reject(new Error("연결 실패"));
});

test("조회 권한만 있으면 실행 및 설정 버튼을 제공하지 않는다", async () => {
  const readOnly = { ...data, capabilities: { view: true, run: false, manage: false } };
  vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(url.endsWith("capabilities") ? response(readOnly.capabilities) : reads(url))));
  render(<BatchConsole initial={readOnly} />);
  expect(screen.queryByRole("button", { name: /Run Now/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "작업 저장" })).not.toBeInTheDocument();
});

test("스케줄 입력 오류를 표시하고 운영 확인 전 stale 실패를 확정하지 않는다", async () => {
  const row = { id: "execution", job_id: "j", status: "running", requested_at: "2026-10-11T00:00:00Z", started_at: "2026-10-11T00:00:00Z", finished_at: null, attempt: 1, is_stale: true, safe_failure_message: "", retry_of_id: null, celery_task_id: "task", worker: "worker", result_summary: {}, input_snapshot: {}, next_attempt_at: null, dispatch_error_code: "", duration_seconds: 900 };
  const operator: Initial = { ...data, capabilities: { view: true, run: true, manage: true }, executions: { count: 1, next: null, previous: null, results: [row] } };
  const fetcher = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Promise.resolve(response({ error: { details: { cron_expression: "실행 가능한 Cron이 아닙니다." } } }, 400));
    if (url === "/api/auth/csrf") return Promise.resolve(response({ csrf_token: "csrf" }));
    if (url.endsWith("executions/execution")) return Promise.resolve(response(row));
    const key = url.replace("/api/batch/", "").split("?")[0] as keyof Initial;
    return Promise.resolve(response(operator[key]));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<BatchConsole initial={operator} />);
  fireEvent.click(screen.getByRole("button", { name: "스케줄 저장" }));
  await screen.findByText(/실행 가능한 Cron/);
  fireEvent.click(screen.getByRole("button", { name: /execution · running/ }));
  expect(await screen.findByText(/시간 초과만으로 종료를 보장하지 않습니다/)).toBeVisible();
  expect(screen.getByRole("checkbox", { name: /기존 실행이 종료/ })).toBeRequired();
  expect(screen.queryByRole("button", { name: /^Retry$/ })).not.toBeInTheDocument();
  expect(fetcher.mock.calls.some(([url]) => url.endsWith("confirm-failure"))).toBe(false);
});
