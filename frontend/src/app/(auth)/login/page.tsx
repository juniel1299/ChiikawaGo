import { AuthForm } from "@/features/auth/auth-form";

export const metadata = { title: "로그인" };
export default async function Login({ searchParams }: { searchParams: Promise<{ registered?: string }> }) {
  const { registered } = await searchParams;
  return <section className="card"><p className="eyebrow">WELCOME BACK</p><h1>다시 만나 반가워요.</h1>
    {registered === "1" && <p role="status">가입이 완료됐어요. 로그인해 주세요.</p>}
    <AuthForm />
  </section>;
}
