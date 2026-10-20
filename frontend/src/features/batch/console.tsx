"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { SessionControls } from "@/features/auth/session-controls";
import type { Execution, Initial, Job, Schedule } from "./types";
import styles from "./console.module.css";

const when = (value: string | null) => value ? new Date(value).toLocaleString() : "—";
export function BatchConsole({ initial }: { initial: Initial }) {
  const [data, setData] = useState(initial);
  const [message, setMessage] = useState("");
  const [expired, setExpired] = useState(false);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const keys = useRef(new Map<string, string>());
  const [jobFilter, setJobFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Execution | null>(null);

  const reload = useCallback(async () => {
    const query = new URLSearchParams({ page: String(page) });
    if (jobFilter) query.set("job", jobFilter);
    if (statusFilter) query.set("status", statusFilter);
    const paths = ["capabilities", "jobs", "sources", "schedules", `executions?${query}`];
    const responses = await Promise.all(paths.map(p => fetch(`/api/batch/${p}`, { cache: "no-store" })));
    if (responses.some(r => r.status === 401)) { setExpired(true); return; }
    if (responses.some(r => !r.ok)) throw new Error("운영 정보를 갱신하지 못했습니다.");
    const [capabilities, jobs, sources, schedules, executions] = await Promise.all(responses.map(r => r.json()));
    setData({ capabilities, jobs, sources, schedules, executions });
    setExpired(false);
    if (selected?.id) {
      const response = await fetch(`/api/batch/executions/${selected.id}`, { cache: "no-store" });
      if (response.ok) setSelected(await response.json());
    }
  }, [page, jobFilter, statusFilter, selected?.id]);

  useEffect(() => {
    const refresh = () => { if (document.visibilityState === "visible") void reload().catch(() => setMessage("갱신에 실패했습니다.")); };
    refresh();
    const timer = setInterval(refresh, 10000);
    document.addEventListener("visibilitychange", refresh);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", refresh); };
  }, [reload]);

  async function mutate(path: string, method: string, body: unknown, idempotent = false) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setMessage("");
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (idempotent) {
        if (!keys.current.has(path)) keys.current.set(path, crypto.randomUUID());
        headers["Idempotency-Key"] = keys.current.get(path)!;
      }
      const csrf = await fetch("/api/auth/csrf", { cache: "no-store" });
      if (!csrf.ok) throw new Error("보안 토큰을 가져오지 못했습니다.");
      headers["X-CSRF-Token"] = (await csrf.json()).csrf_token;
      const response = await fetch(`/api/batch/${path}`, { method, headers, body: JSON.stringify(body) });
      if (response.status === 401) { setExpired(true); return; }
      const payload = await response.json();
      if (!response.ok) {
        // A transport/server failure may follow a committed acceptance; keep its key.
        if (response.status < 500 && response.status !== 401) keys.current.delete(path);
        throw new Error(payload.error?.details ? JSON.stringify(payload.error.details) : "요청을 처리하지 못했습니다.");
      }
      keys.current.delete(path);
      setMessage(response.status === 202 ? "실행을 접수했습니다. 이력에서 결과를 확인하세요." : "처리했습니다.");
      if ("status" in payload) setSelected(payload);
      await reload();
    } catch (error) { setMessage(error instanceof Error ? error.message : "연결에 실패했습니다. 재시도하면 같은 접수 키를 사용합니다."); }
    finally { lock.current = false; setBusy(false); }
  }

  async function detail(id: string) {
    const response = await fetch(`/api/batch/executions/${id}`, { cache: "no-store" });
    if (response.status === 401) { setExpired(true); return; }
    if (!response.ok) { setMessage("상세 조회에 실패했습니다."); return; }
    setSelected(await response.json());
  }

  return <div className={`stack ${styles.console}`}>
    {message && <p role="status">{message}</p>}
    {expired && <SessionControls expired />}
    <h2>작업</h2>
    {data.jobs.map(job => <section key={job.id}>
      <h3>{job.name} · {job.enabled ? "활성" : "비활성"}</h3>
      <p>제한 {job.execution_policy.soft_limit}/{job.execution_policy.hard_limit}초 · 자동 재시도 최대 {job.execution_policy.max_retries}회</p>
      <p>마지막 실행: {job.last_execution_status ?? "없음"} {job.last_execution_id && <button className="secondary" onClick={() => void detail(job.last_execution_id!)}>마지막 결과</button>} / 현재 실행: {job.current_execution_id ?? "없음"}</p>
      <p>다음 예정: {when(data.schedules.find(s => s.job_id === job.id)?.next_run_at ?? null)}</p>
      {data.capabilities.run && <button disabled={busy || !job.enabled} onClick={() => mutate(`jobs/${job.id}/runs`, "POST", {}, true)}>Run Now · {job.name}</button>}
      {data.capabilities.manage && <>
        <JobForm key={`${job.id}:${job.enabled}:${job.source_id}`} job={job} data={data} busy={busy} save={body => mutate(`jobs/${job.id}`, "PATCH", body)} />
        <ScheduleForm key={data.schedules.find(s => s.job_id === job.id)?.id ?? job.id} job={job} schedule={data.schedules.find(s => s.job_id === job.id)} busy={busy} save={(id, body) => mutate(id ? `schedules/${id}` : "schedules", id ? "PATCH" : "POST", body)} />
      </>}
    </section>)}
    <h2>실행 이력</h2>
    <label>작업 필터<select value={jobFilter} onChange={e => { setJobFilter(e.target.value); setPage(1); }}><option value="">전체</option>{data.jobs.map(j => <option key={j.id} value={j.id}>{j.name}</option>)}</select></label>
    <label>상태 필터<select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1); }}><option value="">전체</option>{["queued", "running", "retry_wait", "success", "failed"].map(s => <option key={s}>{s}</option>)}</select></label>
    <p>{data.executions.count}건 · {page}페이지</p>
    {data.executions.results.map(e => <article key={e.id}><button className="secondary" onClick={() => void detail(e.id)}>{e.id} · {e.status}</button><p>{when(e.requested_at)} · 시도 {e.attempt}{e.is_stale && " · 실행 종료 확인 필요"}</p></article>)}
    <button disabled={!data.executions.previous} onClick={() => setPage(p => p - 1)}>이전</button><button disabled={!data.executions.next} onClick={() => setPage(p => p + 1)}>다음</button>
    {selected && <section><h2>실행 상세</h2><p>{selected.id} · {selected.status}</p>
      <p>시작 {when(selected.started_at)} / 종료 {when(selected.finished_at)} / 소요 {selected.duration_seconds?.toFixed(1) ?? "—"}초</p>
      <p>Worker: {selected.worker || "—"} / Task: {selected.celery_task_id || "동기 실행"}</p>
      <p>이전 실패: {selected.retry_of_id || "—"} / 다음 시도: {when(selected.next_attempt_at)}</p>
      <p>{selected.safe_failure_message} {selected.dispatch_error_code}</p>
      <pre>{JSON.stringify(selected.result_summary, null, 2)}</pre>
      <button onClick={() => void detail(selected.id)}>상세 새로고침</button>
      {data.capabilities.run && selected.status === "failed" && <button disabled={busy} onClick={() => mutate(`executions/${selected.id}/retry`, "POST", {}, true)}>Retry</button>}
      {data.capabilities.run && data.capabilities.manage && selected.is_stale && <form onSubmit={e => { e.preventDefault(); void mutate(`executions/${selected.id}/confirm-failure`, "POST", { worker_stopped: true }); }}>
        <p>시간 초과만으로 종료를 보장하지 않습니다. 기존 Worker 실행이 끝났는지 확인하세요.</p>
        <label><input type="checkbox" required />기존 실행이 종료됐음을 확인했습니다.</label><button disabled={busy}>실패 확정</button>
      </form>}
    </section>}
  </div>;
}

function JobForm({ job, data, busy, save }: { job: Job; data: Initial; busy: boolean; save: (body: unknown) => void }) {
  return <form onSubmit={e => { e.preventDefault(); const values = new FormData(e.currentTarget); save({ enabled: values.has("enabled"), source_id: values.get("source") || null }); }}>
    <label><input name="enabled" type="checkbox" defaultChecked={job.enabled} />작업 활성</label>
    {job.code === "news_collection" && <label>수집 출처<select name="source" defaultValue={job.source_id ?? ""}><option value="">선택 없음</option>{data.sources.map(s => <option key={s.id} value={s.id}>{s.name}{!s.is_active && " (비활성)"}</option>)}</select></label>}
    <button disabled={busy}>작업 저장</button>
  </form>;
}
function ScheduleForm({ job, schedule, busy, save }: { job: Job; schedule?: Schedule; busy: boolean; save: (id: string | undefined, body: unknown) => void }) {
  return <form onSubmit={e => {
    e.preventDefault(); const values = new FormData(e.currentTarget);
    save(schedule?.id, { ...(!schedule ? { job_id: job.id } : {}), cron_expression: values.get("cron"), timezone: values.get("zone"), enabled: values.has("enabled"), starts_at: values.get("start") || null, ends_at: values.get("end") || null });
  }}>
    <label>Cron (분 시 일 월 요일)<input name="cron" required defaultValue={schedule?.cron_expression ?? "0 9 * * *"} /></label>
    <label>시간대<select name="zone" defaultValue={schedule?.timezone ?? "Asia/Seoul"}><option>Asia/Seoul</option><option>UTC</option></select></label>
    <label>시작 (UTC ISO 8601)<input name="start" placeholder="2026-11-01T00:00:00Z" defaultValue={schedule?.starts_at ?? ""} /></label>
    <label>종료 (UTC ISO 8601)<input name="end" defaultValue={schedule?.ends_at ?? ""} /></label>
    <label><input type="checkbox" name="enabled" defaultChecked={schedule?.enabled ?? false} />스케줄 활성</label>
    <button disabled={busy}>스케줄 저장</button>
  </form>;
}
