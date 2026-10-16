"""Aggregate sanitized raw samples; no new dependencies."""

import collections
import csv
import json
import pathlib
import statistics

from load import quantile

root = pathlib.Path(__file__).resolve().parent / "results"
summary = []
for f in sorted(root.glob("*-requests.jsonl")):
    if f.name.startswith("pilot-"):
        continue
    meta_file = f.with_name(f.name.replace("-requests", ""))
    meta = collections.defaultdict(list)
    rows = collections.defaultdict(list)
    for line in meta_file.read_text().splitlines():
        r = json.loads(line)
        meta[r["scenario"], r["concurrency"], r["arrival_rate"]].append(r)
    for line in f.read_text().splitlines():
        r = json.loads(line)
        rows[r["scenario"], r["concurrency"], r["arrival_rate"]].append(r)
    for key, requests in rows.items():
        runs = meta[key]
        lat = [r["latency_ms"] for r in requests]
        samples = [s for run in runs for s in run["samples"] if "db" in s]
        cpu = [
            float(c["CPUPerc"].strip("%"))
            for s in samples
            for c in s["containers"]
            if c["Name"] == "chii-perf-db-1"
        ]
        summary.append(
            {
                "label": runs[0]["label"],
                "scale": runs[0]["scale"],
                "scenario": key[0],
                "concurrency": key[1],
                "arrival_rate": key[2],
                "repeats": len(runs),
                "n": len(lat),
                "p50_ms": round(quantile(lat, 0.5), 2),
                "p95_ms": round(quantile(lat, 0.95), 2),
                "p99_ms": round(quantile(lat, 0.99), 2),
                "rps_median": round(statistics.median(r["throughput"] for r in runs), 2),
                "rps_min": round(min(r["throughput"] for r in runs), 2),
                "rps_max": round(max(r["throughput"] for r in runs), 2),
                "status_counts": dict(collections.Counter(str(r["status"]) for r in requests)),
                "success_p95_ms": round(
                    quantile([r["latency_ms"] for r in requests if r["status"] == 200], 0.95), 2
                )
                if any(r["status"] == 200 for r in requests)
                else None,
                "errors": sum(r["status"] != 200 for r in requests),
                "db_cpu_mean": round(statistics.mean(cpu), 1) if cpu else None,
                "db_cpu_max": max(cpu) if cpu else None,
                "connections_max": max((s["db"]["connections"] for s in samples), default=0),
                "lock_wait_max": max((s["db"]["lock_wait"] for s in samples), default=0),
                "reuse_10s_mean": round(statistics.mean(r["reuse"]["10"] or 0 for r in runs), 4),
            }
        )
(root / "summary.json").write_text(json.dumps(summary, indent=2))
if summary:
    with (root / "summary.csv").open("w") as f:
        w = csv.DictWriter(f, fieldnames=summary[0])
        w.writeheader()
        w.writerows(summary)
for r in summary:
    print(r)
