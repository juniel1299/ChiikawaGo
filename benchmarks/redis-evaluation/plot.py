# ruff: noqa: E501
# Literal SQL, synthetic URLs, and rendered table/SVG lines remain intact.
"""Dependency-free standalone SVG curves from summary.json; exact values remain in CSV."""

import html
import json
import pathlib

root = pathlib.Path(__file__).resolve().parent / "results"
rows = json.loads((root / "summary.json").read_text())
charts = []
for scenario in ["nearby_dense", "nearby_wide", "characters", "news"]:
    for field, title in [
        ("p95_ms", "p95 latency (ms)"),
        ("rps_median", "successful throughput (req/s)"),
    ]:
        series = []
        for scale in (1, 10):
            data = sorted(
                [
                    r
                    for r in rows
                    if r["label"] in ["baseline", "concurrency-confirmation"]
                    and r["scale"] == scale
                    and r["scenario"] == scenario
                ],
                key=lambda r: r["concurrency"],
            )
            if data:
                series.append((str(scale) + "x", data))
        if not series:
            continue
        xmax = max(r["concurrency"] for _, rs in series for r in rs)
        ymax = max(r[field] for _, rs in series for r in rs) * 1.15 or 1
        svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="320" viewBox="0 0 640 320"><rect width="640" height="320" fill="white"/><g font-family="sans-serif" font-size="12"><text x="60" y="22">{html.escape(scenario + ": " + title)}</text><path d="M60 40V260H610" fill="none" stroke="#333"/>'
        ]
        for tick in range(6):
            y = 260 - tick * 40
            value = ymax * tick / 5
            svg.append(
                f'<path d="M60 {y}H610" stroke="#ddd"/><text x="5" y="{y + 4}">{value:.1f}</text>'
            )
        for idx, (label, rs) in enumerate(series):
            color = ["#2455aa", "#c54824"][idx]
            pts = [(60 + r["concurrency"] / xmax * 520, 260 - r[field] / ymax * 200) for r in rs]
            svg.append(
                f'<polyline points="{" ".join(f"{x:.2f},{y:.2f}" for x, y in pts)}" fill="none" stroke="{color}" stroke-width="2"/>'
            )
            for r, (x, y) in zip(rs, pts, strict=True):
                svg.append(
                    f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/><text x="{x - 10}" y="{y - 8}" fill="{color}">{r[field]:.1f}</text>'
                )
            svg.append(f'<text x="{430 + idx * 70}" y="40" fill="{color}">{label}</text>')
        svg.append(
            '<text x="240" y="292">Concurrent clients (measured endpoints only)</text></g></svg>'
        )
        name = f"{scenario}-{field}.svg"
        (root / name).write_text("".join(svg))
        charts.append(name)
(root / "charts.html").write_text(
    '<!doctype html><meta charset="utf-8"><title>Phase 11 local baseline</title><h1>Local comparative baseline — not production capacity</h1><p>Lines connect observations only; do not interpolate a capacity claim. Scales and additional concurrency points were measured in separate sessions; see report for variability.</p>'
    + "".join(f'<img src="{n}" alt="{n}">' for n in charts)
)
