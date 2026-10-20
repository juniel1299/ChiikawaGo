let pending: Promise<Response> | undefined;

// Serialize cookie-changing requests within a tab. Web Locks also coordinates tabs when available.
export function authRequest(action: string, body?: unknown): Promise<Response> {
  const perform = async () => {
    const csrf = await fetch("/api/auth/csrf", { cache: "no-store" });
    if (!csrf.ok) throw new Error("보안 토큰을 가져오지 못했습니다.");
    const { csrf_token } = await csrf.json();
    return fetch(`/api/auth/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf_token },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  };
  const run = () => typeof navigator !== "undefined" && navigator.locks
    ? navigator.locks.request("chii-auth", perform) : perform();
  const next = (pending ?? Promise.resolve()).then(run, run);
  pending = next;
  void next.finally(() => { if (pending === next) pending = undefined; }).catch(() => {});
  return next;
}
