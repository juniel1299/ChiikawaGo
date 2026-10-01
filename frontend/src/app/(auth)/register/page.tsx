import { AuthForm } from "@/features/auth/auth-form";

export const metadata = { title: "회원가입" };
export default function Register() {
  return <section className="card"><p className="eyebrow">YOUR WORLD STARTS HERE</p><h1>첫 만남을 준비해요.</h1><AuthForm register /></section>;
}
