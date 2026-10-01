import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "CHII WORLD", template: "%s | CHII WORLD" },
  description: "작은 만남을 모아 나만의 컬렉션으로.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ko"><body>
    <header><Link className="brand" href="/">CHII WORLD<span>작은 만남의 시작</span></Link>
      <nav aria-label="주 메뉴"><Link href="/account">내 계정</Link><Link href="/login">로그인</Link></nav>
    </header>
    <main>{children}</main>
    <footer>CHII WORLD · 나만의 작은 컬렉션</footer>
  </body></html>;
}
