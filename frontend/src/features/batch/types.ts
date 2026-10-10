export type Capabilities = { view: boolean; run: boolean; manage: boolean };
export type Job = { last_execution_id?: string | null; last_execution_status?: string | null; current_execution_id?: string | null; id: string; code: string; name: string; enabled: boolean; source_id: string | null; execution_policy: { soft_limit: number; hard_limit: number; max_retries: number } };
export type Source = { id: string; name: string; is_active: boolean };
export type Schedule = { id: string; job_id: string; cron_expression: string; timezone: string; enabled: boolean; starts_at: string | null; ends_at: string | null; next_run_at: string | null };
export type Execution = { duration_seconds: number | null; id: string; job_id: string; status: string; requested_at: string; started_at: string | null; finished_at: string | null; attempt: number; is_stale: boolean; safe_failure_message: string; retry_of_id: string | null; celery_task_id: string | null; worker: string; result_summary: unknown; input_snapshot: unknown; next_attempt_at: string | null; dispatch_error_code: string };
export type Page = { count: number; next: string | null; previous: string | null; results: Execution[] };
export type Initial = { capabilities: Capabilities; jobs: Job[]; sources: Source[]; schedules: Schedule[]; executions: Page };
