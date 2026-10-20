import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SessionControls } from "@/features/auth/session-controls";
import { currentAccount, REFRESH_COOKIE } from "@/lib/server/auth";

export const metadata = { title: "내 계정" };
export default async function AccountPage() {
  const account = await currentAccount();
  if (!account && !(await cookies()).has(REFRESH_COOKIE)) redirect("/login");
  return <section className="card"><p className="eyebrow">MY LITTLE WORLD</p>
    <h1>{account ? `${account.display_name} 님의 공간` : "다시 이어가 볼까요?"}</h1>
    {account && <dl><dt>이메일</dt><dd>{account.email}</dd><dt>가입일</dt><dd>{new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul" }).format(new Date(account.date_joined))}</dd></dl>}
    <SessionControls expired={!account} />
  </section>;
}
