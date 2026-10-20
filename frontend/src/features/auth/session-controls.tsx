"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { authRequest } from "@/lib/api/auth";

export function SessionControls({ expired = false }: { expired?: boolean }) {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function act(action: "refresh" | "logout") {
    setBusy(true);
    try {
      const response = await authRequest(action);
      if (response.status !== 204) await response.json();
      if (response.status === 401) {
        router.replace("/login");
      } else if (!response.ok) {
        setMessage("처리하지 못했습니다. 잠시 후 다시 시도하세요.");
      } else if (action === "logout") {
        router.replace("/login");
      } else setMessage("로그인을 연장했습니다.");
      router.refresh();
    } catch { setMessage("서버에 연결할 수 없습니다."); }
    finally { setBusy(false); }
  }
  return <div className="stack">
    {expired && <p>로그인을 연장하면 계정 정보를 계속 볼 수 있습니다.</p>}
    <button disabled={busy} onClick={() => act("refresh")}>로그인 연장</button>
    <button className="secondary" disabled={busy} onClick={() => act("logout")}>로그아웃</button>
    {message && <p role="status">{message}</p>}
  </div>;
}
