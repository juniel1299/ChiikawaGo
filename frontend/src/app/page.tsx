import Link from "next/link";

export default function Home() {
  return <section className="hero">
    <p className="eyebrow">A LITTLE WORLD OF DISCOVERY</p>
    <h1>작은 만남이 모여,<br />나만의 세계가 돼요.</h1>
    <p className="intro">일상 속 새로운 발견을 모으는 곳.<br />계정을 만들고 첫 만남을 준비해 보세요.</p>
    <div className="actions"><Link className="button" href="/register">함께 시작하기</Link><Link href="/login">로그인하기 →</Link></div>
    <p className="muted">주변 탐색과 캐릭터 수집은 준비 중이에요.</p>
  </section>;
}
