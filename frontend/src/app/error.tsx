"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return <section className="card"><h1>잠시 연결이 어려워요.</h1><p>조금 뒤 다시 시도해 주세요.</p><button onClick={reset}>다시 시도</button></section>;
}
