# ruff: noqa: E501
# Literal SQL, synthetic URLs, and rendered table/SVG lines remain intact.
# ruff: noqa: B023
# Each iteration completes and joins all callbacks before loop variables change.
"""Standard-library HTTP load generator. Never persists paths, headers, bodies or tokens."""

import argparse
import concurrent.futures
import http.client
import json
import math
import pathlib
import subprocess
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent
COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.yaml")]
SCENARIOS = {
    "nearby_dense": ("/api/v1/spots/nearby?latitude=37&longitude=127&radius_m=1000", True),
    "nearby_sparse": ("/api/v1/spots/nearby?latitude=37.8&longitude=127.8&radius_m=1000", True),
    "nearby_wide": (
        "/api/v1/spots/nearby?latitude=37&longitude=127&radius_m=5000&page_size=100",
        True,
    ),
    "nearby_moving": ("/api/v1/spots/nearby", True),
    "characters": ("/api/v1/characters", False),
    "news": ("/api/v1/news", False),
    "news_filter": ("/api/v1/news?category=goods", False),
    "news_deep": ("/api/v1/news?page=100&page_size=100", False),
}


def quantile(xs, p):
    xs = sorted(xs)
    return xs[max(0, math.ceil(len(xs) * p) - 1)] if xs else None


def token():
    code = "from apps.accounts.models import User; from rest_framework_simplejwt.tokens import AccessToken; print(str(AccessToken.for_user(User.objects.get(email='perf@example.invalid'))))"
    return (
        subprocess.check_output(
            COMPOSE + ["exec", "-T", "api", "python", "manage.py", "shell", "-c", code], text=True
        )
        .strip()
        .splitlines()[-1]
    )


def cpu_sample():
    out = subprocess.check_output(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            "chii-perf-db-1",
            "chii-perf-api-1",
        ],
        text=True,
    )
    return [
        {k: j[k] for k in ("Name", "CPUPerc", "MemUsage", "PIDs")}
        for j in map(json.loads, out.splitlines())
    ]


def monitor(stop, samples):
    while not stop.is_set():
        try:
            stats = cpu_sample()
            sql = "SELECT json_build_object('connections',count(*),'active',count(*) FILTER (WHERE state='active'),'lock_wait',count(*) FILTER (WHERE wait_event_type='Lock')) FROM pg_stat_activity WHERE datname='chii_perf' AND pid<>pg_backend_pid()"
            db = json.loads(
                subprocess.check_output(
                    COMPOSE
                    + ["exec", "-T", "db", "psql", "-U", "perf", "-d", "chii_perf", "-Atc", sql],
                    text=True,
                )
            )
            samples.append({"time": time.time(), "containers": stats, "db": db})
        except subprocess.CalledProcessError:
            samples.append({"monitor_error": True})
        stop.wait(1)


def quiesce():
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        sql = "SELECT count(*) FROM pg_stat_activity WHERE datname='chii_perf' AND state='active' AND pid<>pg_backend_pid()"
        count = int(
            subprocess.check_output(
                COMPOSE
                + ["exec", "-T", "db", "psql", "-U", "perf", "-d", "chii_perf", "-Atc", sql],
                text=True,
            )
        )
        if count == 0:
            return
        time.sleep(0.5)
    raise RuntimeError("DB did not drain; stop instead of contaminating next trial")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scale", type=int, required=True)
    p.add_argument("--label", default="baseline")
    p.add_argument("--scenarios", nargs="+", default=list(SCENARIOS))
    p.add_argument("--concurrency", nargs="+", type=int, default=[1, 5])
    p.add_argument("--warmup", type=float, default=2)
    p.add_argument("--duration", type=float, default=8)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--rate", type=float, default=0)
    a = p.parse_args()
    probe = http.client.HTTPConnection("127.0.0.1", 18080, timeout=5)
    probe.request("GET", "/ready")
    assert probe.getresponse().status == 200
    probe.close()
    output = ROOT / "results" / f"{a.label}-{a.scale}x.jsonl"
    records = ROOT / "results" / f"{a.label}-{a.scale}x-requests.jsonl"
    for name in a.scenarios:
        for concurrency in a.concurrency:
            for repeat in range(a.repeats):
                quiesce()
                jwt = token() if SCENARIOS[name][1] else None
                samples = []
                stop = threading.Event()
                mon = threading.Thread(target=monitor, args=(stop, samples))
                mon.start()
                barrier = threading.Barrier(concurrency + 1)
                warm_done = threading.Barrier(concurrency + 1)
                go = threading.Event()
                start_box = []

                def client(worker):
                    conn = http.client.HTTPConnection("127.0.0.1", 18080, timeout=10)
                    rows = []
                    barrier.wait()
                    start = start_box[0]
                    i = 0
                    end = start + a.warmup
                    measuring = False
                    while True:
                        if time.monotonic() >= end:
                            if measuring:
                                break
                            warm_done.wait()
                            go.wait()
                            start = start_box[1]
                            end = start + a.duration
                            measuring = True
                            i = 0
                        if a.rate:
                            due = start + (i * concurrency + worker) / a.rate
                            if due >= end:
                                time.sleep(max(0, end - time.monotonic()))
                                continue
                            time.sleep(max(0, due - time.monotonic()))
                        begin = time.monotonic()
                        path = SCENARIOS[name][0]
                        key = 0
                        if name == "nearby_moving":
                            key = (worker * 101 + i) % 10000
                            path += f"?latitude={37 + (key // 100) * 0.0001:.4f}&longitude={127 + (key % 100) * 0.0001:.4f}&radius_m=1000"
                        headers = {"Authorization": "Bearer " + jwt} if jwt else {}
                        try:
                            conn.request("GET", path, headers=headers)
                            r = conn.getresponse()
                            r.read()
                            status = r.status
                        except (OSError, http.client.HTTPException):
                            status = 0
                            conn.close()
                            conn = http.client.HTTPConnection("127.0.0.1", 18080, timeout=10)
                        finished = time.monotonic()
                        if measuring:
                            rows.append(
                                {
                                    "offset_s": round(begin - start, 6),
                                    "latency_ms": round((finished - begin) * 1000, 4),
                                    "status": status,
                                    "key_id": key,
                                    "schedule_lag_ms": round(max(0, begin - due) * 1000, 4)
                                    if a.rate
                                    else 0,
                                }
                            )
                        i += 1
                    conn.close()
                    return rows

                before = time.process_time()
                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futures = [pool.submit(client, i) for i in range(concurrency)]
                    start_box.append(time.monotonic())
                    barrier.wait()
                    warm_done.wait()
                    quiesce()
                    start_box.append(time.monotonic())
                    go.set()
                    rows = [r for f in futures for r in f.result()]
                elapsed = time.monotonic() - start_box[1]
                stop.set()
                mon.join()
                quiesce()
                lat = [r["latency_ms"] for r in rows]
                good = sum(r["status"] == 200 for r in rows)
                reuse = {}
                for ttl in (10, 30, 60):
                    last = {}
                    hits = 0
                    for r in sorted(rows, key=lambda r: r["offset_s"]):
                        k = r["key_id"]
                        t = r["offset_s"]
                        if k in last and t - last[k] < ttl:
                            hits += 1
                        else:
                            last[k] = t
                    reuse[str(ttl)] = hits / len(rows) if rows else 0
                meta = {
                    "scenario": name,
                    "scale": a.scale,
                    "label": a.label,
                    "concurrency": concurrency,
                    "repeat": repeat,
                    "warmup_s": a.warmup,
                    "duration_s": a.duration,
                    "elapsed_with_drain_s": round(elapsed, 3),
                    "arrival_rate": a.rate,
                    "requests": len(rows),
                    "success": good,
                    "error_rate": 1 - good / len(rows) if rows else 1,
                    "throughput": good / elapsed,
                    "p50_ms": quantile(lat, 0.5),
                    "p95_ms": quantile(lat, 0.95),
                    "p99_ms": quantile(lat, 0.99),
                    "generator_cpu_s": time.process_time() - before,
                    "reuse": reuse,
                    "samples": samples,
                }
                with output.open("a") as f:
                    f.write(json.dumps(meta) + "\n")
                with records.open("a") as f:
                    for r in rows:
                        f.write(
                            json.dumps(
                                {
                                    k: meta[k]
                                    for k in (
                                        "scenario",
                                        "scale",
                                        "label",
                                        "concurrency",
                                        "repeat",
                                        "arrival_rate",
                                    )
                                }
                                | r
                            )
                            + "\n"
                        )
                print(
                    json.dumps({k: v for k, v in meta.items() if k not in ("samples", "reuse")}),
                    flush=True,
                )


if __name__ == "__main__":
    main()
