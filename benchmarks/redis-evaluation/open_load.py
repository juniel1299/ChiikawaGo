# ruff: noqa: B023
# Each iteration completes and joins all callbacks before loop variables change.
"""Fixed-arrival confirmation. Includes executor queue delay in latency."""

import argparse
import concurrent.futures
import http.client
import json
import threading
import time

from load import ROOT, SCENARIOS, monitor, quantile, quiesce, token

p = argparse.ArgumentParser()
p.add_argument("--scale", type=int, required=True)
p.add_argument("--rates", type=float, nargs="+", required=True)
p.add_argument("--scenario", default="nearby_dense")
p.add_argument("--duration", type=int, default=30)
p.add_argument("--repeats", type=int, default=3)
a = p.parse_args()
for rate in a.rates:
    for rep in range(a.repeats):
        quiesce()
        jwt = token() if SCENARIOS[a.scenario][1] else None

        def request(due):
            start = time.monotonic()
            conn = http.client.HTTPConnection("127.0.0.1", 18080, timeout=10)
            try:
                conn.request(
                    "GET",
                    SCENARIOS[a.scenario][0],
                    headers={"Authorization": "Bearer " + jwt} if jwt else {},
                )
                r = conn.getresponse()
                r.read()
                status = r.status
            except (OSError, http.client.HTTPException):
                status = 0
            finally:
                conn.close()
            end = time.monotonic()
            return {
                "latency_ms": round((end - due) * 1000, 4),
                "schedule_lag_ms": round((start - due) * 1000, 4),
                "service_ms": round((end - start) * 1000, 4),
                "status": status,
                "key_id": 0,
            }

        def phase(seconds):
            start = time.monotonic()
            futures = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
                for i in range(int(rate * seconds)):
                    due = start + i / rate
                    time.sleep(max(0, due - time.monotonic()))
                    futures.append(pool.submit(request, due))
                rows = [f.result() | {"offset_s": i / rate} for i, f in enumerate(futures)]
            return rows, max(seconds, time.monotonic() - start)

        phase(3)
        quiesce()
        samples = []
        stop = threading.Event()
        mon = threading.Thread(target=monitor, args=(stop, samples))
        mon.start()
        rows, elapsed = phase(a.duration)
        stop.set()
        mon.join()
        quiesce()
        lat = [r["latency_ms"] for r in rows]
        good = sum(r["status"] == 200 for r in rows)
        reuse = {}
        for ttl in (10, 30, 60):
            last = None
            hits = 0
            for r in rows:
                if last is not None and r["offset_s"] - last < ttl:
                    hits += 1
                else:
                    last = r["offset_s"]
            reuse[str(ttl)] = hits / len(rows)
        meta = {
            "label": "fixed-arrival",
            "scale": a.scale,
            "scenario": a.scenario,
            "concurrency": 50,
            "arrival_rate": rate,
            "repeat": rep,
            "warmup_s": 3,
            "duration_s": a.duration,
            "elapsed_with_drain_s": elapsed,
            "requests": len(rows),
            "success": good,
            "throughput": good / elapsed,
            "error_rate": 1 - good / len(rows),
            "p50_ms": quantile(lat, 0.5),
            "p95_ms": quantile(lat, 0.95),
            "p99_ms": quantile(lat, 0.99),
            "reuse": reuse,
            "samples": samples,
        }
        with (ROOT / "results" / f"fixed-arrival-{a.scale}x.jsonl").open("a") as f:
            f.write(json.dumps(meta) + "\n")
        with (ROOT / "results" / f"fixed-arrival-{a.scale}x-requests.jsonl").open("a") as f:
            for r in rows:
                f.write(
                    json.dumps(
                        {
                            k: meta[k]
                            for k in (
                                "label",
                                "scale",
                                "scenario",
                                "concurrency",
                                "arrival_rate",
                                "repeat",
                            )
                        }
                        | r
                    )
                    + "\n"
                )
        print({k: v for k, v in meta.items() if k not in ("samples", "reuse")}, flush=True)
