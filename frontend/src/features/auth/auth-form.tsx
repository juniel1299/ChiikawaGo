"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { authRequest } from "@/lib/api/auth";

export function AuthForm({ register = false }: { register?: boolean }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      const response = await authRequest(register ? "register" : "login", {
        email: data.get("email"), password: data.get("password"),
        ...(register ? { display_name: data.get("display_name") } : {}),
      });
      const result = await response.json();
      if (!response.ok) {
        const details = result.error?.details;
        const fieldErrors = details && Object.entries(details)
          .filter(([key]) => key !== "detail")
          .map(([, value]) => Array.isArray(value) ? value.join(" ") : String(value)).join(" ");
        setError(fieldErrors || result.error?.message || "요청을 처리하지 못했습니다.");
        return;
      }
      router.push(register ? "/login?registered=1" : "/account");
      router.refresh();
    } catch {
      setError("서버에 연결하지 못했습니다. 다시 시도하세요.");
    } finally { setBusy(false); }
  }

  return <form onSubmit={submit} className="stack">
    {register && <label>표시 이름<input name="display_name" required maxLength={80} autoComplete="nickname" /></label>}
    <label>이메일<input name="email" type="email" required autoComplete="email" /></label>
    <label>비밀번호<input name="password" type="password" required maxLength={128} autoComplete={register ? "new-password" : "current-password"} /></label>
    {register && <p className="muted">8자 이상이며 이메일과 다르고, 숫자로만 이루어지지 않은 비밀번호를 사용하세요.</p>}
    {error && <p role="alert">{error}</p>}
    <button disabled={busy}>{busy ? "처리 중…" : register ? "가입하기" : "로그인"}</button>
    <Link href={register ? "/login" : "/register"}>{register ? "이미 계정이 있어요" : "새 계정 만들기"}</Link>
  </form>;
}
