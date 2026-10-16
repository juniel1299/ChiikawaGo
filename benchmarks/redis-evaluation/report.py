# ruff: noqa: E501
# Literal SQL, synthetic URLs, and rendered table/SVG lines remain intact.
"""Build the measured tables from raw-derived summary, not handwritten numbers."""

import json
import pathlib
import re
import statistics

root = pathlib.Path(__file__).resolve().parent
rows = json.loads((root / "results/summary.json").read_text())


def table(selected):
    lines = [
        "|구분|규모|시나리오|동시성/도착률|N|p50 ms|p95 ms|p99 ms|성공 req/s|오류|",
        "|---|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in selected:
        load = f"{r['arrival_rate']} req/s" if r["arrival_rate"] else str(r["concurrency"])
        lines.append(
            f"|{r['label']}|{r['scale']}x|{r['scenario']}|{load}|{r['n']}|{r['p50_ms']}|{r['p95_ms']}|{r['p99_ms']}|{r['rps_median']}|{r['errors']}/{r['n']}|"
        )
    return "\n".join(lines)


sections = [
    "# Phase 11 측정 결과표",
    "자동 생성 표. 해석과 결론은 REPORT.md를 참고한다. req/s는 반복별 성공 처리량의 중앙값, latency는 모든 반복의 raw 요청을 합친 nearest-rank percentile이다.",
    "오류 포함 percentile은 실패 응답과 10초 client timeout을 포함한다. 이는 성공 latency나 timeout 이후 실제 서버 완료 시각이 아니다. status_counts 및 성공 응답만의 success_p95_ms는 summary.json/CSV에서 별도로 제공한다.",
    "## Baseline",
    table([r for r in rows if r["label"] == "baseline"]),
    "## 단일 변경 및 원복",
    table([r for r in rows if r["label"] in ["jit-off", "jit-restored"]]),
    "## 고정 도착률",
    table([r for r in rows if r["label"] == "fixed-arrival"]),
    "## 추가 동시성",
    table([r for r in rows if r["label"] == "concurrency-confirmation"]),
]
for f in sorted((root / "results").glob("*-diagnostics.json")):
    j = json.loads(f.read_text())
    sections.extend(
        [
            "## 진단: " + f.stem,
            "단일 프로세스 APIClient 진단이며 HTTP 부하 percentile에 더하지 않는다. 인증에는 연결/사용자 SQL이 포함된다. 각 항목은 개별 중앙값이다.",
            "|시나리오|전체 ms|인증 ms|연결 ms|count SQL ms|page SQL ms|직렬화(SQL 제외) ms|",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for name, rs in j["samples"].items():

        def med(k, samples=rs):
            return round(statistics.median(r[k] for r in samples), 2)

        def sql(k, samples=rs):
            return round(
                statistics.median(
                    sum(q["ms"] for q in r["sql"] if q["kind"] == k) for r in samples
                ),
                2,
            )

        sections.append(
            f"|{name}|{med('total_ms')}|{med('auth_ms')}|{med('connection_ms')}|{sql('count')}|{sql('page')}|{med('serialization_excluding_sql_ms')}|"
        )
f = root / "results/login-burst.jsonl"
if f.exists():
    sections += [
        "## 잘못된 비밀번호 로그인 burst",
        "|동시성|반복|요청|p50 ms|p95 ms|p99 ms|req/s|응답 분포|",
        "|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for line in f.read_text().splitlines():
        r = json.loads(line)
        sections.append(
            f"|{r['concurrency']}|{r['repeat']}|{r['requests']}|{r['p50_ms']:.2f}|{r['p95_ms']:.2f}|{r['p99_ms']:.2f}|{r['throughput']:.2f}|{r['status_counts']}|"
        )
text = "\n".join(sections)
text = re.sub(r"(?m)^(#{1,3} .*)$", r"\n\1\n", text)
text = re.sub(r"\n(?=\|구분|\|시나리오|\|동시성)", "\n\n", text)
(root / "RESULTS.md").write_text(text + "\n")
